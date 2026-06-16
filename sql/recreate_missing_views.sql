
-- ============================================================
--  RECRÉATION DES VUES MANQUANTES — Job Intelligent
--  À exécuter si dbt run a supprimé les vues en CASCADE
-- ============================================================

-- 1. VUE PRINCIPALE : Offres dénormalisées
DROP VIEW IF EXISTS vw_offres_complete;
CREATE OR REPLACE VIEW vw_offres_complete AS
SELECT
    f.offre_id,
    f.titre,
    f.description,
    f.type_contrat,
    f.experience,
    f.salaire_min,
    f.salaire_max,
    f.salaire_predit_eur,
    f.salaire_confiance,
    f.rome_libelle          AS metier,
    f.source,
    f.url_offre,
    f.date_creation,
    d.annee,
    d.mois,
    TO_CHAR(f.date_creation, 'YYYY-MM') AS annee_mois,
    d.jour_semaine,
    COALESCE(l.ville,  'Non renseigné') AS ville,
    COALESCE(l.region, 'Non renseigné') AS region,
    COALESCE(l.pays,   'France')        AS pays,
    l.latitude,
    l.longitude,
    COALESCE(e.nom,     'Non renseigné') AS entreprise,
    COALESCE(e.secteur, 'Non renseigné') AS secteur,
    COALESCE(e.taille,  'Non renseigné') AS taille_entreprise,
    CASE WHEN f.salaire_min IS NOT NULL AND f.salaire_max IS NOT NULL 
         THEN 1 ELSE 0 END AS a_salaire_connu,
    CASE WHEN f.salaire_predit_eur IS NOT NULL 
         THEN 1 ELSE 0 END AS a_salaire_predite,
    COALESCE(
        (f.salaire_min + f.salaire_max) / 2.0,
        f.salaire_predit_eur
    ) AS salaire_estime
FROM fact_offres f
LEFT JOIN dim_date       d ON f.date_id = d.date_id
LEFT JOIN dim_lieu       l ON f.lieu_id = l.lieu_id
LEFT JOIN dim_entreprise e ON f.entreprise_id = e.entreprise_id;


-- 2. VUE MARCHÉ & SALAIRES
DROP VIEW IF EXISTS vw_salaires_marche;
CREATE OR REPLACE VIEW vw_salaires_marche AS
SELECT
    f.rome_libelle          AS metier,
    COALESCE(l.pays, 'France')        AS pays,
    COALESCE(l.ville, 'Non renseigné') AS ville,
    f.type_contrat,
    f.experience,
    COUNT(*)                                            AS nb_offres,
    ROUND(AVG(f.salaire_min)::numeric, 0)              AS salaire_moyen_min,
    ROUND(AVG(f.salaire_max)::numeric, 0)              AS salaire_moyen_max,
    ROUND(AVG(COALESCE(f.salaire_min, f.salaire_predit_eur * 0.9))::numeric, 0) AS salaire_moyen_estime_min,
    ROUND(AVG(COALESCE(f.salaire_max, f.salaire_predit_eur * 1.1))::numeric, 0) AS salaire_moyen_estime_max,
    ROUND(AVG(f.salaire_predit_eur)::numeric, 0)       AS salaire_predit_moyen,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY 
        COALESCE((f.salaire_min + f.salaire_max)/2.0, f.salaire_predit_eur)
    )::numeric, 0) AS salaire_mediane
FROM fact_offres f
LEFT JOIN dim_lieu l ON f.lieu_id = l.lieu_id
WHERE f.salaire_min IS NOT NULL OR f.salaire_predit_eur IS NOT NULL
GROUP BY f.rome_libelle, l.pays, l.ville, f.type_contrat, f.experience;


-- 3. VUE KPI GLOBAL
DROP VIEW IF EXISTS vw_kpi_global;
CREATE OR REPLACE VIEW vw_kpi_global AS
SELECT
    COUNT(*)                                   AS total_offres,
    COUNT(DISTINCT f.source)                   AS nb_sources,
    COUNT(DISTINCT f.entreprise_id)            AS nb_entreprises,
    COUNT(DISTINCT l.ville)                    AS nb_villes,
    COUNT(DISTINCT f.rome_libelle)             AS nb_metiers,
    ROUND(AVG(f.salaire_min)::numeric, 0)      AS salaire_moyen_min,
    ROUND(AVG(f.salaire_max)::numeric, 0)      AS salaire_moyen_max,
    ROUND(AVG(f.salaire_predit_eur)::numeric, 0) AS salaire_predit_moyen,
    COUNT(*) FILTER (WHERE f.salaire_min IS NULL) AS offres_sans_salaire,
    COUNT(*) FILTER (WHERE f.salaire_predit_eur IS NOT NULL) AS offres_avec_prediction,
    MAX(f.date_creation)                       AS date_derniere_offre,
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.salaire_min IS NOT NULL) / COUNT(*), 1) AS pct_salaire_connu,
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.salaire_predit_eur IS NOT NULL) / COUNT(*), 1) AS pct_salaire_predite
FROM fact_offres f
LEFT JOIN dim_lieu l ON f.lieu_id = l.lieu_id;


-- 4. VUE ENTREPRISES
DROP VIEW IF EXISTS vw_entreprises_kpi;
CREATE OR REPLACE VIEW vw_entreprises_kpi AS
SELECT
    COALESCE(e.nom, 'Non renseigné')     AS entreprise,
    COALESCE(e.secteur, 'Non renseigné') AS secteur,
    COALESCE(e.taille, 'Non renseigné')  AS taille,
    COUNT(*)                       AS nb_offres,
    COUNT(DISTINCT f.rome_libelle) AS nb_metiers_differents,
    ROUND(AVG(f.salaire_min)::numeric, 0) AS salaire_moyen_min,
    ROUND(AVG(f.salaire_max)::numeric, 0) AS salaire_moyen_max,
    MAX(f.date_creation)           AS derniere_offre,
    EXTRACT(DAY FROM MAX(f.date_creation) - MIN(f.date_creation)) AS duree_presence_jours
FROM fact_offres f
LEFT JOIN dim_entreprise e ON f.entreprise_id = e.entreprise_id
GROUP BY e.nom, e.secteur, e.taille;


-- 5. VUE MATRICE OFFRES × COMPÉTENCES
DROP VIEW IF EXISTS vw_offre_competences_flat;
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


-- VÉRIFICATION
SELECT 'vw_offres_complete' AS vue, COUNT(*) AS nb_lignes FROM vw_offres_complete
UNION ALL
SELECT 'vw_salaires_marche', (SELECT COUNT(*) FROM vw_salaires_marche)
UNION ALL
SELECT 'vw_kpi_global', (SELECT COUNT(*) FROM vw_kpi_global)
UNION ALL
SELECT 'vw_entreprises_kpi', (SELECT COUNT(*) FROM vw_entreprises_kpi)
UNION ALL
SELECT 'vw_offre_competences_flat', (SELECT COUNT(*) FROM vw_offre_competences_flat);
