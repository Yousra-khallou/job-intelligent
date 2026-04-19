
  
    

  create  table "dwh_job_intelligent"."public"."dim_entreprise__dbt_tmp"
  
  
    as
  
  (
    WITH entreprises AS (
    SELECT DISTINCT
        COALESCE(entreprise, 'Non renseigné') AS nom,
        COALESCE(secteur, 'Non renseigné')    AS secteur,
        COALESCE(taille_entreprise, 'Non renseigné') AS taille
    FROM "dwh_job_intelligent"."public"."stg_offres"
)
SELECT
    ROW_NUMBER() OVER (ORDER BY nom) AS entreprise_id,
    nom,
    secteur,
    taille
FROM entreprises
  );
  