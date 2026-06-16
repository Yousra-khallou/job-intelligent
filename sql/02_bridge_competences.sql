
-- ============================================================
--  TABLES PONT & VUES COMPÉTENCES — Job Intelligent
--  Permet d'analyser les skills demandées vs skills candidats
-- ============================================================

-- 1. TABLE DE RÉFÉRENCE : Compétences techniques Data (si pas déjà créée par load_silver_to_postgres)
-- Note : dim_competence est déjà créée et peuplée par load_silver_to_postgres.py
-- Cette section ajoute uniquement les vues analytiques

-- 2. TABLE PONT : Compétences extraites des offres (many-to-many)
--    Scanne description + titre pour détecter les compétences
DROP TABLE IF EXISTS bridge_offre_competence CASCADE;
CREATE TABLE bridge_offre_competence (
    offre_id      VARCHAR(50) NOT NULL REFERENCES fact_offres(offre_id) ON DELETE CASCADE,
    competence_id INT NOT NULL REFERENCES dim_competence(competence_id),
    source_champ  VARCHAR(20) NOT NULL DEFAULT 'description',
    PRIMARY KEY (offre_id, competence_id)
);

-- Remplissage automatique : scan description + titre via dim_competence
INSERT INTO bridge_offre_competence (offre_id, competence_id, source_champ)
SELECT DISTINCT f.offre_id, c.competence_id, 'description'
FROM fact_offres f
CROSS JOIN dim_competence c
WHERE (
    f.description ILIKE '%' || c.nom || '%'
    OR f.titre ILIKE '%' || c.nom || '%'
    OR f.description ILIKE '%' || LOWER(c.nom) || '%'
    OR f.titre ILIKE '%' || LOWER(c.nom) || '%'
)
ON CONFLICT (offre_id, competence_id) DO NOTHING;

CREATE INDEX idx_bridge_comp ON bridge_offre_competence(competence_id);
CREATE INDEX idx_bridge_offre ON bridge_offre_competence(offre_id);

-- Mettre à jour le compteur dans dim_competence
UPDATE dim_competence c
SET nb_offres = (
    SELECT COUNT(*) 
    FROM bridge_offre_competence b 
    WHERE b.competence_id = c.competence_id
);


-- 3. VUE : Compétences les plus demandées (pour Power BI)
CREATE OR REPLACE VIEW vw_competences_top AS
SELECT
    c.nom AS competence,
    c.categorie,
    COUNT(DISTINCT b.offre_id) AS nb_offres,
    ROUND(100.0 * COUNT(DISTINCT b.offre_id) / NULLIF((SELECT COUNT(*) FROM fact_offres), 0), 1) AS pct_offres,
    ROUND(AVG(f.salaire_min)::numeric, 0) AS salaire_moyen_min,
    ROUND(AVG(f.salaire_max)::numeric, 0) AS salaire_moyen_max,
    ROUND(AVG(f.salaire_predit_eur)::numeric, 0) AS salaire_predit_moyen
FROM bridge_offre_competence b
JOIN dim_competence c ON b.competence_id = c.competence_id
LEFT JOIN fact_offres f ON b.offre_id = f.offre_id
GROUP BY c.nom, c.categorie
ORDER BY nb_offres DESC;


-- 4. VUE : Matrice Offres × Compétences (pour filtres croisés Power BI)
CREATE OR REPLACE VIEW vw_offre_competences_flat AS
SELECT
    b.offre_id,
    f.titre,
    f.rome_libelle AS metier,
    f.source,
    f.type_contrat,
    f.experience,
    c.nom AS competence,
    c.categorie,
    f.salaire_min,
    f.salaire_max,
    f.salaire_predit_eur,
    f.salaire_confiance,
    l.ville, 
    l.pays,
    e.nom AS entreprise,
    e.secteur
FROM bridge_offre_competence b
JOIN dim_competence c ON b.competence_id = c.competence_id
JOIN fact_offres f ON b.offre_id = f.offre_id
LEFT JOIN dim_lieu l ON f.lieu_id = l.lieu_id
LEFT JOIN dim_entreprise e ON f.entreprise_id = e.entreprise_id;


-- 5. VUE APP : Candidats et leurs compétences (base app_job_intelligent)
--    À exécuter sur app_job_intelligent si besoin de croiser offres vs candidats
-- CREATE OR REPLACE VIEW vw_candidat_competences AS
-- SELECT
--     c.candidat_id,
--     c.nom,
--     c.prenom,
--     c.email,
--     c.created_at,
--     UNNEST(string_to_array(c.competences, ',')) AS competence,
--     LENGTH(c.texte_cv) AS taille_cv
-- FROM candidats c;
