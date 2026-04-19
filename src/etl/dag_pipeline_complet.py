"""
=============================================================
  Job Intelligent — DAG Pipeline Complet
  
  Pipeline automatique quotidien :
  1. Collecte (3 scrapers en parallèle) → MinIO Bronze
  2. Transformation pandas → MinIO Silver
  3. Chargement Silver → PostgreSQL raw_offres
  4. dbt run → dimensions + fact_offres
=============================================================
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys
import logging

sys.path.insert(0, '/opt/airflow/dags')

log = logging.getLogger(__name__)

default_args = {
    'owner': 'job_intelligent',
    'depends_on_past': False,
    'start_date': datetime(2026, 3, 29),
    'retries': 1,
    'retry_delay': timedelta(minutes=5)
}

# ─── PHASE 2 : Transformation Silver (pandas) ─────────────────────────────────

def run_silver_transform():
    import boto3
    import pandas as pd
    import json
    from io import BytesIO

    minio = boto3.client(
        's3',
        endpoint_url='http://minio:9000',
        aws_access_key_id='minioadmin',
        aws_secret_access_key='minioadmin123',
        region_name='us-east-1'
    )

    sources = {
        'france_travail': 'france_travail/',
        'adzuna':         'adzuna/',
        'emploima':       'emploima/'
    }

    COLS = [
        'offre_id', 'titre', 'type_contrat', 'experience',
        'description', 'ville', 'region', 'code_postal',
        'latitude', 'longitude', 'pays', 'entreprise', 'secteur',
        'taille_entreprise', 'salaire_libelle', 'salaire_min',
        'salaire_max', 'rome_code', 'rome_libelle',
        'url_offre', 'date_creation', 'source'
    ]

    all_dfs = []

    for source, prefix in sources.items():
        log.info(f"=== Traitement {source} ===")

        response = minio.list_objects_v2(Bucket='bronze', Prefix=prefix)
        files = [
            o['Key'] for o in response.get('Contents', [])
            if o['Key'].endswith('.json')
        ]
        log.info(f"{source} : {len(files)} fichiers JSON trouvés")

        dfs = []
        for key in files:
            try:
                obj    = minio.get_object(Bucket='bronze', Key=key)
                data   = json.loads(obj['Body'].read())
                offres = data.get('offres', [])
                if offres:
                    df = pd.json_normalize(offres)
                    df = df.reset_index(drop=True)
                    df['source'] = source
                    dfs.append(df)
            except Exception as e:
                log.warning(f"  Fichier ignoré {key} : {e}")

        if not dfs:
            log.warning(f"{source} : aucune offre trouvée")
            continue

        df_source = pd.concat(dfs, ignore_index=True)
        df_source = df_source.reset_index(drop=True)
        log.info(f"{source} : {len(df_source)} offres brutes")

        # ── Renommage colonnes selon source ──────────────────────────────────
        if source == 'france_travail':
            df_source = df_source.rename(columns={
                'id':                      'offre_id',
                'intitule':                'titre',
                'typeContrat':             'type_contrat',
                'experienceLibelle':       'experience',
                'lieuTravail.libelle':     'ville',
                'lieuTravail.codePostal':  'code_postal',
                'lieuTravail.latitude':    'latitude',
                'lieuTravail.longitude':   'longitude',
                'entreprise.nom':          'entreprise',
                'secteurActiviteLibelle':  'secteur',
                'trancheEffectifEtab':     'taille_entreprise',
                'salaire.libelle':         'salaire_libelle',
                'romeCode':                'rome_code',
                'romeLibelle':             'rome_libelle',
                'origineOffre.urlOrigine': 'url_offre',
                'dateCreation':            'date_creation',
            })
            df_source['pays'] = 'France'

        elif source == 'adzuna':
            df_source = df_source.rename(columns={
                'id':                    'offre_id',
                'title':                 'titre',
                'contract_type':         'type_contrat',
                'location.display_name': 'ville',
                'company.display_name':  'entreprise',
                'category.label':        'secteur',
                'salary_min':            'salaire_min',
                'salary_max':            'salaire_max',
                'redirect_url':          'url_offre',
                'created':               'date_creation',
            })
            df_source['pays'] = 'France'

        elif source == 'emploima':
            df_source = df_source.rename(columns={
                'url':              'url_offre',
                'date_publication': 'date_creation',
            })
            df_source['pays'] = 'Maroc'
            df_source = df_source.loc[:, ~df_source.columns.duplicated()]
            # Génération offre_id sans problème d'index mixtes
            df_source = df_source.reset_index(drop=True)
            df_source['offre_id'] = [
                str(abs(hash(
                    str(row.get('titre', '')) + '|' +
                    str(row.get('entreprise', '')) + '|' +
                    str(row.get('url_offre', ''))
                ))% 999999999)
                for row in df_source.to_dict('records')
            ]

        # ── Ajouter colonnes manquantes ───────────────────────────────────────
        for col in COLS:
            if col not in df_source.columns:
                df_source[col] = None

        df_source = df_source[COLS].copy()
        df_source = df_source.reset_index(drop=True)

        # ── Nettoyage ────────────────────────────────────────────────────────
        df_source['titre'] = df_source['titre'].astype(str).str.strip()
        df_source = df_source[df_source['titre'].notna()]
        df_source = df_source[df_source['titre'] != 'None']
        df_source = df_source[df_source['titre'].str.len() > 3]
        df_source = df_source.drop_duplicates(subset=['offre_id'])
        df_source = df_source.reset_index(drop=True)

        log.info(f"{source} : {len(df_source)} offres après nettoyage")

        # ── Sauvegarder Parquet dans Silver ──────────────────────────────────
        buffer = BytesIO()
        df_source.to_parquet(buffer, index=False)
        buffer.seek(0)
        parquet_bytes = buffer.getvalue()

        minio.put_object(
            Bucket='silver',
            Key=f'{source}/offres.parquet',
            Body=parquet_bytes,
            ContentLength=len(parquet_bytes),
            ContentType='application/octet-stream'
        )
        log.info(f"{source} : écrit dans s3://silver/{source}/offres.parquet")
        all_dfs.append(df_source)

    # ── Table unifiée ─────────────────────────────────────────────────────────
    if all_dfs:
        df_unified = pd.concat(all_dfs, ignore_index=True)
        df_unified = df_unified.reset_index(drop=True)
        df_unified = df_unified.drop_duplicates(subset=['offre_id'])

        buffer = BytesIO()
        df_unified.to_parquet(buffer, index=False)
        buffer.seek(0)
        parquet_bytes = buffer.getvalue()

        minio.put_object(
            Bucket='silver',
            Key='unified/offres.parquet',
            Body=parquet_bytes,
            ContentLength=len(parquet_bytes),
            ContentType='application/octet-stream'
        )
        log.info(f"Unified : {len(df_unified)} offres totales")

        log.info("=== Distribution par source ===")
        for src, cnt in df_unified['source'].value_counts().items():
            log.info(f"  {src} : {cnt} offres")

        log.info("=== Rapport qualité Silver ===")
        for col in ['titre', 'entreprise', 'ville', 'type_contrat', 'date_creation']:
            if col in df_unified.columns:
                nulls  = df_unified[col].isna().sum()
                total  = len(df_unified)
                pct    = round(100 * nulls / total, 1) if total > 0 else 0
                status = "✓" if pct < 10 else "⚠"
                log.info(f"  {status} {col:20s} : {nulls} nulls ({pct}%)")
    else:
        raise Exception("Aucune donnée Silver produite !")


# ─── PHASE 3 : Chargement Silver → PostgreSQL ────────────────────────────────

def run_load_postgres():
    from load_silver_to_postgres import run
    run()


# ─── PHASE 4 : dbt ───────────────────────────────────────────────────────────

def run_dbt():
    import subprocess, os
    # Créer dossier logs dans /tmp (accessible par airflow)
    os.makedirs('/tmp/dbt_logs', exist_ok=True)
    
    result = subprocess.run(
        [
            'dbt', 'run',
            '--project-dir', '/opt/airflow/dbt',
            '--profiles-dir', '/opt/airflow/dbt',
            '--log-path', '/tmp/dbt_logs'
        ],
        capture_output=True, text=True
    )
    log.info(result.stdout)
    if result.returncode != 0:
        log.error(result.stderr)
        raise Exception(f"dbt run échoué : {result.stderr}")
    log.info("dbt run terminé avec succès !")


def run_dbt_test():
    import subprocess, os
    os.makedirs('/tmp/dbt_logs', exist_ok=True)
    
    result = subprocess.run(
        [
            'dbt', 'test',
            '--project-dir', '/opt/airflow/dbt',
            '--profiles-dir', '/opt/airflow/dbt',
            '--log-path', '/tmp/dbt_logs'
        ],
        capture_output=True, text=True
    )
    log.info(result.stdout)
    if result.returncode != 0:
        log.warning("dbt test : certains tests ont échoué")
    log.info("dbt test terminé !")


# ─── DAG ─────────────────────────────────────────────────────────────────────

with DAG(
    dag_id='pipeline_complet_job_intelligent',
    default_args=default_args,
    description='Pipeline complet : Collecte → Silver → PostgreSQL → dbt',
    schedule_interval='0 8 * * *',
    catchup=False,
    tags=['collecte', 'silver', 'dbt', 'pipeline']
) as dag:

    def run_france_travail():
        from scraper_france_travail import run
        run()

    def run_adzuna():
        from scraper_adzuna import run
        run()

    def run_emploima():
        from scraper_emploima import run
        run()

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

    task_silver = PythonOperator(
        task_id='silver_transform',
        python_callable=run_silver_transform
    )

    task_load_postgres = PythonOperator(
        task_id='load_silver_to_postgres',
        python_callable=run_load_postgres
    )

    task_dbt_run = PythonOperator(
        task_id='dbt_run',
        python_callable=run_dbt
    )

    task_dbt_test = PythonOperator(
        task_id='dbt_test',
        python_callable=run_dbt_test
    )

    # ─── Dépendances ──────────────────────────────────────────────────────────
    #
    #  [france_travail] ─┐
    #  [adzuna]          ─┼→ [silver_transform] → [load_postgres] → [dbt_run] → [dbt_test]
    #  [emploima]        ─┘
    #

    [task_france_travail, task_adzuna, task_emploima] >> task_silver
    task_silver >> task_load_postgres
    task_load_postgres >> task_dbt_run
    task_dbt_run >> task_dbt_test
