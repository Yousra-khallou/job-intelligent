# Mapping des champs — API France-Travail

Analyse effectuée le : 22/03/2026
Source : API Offres d'emploi v2

## Champs retenus pour le Data Warehouse

| Champ API            | Table DWH        | Colonne DWH       | Type      |
|----------------------|------------------|-------------------|-----------|
| id                   | fact_offres      | offre_id          | VARCHAR   |
| intitule             | fact_offres      | titre             | VARCHAR   |
| dateCreation         | dim_date         | date_creation     | TIMESTAMP |
| typeContrat          | dim_contrat      | type_contrat      | VARCHAR   |
| experienceLibelle    | fact_offres      | experience        | VARCHAR   |
| description          | fact_offres      | description       | TEXT      |
| lieuTravail.libelle  | dim_lieu         | ville             | VARCHAR   |
| lieuTravail.codePostal| dim_lieu        | code_postal       | VARCHAR   |
| lieuTravail.latitude | dim_lieu         | latitude          | FLOAT     |
| lieuTravail.longitude| dim_lieu         | longitude         | FLOAT     |
| entreprise.nom       | dim_entreprise   | nom               | VARCHAR   |
| secteurActiviteLibelle| dim_entreprise  | secteur           | VARCHAR   |
| trancheEffectifEtab  | dim_entreprise   | taille            | VARCHAR   |
| salaire.libelle      | fact_offres      | salaire_libelle   | VARCHAR   |
| competences          | dim_competence   | nom_competence    | VARCHAR   |
| romeCode             | fact_offres      | rome_code         | VARCHAR   |
| romeLibelle          | fact_offres      | rome_libelle      | VARCHAR   |
| origineOffre.urlOrigine| fact_offres    | url_offre         | VARCHAR   |

## Champs ignorés
- accessibleTH, employeurHandiEngage : hors périmètre
- agence : souvent vide
- contexteTravail : redondant avec dureeTravailLibelle
- contact.coordonnees1 : données personnelles sensibles (RGPD)
- contact.urlPostulation : remplacé par origineOffre.urlOrigine
  qui pointe vers la page officielle France-Travail

## Observations importantes
- Le champ "competences" est une liste (plusieurs compétences par offre)
  → nécessite une table de jointure : fact_offres_competences
- Le salaire est en texte libre (pas structuré)
  → nécessite un parsing pour extraire min/max
- dateCreation est en format ISO 8601
  → nécessite une conversion pour la dim_date