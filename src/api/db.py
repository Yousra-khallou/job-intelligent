"""
=============================================================
  Job Intelligent — Database & Models
=============================================================
"""

import psycopg2
import logging
from pydantic import BaseModel
from typing import Optional

log = logging.getLogger(__name__)

PG_HOST     = "postgres_db"
PG_PORT     = 5432
PG_USER     = "admin"
PG_PASSWORD = "admin123"
PG_DB       = "dwh_job_intelligent"


def get_db_connection():
    """Retourne une connexion PostgreSQL."""
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DB
    )


def init_db():
    """Crée les tables nécessaires si elles n'existent pas."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Table candidats
    cur.execute("""
        CREATE TABLE IF NOT EXISTS candidats (
            candidat_id  SERIAL PRIMARY KEY,
            nom          VARCHAR(100) NOT NULL,
            prenom       VARCHAR(100) NOT NULL,
            email        VARCHAR(200) UNIQUE NOT NULL,
            texte_cv     TEXT,
            competences  TEXT,
            created_at   TIMESTAMP DEFAULT NOW(),
            updated_at   TIMESTAMP DEFAULT NOW()
        );
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    log.info("Base de données initialisée ✓")


# ─── Modèles Pydantic ─────────────────────────────────────────────────────────

class CandidatCreate(BaseModel):
    nom: str
    prenom: str
    email: str

class RecommandationRequest(BaseModel):
    email: str
    top_k: Optional[int] = 10
