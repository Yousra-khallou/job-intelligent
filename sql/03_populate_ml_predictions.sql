
-- ============================================================
--  PEUPLEMENT DES PRÉDICTIONS ML DANS FACT_OFFRES
--  À exécuter APRÈS que le modèle ML soit entraîné
--  Et APRÈS le dbt run
-- ============================================================

-- Option 1 : Si tu veux utiliser le modèle ML via Python (RECOMMANDÉ)
-- Exécute ce script Python dans le conteneur fastapi :
--
-- docker exec fastapi_nlp python -c "
-- import psycopg2
-- import pandas as pd
-- from salary_predictor import predict_batch, load_offres_from_db
-- 
-- # Charger les offres depuis raw_offres
-- df = predict_batch(load_offres_from_db())
-- 
-- conn = psycopg2.connect(
--     host='postgres_db', port=5432, dbname='dwh_job_intelligent',
--     user='admin', password='admin123'
-- )
-- cur = conn.cursor()
-- 
-- updated = 0
-- for _, row in df.iterrows():
--     if pd.notna(row['salaire_predit_eur']):
--         cur.execute('''
--             UPDATE fact_offres
--             SET salaire_predit_eur = %s,
--                 salaire_confiance = %s,
--                 date_prediction = NOW()
--             WHERE offre_id = %s
--               AND salaire_min IS NULL
--         ''', (
--             float(row['salaire_predit_eur']),
--             'moyenne',
--             str(row['offre_id'])
--         ))
--         updated += cur.rowcount
-- 
-- conn.commit()
-- cur.close()
-- conn.close()
-- print(f'✅ {updated} offres mises à jour avec salaire prédit')
-- "


-- Option 2 : Si tu n'as pas encore de modèle ML entraîné,
-- tu peux utiliser cette vue qui calcule un salaire estimé approximatif
-- basé sur les données existantes (médiane par métier/contrat)
CREATE OR REPLACE VIEW vw_salaire_estime_fallback AS
WITH stats_metier AS (
    SELECT
        rome_libelle,
        type_contrat,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY (salaire_min + salaire_max) / 2.0) AS mediane_salaire
    FROM fact_offres
    WHERE salaire_min IS NOT NULL AND salaire_max IS NOT NULL
    GROUP BY rome_libelle, type_contrat
)
SELECT
    f.offre_id,
    COALESCE(
        s.mediane_salaire,
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY (salaire_min + salaire_max) / 2.0) 
         FROM fact_offres WHERE salaire_min IS NOT NULL)
    ) AS salaire_estime_fallback
FROM fact_offres f
LEFT JOIN stats_metier s ON f.rome_libelle = s.rome_libelle AND f.type_contrat = s.type_contrat
WHERE f.salaire_min IS NULL;


-- Option 3 : Mettre à jour fact_offres avec le fallback (si pas de ML)
-- UPDATE fact_offres f
-- SET salaire_predit_eur = v.salaire_estime_fallback,
--     salaire_confiance = 'basse (fallback)',
--     date_prediction = NOW()
-- FROM vw_salaire_estime_fallback v
-- WHERE f.offre_id = v.offre_id
--   AND f.salaire_min IS NULL
--   AND f.salaire_predit_eur IS NULL;
