SELECT
    offre_id,
    titre,
    type_contrat,
    experience,
    description,
    ville,
    region,
    code_postal,
    latitude::FLOAT,
    longitude::FLOAT,
    pays,
    entreprise,
    secteur,
    taille_entreprise,
    salaire_libelle,
    salaire_min::INT,
    salaire_max::INT,
    rome_code,
    rome_libelle,
    url_offre,
    date_creation::TIMESTAMP,
    source
FROM raw_offres
WHERE offre_id IS NOT NULL
  AND titre IS NOT NULL