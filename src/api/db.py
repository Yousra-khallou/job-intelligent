"""
=============================================================
  Job Intelligent — Database connections
  
  2 bases séparées :
  - dwh_job_intelligent  : Data Warehouse (offres, dimensions)
  - app_job_intelligent  : Base applicative (candidats)
=============================================================
"""

import psycopg2
import logging
from typing import Optional

log = logging.getLogger(__name__)

# ─── Paramètres communs ───────────────────────────────────────────────────────

PG_HOST     = "postgres_db"
PG_PORT     = 5432
PG_USER     = "admin"
PG_PASSWORD = "admin123"

# ─── Base 1 : Data Warehouse ─────────────────────────────────────────────────
# Contient : fact_offres, dim_date, dim_lieu, dim_entreprise, dim_competence

PG_DWH = "dwh_job_intelligent"

def get_dwh_connection():
    """Connexion au Data Warehouse — lecture des offres et dimensions."""
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DWH
    )

# ─── Base 2 : Base applicative ────────────────────────────────────────────────
# Contient : candidats (et futures tables : matching_history, sessions...)

PG_APP = "app_job_intelligent"

def get_app_connection():
    """Connexion à la base applicative — gestion des candidats."""
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_APP
    )

# ─── Rétrocompatibilité (ne pas casser nlp_engine.py) ────────────────────────

def get_db_connection():
    """Alias vers le DWH — conservé pour compatibilité avec nlp_engine.py."""
    return get_dwh_connection()

# ─── Initialisation ───────────────────────────────────────────────────────────

def init_db():
    """
    Vérifie et crée si nécessaire la table candidats
    dans la base applicative app_job_intelligent.
    """
    conn = get_app_connection()
    cur  = conn.cursor()

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
    log.info("Base applicative initialisée ✓ (app_job_intelligent)")
