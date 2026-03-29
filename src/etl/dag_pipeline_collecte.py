from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, '/opt/airflow/dags')

# Import des scrapers
from scraper_france_travail import run as run_france_travail
from scraper_adzuna import run as run_adzuna
from scraper_emploima import run as run_emploima

# Configuration par defaut du DAG
default_args = {
    'owner': 'job_intelligent',
    'depends_on_past': False,
    'start_date': datetime(2026, 3, 29),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5)
}

# Definition du DAG
with DAG(
    dag_id='pipeline_collecte_offres',
    default_args=default_args,
    description='Collecte quotidienne des offres emploi Data',
    schedule_interval='0 8 * * *',  # Tous les jours a 8h
    catchup=False,
    tags=['collecte', 'scraping', 'bronze']
) as dag:

    # Task 1 : France-Travail
    task_france_travail = PythonOperator(
        task_id='scraper_france_travail',
        python_callable=run_france_travail,
        doc_md="Collecte les offres depuis l'API France-Travail"
    )

    # Task 2 : Adzuna
    task_adzuna = PythonOperator(
        task_id='scraper_adzuna',
        python_callable=run_adzuna,
        doc_md="Collecte les offres depuis l'API Adzuna"
    )

    # Task 3 : Emploi.ma
    task_emploima = PythonOperator(
        task_id='scraper_emploima',
        python_callable=run_emploima,
        doc_md="Collecte les offres depuis Emploi.ma"
    )

    # Les 3 scrapers tournent en parallele
    [task_france_travail, task_adzuna, task_emploima]