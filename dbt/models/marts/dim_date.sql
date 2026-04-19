WITH dates AS (
    SELECT DISTINCT DATE(date_creation::TIMESTAMP) AS date_full
    FROM {{ ref('stg_offres') }}
    WHERE date_creation IS NOT NULL
)
SELECT
    ROW_NUMBER() OVER (ORDER BY date_full) AS date_id,
    date_full,
    EXTRACT(YEAR  FROM date_full)::INT AS annee,
    EXTRACT(MONTH FROM date_full)::INT AS mois,
    EXTRACT(WEEK  FROM date_full)::INT AS semaine,
    TO_CHAR(date_full, 'Day')          AS jour_semaine
FROM dates