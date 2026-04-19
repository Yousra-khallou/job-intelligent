-- ============================================================
--  Job Intelligent — Data Warehouse
--  Schéma en étoile — PostgreSQL 15
--  Base : dwh_job_intelligent
--  Date : Avril 2026
-- ============================================================

-- Étape 1 : Créer la base (à exécuter une seule fois)
-- CREATE DATABASE dwh_job_intelligent;

-- ============================================================
--  DIMENSIONS
-- ============================================================

-- Dimension Date
CREATE TABLE IF NOT EXISTS dim_date (
    date_id      SERIAL PRIMARY KEY,
    date_full    DATE NOT NULL,
    annee        INT,
    mois         INT,
    semaine      INT,
    jour_semaine VARCHAR(20)
);

-- Dimension Entreprise
CREATE TABLE IF NOT EXISTS dim_entreprise (
    entreprise_id SERIAL PRIMARY KEY,
    nom           VARCHAR(200),
    secteur       VARCHAR(100),
    taille        VARCHAR(50)
);

-- Dimension Lieu
CREATE TABLE IF NOT EXISTS dim_lieu (
    lieu_id     SERIAL PRIMARY KEY,
    ville       VARCHAR(100),
    region      VARCHAR(100),
    pays        VARCHAR(50) DEFAULT 'France',
    code_postal VARCHAR(10),
    latitude    FLOAT,
    longitude   FLOAT
);

-- Dimension Compétence
CREATE TABLE IF NOT EXISTS dim_competence (
    competence_id SERIAL PRIMARY KEY,
    nom           VARCHAR(100),
    categorie     VARCHAR(50)
);

-- ============================================================
--  TABLE DE FAITS
-- ============================================================

CREATE TABLE IF NOT EXISTS fact_offres (
    offre_id        VARCHAR(50)  PRIMARY KEY,
    date_id         INT          REFERENCES dim_date(date_id),
    entreprise_id   INT          REFERENCES dim_entreprise(entreprise_id),
    lieu_id         INT          REFERENCES dim_lieu(lieu_id),
    source          VARCHAR(50),
    titre           VARCHAR(300),
    type_contrat    VARCHAR(30),
    salaire_min     INT,
    salaire_max     INT,
    salaire_libelle VARCHAR(200),
    rome_code       VARCHAR(10),
    rome_libelle    VARCHAR(100),
    experience      VARCHAR(50),
    description     TEXT,
    url_offre       VARCHAR(500),
    date_creation   TIMESTAMP DEFAULT NOW()
);

-- ============================================================
--  VÉRIFICATION
-- ============================================================

-- Lister toutes les tables créées
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;