
      
        
        
        delete from "dwh_job_intelligent"."public"."fact_offres" as DBT_INTERNAL_DEST
        where (offre_id) in (
            select distinct offre_id
            from "fact_offres__dbt_tmp081028943829" as DBT_INTERNAL_SOURCE
        );

    

    insert into "dwh_job_intelligent"."public"."fact_offres" ("offre_id", "date_id", "entreprise_id", "lieu_id", "source", "titre", "type_contrat", "salaire_min", "salaire_max", "salaire_libelle", "salaire_predit_eur", "salaire_confiance", "date_prediction", "rome_code", "rome_libelle", "experience", "description", "url_offre", "date_creation")
    (
        select "offre_id", "date_id", "entreprise_id", "lieu_id", "source", "titre", "type_contrat", "salaire_min", "salaire_max", "salaire_libelle", "salaire_predit_eur", "salaire_confiance", "date_prediction", "rome_code", "rome_libelle", "experience", "description", "url_offre", "date_creation"
        from "fact_offres__dbt_tmp081028943829"
    )
  