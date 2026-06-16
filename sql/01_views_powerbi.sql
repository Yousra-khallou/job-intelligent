
-- ============================================================
--  VUES ANALYTIQUES POUR POWER BI — Job Intelligent
--  Base : dwh_job_intelligent (fact_offres + dimensions)
--  Auteur : Généré automatiquement pour le projet Job Intelligent
--  Date : 2026-05-15
-- ============================================================

-- 1. VUE PRINCIPALE : Offres dénormalisées (Star-Schema flatten)
--    Utilisée pour 80% des visuels Power BI
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
    -- Dimension Date
    d.annee,
    d.mois,
    TO_CHAR(f.date_creation, 'YYYY-MM') AS annee_mois,
    d.jour_semaine,
    -- Dimension Lieu
    COALESCE(l.ville,  'Non renseigné') AS ville,
    COALESCE(l.region, 'Non renseigné') AS region,
    COALESCE(l.pays,   'France')        AS pays,
    l.latitude,
    l.longitude,
    -- Dimension Entreprise
    COALESCE(e.nom,     'Non renseigné') AS entreprise,
    COALESCE(e.secteur, 'Non renseigné') AS secteur,
    COALESCE(e.taille,  'Non renseigné') AS taille_entreprise,
    -- Flags analytiques
    CASE WHEN f.salaire_min IS NOT NULL AND f.salaire_max IS NOT NULL 
         THEN 1 ELSE 0 END AS a_salaire_connu,
    CASE WHEN f.salaire_predit_eur IS NOT NULL 
         THEN 1 ELSE 0 END AS a_salaire_predite,
    -- Fourchette salariale estimée (réel ou prédit)
    COALESCE(
        (f.salaire_min + f.salaire_max) / 2.0,
        f.salaire_predit_eur
    ) AS salaire_estime
FROM fact_offres f
LEFT JOIN dim_date       d ON f.date_id = d.date_id
LEFT JOIN dim_lieu       l ON f.lieu_id = l.lieu_id
LEFT JOIN dim_entreprise e ON f.entreprise_id = e.entreprise_id;


-- 2. VUE MARCHÉ & SALAIRES : Benchmark par métier / lieu / contrat
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


-- 3. VUE KPI GLOBAL : Agrégation pour cartes KPI en haut de page
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
    -- Taux de couverture
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.salaire_min IS NOT NULL) / COUNT(*), 1) AS pct_salaire_connu,
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.salaire_predit_eur IS NOT NULL) / COUNT(*), 1) AS pct_salaire_predite
FROM fact_offres f
LEFT JOIN dim_lieu l ON f.lieu_id = l.lieu_id;


-- 4. VUE SOURCES : Répartition et qualité par source de scraping
CREATE OR REPLACE VIEW vw_sources_kpi AS
SELECT
    f.source,
    COUNT(*)                                           AS nb_offres,
    COUNT(DISTINCT f.entreprise_id)                    AS nb_entreprises,
    COUNT(DISTINCT f.rome_libelle)                     AS nb_metiers,
    ROUND(AVG(f.salaire_min)::numeric, 0)              AS salaire_moyen_min,
    ROUND(AVG(f.salaire_max)::numeric, 0)              AS salaire_moyen_max,
    COUNT(*) FILTER (WHERE f.salaire_min IS NULL)    AS nb_sans_salaire,
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.salaire_min IS NULL) / COUNT(*), 1) AS pct_sans_salaire,
    COUNT(*) FILTER (WHERE f.salaire_predit_eur IS NOT NULL) AS nb_avec_prediction,
    MIN(f.date_creation)                               AS date_premiere_offre,
    MAX(f.date_creation)                               AS date_derniere_offre,
    -- Qualité des données
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.description IS NOT NULL) / COUNT(*), 1) AS pct_avec_description,
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.experience IS NOT NULL) / COUNT(*), 1) AS pct_avec_experience
FROM fact_offres f
GROUP BY f.source;


-- 5. VUE TENDANCES : Séries temporelles pour graphiques linéaires
CREATE OR REPLACE VIEW vw_tendances_offres AS
SELECT
    DATE_TRUNC('week', f.date_creation)  AS semaine,
    TO_CHAR(DATE_TRUNC('week', f.date_creation), 'YYYY-MM-DD') AS semaine_label,
    f.source,
    f.rome_libelle AS metier,
    COUNT(*)       AS nb_offres,
    ROUND(AVG(f.salaire_min)::numeric, 0) AS salaire_moyen_min,
    ROUND(AVG(f.salaire_max)::numeric, 0) AS salaire_moyen_max,
    ROUND(AVG(f.salaire_predit_eur)::numeric, 0) AS salaire_predit_moyen
FROM fact_offres f
WHERE f.date_creation >= CURRENT_DATE - INTERVAL '6 months'
GROUP BY DATE_TRUNC('week', f.date_creation), f.source, f.rome_libelle;


-- 6. VUE ENTREPRISES : Top recruteurs et secteurs
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
    -- Présence sur le marché (jours entre première et dernière offre)
    EXTRACT(DAY FROM MAX(f.date_creation) - MIN(f.date_creation)) AS duree_presence_jours
FROM fact_offres f
LEFT JOIN dim_entreprise e ON f.entreprise_id = e.entreprise_id
GROUP BY e.nom, e.secteur, e.taille;


-- 7. VUE COMPÉTENCES : Analyse des compétences extraites
CREATE OR REPLACE VIEW vw_competences_demandees AS
SELECT
    c.nom AS competence,
    c.categorie,
    c.nb_offres,
    -- Si nb_offres n'existe pas dans dim_competence, compter depuis bridge
    COALESCE(c.nb_offres, 0) AS nb_offres_detectees
FROM dim_competence c
ORDER BY c.nb_offres DESC NULLS LAST;


-- 8. VUE QUALITÉ DES DONNÉES : Pour page admin/monitoring
CREATE OR REPLACE VIEW vw_qualite_donnees AS
SELECT
    'titre' AS colonne,
    COUNT(*) FILTER (WHERE titre IS NULL) AS nb_nulls,
    ROUND(100.0 * COUNT(*) FILTER (WHERE titre IS NULL) / COUNT(*), 1) AS pct_nulls
FROM fact_offres
UNION ALL
SELECT 'description', COUNT(*) FILTER (WHERE description IS NULL), ROUND(100.0 * COUNT(*) FILTER (WHERE description IS NULL) / COUNT(*), 1) FROM fact_offres
UNION ALL
SELECT 'salaire_min', COUNT(*) FILTER (WHERE salaire_min IS NULL), ROUND(100.0 * COUNT(*) FILTER (WHERE salaire_min IS NULL) / COUNT(*), 1) FROM fact_offres
UNION ALL
SELECT 'salaire_predit_eur', COUNT(*) FILTER (WHERE salaire_predit_eur IS NULL), ROUND(100.0 * COUNT(*) FILTER (WHERE salaire_predit_eur IS NULL) / COUNT(*), 1) FROM fact_offres
UNION ALL
SELECT 'experience', COUNT(*) FILTER (WHERE experience IS NULL), ROUND(100.0 * COUNT(*) FILTER (WHERE experience IS NULL) / COUNT(*), 1) FROM fact_offres
UNION ALL
SELECT 'ville', COUNT(*) FILTER (WHERE lieu_id IS NULL), ROUND(100.0 * COUNT(*) FILTER (WHERE lieu_id IS NULL) / COUNT(*), 1) FROM fact_offres
UNION ALL
SELECT 'entreprise', COUNT(*) FILTER (WHERE entreprise_id IS NULL), ROUND(100.0 * COUNT(*) FILTER (WHERE entreprise_id IS NULL) / COUNT(*), 1) FROM fact_offres;
