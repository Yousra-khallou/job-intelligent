# Justification des choix techniques

Projet : Job Intelligent
Étudiant : Khallou Yousra 
Date : Mars 2026

## 1. Python 3.11
**Choix retenu :** Python 3.11
**Raison :** Langage dominant dans l'écosystème Data.
Bibliothèques riches : pandas, requests, scikit-learn.
**Alternatives rejetées :**
- Java : syntaxe lourde, moins adapté au prototypage rapide
- R : bon pour la statistique mais limité pour les pipelines ETL

## 2. Apache Airflow
**Choix retenu :** Apache Airflow 2.x
**Raison :** Standard industriel pour orchestrer les pipelines.
Interface web pour visualiser les DAGs et les erreurs.
**Alternatives rejetées :**
- Luigi : moins de fonctionnalités, communauté plus petite
- Cron : pas de gestion des dépendances entre tâches

## 3. PostgreSQL
**Choix retenu :** PostgreSQL 15
**Raison :** SGBD open-source performant pour l'analytique.
Compatible nativement avec dbt et Power BI.
**Alternatives rejetées :**
- MySQL : moins performant pour les requêtes analytiques
- SQLite : trop limité pour un Data Warehouse

## 4. dbt (data build tool)
**Choix retenu :** dbt-core
**Raison :** Permet de versionner les transformations SQL.
Génère automatiquement la documentation du modèle de données.
**Alternatives rejetées :**
- Scripts SQL manuels : pas de versioning, pas de tests

## 5. Power BI
**Choix retenu :** Microsoft Power BI
**Raison :** Spécifié dans le cahier des charges.
Connexion native à PostgreSQL, création de dashboards interactifs.
**Alternatives rejetées :**
- Tableau : non spécifié dans le cahier des charges
- Metabase : moins de fonctionnalités avancées

## 6. Hugging Face / Sentence-BERT
**Choix retenu :** Sentence-BERT (all-MiniLM-L6-v2)
**Raison :** Modèle pré-entraîné pour la similarité sémantique.
Idéal pour le matching profil/offre d'emploi.
**Alternatives rejetées :**
- TF-IDF : approche classique, moins précise sémantiquement
- Word2Vec : moins performant sur des textes courts