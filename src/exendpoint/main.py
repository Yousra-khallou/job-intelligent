"""
=============================================================
  Job Intelligent — FastAPI NLP
  Système de recommandation d'offres d'emploi
  avec RAG (Sentence-BERT + Ollama)

  Connexions :
  - get_dwh_connection() → dwh_job_intelligent (offres, dimensions)
  - get_app_connection() → app_job_intelligent (candidats)
=============================================================
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
import os
import logging
import numpy as np
import pickle

from db import init_db, get_dwh_connection, get_app_connection
from nlp_engine import NLPEngine
from models import CandidatCreate, RecommandationRequest

# ── Salary Prediction ──────────────────────────────────────────────────────────
from salary_routes import router as salary_router       # endpoints /api/salary/*

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(
    title="Job Intelligent API",
    description="API de recommandation d'offres d'emploi basée sur NLP",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(salary_router, prefix="/api")        # monte /api/salary/*

nlp_engine = None

@app.on_event("startup")
async def startup_event():
    global nlp_engine
    log.info("Initialisation de la base applicative...")
    init_db()  # crée candidats dans app_job_intelligent si nécessaire
    log.info("Chargement du moteur NLP...")
    nlp_engine = NLPEngine()
    log.info("Vectorisation des offres depuis le DWH...")
    nlp_engine.vectorize_offres()

    # ── Entraînement du modèle salarial en arrière-plan ──────────────────────
    import threading
    def _train_salary_model():
        try:
            from salary_predictor import train
            log.info("🎯 Entraînement du modèle salarial...")
            metrics = train(force_retrain=False)   # utilise le cache si disponible
            log.info(f"✅ Modèle salarial prêt — MAE={metrics.get('mae_eur')} € | R²={metrics.get('r2_score')}")
        except Exception as e:
            log.warning(f"⚠️  Modèle salarial non disponible : {e}")
    threading.Thread(target=_train_salary_model, daemon=True).start()
    # ─────────────────────────────────────────────────────────────────────────

    log.info("API prête !")


# ─── Routes Candidat → app_job_intelligent ───────────────────────────────────

@app.post("/api/candidat/inscription")
async def inscription(
    nom: str = Form(...),
    prenom: str = Form(...),
    email: str = Form(...),
    cv: UploadFile = File(...)
):
    """Inscription d'un nouveau candidat avec upload CV."""
    try:
        cv_bytes = await cv.read()
        texte_cv = nlp_engine.extraire_texte_cv(cv_bytes)
        competences = nlp_engine.extraire_competences(texte_cv)

        # ← base applicative (candidats)
        conn = get_app_connection()
        cur = conn.cursor()

        cur.execute("SELECT candidat_id FROM candidats WHERE email = %s", (email,))
        existing = cur.fetchone()

        if existing:
            cur.execute("""
                UPDATE candidats
                SET nom=%s, prenom=%s, texte_cv=%s, competences=%s, updated_at=NOW()
                WHERE email=%s
                RETURNING candidat_id
            """, (nom, prenom, texte_cv, ','.join(competences), email))
            candidat_id = cur.fetchone()[0]
        else:
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
    # ← base applicative (candidats)
    conn = get_app_connection()
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
        "nom":         row[1],
        "prenom":      row[2],
        "email":       row[3],
        "competences": row[4].split(',') if row[4] else [],
        "created_at":  str(row[5])
    }


# ─── Routes Recommandation ────────────────────────────────────────────────────

@app.get("/api/recommandations/{email}")
async def get_recommandations(email: str, top_k: int = 10):
    """
    Génère les recommandations d'offres pour un candidat.
    - Candidat lu depuis app_job_intelligent
    - Offres matchées depuis dwh_job_intelligent (via NLP)
    """
    try:
        # ← base applicative (candidat)
        conn = get_app_connection()
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

        # Matching NLP sur les offres du DWH (déjà vectorisées en mémoire)
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
                "offre":       offre,
                "score":       round(float(score) * 100, 1),
                "explication": explication
            })

        for offre, score in top_offres[5:]:
            recommandations.append({
                "offre":       offre,
                "score":       round(float(score) * 100, 1),
                "explication": None
            })

        return {
            "candidat":            f"{prenom} {nom}",
            "competences":         competences,
            "nb_offres_analysees": nlp_engine.nb_offres,
            "recommandations":     recommandations
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
        cv_bytes   = await cv.read()
        texte_cv   = nlp_engine.extraire_texte_cv(cv_bytes)
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
                "offre":       offre,
                "score":       round(float(score) * 100, 1),
                "explication": explication
            })

        for offre, score in top_offres[5:]:
            recommandations.append({
                "offre":       offre,
                "score":       round(float(score) * 100, 1),
                "explication": None
            })

        return {
            "competences":         competences,
            "nb_offres_analysees": nlp_engine.nb_offres,
            "recommandations":     recommandations
        }
    except Exception as e:
        log.error(f"Erreur : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Routes utilitaires → dwh_job_intelligent ────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status":               "ok",
        "nb_offres_vectorisees": nlp_engine.nb_offres if nlp_engine else 0,
        "ollama":               "http://host.docker.internal:11434"
    }


@app.get("/api/stats")
async def stats():
    """Statistiques générales du marché — depuis le DWH."""
    # ← Data Warehouse (offres)
    conn = get_dwh_connection()
    cur  = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM fact_offres")
    total = cur.fetchone()[0]

    cur.execute("""
        SELECT source, COUNT(*)
        FROM fact_offres
        GROUP BY source
        ORDER BY COUNT(*) DESC
    """)
    par_source = {str(r[0]): r[1] for r in cur.fetchall()}

    cur.execute("""
        SELECT type_contrat, COUNT(*)
        FROM fact_offres
        WHERE type_contrat IS NOT NULL
        GROUP BY type_contrat
        ORDER BY COUNT(*) DESC
        LIMIT 5
    """)
    par_contrat = {str(r[0]): r[1] for r in cur.fetchall()}

    cur.close()
    conn.close()

    return JSONResponse(
        content={
            "total_offres":     total,
            "par_source":       par_source,
            "par_type_contrat": par_contrat
        },
        media_type="application/json; charset=utf-8"
    )


# ─── Refresh incrémental des vecteurs → dwh_job_intelligent ──────────────────

@app.post("/api/refresh-vectors")
async def refresh_vectors():
    """
    Vectorisation INCRÉMENTALE — seulement les nouvelles offres du DWH.
    Appelle dwh_job_intelligent pour récupérer les offres absentes du cache.
    """
    global nlp_engine
    try:
        import time

        if nlp_engine is None:
            nlp_engine = NLPEngine()
            nlp_engine.vectorize_offres()

        nb_avant    = nlp_engine.nb_offres
        ids_en_cache = set(o['offre_id'] for o in nlp_engine.offres_data)
        log.info(f"Cache actuel : {len(ids_en_cache)} offres")

        # ← Data Warehouse (nouvelles offres)
        conn = get_dwh_connection()
        cur  = conn.cursor()

        if ids_en_cache:
            cur.execute("""
                SELECT
                    f.offre_id,
                    f.titre,
                    COALESCE(f.description, '')   AS description,
                    COALESCE(f.type_contrat, '')   AS type_contrat,
                    COALESCE(f.experience, '')     AS experience,
                    COALESCE(f.salaire_min, 0)     AS salaire_min,
                    COALESCE(f.salaire_max, 0)     AS salaire_max,
                    COALESCE(f.rome_libelle, '')   AS rome_libelle,
                    COALESCE(f.source, '')         AS source,
                    COALESCE(f.url_offre, '')      AS url_offre,
                    COALESCE(l.ville, '')          AS ville,
                    COALESCE(l.pays, 'France')     AS pays,
                    COALESCE(e.nom, '')            AS entreprise,
                    COALESCE(e.secteur, '')        AS secteur
                FROM fact_offres f
                LEFT JOIN dim_lieu       l ON f.lieu_id       = l.lieu_id
                LEFT JOIN dim_entreprise e ON f.entreprise_id = e.entreprise_id
                WHERE f.titre IS NOT NULL
                  AND f.description IS NOT NULL
                  AND f.offre_id NOT IN %s
                LIMIT 5000
            """, (tuple(ids_en_cache),))
        else:
            cur.execute("""
                SELECT
                    f.offre_id, f.titre,
                    COALESCE(f.description, ''),
                    COALESCE(f.type_contrat, ''),
                    COALESCE(f.experience, ''),
                    COALESCE(f.salaire_min, 0),
                    COALESCE(f.salaire_max, 0),
                    COALESCE(f.rome_libelle, ''),
                    COALESCE(f.source, ''),
                    COALESCE(f.url_offre, ''),
                    COALESCE(l.ville, ''),
                    COALESCE(l.pays, 'France'),
                    COALESCE(e.nom, ''),
                    COALESCE(e.secteur, '')
                FROM fact_offres f
                LEFT JOIN dim_lieu       l ON f.lieu_id       = l.lieu_id
                LEFT JOIN dim_entreprise e ON f.entreprise_id = e.entreprise_id
                WHERE f.titre IS NOT NULL AND f.description IS NOT NULL
                LIMIT 5000
            """)

        nouvelles_rows = cur.fetchall()
        cur.close()
        conn.close()

        nb_nouvelles = len(nouvelles_rows)

        if nb_nouvelles == 0:
            return JSONResponse(
                content={
                    "status":    "ok",
                    "nb_avant":  nb_avant,
                    "nb_apres":  nb_avant,
                    "nouvelles": 0,
                    "duree_sec": 0,
                    "message":   "Aucune nouvelle offre — cache conservé ✅"
                },
                media_type="application/json; charset=utf-8"
            )

        t0 = time.time()
        textes_nouveaux = [f"{r[1]} {r[2][:500]}" for r in nouvelles_rows]

        log.info(f"Vectorisation de {nb_nouvelles} nouvelles offres...")
        nouveaux_vecteurs = nlp_engine.model.encode(
            textes_nouveaux,
            batch_size=64,
            normalize_embeddings=True,
            show_progress_bar=False
        )

        for r in nouvelles_rows:
            nlp_engine.offres_data.append({
                "offre_id":    r[0],  "titre":       r[1] or "",
                "description": r[2] or "",  "type_contrat":r[3] or "",
                "experience":  r[4] or "",  "salaire_min": r[5],
                "salaire_max": r[6],        "rome_libelle":r[7] or "",
                "source":      r[8] or "",  "url_offre":   r[9] or "",
                "ville":       r[10] or "", "pays":        r[11] or "",
                "entreprise":  r[12] or "", "secteur":     r[13] or "",
            })

        nlp_engine.offres_vectors = np.vstack([
            nlp_engine.offres_vectors,
            nouveaux_vecteurs
        ])
        nlp_engine.nb_offres = len(nlp_engine.offres_data)
        duree = round(time.time() - t0, 2)

        os.makedirs("/app/cache", exist_ok=True)
        np.save("/app/cache/offres_vectors.npy", nlp_engine.offres_vectors)
        with open("/app/cache/offres_data.pkl", "wb") as f:
            pickle.dump(nlp_engine.nb_offres, f)

        log.info(f"✅ Cache mis à jour : {nb_avant} → {nlp_engine.nb_offres} offres")

        return JSONResponse(
            content={
                "status":    "ok",
                "nb_avant":  nb_avant,
                "nb_apres":  nlp_engine.nb_offres,
                "nouvelles": nb_nouvelles,
                "duree_sec": duree,
                "message":   f"{nb_nouvelles} nouvelles offres vectorisées en {duree}s ✅"
            },
            media_type="application/json; charset=utf-8"
        )

    except Exception as e:
        log.error(f"Erreur refresh-vectors : {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    with open("/app/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
