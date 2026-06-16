"""
=============================================================
  Job Intelligent — Moteur NLP
  - Extraction texte CV (PDF)
  - Extraction compétences
  - Vectorisation Sentence-BERT
  - Matching cosinus
  - Explication Ollama (RAG)
=============================================================
"""

import pdfplumber
import numpy as np
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine
import httpx
import asyncio
import logging
import re
from io import BytesIO
from db import get_db_connection
import os
import numpy as np

log = logging.getLogger(__name__)

# Liste de compétences techniques à détecter
COMPETENCES_TECH = [
    # Langages
    "python", "java", "scala", "r", "sql", "nosql", "bash", "javascript",
    "typescript", "c++", "go", "rust", "julia",
    # Data Engineering
    "spark", "pyspark", "hadoop", "kafka", "airflow", "dbt", "luigi",
    "nifi", "flink", "beam", "databricks", "delta lake",
    # Bases de données
    "postgresql", "mysql", "mongodb", "cassandra", "redis", "elasticsearch",
    "snowflake", "bigquery", "redshift", "hive", "hbase",
    # Cloud
    "aws", "azure", "gcp", "google cloud", "s3", "ec2", "lambda",
    "kubernetes", "docker", "terraform", "ansible",
    # ML / AI
    "machine learning", "deep learning", "tensorflow", "pytorch", "keras",
    "scikit-learn", "nlp", "llm", "transformers", "bert", "gpt",
    "computer vision", "mlflow", "kubeflow",
    # BI / Viz
    "power bi", "tableau", "looker", "metabase", "grafana", "matplotlib",
    "seaborn", "plotly", "d3.js",
    # Méthodes
    "etl", "elt", "data warehouse", "data lake", "data mesh", "lakehouse",
    "agile", "scrum", "ci/cd", "git", "github", "gitlab",
    # Soft skills data
    "analyse de données", "modélisation", "statistiques", "data quality",
    "data governance", "api rest", "microservices",
]


class NLPEngine:
    def __init__(self):
        log.info("Chargement du modèle Sentence-BERT...")
        # Modèle multilingue pour supporter FR et EN
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.offres_data = []
        self.offres_vectors = None
        self.nb_offres = 0
        self.ollama_url = "http://192.168.1.10:11434"
        log.info("Modèle chargé ")

    # ─── Extraction CV ────────────────────────────────────────────────────────

    def extraire_texte_cv(self, cv_bytes: bytes) -> str:
        """Extrait le texte d'un CV PDF."""
        try:
            with pdfplumber.open(BytesIO(cv_bytes)) as pdf:
                texte = ""
                for page in pdf.pages:
                    texte += page.extract_text() or ""
            texte = texte.strip()
            if not texte:
                raise ValueError("PDF vide ou non lisible")
            log.info(f"CV extrait : {len(texte)} caractères")
            return texte
        except Exception as e:
            log.error(f"Erreur extraction PDF : {e}")
            raise

    def extraire_competences(self, texte_cv: str) -> list:
        """Extrait les compétences techniques du texte du CV."""
        texte_lower = texte_cv.lower()
        competences_trouvees = []

        for comp in COMPETENCES_TECH:
            if comp.lower() in texte_lower:
                competences_trouvees.append(comp)

        # Dédoublonnage
        competences_trouvees = list(dict.fromkeys(competences_trouvees))
        log.info(f"Compétences extraites : {competences_trouvees}")
        return competences_trouvees

    # ─── Vectorisation des offres ─────────────────────────────────────────────

    def vectorize_offres(self):
        import pickle
        import os

        os.makedirs("/app/cache", exist_ok=True)

        # Charger les offres depuis PostgreSQL
        log.info("Chargement des offres depuis PostgreSQL...")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
        SELECT 
            f.offre_id, f.titre, f.description, f.type_contrat,
            COALESCE(l.ville, '') as ville,
            COALESCE(l.pays, 'France') as pays,
            COALESCE(e.nom, '') as entreprise,
            COALESCE(e.secteur, '') as secteur,
            f.experience, f.salaire_min, f.salaire_max,
            f.rome_libelle, f.source, f.url_offre
        FROM fact_offres f
        LEFT JOIN dim_lieu l ON f.lieu_id = l.lieu_id
        LEFT JOIN dim_entreprise e ON f.entreprise_id = e.entreprise_id
        WHERE f.titre IS NOT NULL AND f.description IS NOT NULL
        LIMIT 5000
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        self.offres_data = []
        textes_offres = []

        for row in rows:
            offre = {
                "offre_id": row[0], "titre": row[1] or "",
                "description": row[2] or "", "type_contrat": row[3] or "",
                "ville": row[4], "pays": row[5], "entreprise": row[6],
                "secteur": row[7], "experience": row[8] or "",
                "salaire_min": row[9], "salaire_max": row[10],
                "rome_libelle": row[11] or "", "source": row[12] or "",
                "url_offre": row[13] or "",
            }
            self.offres_data.append(offre)
            textes_offres.append(f"{offre['titre']} {offre['description'][:500]}")

        self.nb_offres = len(self.offres_data)

        # Vérifier si le cache est valide
        if (
            os.path.exists("/app/cache/offres_vectors.npy") and
            os.path.exists("/app/cache/offres_data.pkl")
        ):
            with open("/app/cache/offres_data.pkl", "rb") as f:
                cached_nb = pickle.load(f)
            if cached_nb == self.nb_offres:
                log.info(f"Cache trouvé — chargement de {self.nb_offres} vecteurs...")
                self.offres_vectors = np.load("/app/cache/offres_vectors.npy")
                log.info(f"Cache chargé en quelques secondes ✓")
                return

        # Pas de cache valide — vectoriser et sauvegarder
        log.info(f"{self.nb_offres} offres chargées. Vectorisation...")
        self.offres_vectors = self.model.encode(
            textes_offres,
            batch_size=64,
            show_progress_bar=True,
            normalize_embeddings=True
        )

        np.save("/app/cache/offres_vectors.npy", self.offres_vectors)

        with open("/app/cache/offres_data.pkl", "wb") as f:
            pickle.dump(self.nb_offres, f)

        log.info("Vectorisation terminée et cache sauvegardé ✓")

    # ─── Matching ─────────────────────────────────────────────────────────────

    def matcher_offres(self, texte_cv: str, top_k: int = 10) -> list:
        """
        Calcule la similarité cosinus entre le CV et toutes les offres.
        Retourne les top_k offres les plus similaires.
        """
        if self.offres_vectors is None or len(self.offres_data) == 0:
            raise ValueError("Les offres ne sont pas vectorisées")

        # Vectoriser le CV
        cv_vector = self.model.encode(
            texte_cv[:1000],
            normalize_embeddings=True
        )

        # Calcul similarités cosinus (1 - distance)
        similarities = []
        for i, offre_vec in enumerate(self.offres_vectors):
            sim = float(1 - cosine(cv_vector, offre_vec))
            similarities.append((self.offres_data[i], sim))

        # Trier par similarité décroissante
        similarities.sort(key=lambda x: x[1], reverse=True)

        return similarities[:top_k]

    # ─── Explication Ollama (RAG) ─────────────────────────────────────────────

    async def generer_explication_ollama(
        self,
        cv_texte: str,
        competences: list,
        offre: dict,
        score: float
    ) -> str:
        """
        Génère une explication personnalisée avec Ollama (Llama3.2).
        C'est la partie RAG du système.
        """

        prompt = f"""Tu es un conseiller emploi expert. Analyse la compatibilité entre ce candidat et cette offre.

COMPÉTENCES DU CANDIDAT : {', '.join(competences[:15])}

OFFRE D'EMPLOI :
- Titre : {offre['titre']}
- Entreprise : {offre['entreprise']}
- Lieu : {offre['ville']}, {offre['pays']}
- Contrat : {offre['type_contrat']}
- Description : {offre['description'][:400]}

SCORE DE COMPATIBILITÉ : {round(score * 100, 1)}%

Réponds UNIQUEMENT avec ce format JSON :
{{
  "points_forts": ["point 1", "point 2", "point 3"],
  "points_amelioration": ["point 1", "point 2"],
  "conseil": "Un conseil personnalisé en une phrase."
}}"""

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": "llama3.2",
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 300
                        }
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    texte = result.get("response", "")

                    # Parser le JSON retourné
                    import json
                    try:
                        json_match = re.search(r'\{.*\}', texte, re.DOTALL)
                        if json_match:
                            data = json.loads(json_match.group())
                            return data
                    except Exception:
                        pass

                    return {
                        "points_forts": ["Profil compatible avec le poste"],
                        "points_amelioration": ["Voir la description complète"],
                        "conseil": texte[:200] if texte else "Postulez rapidement !"
                    }
                else:
                    log.warning(f"Ollama status {response.status_code}")
                    return self._explication_fallback(competences, offre, score)

        except Exception as e:
            log.warning(f"Ollama indisponible : {e}")
            return self._explication_fallback(competences, offre, score)

    def _explication_fallback(self, competences, offre, score):
        """Explication sans Ollama si indisponible."""
        desc_lower = (offre['description'] + " " + offre['titre']).lower()

    # Skills du CV présents dans l'offre → points forts
        matching = [c for c in competences if c.lower() in desc_lower]

    # Skills demandés par l'offre mais absents du CV → vraiment à renforcer
        offre_skills = [c for c in COMPETENCES_TECH if c.lower() in desc_lower]
        manquantes = [c for c in offre_skills if c.lower() not in [s.lower() for s in competences]]

        return {
           "points_forts": [f"Compétence '{c}' requise et présente" for c in matching[:3]] or ["Profil pertinent"],
           "points_amelioration": [f"À acquérir : '{c}'" for c in manquantes[:2]] or ["Personnaliser la candidature"],
           "conseil": f"Score de {round(score*100,1)}% — candidature recommandée !"
        }