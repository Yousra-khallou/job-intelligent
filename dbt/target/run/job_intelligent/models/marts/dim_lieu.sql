
  
    

  create  table "dwh_job_intelligent"."public"."dim_lieu__dbt_tmp"
  
  
    as
  
  (
    WITH lieux AS (
    SELECT DISTINCT
        COALESCE(ville, 'Non renseigné') AS ville,
        region,
        COALESCE(pays, 'France')         AS pays,
        code_postal,
        latitude::FLOAT,
        longitude::FLOAT
    FROM "dwh_job_intelligent"."public"."stg_offres"
)
SELECT
    ROW_NUMBER() OVER (ORDER BY ville) AS lieu_id,
    ville,
    region,
    pays,
    code_postal,
    latitude,
    longitude
FROM lieux
  );
  