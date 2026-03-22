# Journal de bord — Projet Job Intelligent

Étudiant : Khallou Yousra

Début du projet : Mars 2026

---

## Session 1 — 22/03/2026

**Durée :** 2h
**Phase :** 1.1 Kick-off et gouvernance

**Ce que j'ai fait :**
- Installé Git sur Windows
- Créé la structure complète du projet
- Créé le fichier .gitignore
- Rédigé le README du projet
- Documenté les choix techniques et leurs justifications

**Décisions prises :**
- Choix de PostgreSQL comme Data Warehouse
- Choix d'Airflow pour l'orchestration
- Choix de Sentence-BERT pour le système de recommandation

**Difficultés rencontrées :**
- Problème avec .gitignore.txt renommé en .gitignore
- Résolu avec la commande ren

**Prochaine session :**
- Créer l'environnement virtuel Python
- Tester l'API France-Travail

**Mis à jour :**
- Installé et configuré Docker-compose
- Lancé PostgreSQL, Airflow et pgAdmin
- Vérifié les 3 interfaces web opérationnelles
- 2 commits Git effectués
---
## Session 2 — 22/03/2026

**Durée :** 1h
**Phase :** 1.2 Analyse des sources

**Ce que j'ai fait :**
- Créé le compte développeur France-Travail
- Obtenu le Client ID et la Clé secrète
- Créé l'environnement virtuel Python
- Installé requests et python-dotenv
- Écrit le script test_api.py
- Récupéré 5 vraies offres d'emploi Data Engineer

**Résultat :**
- Token OAuth2 obtenu avec succès
- 5 offres récupérées : Nantes, Paris, Lille, Montpellier, Toulouse
- Champs disponibles : titre, entreprise, lieu, type contrat

**Prochaine session :**
- Analyser tous les champs disponibles dans le JSON
- Écrire le scraper complet pour 100+ offres