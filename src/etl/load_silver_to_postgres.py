"""
=============================================================
  Job Intelligent — Phase 3
  Chargement Silver (Parquet MinIO) → PostgreSQL
  - raw_offres         (offres nettoyées)
  - dim_competence     (compétences extraites automatiquement)
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
BUCKET_GOLD    = "gold"
SILVER_PATH    = "unified/"
COMPETENCES_PATH = "competences/"

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

# ─── Lire les Parquet offres depuis MinIO ─────────────────────────────────────

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

# ─── Lire les compétences depuis MinIO ───────────────────────────────────────

def read_competences_parquet():
    """Lire le fichier compétences généré par silver_transform."""
    client = get_minio_client()
    log.info(f"Lecture compétences depuis s3://{BUCKET_SILVER}/{COMPETENCES_PATH}")

    response = client.list_objects_v2(
        Bucket=BUCKET_SILVER,
        Prefix=COMPETENCES_PATH
    )

    parquet_files = [
        obj['Key'] for obj in response.get('Contents', [])
        if obj['Key'].endswith('.parquet')
    ]

    if not parquet_files:
        log.warning("Aucun fichier compétences trouvé dans Silver/competences/")
        return None

    obj = client.get_object(Bucket=BUCKET_SILVER, Key=parquet_files[0])
    df  = pd.read_parquet(BytesIO(obj['Body'].read()))
    log.info(f"{len(df)} compétences lues depuis Silver")
    return df

# ─── Créer la table raw_offres ───────────────────────────────────────────────

def create_raw_table(conn):
    with conn.cursor() as cur:
        # Vérifier si la table existe déjà
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'raw_offres'
            );
        """)
        exists = cur.fetchone()[0]

        if exists:
            # Table existe → insertion incrémentale (ON CONFLICT DO NOTHING)
            log.info("Table raw_offres existe — insertion incrémentale activée.")
        else:
            # Table n'existe pas → créer
            cur.execute("""
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
            log.info("Table raw_offres créée.")

        conn.commit()

# ─── Nettoyer et charger raw_offres ──────────────────────────────────────────

def load_to_postgres(df, conn):
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

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    df = df[COLUMNS].copy()

    rows = []
    for record in df.to_dict('records'):
        row = (
            safe_str(record.get('offre_id'),          200),
            safe_str(record.get('titre'),              500),
            safe_str(record.get('type_contrat'),        50),
            safe_str(record.get('experience'),         100),
            safe_str(record.get('description')),
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
            safe_str(record.get('url_offre')),
            safe_timestamp(record.get('date_creation')),
            safe_str(record.get('source'),              50),
        )
        rows.append(row)

    with conn.cursor() as cur:
        execute_values(
            cur,
            f"INSERT INTO raw_offres ({', '.join(COLUMNS)}) VALUES %s ON CONFLICT (offre_id) DO NOTHING",
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

    return len(rows)

# ─── NOUVEAU : Charger dim_competence ────────────────────────────────────────

def load_competences_to_postgres(df_competences, conn):
    """
    Vider et recharger dim_competence depuis le Parquet Silver.
    La colonne nb_offres n'est pas dans dim_competence (schéma étoile),
    elle sert juste de métrique de détection.
    """
    if df_competences is None or df_competences.empty:
        log.warning("Aucune compétence à charger — dim_competence reste inchangée.")
        return 0

    with conn.cursor() as cur:
        # Vider la table proprement (RESTART IDENTITY remet l'auto-incrément à 1)
        cur.execute("TRUNCATE TABLE dim_competence RESTART IDENTITY;")
        conn.commit()
        log.info("Table dim_competence vidée.")

        rows = []
        for _, row in df_competences.iterrows():
            rows.append((
                safe_int(row.get('competence_id')),
                safe_str(row.get('nom'),       100),
                safe_str(row.get('categorie'),  50),
            ))

        execute_values(
            cur,
            "INSERT INTO dim_competence (competence_id, nom, categorie) VALUES %s",
            rows,
            page_size=50
        )
        conn.commit()
        log.info(f"✅ {len(rows)} compétences chargées dans dim_competence.")

    # Vérification par catégorie
    with conn.cursor() as cur:
        cur.execute("""
            SELECT categorie, COUNT(*) AS nb
            FROM dim_competence
            GROUP BY categorie
            ORDER BY nb DESC;
        """)
        log.info("Distribution par catégorie :")
        for categorie, nb in cur.fetchall():
            log.info(f"  {categorie:20s} : {nb} compétences")

    return len(rows)

# ─── GOLD : Agrégats prêts pour Power BI ─────────────────────────────────────

def save_gold_layer(df):
    """
    Crée et sauvegarde la couche Gold dans MinIO.
    Contient des agrégats pré-calculés prêts pour Power BI.

    Fichiers générés :
      gold/offres_par_source/data.parquet      — nb offres par source + pays
      gold/offres_par_contrat/data.parquet     — nb offres par type contrat
      gold/offres_par_competence/data.parquet  — nb offres par compétence
      gold/offres_par_ville/data.parquet       — top villes
      gold/salaires/data.parquet               — stats salaires par source
      gold/offres_par_mois/data.parquet        — évolution temporelle
    """
    client = get_minio_client()

    # Créer le bucket Gold si nécessaire
    try:
        client.head_bucket(Bucket=BUCKET_GOLD)
    except Exception:
        client.create_bucket(Bucket=BUCKET_GOLD)
        log.info("Bucket 'gold' créé.")

    def upload_gold(df_gold, key, label):
        """Helper : sauvegarder un DataFrame Parquet dans Gold."""
        buffer = BytesIO()
        df_gold.to_parquet(buffer, index=False)
        buffer.seek(0)
        data = buffer.getvalue()
        client.put_object(
            Bucket=BUCKET_GOLD,
            Key=key,
            Body=data,
            ContentLength=len(data),
            ContentType='application/octet-stream'
        )
        log.info(f"  ✅ Gold/{label} — {len(df_gold)} lignes")

    log.info("=== Génération couche Gold ===")

    # ── 1. Offres par source et pays ──────────────────────────────────────────
    gold_source = df.groupby(
        ['source', 'pays'], dropna=False
    ).agg(nb_offres=('offre_id', 'count')).reset_index()
    gold_source['pays'] = gold_source['pays'].fillna('Non renseigné')
    gold_source['source'] = gold_source['source'].fillna('inconnu')
    upload_gold(gold_source, 'offres_par_source/data.parquet', 'offres_par_source')

    # ── 2. Offres par type de contrat ─────────────────────────────────────────
    gold_contrat = df.groupby(
        ['type_contrat'], dropna=False
    ).agg(nb_offres=('offre_id', 'count')).reset_index()
    gold_contrat['type_contrat'] = gold_contrat['type_contrat'].fillna('Non renseigné')
    gold_contrat = gold_contrat.sort_values('nb_offres', ascending=False)
    upload_gold(gold_contrat, 'offres_par_contrat/data.parquet', 'offres_par_contrat')

    # ── 3. Offres par ville (top 30) ──────────────────────────────────────────
    gold_ville = df.groupby(
        ['ville', 'pays'], dropna=False
    ).agg(nb_offres=('offre_id', 'count')).reset_index()
    gold_ville = gold_ville.dropna(subset=['ville'])
    gold_ville = gold_ville.sort_values('nb_offres', ascending=False).head(30)
    upload_gold(gold_ville, 'offres_par_ville/data.parquet', 'offres_par_ville')

    # ── 4. Stats salaires par source ──────────────────────────────────────────
    df_sal = df[df['salaire_min'].notna() & (df['salaire_min'] > 0)]
    if not df_sal.empty:
        gold_sal = df_sal.groupby('source').agg(
            salaire_min_moyen=('salaire_min', 'mean'),
            salaire_max_moyen=('salaire_max', 'mean'),
            nb_offres_avec_salaire=('offre_id', 'count')
        ).reset_index()
        gold_sal = gold_sal.round(0)
        upload_gold(gold_sal, 'salaires/data.parquet', 'salaires')
    else:
        log.warning("  ⚠ Pas de données salaires — Gold/salaires ignoré")

    # ── 5. Évolution temporelle par mois ──────────────────────────────────────
    df_dates = df.copy()
    df_dates['date_creation'] = pd.to_datetime(df_dates['date_creation'], errors='coerce')
    df_dates = df_dates.dropna(subset=['date_creation'])
    df_dates['annee_mois'] = df_dates['date_creation'].dt.to_period('M').astype(str)
    gold_mois = df_dates.groupby(
        ['annee_mois', 'source']
    ).agg(nb_offres=('offre_id', 'count')).reset_index()
    gold_mois = gold_mois.sort_values('annee_mois')
    upload_gold(gold_mois, 'offres_par_mois/data.parquet', 'offres_par_mois')

    # ── 6. Top secteurs ───────────────────────────────────────────────────────
    gold_secteur = df.groupby(
        ['secteur'], dropna=False
    ).agg(nb_offres=('offre_id', 'count')).reset_index()
    gold_secteur = gold_secteur.dropna(subset=['secteur'])
    gold_secteur = gold_secteur.sort_values('nb_offres', ascending=False).head(20)
    upload_gold(gold_secteur, 'offres_par_secteur/data.parquet', 'offres_par_secteur')

    log.info("=== Couche Gold complète ✅ ===")


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def run():
    log.info("=" * 60)
    log.info("CHARGEMENT SILVER → POSTGRESQL")
    log.info("=" * 60)

    # Connexion unique réutilisée
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASSWORD,
        dbname=PG_DB
    )

    try:
        # ── 1. Offres ──────────────────────────────────────────────────────
        log.info("--- Chargement raw_offres ---")
        df_offres = read_silver_parquet()
        count_offres = load_to_postgres(df_offres, conn)
        log.info(f"✅ raw_offres : {count_offres} lignes")

        # ── 2. Compétences ─────────────────────────────────────────────────
        log.info("--- Chargement dim_competence ---")
        df_competences = read_competences_parquet()
        count_comp = load_competences_to_postgres(df_competences, conn)
        log.info(f"✅ dim_competence : {count_comp} compétences")

        # ── 3. Couche Gold ─────────────────────────────────────────────────
        log.info("--- Génération couche Gold (MinIO) ---")
        save_gold_layer(df_offres)

        log.info("=" * 60)
        log.info(f"SUCCÈS TOTAL — {count_offres} offres + {count_comp} compétences + Gold ✅")
        log.info("=" * 60)

    except Exception as e:
        log.error(f"Erreur : {e}", exc_info=True)
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    run()
