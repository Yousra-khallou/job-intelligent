# Projet Job Intelligent

## Contexte
Projet académique - Examen Final Data Engineering
Réalisé individuellement par : [Ton Prénom Nom]
Date : Mars 2026

## Objectif
Centraliser les offres d'emploi dans le domaine de la Data
(Indeed, LinkedIn, France-Travail) et proposer un système
de recommandation intelligent basé sur le NLP.

## Stack technique
| Composant       | Outil           |
|-----------------|-----------------|
| Langage         | Python 3.11     |
| Orchestration   | Apache Airflow  |
| Transformation  | dbt             |
| Base de données | PostgreSQL      |
| NLP / ML        | Hugging Face    |
| Visualisation   | Power BI        |
| Conteneurs      | Docker          |

## Structure du projet
- src/scraping  : scripts de collecte des offres
- src/etl       : pipelines de transformation
- src/ml        : système de recommandation
- src/api       : API FastAPI
- dbt/          : modèles de transformation SQL
- dashboards/   : fichiers Power BI
- docs/         : documentation du projet
- data/         : données brutes et traitées