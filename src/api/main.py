"""
=============================================================
  Job Intelligent — FastAPI NLP
  Système de recommandation d'offres d'emploi
  avec RAG (Sentence-BERT + Ollama)
=============================================================
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
import os
import logging

from db import init_db, get_db_connection
from nlp_engine import NLPEngine
from models import CandidatCreate, RecommandationRequest

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(
    title="Job Intelligent API",
    description="API de recommandation d'offres d'emploi basée sur NLP",
    version="1.0.0"
)

# CORS pour l'interface HTML
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialisation du moteur NLP au démarrage
nlp_engine = None

@app.on_event("startup")
async def startup_event():
    global nlp_engine
    log.info("Initialisation de la base de données...")
    init_db()
    log.info("Chargement du moteur NLP...")
    nlp_engine = NLPEngine()
    log.info("Vectorisation des offres...")
    nlp_engine.vectorize_offres()
    log.info("API prête !")


# ─── Routes Candidat ──────────────────────────────────────────────────────────

@app.post("/api/candidat/inscription")
async def inscription(
    nom: str = Form(...),
    prenom: str = Form(...),
    email: str = Form(...),
    cv: UploadFile = File(...)
):
    """Inscription d'un nouveau candidat avec upload CV."""
    try:
        # Lire le CV
        cv_bytes = await cv.read()
        
        # Extraire le texte du CV
        texte_cv = nlp_engine.extraire_texte_cv(cv_bytes)
        
        # Extraire les compétences
        competences = nlp_engine.extraire_competences(texte_cv)
        
        # Sauvegarder en base
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Vérifier si email existe déjà
        cur.execute("SELECT candidat_id FROM candidats WHERE email = %s", (email,))
        existing = cur.fetchone()
        
        if existing:
            # Mettre à jour
            cur.execute("""
                UPDATE candidats 
                SET nom=%s, prenom=%s, texte_cv=%s, competences=%s
                WHERE email=%s
                RETURNING candidat_id
            """, (nom, prenom, texte_cv, ','.join(competences), email))
            candidat_id = cur.fetchone()[0]
        else:
            # Créer nouveau
            cur.execute("""
                INSERT INTO candidats (nom, prenom, email, texte_cv, competences)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING candidat_id
            """, (nom, prenom, email, texte_cv, ','.join(competences)))
            candidat_id = cur.fetchone()[0]
        
        conn.commit()
        cur.close()
        conn.close()
        
        return {
            "success": True,
            "candidat_id": candidat_id,
            "nom": nom,
            "prenom": prenom,
            "competences_extraites": competences,
            "nb_competences": len(competences),
            "message": f"Profil créé avec {len(competences)} compétences détectées"
        }
        
    except Exception as e:
        log.error(f"Erreur inscription : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/candidat/{email}")
async def get_candidat(email: str):
    """Récupérer le profil d'un candidat."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT candidat_id, nom, prenom, email, competences, created_at
        FROM candidats WHERE email = %s
    """, (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Candidat non trouvé")
    
    return {
        "candidat_id": row[0],
        "nom": row[1],
        "prenom": row[2],
        "email": row[3],
        "competences": row[4].split(',') if row[4] else [],
        "created_at": str(row[5])
    }


# ─── Routes Recommandation ────────────────────────────────────────────────────

@app.get("/api/recommandations/{email}")
async def get_recommandations(email: str, top_k: int = 10):
    """
    Génère les recommandations d'offres pour un candidat.
    Utilise Sentence-BERT + similarité cosinus + Ollama pour l'explication.
    """
    try:
        # Récupérer le profil candidat
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT nom, prenom, texte_cv, competences 
            FROM candidats WHERE email = %s
        """, (email,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Candidat non trouvé")
        
        nom, prenom, texte_cv, competences_str = row
        competences = competences_str.split(',') if competences_str else []
        
        # Matching sémantique
        top_offres = nlp_engine.matcher_offres(texte_cv, top_k=top_k)
        
        # Générer explications avec Ollama
        recommandations = []
        for offre, score in top_offres[:5]:  # Ollama pour top 5 seulement
            explication = await nlp_engine.generer_explication_ollama(
                cv_texte=texte_cv,
                competences=competences,
                offre=offre,
                score=score
            )
            recommandations.append({
                "offre": offre,
                "score": round(score * 100, 1),
                "explication": explication
            })
        
        # Ajouter les offres 6-10 sans explication Ollama
        for offre, score in top_offres[5:]:
            recommandations.append({
                "offre": offre,
                "score": round(score * 100, 1),
                "explication": None
            })
        
        return {
            "candidat": f"{prenom} {nom}",
            "competences": competences,
            "nb_offres_analysees": nlp_engine.nb_offres,
            "recommandations": recommandations
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Erreur recommandations : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/recommandations/cv-direct")
async def recommandations_cv_direct(
    cv: UploadFile = File(...),
    top_k: int = Form(default=10)
):
    """Recommandations sans inscription — upload CV direct."""
    try:
        cv_bytes = await cv.read()
        texte_cv = nlp_engine.extraire_texte_cv(cv_bytes)
        competences = nlp_engine.extraire_competences(texte_cv)
        top_offres = nlp_engine.matcher_offres(texte_cv, top_k=top_k)
        
        recommandations = []
        for offre, score in top_offres[:5]:
            explication = await nlp_engine.generer_explication_ollama(
                cv_texte=texte_cv,
                competences=competences,
                offre=offre,
                score=score
            )
            recommandations.append({
                "offre": offre,
                "score": round(score * 100, 1),
                "explication": explication
            })

        for offre, score in top_offres[5:]:
            recommandations.append({
                "offre": offre,
                "score": round(score * 100, 1),
                "explication": None
            })

        return {
            "competences": competences,
            "nb_offres_analysees": nlp_engine.nb_offres,
            "recommandations": recommandations
        }
    except Exception as e:
        log.error(f"Erreur : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Route santé ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "nb_offres_vectorisees": nlp_engine.nb_offres if nlp_engine else 0,
        "ollama": "http://host.docker.internal:11434"
    }


@app.get("/api/stats")
async def stats():
    """Statistiques générales du marché."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM fact_offres")
    total = cur.fetchone()[0]
    
    cur.execute("""
        SELECT source, COUNT(*) 
        FROM fact_offres 
        GROUP BY source 
        ORDER BY COUNT(*) DESC
    """)
    par_source = {row[0]: row[1] for row in cur.fetchall()}
    
    cur.execute("""
        SELECT type_contrat, COUNT(*) 
        FROM fact_offres 
        WHERE type_contrat IS NOT NULL
        GROUP BY type_contrat 
        ORDER BY COUNT(*) DESC
        LIMIT 5
    """)
    par_contrat = {row[0]: row[1] for row in cur.fetchall()}
    
    cur.close()
    conn.close()
    
    return {
        "total_offres": total,
        "par_source": par_source,
        "par_type_contrat": par_contrat
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
