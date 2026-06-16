{{ config(
    materialized='incremental',
    unique_key='offre_id',
    on_schema_change='sync_all_columns'
) }}

WITH offres AS (
    SELECT * FROM {{ ref('stg_offres') }}
),
dates AS (
    SELECT * FROM {{ ref('dim_date') }}
),
entreprises AS (
    SELECT * FROM {{ ref('dim_entreprise') }}
),
lieux AS (
    SELECT * FROM {{ ref('dim_lieu') }}
)
SELECT
    o.offre_id,
    d.date_id,
    e.entreprise_id,
    l.lieu_id,
    o.source,
    o.titre,
    o.type_contrat,
    o.salaire_min,
    o.salaire_max,
    o.salaire_libelle,
    -- Colonnes ML (seront peuplées par script Python post-dbt)
    NULL::NUMERIC(10,2) AS salaire_predit_eur,
    NULL::VARCHAR(10)   AS salaire_confiance,
    NULL::TIMESTAMP     AS date_prediction,
    o.rome_code,
    o.rome_libelle,
    o.experience,
    o.description,
    o.url_offre,
    o.date_creation
FROM offres o
LEFT JOIN dates       d ON DATE(o.date_creation) = d.date_full
LEFT JOIN entreprises e ON COALESCE(o.entreprise, 'Non renseigné') = e.nom
LEFT JOIN lieux       l ON COALESCE(o.ville, 'Non renseigné') = l.ville
                       AND COALESCE(o.pays, 'France') = l.pays

{% if is_incremental() %}
WHERE o.offre_id NOT IN (SELECT offre_id FROM {{ this }})
{% endif %}