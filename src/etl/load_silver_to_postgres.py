"""
=============================================================
  Job Intelligent — Phase 3
  Chargement Silver (Parquet MinIO) → PostgreSQL (raw_offres)
=============================================================
"""

import boto3
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from io import BytesIO
import logging
import math

MINIO_ENDPOINT = "http://minio:9000"
MINIO_ACCESS   = "minioadmin"
MINIO_SECRET   = "minioadmin123"
BUCKET_SILVER  = "silver"
SILVER_PATH    = "unified/"

PG_HOST     = "postgres_db"
PG_PORT     = 5432
PG_USER     = "admin"
PG_PASSWORD = "admin123"
PG_DB       = "dwh_job_intelligent"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("load_silver")

# ─── Helpers de nettoyage ─────────────────────────────────────────────────────

def safe_str(val, max_len=None):
    """Convertit en string propre, tronque si nécessaire."""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    s = str(val).strip()
    if s in ('None', 'nan', 'NaN', ''):
        return None
    if max_len and len(s) > max_len:
        s = s[:max_len]
    return s

def safe_int(val):
    """Convertit en entier PostgreSQL INT (32 bits)."""
    INT_MAX = 2_147_483_647
    INT_MIN = -2_147_483_648
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    try:
        v = int(float(val))
        if v > INT_MAX or v < INT_MIN:
            return None
        return v
    except Exception:
        return None

def safe_float(val):
    """Convertit en float, retourne None si invalide."""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    try:
        return float(val)
    except Exception:
        return None

def safe_timestamp(val):
    """Convertit en timestamp string pour PostgreSQL."""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    try:
        return pd.to_datetime(val).isoformat()
    except Exception:
        return safe_str(val, max_len=50)

# ─── Connexion MinIO ──────────────────────────────────────────────────────────

def get_minio_client():
    return boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS,
        aws_secret_access_key=MINIO_SECRET,
        region_name='us-east-1'
    )

# ─── Lire les Parquet depuis MinIO ───────────────────────────────────────────

def read_silver_parquet():
    client = get_minio_client()
    log.info(f"Listage des fichiers dans s3://{BUCKET_SILVER}/{SILVER_PATH}")

    response = client.list_objects_v2(
        Bucket=BUCKET_SILVER,
        Prefix=SILVER_PATH
    )

    parquet_files = [
        obj['Key'] for obj in response.get('Contents', [])
        if obj['Key'].endswith('.parquet')
    ]
    log.info(f"Fichiers Parquet trouvés : {len(parquet_files)}")

    dfs = []
    for key in parquet_files:
        log.info(f"  Lecture : {key}")
        obj = client.get_object(Bucket=BUCKET_SILVER, Key=key)
        df  = pd.read_parquet(BytesIO(obj['Body'].read()))
        dfs.append(df)

    if not dfs:
        raise ValueError("Aucun fichier Parquet trouvé dans Silver/unified/")

    df_all = pd.concat(dfs, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=['offre_id'])
    log.info(f"Total lignes lues : {len(df_all)}")
    return df_all

# ─── Créer la table raw_offres ───────────────────────────────────────────────

def create_raw_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            DROP TABLE IF EXISTS raw_offres;
            CREATE TABLE raw_offres (
                offre_id          VARCHAR(200),
                titre             VARCHAR(500),
                type_contrat      VARCHAR(50),
                experience        VARCHAR(100),
                description       TEXT,
                ville             VARCHAR(200),
                region            VARCHAR(200),
                code_postal       VARCHAR(20),
                latitude          FLOAT,
                longitude         FLOAT,
                pays              VARCHAR(50),
                entreprise        VARCHAR(300),
                secteur           VARCHAR(200),
                taille_entreprise VARCHAR(100),
                salaire_libelle   VARCHAR(300),
                salaire_min       INT,
                salaire_max       INT,
                rome_code         VARCHAR(20),
                rome_libelle      VARCHAR(200),
                url_offre         TEXT,
                date_creation     TIMESTAMP,
                source            VARCHAR(50)
            );
        """)
        conn.commit()
        log.info("Table raw_offres créée avec les bons types.")

# ─── Nettoyer et charger ──────────────────────────────────────────────────────

def load_to_postgres(df):
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASSWORD,
        dbname=PG_DB
    )

    create_raw_table(conn)

    COLUMNS = [
        'offre_id', 'titre', 'type_contrat', 'experience',
        'description', 'ville', 'region', 'code_postal',
        'latitude', 'longitude', 'pays',
        'entreprise', 'secteur', 'taille_entreprise',
        'salaire_libelle', 'salaire_min', 'salaire_max',
        'rome_code', 'rome_libelle',
        'url_offre', 'date_creation', 'source'
    ]

    # Ajouter colonnes manquantes
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    df = df[COLUMNS].copy()

    # Nettoyage typé colonne par colonne
    rows = []
    for record in df.to_dict('records'):
        row = (
            safe_str(record.get('offre_id'),          200),
            safe_str(record.get('titre'),              500),
            safe_str(record.get('type_contrat'),        50),
            safe_str(record.get('experience'),         100),
            safe_str(record.get('description')),           # TEXT — pas de limite
            safe_str(record.get('ville'),              200),
            safe_str(record.get('region'),             200),
            safe_str(record.get('code_postal'),         20),
            safe_float(record.get('latitude')),
            safe_float(record.get('longitude')),
            safe_str(record.get('pays'),                50),
            safe_str(record.get('entreprise'),         300),
            safe_str(record.get('secteur'),            200),
            safe_str(record.get('taille_entreprise'),  100),
            safe_str(record.get('salaire_libelle'),    300),
            safe_int(record.get('salaire_min')),
            safe_int(record.get('salaire_max')),
            safe_str(record.get('rome_code'),           20),
            safe_str(record.get('rome_libelle'),       200),
            safe_str(record.get('url_offre')),             # TEXT — pas de limite
            safe_timestamp(record.get('date_creation')),
            safe_str(record.get('source'),              50),
        )
        rows.append(row)

    with conn.cursor() as cur:
        execute_values(
            cur,
            f"INSERT INTO raw_offres ({', '.join(COLUMNS)}) VALUES %s",
            rows,
            page_size=100
        )
        conn.commit()
        log.info(f"{len(rows)} lignes insérées dans raw_offres.")

    # Vérification
    with conn.cursor() as cur:
        cur.execute("""
            SELECT source, COUNT(*) 
            FROM raw_offres 
            GROUP BY source 
            ORDER BY source;
        """)
        log.info("Distribution par source :")
        for source, count in cur.fetchall():
            log.info(f"  {source} : {count} offres")

        cur.execute("SELECT COUNT(*) FROM raw_offres;")
        total = cur.fetchone()[0]
        log.info(f"Total raw_offres : {total} lignes")

    conn.close()
    return len(rows)

# ─── Point d'entrée ───────────────────────────────────────────────────────────

def run():
    log.info("=" * 50)
    log.info("CHARGEMENT SILVER → POSTGRESQL")
    log.info("=" * 50)
    try:
        df    = read_silver_parquet()
        count = load_to_postgres(df)
        log.info("=" * 50)
        log.info(f"SUCCÈS — {count} offres dans raw_offres")
        log.info("=" * 50)
    except Exception as e:
        log.error(f"Erreur : {e}", exc_info=True)
        raise

if __name__ == "__main__":
    run()
