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