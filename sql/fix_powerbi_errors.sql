
-- ============================================================
--  SCRIPT DE CORRECTION — Job Intelligent
--  Résout : dim_competence.nb_offres manquant + FK fact_offres
--  À exécuter APRÈS les 3 fichiers précédents
-- ============================================================

-- ============================================================
-- 1. CORRECTION VUE vw_competences_demandees
--    Problème : dim_competence n'a pas la colonne nb_offres
-- ============================================================
DROP VIEW IF EXISTS vw_competences_demandees;

CREATE OR REPLACE VIEW vw_competences_demandees AS
SELECT
    c.nom AS competence,
    c.categorie,
    COALESCE(b.cnt, 0) AS nb_offres_detectees
FROM dim_competence c
LEFT JOIN (
    SELECT competence_id, COUNT(DISTINCT offre_id) AS cnt
    FROM bridge_offre_competence
    GROUP BY competence_id
) b ON c.competence_id = b.competence_id
ORDER BY nb_offres_detectees DESC NULLS LAST;


-- ============================================================
-- 2. CORRECTION TABLE PONT bridge_offre_competence
--    Problème : fact_offres.offre_id n'a pas de contrainte UNIQUE
--    Solution : supprimer les FK, garder uniquement les index
-- ============================================================

-- Nettoyage complet
DROP TABLE IF EXISTS bridge_offre_competence CASCADE;
DROP VIEW IF EXISTS vw_competences_top;
DROP VIEW IF EXISTS vw_offre_competences_flat;

-- Recréation SANS contraintes d'intégrité référentielle
-- (car fact_offres.offre_id n'est pas UNIQUE)
CREATE TABLE bridge_offre_competence (
    offre_id      VARCHAR(200) NOT NULL,
    competence_id INT NOT NULL,
    source_champ  VARCHAR(20) NOT NULL DEFAULT 'description',
    PRIMARY KEY (offre_id, competence_id)
);

CREATE INDEX idx_bridge_comp ON bridge_offre_competence(competence_id);
CREATE INDEX idx_bridge_offre ON bridge_offre_competence(offre_id);


-- ============================================================
-- 3. REMPLISSAGE TABLE PONT
-- ============================================================
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


-- ============================================================
-- 4. RECRÉATION DES VUES COMPÉTENCES
-- ============================================================

-- Vue : Compétences les plus demandées
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


-- Vue : Matrice Offres × Compétences (pour filtres croisés Power BI)
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


-- ============================================================
-- 5. VÉRIFICATION
-- ============================================================
SELECT 'bridge_offre_competence' AS table_name, COUNT(*) AS nb_lignes FROM bridge_offre_competence
UNION ALL
SELECT 'vw_competences_top', (SELECT COUNT(*) FROM vw_competences_top)
UNION ALL
SELECT 'vw_competences_demandees', (SELECT COUNT(*) FROM vw_competences_demandees);
