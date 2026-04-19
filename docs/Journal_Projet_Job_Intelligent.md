# Journal de Projet — Job Intelligent
**Data Engineering & Power BI | Examen Final**
Étudiant : [Ton Prénom Nom] | Date de début : Mars 2026

---

## Contexte du Projet

Projet académique individuel d'examen final visant à centraliser les offres d'emploi dans le domaine de la Data (Data Engineer, Data Scientist, Data Analyst, etc.) et à proposer un système de recommandation intelligent basé sur le NLP.

---

## Stack Technique Finale

| Composant | Outil | Rôle |
|---|---|---|
| Langage | Python 3.11 | Développement principal |
| Orchestration | Apache Airflow 2.9.0 | Planification des pipelines |
| Traitement | Apache Spark 3.5.1 | Transformation des données |
| Data Lake | MinIO | Stockage Bronze/Silver/Gold |
| Data Warehouse | PostgreSQL 15 | Stockage structuré |
| Interface DB | pgAdmin 4 | Administration PostgreSQL |
| Transformation | dbt | Modèles SQL versionnés |
| NLP / ML | Hugging Face / Sentence-BERT | Système de recommandation |
| Visualisation | Power BI | Dashboards analytiques |
| API | FastAPI | Endpoint de recommandation |
| Conteneurs | Docker | Environnement reproductible |

> Kubernetes et Kafka ont été exclus du périmètre — over-engineering pour un projet académique individuel.

---

## Infrastructure Docker

### Ports des services

| Service | Port externe | Port interne |
|---|---|---|
| PostgreSQL | 5433 | 5432 |
| pgAdmin | 5050 | 80 |
| Airflow | 8082 | 8080 |
| Spark Master UI | 8083 | 8080 |
| Spark Master | 7077 | 7077 |
| MinIO API | 9002 | 9000 |
| MinIO Console | 9003 | 9001 |

### docker-compose.yml

```yaml
services:

  postgres:
    image: postgres:15
    container_name: postgres_db
    environment:
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: admin123
      POSTGRES_DB: job_intelligent
    ports:
      - "5433:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  pgadmin:
    image: dpage/pgadmin4
    container_name: pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@jobintelligent.com
      PGADMIN_DEFAULT_PASSWORD: admin123
    ports:
      - "5050:80"
    depends_on:
      - postgres

  airflow:
    image: apache/airflow:2.9.0
    container_name: airflow
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://admin:admin123@postgres/job_intelligent
      AIRFLOW__CORE__LOAD_EXAMPLES: 'false'
    ports:
      - "8082:8080"
    volumes:
      - ./src/etl:/opt/airflow/dags
    depends_on:
      - postgres
    command: standalone

  spark-master:
    image: apache/spark:3.5.1-python3
    container_name: spark_master
    environment:
      SPARK_MODE: master
      SPARK_MASTER_HOST: spark-master
    ports:
      - "7077:7077"
      - "8083:8080"
    command: /opt/spark/bin/spark-class org.apache.spark.deploy.master.Master

  spark-worker-1:
    image: apache/spark:3.5.1-python3
    container_name: spark_worker_1
    environment:
      SPARK_MODE: worker
      SPARK_MASTER_URL: spark://spark-master:7077
      SPARK_WORKER_MEMORY: 2G
      SPARK_WORKER_CORES: 2
    depends_on:
      - spark-master
    command: /opt/spark/bin/spark-class org.apache.spark.deploy.worker.Worker spark://spark-master:7077

  spark-worker-2:
    image: apache/spark:3.5.1-python3
    container_name: spark_worker_2
    environment:
      SPARK_MODE: worker
      SPARK_MASTER_URL: spark://spark-master:7077
      SPARK_WORKER_MEMORY: 2G
      SPARK_WORKER_CORES: 2
    depends_on:
      - spark-master
    command: /opt/spark/bin/spark-class org.apache.spark.deploy.worker.Worker spark://spark-master:7077

  minio:
    image: minio/minio
    container_name: minio
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin123
    ports:
      - "9002:9000"
      - "9003:9001"
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"

volumes:
  postgres_data:
  minio_data:
```

### Commandes Docker utiles

```bash
# Démarrer tous les services
docker-compose up -d

# Vérifier l'état des conteneurs
docker ps

# Arrêter tous les services
docker-compose down

# Voir les logs Airflow
docker logs airflow --tail 30

# Récupérer le mot de passe Airflow
docker logs airflow | findstr "password"

# Supprimer le fichier PID bloqué (si Airflow ne démarre pas)
docker exec airflow rm -f /opt/airflow/airflow-webserver.pid
docker restart airflow
```

---

## Structure du Projet

```
job-intelligent/
├── config/
├── dashboards/
├── data/
│   ├── raw/
│   ├── processed/
│   └── warehouse/
├── dbt/
│   ├── models/
│   └── tests/
├── docs/
│   ├── README.md
│   ├── architecture.md
│   ├── choix_techniques.md
│   ├── journal_bord.md
│   ├── mapping_champs.md
│   └── equipe.md
├── notebooks/
├── src/
│   ├── api/
│   ├── etl/
│   │   ├── dag_pipeline_collecte.py
│   │   ├── scraper_france_travail.py
│   │   ├── scraper_adzuna.py
│   │   └── scraper_emploima.py
│   ├── ml/
│   └── scraping/
│       ├── scraper_france_travail.py
│       ├── scraper_adzuna.py
│       ├── scraper_emploima.py
│       ├── test_api.py
│       └── analyse_structure.py
├── tests/
├── .env
├── .gitignore
├── docker-compose.yml
└── requirements.txt
```

---

## Data Lake — Architecture Bronze / Silver / Gold

| Couche | Dossier MinIO | Format | Description |
|---|---|---|---|
| Bronze | `bronze/` | JSON | Données brutes telles que reçues des APIs |
| Silver | `silver/` | Parquet/CSV | Données nettoyées et standardisées |
| Gold | `gold/` | Tables agrégées | Données prêtes pour le DWH et Power BI |

### Buckets MinIO créés
- `bronze` — données brutes
- `silver` — données nettoyées
- `gold` — données agrégées

---

## Sources de Données

| Source | Méthode | Profils collectés | Statut |
|---|---|---|---|
| France-Travail | API officielle OAuth2 | 6 profils | ✅ Opérationnel |
| Adzuna | API officielle | 6 profils | ✅ Opérationnel |
| Emploi.ma | Scraping HTML | 3 profils | ✅ Opérationnel |

### Profils métiers collectés
- Data Engineer
- Data Scientist
- Data Analyst
- Machine Learning Engineer
- Business Intelligence
- Data Architect

### Total offres collectées

| Source | Offres |
|---|---|
| France-Travail | 421 |
| Adzuna | 600 |
| Emploi.ma | 140 |
| **Total** | **1 161 offres** |

---

## Scrapers Python

### Scraper France-Travail (`src/etl/scraper_france_travail.py`)

```python
import requests
import os
import json
import boto3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")

minio_client = boto3.client(
    's3',
    endpoint_url='http://minio:9000',  # nom service Docker
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin123',
    region_name='us-east-1'
)

def get_token():
    url = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
    params = {"realm": "/partenaire"}
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "api_offresdemploiv2 o2dsoffre"
    }
    response = requests.post(url, params=params, data=data)
    return response.json().get("access_token")

def collecter_offres(token, keyword="data", nb_offres=100):
    url = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
    headers = {"Authorization": f"Bearer {token}"}
    toutes_offres = []

    for start in range(0, nb_offres, 50):
        end = min(start + 49, nb_offres - 1)
        params = {"motsCles": keyword, "range": f"{start}-{end}"}
        response = requests.get(url, headers=headers, params=params)
        if response.status_code in [200, 206]:
            resultats = response.json().get("resultats", [])
            toutes_offres.extend(resultats)
        elif response.status_code == 204:
            break
        else:
            break

    return toutes_offres
```

> **Note importante** : Dans les scrapers utilisés par Airflow, l'endpoint MinIO doit être `http://minio:9000` (nom du service Docker) et non `http://localhost:9002`. Les conteneurs Docker ne se voient pas via `localhost`.

### Scraper Adzuna (`src/etl/scraper_adzuna.py`)

Utilise l'API publique Adzuna avec `app_id` et `app_key`. Collecte 20 offres par page sur 5 pages par profil.

### Scraper Emploi.ma (`src/etl/scraper_emploima.py`)

Scraping HTML avec BeautifulSoup. Structure HTML :
- Titre : `div.card-job-detail > h3 > a`
- Entreprise : `a.card-job-company`
- Infos : balises `<li>` avec `<strong>` pour les valeurs

---

## DAG Airflow

### Fichier : `src/etl/dag_pipeline_collecte.py`

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys

sys.path.insert(0, '/opt/airflow/dags')

from scraper_france_travail import run as run_france_travail
from scraper_adzuna import run as run_adzuna
from scraper_emploima import run as run_emploima

default_args = {
    'owner': 'job_intelligent',
    'depends_on_past': False,
    'start_date': datetime(2026, 3, 29),
    'retries': 2,
    'retry_delay': timedelta(minutes=5)
}

with DAG(
    dag_id='pipeline_collecte_offres',
    default_args=default_args,
    description='Collecte quotidienne des offres emploi Data',
    schedule_interval='0 8 * * *',
    catchup=False,
    tags=['collecte', 'scraping', 'bronze']
) as dag:

    task_france_travail = PythonOperator(
        task_id='scraper_france_travail',
        python_callable=run_france_travail
    )

    task_adzuna = PythonOperator(
        task_id='scraper_adzuna',
        python_callable=run_adzuna
    )

    task_emploima = PythonOperator(
        task_id='scraper_emploima',
        python_callable=run_emploima
    )

    # Les 3 scrapers tournent en parallèle
    [task_france_travail, task_adzuna, task_emploima]
```

### Résultat du DAG

- `scraper_france_travail` → ✅ success
- `scraper_adzuna` → ✅ success
- `scraper_emploima` → ✅ success
- Schedule : tous les jours à 8h00

---

## Mapping des Champs — API France-Travail

| Champ API | Table DWH | Colonne DWH | Type |
|---|---|---|---|
| id | fact_offres | offre_id | VARCHAR |
| intitule | fact_offres | titre | VARCHAR |
| dateCreation | dim_date | date_creation | TIMESTAMP |
| typeContrat | dim_contrat | type_contrat | VARCHAR |
| experienceLibelle | fact_offres | experience | VARCHAR |
| description | fact_offres | description | TEXT |
| lieuTravail.libelle | dim_lieu | ville | VARCHAR |
| lieuTravail.codePostal | dim_lieu | code_postal | VARCHAR |
| lieuTravail.latitude | dim_lieu | latitude | FLOAT |
| lieuTravail.longitude | dim_lieu | longitude | FLOAT |
| entreprise.nom | dim_entreprise | nom | VARCHAR |
| secteurActiviteLibelle | dim_entreprise | secteur | VARCHAR |
| trancheEffectifEtab | dim_entreprise | taille | VARCHAR |
| salaire.libelle | fact_offres | salaire_libelle | VARCHAR |
| competences | dim_competence | nom_competence | VARCHAR |
| romeCode | fact_offres | rome_code | VARCHAR |
| origineOffre.urlOrigine | fact_offres | url_offre | VARCHAR |

---

## Modèle de Données DWH — Schéma en Étoile

```sql
-- Table de faits
CREATE TABLE fact_offres (
    offre_id        VARCHAR(50)  PRIMARY KEY,
    date_id         INT          REFERENCES dim_date(date_id),
    entreprise_id   INT          REFERENCES dim_entreprise(entreprise_id),
    lieu_id         INT          REFERENCES dim_lieu(lieu_id),
    source          VARCHAR(50),
    type_contrat    VARCHAR(30),
    salaire_min     INT,
    salaire_max     INT,
    rome_code       VARCHAR(10),
    rome_libelle    VARCHAR(100),
    experience      VARCHAR(50),
    description     TEXT,
    url_offre       VARCHAR(500),
    date_creation   TIMESTAMP DEFAULT NOW()
);

-- Dimension Date
CREATE TABLE dim_date (
    date_id      SERIAL PRIMARY KEY,
    date_full    DATE NOT NULL,
    annee        INT,
    mois         INT,
    semaine      INT,
    jour_semaine VARCHAR(20)
);

-- Dimension Entreprise
CREATE TABLE dim_entreprise (
    entreprise_id SERIAL PRIMARY KEY,
    nom           VARCHAR(200),
    secteur       VARCHAR(100),
    taille        VARCHAR(50)
);

-- Dimension Lieu
CREATE TABLE dim_lieu (
    lieu_id     SERIAL PRIMARY KEY,
    ville       VARCHAR(100),
    region      VARCHAR(100),
    pays        VARCHAR(50) DEFAULT 'France',
    code_postal VARCHAR(10),
    latitude    FLOAT,
    longitude   FLOAT
);

-- Dimension Compétence
CREATE TABLE dim_competence (
    competence_id SERIAL PRIMARY KEY,
    nom           VARCHAR(100),
    categorie     VARCHAR(50)
);
```

---

## Variables d'Environnement (.env)

```env
# PostgreSQL
POSTGRES_USER=admin
POSTGRES_PASSWORD=admin123
POSTGRES_DB=job_intelligent
DATABASE_URL=postgresql://admin:admin123@localhost:5433/job_intelligent

# pgAdmin
PGADMIN_EMAIL=admin@jobintelligent.com
PGADMIN_PASSWORD=admin123

# Airflow
AIRFLOW_USER=admin
AIRFLOW_PASSWORD=admin123

# MinIO
MINIO_ENDPOINT=localhost:9002
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET_BRONZE=bronze
MINIO_BUCKET_SILVER=silver

# Spark
SPARK_MASTER=spark://spark-master:7077

# APIs
FRANCE_TRAVAIL_CLIENT_ID=PAR_jobintelligentapp_...
FRANCE_TRAVAIL_CLIENT_SECRET=...
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...
```

---

## Problèmes Rencontrés et Solutions

| Problème | Cause | Solution |
|---|---|---|
| `.gitignore.txt` au lieu de `.gitignore` | Windows Notepad ajoute `.txt` | Commande `ren .gitignore.txt .gitignore` |
| Port 5432 déjà utilisé | PostgreSQL installé localement | Changer le port en `5433:5432` |
| Port 9000 déjà utilisé | Autre service | Changer en `9002:9000` |
| Port 8080 déjà utilisé | Autre service | Changer en `8082:8080` |
| Airflow webserver PID bloqué | Arrêt brutal du conteneur | `docker exec airflow rm -f /opt/airflow/airflow-webserver.pid` |
| Erreur 206 France-Travail | Code 206 = contenu partiel, pas une erreur | Traiter 206 comme 200 dans le code |
| MinIO inaccessible depuis Airflow | `localhost` ne fonctionne pas dans Docker | Utiliser `minio:9000` (nom de service Docker) |
| Indeed bloque le scraping | Protection anti-bot 403 | Remplacé par Emploi.ma |
| `venv\Scripts\activate` bloqué | PowerShell désactive les scripts | Utiliser CMD au lieu de PowerShell |

---

## Commits Git

```
feat: initialisation du projet Job Intelligent - Phase 1.1 Kick-off
feat: ajout docker-compose - PostgreSQL + Airflow + pgAdmin operationnels
docs: mise a jour journal de bord - infrastructure complete
feat: infrastructure complete - Airflow + Spark cluster + MinIO + PostgreSQL
feat: scraper Adzuna - 600 offres collectees dans MinIO Bronze
feat: analyse structure JSON API France-Travail - mapping champs DWH
feat: scrapers complets - 1161 offres collectees FranceTravail + Adzuna + Emploima
feat: DAG Airflow pipeline_collecte_offres - 3 scrapers success
```

---

## Prochaines Étapes

### Phase 2 — Couche Silver (Transformation Spark)
- Lire les JSON depuis MinIO Bronze
- Nettoyer avec PySpark (dédoublonnage, normalisation)
- Sauvegarder en Parquet dans MinIO Silver

### Phase 3 — Data Warehouse (dbt + PostgreSQL)
- Créer les modèles dbt
- Charger les tables fact_offres et dimensions
- Tests de qualité des données

### Phase 4 — Système de Recommandation NLP
- Vectorisation des offres (Sentence-BERT)
- API FastAPI de recommandation
- Calcul de similarité cosinus

### Phase 5 — Power BI
- Connexion au DWH PostgreSQL
- Dashboard marché de l'emploi Data
- Dashboard recommandations personnalisées

### Phase 6 — Finalisation
- Tests end-to-end
- Documentation finale
- Rapport et présentation

---

## Justification des Choix Techniques

### Pourquoi MinIO et non stockage local ?
Le cahier des charges exige une architecture **scalable**. Un stockage local est limité en volume et ne peut pas grandir. MinIO est compatible S3, tourne dans Docker, et peut être remplacé par AWS S3 ou Azure Blob Storage en production sans changer le code.

### Pourquoi Spark Master + 2 Workers ?
Le mode cluster reproduit une vraie architecture industrielle. Avec 25 Go de RAM disponibles, le cluster tourne sans problème et impressionne lors de la soutenance.

### Pourquoi Airflow plutôt qu'APScheduler ?
Airflow est le standard industriel pour l'orchestration de pipelines data. Il offre une interface web, la gestion des dépendances entre tâches, les retry automatiques, et un historique des exécutions.

### Pourquoi 3 sources de données ?
La diversité des sources (API officielle FR, API internationale, scraping Maroc) démontre la capacité à intégrer des formats hétérogènes — compétence clé d'un Data Engineer.

---

*Document généré automatiquement — Projet Job Intelligent — Examen Final Data Engineering*
