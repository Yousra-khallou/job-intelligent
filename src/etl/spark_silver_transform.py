"""
=============================================================
  Job Intelligent — Phase 2 : Couche Silver
  Transformation PySpark : Bronze (JSON) → Silver (Parquet)
  
  Sources traitées :
    - france_travail  (API OAuth2)
    - adzuna          (API officielle)
    - emploima        (Scraping HTML)
=============================================================
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, FloatType,
    IntegerType, TimestampType
)
import logging
import sys

# ─── Configuration ────────────────────────────────────────────────────────────

MINIO_ENDPOINT  = "http://minio:9000"        # nom service Docker
MINIO_ACCESS    = "minioadmin"
MINIO_SECRET    = "minioadmin123"

BUCKET_BRONZE   = "bronze"
BUCKET_SILVER   = "silver"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("silver_transform")


# ─── Initialisation Spark ──────────────────────────────────────────────────────

def create_spark_session() -> SparkSession:
    """Crée une SparkSession avec accès S3/MinIO."""
    spark = (
    SparkSession.builder
    .appName("JobIntelligent_Silver_Transform")
    .master("spark://spark-master:7077")
    # Remplace spark.jars.packages par spark.jars (JARs locaux)
    # NOUVEAU — bundle remplace les 3 fichiers séparés
    .config("spark.jars",
    "/opt/spark/extra-jars/hadoop-aws-3.3.4.jar,"
    "/opt/spark/extra-jars/aws-java-sdk-bundle-1.11.1026.jar")
    # Reste de la config MinIO (inchangé)
    .config("spark.hadoop.fs.s3a.endpoint",          "http://minio:9000")
    .config("spark.hadoop.fs.s3a.access.key",        "minioadmin")
    .config("spark.hadoop.fs.s3a.secret.key",        "minioadmin123")
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .config("spark.hadoop.fs.s3a.impl",
            "org.apache.hadoop.fs.s3a.S3AFileSystem")
    .config("spark.hadoop.fs.s3a.aws.credentials.provider",
            "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")
    .config("spark.sql.shuffle.partitions", "4")
    .config("spark.sql.adaptive.enabled",   "true")
    .getOrCreate()
)
    spark.sparkContext.setLogLevel("WARN")
    log.info("SparkSession créée avec succès.")
    return spark


# ─── Helpers communs ───────────────────────────────────────────────────────────

def clean_text(col_name: str) -> F.Column:
    """Nettoie une colonne texte : trim + suppression des espaces multiples."""
    return F.trim(F.regexp_replace(F.col(col_name), r"\s+", " "))


def normalize_contract(col_name: str) -> F.Column:
    """Normalise les types de contrat vers un vocabulaire commun."""
    c = F.upper(F.trim(F.col(col_name)))
    return (
        F.when(c.isin("CDI", "PERMANENT", "FULL_TIME", "FULL-TIME"), F.lit("CDI"))
         .when(c.isin("CDD", "TEMPORARY", "CONTRACT"),               F.lit("CDD"))
         .when(c.isin("STAGE", "INTERNSHIP", "INTERN"),              F.lit("Stage"))
         .when(c.isin("ALTERNANCE", "APPRENTISSAGE"),                F.lit("Alternance"))
         .when(c.isin("FREELANCE", "SELF_EMPLOYED", "CONTRACTOR"),   F.lit("Freelance"))
         .otherwise(F.lit("Autre"))
    )


def extract_salary(libelle_col: str):
    """
    Extrait salaire_min et salaire_max depuis une colonne texte libre.
    Ex: '30000 - 45000 EUR' → (30000, 45000)
    """
    pattern = r"(\d[\d\s]*)\s*[-–]\s*(\d[\d\s]*)"
    min_sal = F.regexp_extract(F.col(libelle_col), pattern, 1)
    max_sal = F.regexp_extract(F.col(libelle_col), pattern, 2)
    return (
        F.when(min_sal != "", F.regexp_replace(min_sal, r"\s", "").cast(IntegerType())).otherwise(None),
        F.when(max_sal != "", F.regexp_replace(max_sal, r"\s", "").cast(IntegerType())).otherwise(None),
    )


def deduplicate(df, key_col: str = "offre_id"):
    """
    Dédoublonne par offre_id en gardant la ligne la plus récente.
    Utile si le DAG a tourné plusieurs fois.
    """
    from pyspark.sql.window import Window
    w = Window.partitionBy(key_col).orderBy(F.col("date_creation").desc())
    return (
        df.withColumn("_rn", F.row_number().over(w))
          .filter(F.col("_rn") == 1)
          .drop("_rn")
    )


# ─── Transformation France-Travail ────────────────────────────────────────────

def transform_france_travail(spark: SparkSession) -> int:
    """
    Lit tous les JSON france_travail du bucket Bronze,
    normalise et écrit en Parquet dans Silver.
    Retourne le nombre de lignes écrites.
    """
    log.info("=== France-Travail : début transformation ===")

    path_in  = f"s3a://{BUCKET_BRONZE}/france_travail/*.json"
    path_out = f"s3a://{BUCKET_SILVER}/france_travail/"

    df_raw = spark.read.option("multiline", "true").json(path_in)

    # AJOUTER CES 2 LIGNES — exploser le tableau offres
    from pyspark.sql.functions import explode
    df_raw = df_raw.select(explode("offres").alias("o"), "source").select("o.*", "source")

    log.info(f"France-Travail : {df_raw.count()} lignes brutes lues.")

    sal_min, sal_max = extract_salary("salaire.libelle")

    df_silver = (
        df_raw
        .select(
            F.col("id")                              .alias("offre_id"),
            clean_text("intitule")                   .alias("titre"),
            F.col("typeContrat")                     .alias("type_contrat_raw"),
            F.col("experienceLibelle")               .alias("experience"),
            F.col("description")                     .alias("description"),
            F.col("lieuTravail.libelle")             .alias("ville"),
            F.col("lieuTravail.codePostal")          .alias("code_postal"),
            F.col("lieuTravail.latitude")            .cast(FloatType()).alias("latitude"),
            F.col("lieuTravail.longitude")           .cast(FloatType()).alias("longitude"),
            F.col("entreprise.nom")                  .alias("entreprise"),
            F.col("secteurActiviteLibelle")          .alias("secteur"),
            F.col("trancheEffectifEtab")             .alias("taille_entreprise"),
            F.col("salaire.libelle")                 .alias("salaire_libelle"),
            sal_min                                  .alias("salaire_min"),
            sal_max                                  .alias("salaire_max"),
            F.col("romeCode")                        .alias("rome_code"),
            F.col("romeLibelle")                     .alias("rome_libelle"),
            F.col("origineOffre.urlOrigine")         .alias("url_offre"),
            F.to_timestamp("dateCreation")           .alias("date_creation"),
            F.lit("france_travail")                  .alias("source"),
            F.lit("France")                          .alias("pays"),
        )
        # Normalisation contrat
        .withColumn("type_contrat", normalize_contract("type_contrat_raw"))
        .drop("type_contrat_raw")
        # Filtres qualité
        .filter(F.col("offre_id").isNotNull())
        .filter(F.col("titre").isNotNull())
        .filter(F.length(F.col("titre")) > 3)
        # Dédoublonnage
    )

    df_silver = deduplicate(df_silver)

    count = df_silver.count()
    log.info(f"France-Travail : {count} lignes après nettoyage.")

    (
        df_silver
        .write
        .mode("overwrite")
        .partitionBy("source")
        .parquet(path_out)
    )
    log.info(f"France-Travail : écrit dans {path_out}")
    return count


# ─── Transformation Adzuna ────────────────────────────────────────────────────

def transform_adzuna(spark: SparkSession) -> int:
    """
    Lit tous les JSON adzuna du bucket Bronze,
    normalise et écrit en Parquet dans Silver.
    """
    log.info("=== Adzuna : début transformation ===")

    path_in  = f"s3a://{BUCKET_BRONZE}/adzuna/*.json"
    path_out = f"s3a://{BUCKET_SILVER}/adzuna/"

    df_raw = spark.read.option("multiline", "true").json(path_in)

    # AJOUTER CES 2 LIGNES
    from pyspark.sql.functions import explode
    df_raw = df_raw.select(explode("offres").alias("o"), "source").select("o.*", "source")

    log.info(f"Adzuna : {df_raw.count()} lignes brutes lues.")
    

    df_silver = (
        df_raw
        .select(
            F.col("id")                              .alias("offre_id"),
            clean_text("title")                      .alias("titre"),
            F.col("contract_type")                   .alias("type_contrat_raw"),
            F.col("description")                     .alias("description"),
            F.col("location.display_name")           .alias("ville"),
            F.col("location.area").getItem(0)        .alias("region"),
            F.col("latitude")                        .cast(FloatType()).alias("latitude"),
            F.col("longitude")                       .cast(FloatType()).alias("longitude"),
            F.col("company.display_name")            .alias("entreprise"),
            F.col("category.label")                  .alias("secteur"),
            F.col("salary_min")                      .cast(IntegerType()).alias("salaire_min"),
            F.col("salary_max")                      .cast(IntegerType()).alias("salaire_max"),
            F.col("redirect_url")                    .alias("url_offre"),
            F.to_timestamp("created")                .alias("date_creation"),
            F.lit("adzuna")                          .alias("source"),
            # Pays depuis le code de pays dans l'URL ou à déduire
            F.lit("France")                          .alias("pays"),
        )
        .withColumn("type_contrat", normalize_contract("type_contrat_raw"))
        .drop("type_contrat_raw")
        # Champs absents dans Adzuna : on crée des colonnes vides pour uniformité
        .withColumn("code_postal",      F.lit(None).cast(StringType()))
        .withColumn("taille_entreprise",F.lit(None).cast(StringType()))
        .withColumn("salaire_libelle",  F.lit(None).cast(StringType()))
        .withColumn("rome_code",        F.lit(None).cast(StringType()))
        .withColumn("rome_libelle",     F.lit(None).cast(StringType()))
        .withColumn("experience",       F.lit(None).cast(StringType()))
        # Filtres qualité
        .filter(F.col("offre_id").isNotNull())
        .filter(F.col("titre").isNotNull())
        .filter(F.length(F.col("titre")) > 3)
    )

    df_silver = deduplicate(df_silver)

    count = df_silver.count()
    log.info(f"Adzuna : {count} lignes après nettoyage.")

    (
        df_silver
        .write
        .mode("overwrite")
        .partitionBy("source")
        .parquet(path_out)
    )
    log.info(f"Adzuna : écrit dans {path_out}")
    return count


# ─── Transformation Emploi.ma ─────────────────────────────────────────────────

def transform_emploima(spark: SparkSession) -> int:
    log.info("=== Emploi.ma : début transformation ===")

    path_in  = f"s3a://{BUCKET_BRONZE}/emploima/*.json"
    path_out = f"s3a://{BUCKET_SILVER}/emploima/"

    df_raw = spark.read.option("multiline", "true").json(path_in)
    log.info(f"Emploi.ma : {df_raw.count()} fichiers bruts lus.")

    # ← AJOUT : exploser le tableau offres
    df_exploded = df_raw.select(F.explode("offres").alias("o")).select("o.*")
    log.info(f"Emploi.ma : {df_exploded.count()} offres après explosion.")

    df_silver = (
        df_exploded
        .select(
            F.md5(F.concat_ws("|", F.col("titre"), F.col("entreprise"), F.col("url")))
                                                     .alias("offre_id"),
            clean_text("titre")                      .alias("titre"),
            F.col("type_contrat")                    .alias("type_contrat_raw"),
            F.col("experience")                      .alias("experience"),
            F.lit(None).cast(StringType())           .alias("description"),
            F.col("region")                          .alias("ville"),
            F.col("region")                          .alias("region"),
            F.col("entreprise")                      .alias("entreprise"),
            F.col("competences")                     .alias("secteur"),
            F.col("url")                             .alias("url_offre"),
            F.to_timestamp("date_publication", "dd.MM.yyyy").alias("date_creation"),
            F.lit("emploima")                        .alias("source"),
            F.col("pays")                            .alias("pays"),
        )
        .withColumn("type_contrat", normalize_contract("type_contrat_raw"))
        .drop("type_contrat_raw")
        .withColumn("code_postal",      F.lit(None).cast(StringType()))
        .withColumn("latitude",         F.lit(None).cast(FloatType()))
        .withColumn("longitude",        F.lit(None).cast(FloatType()))
        .withColumn("taille_entreprise",F.lit(None).cast(StringType()))
        .withColumn("salaire_libelle",  F.lit(None).cast(StringType()))
        .withColumn("salaire_min",      F.lit(None).cast(IntegerType()))
        .withColumn("salaire_max",      F.lit(None).cast(IntegerType()))
        .withColumn("rome_code",        F.lit(None).cast(StringType()))
        .withColumn("rome_libelle",     F.lit(None).cast(StringType()))
        .filter(F.col("offre_id").isNotNull())
        .filter(F.col("titre").isNotNull())
        .filter(F.length(F.col("titre")) > 3)
    )

    df_silver = deduplicate(df_silver)
    count = df_silver.count()
    log.info(f"Emploi.ma : {count} lignes après nettoyage.")

    df_silver.write.mode("overwrite").partitionBy("source").parquet(path_out)
    log.info(f"Emploi.ma : écrit dans {path_out}")
    return count


# ─── Union Silver consolidée ──────────────────────────────────────────────────

def build_silver_unified(spark: SparkSession):
    log.info("=== Construction table Silver unifiée ===")

    COLUMNS_ORDER = [
        "offre_id", "titre", "type_contrat", "experience",
        "description", "ville", "region", "code_postal",
        "latitude", "longitude", "pays",
        "entreprise", "secteur", "taille_entreprise",
        "salaire_libelle", "salaire_min", "salaire_max",
        "rome_code", "rome_libelle",
        "url_offre", "date_creation", "source",
    ]

    dfs = []
    for source, path in [
        ("france_travail", f"s3a://{BUCKET_SILVER}/france_travail/"),
        ("adzuna",         f"s3a://{BUCKET_SILVER}/adzuna/"),
        ("emploima",       f"s3a://{BUCKET_SILVER}/emploima/"),
    ]:
        try:
            df = spark.read.parquet(path)
            # Ajouter colonnes manquantes
            for col in COLUMNS_ORDER:
                if col not in df.columns:
                    df = df.withColumn(col, F.lit(None).cast(StringType()))
            dfs.append(df.select(*COLUMNS_ORDER))
            log.info(f"{source} : chargé depuis Silver.")
        except Exception as e:
            log.warning(f"{source} absent de Silver, ignoré : {e}")

    if not dfs:
        log.warning("Aucune source Silver disponible.")
        return 0

    df_all = dfs[0]
    for df in dfs[1:]:
        df_all = df_all.union(df)

    # Dédoublonnage inter-sources
    from pyspark.sql.window import Window
    df_all = (
        df_all
        .withColumn("_titre_norm",
            F.lower(F.regexp_replace(F.col("titre"), r"[^a-zA-Z0-9\u00C0-\u024F ]", "")))
        .withColumn("_dup_key",
            F.md5(F.concat_ws("|", F.col("_titre_norm"), F.col("entreprise"), F.col("ville"))))
    )
    priority = F.when(F.col("source") == "france_travail", 1) \
                .when(F.col("source") == "adzuna",          2) \
                .otherwise(3)
    w = Window.partitionBy("_dup_key").orderBy(priority)
    df_all = (
        df_all
        .withColumn("_rn", F.row_number().over(w))
        .filter(F.col("_rn") == 1)
        .drop("_rn", "_titre_norm", "_dup_key")
    )

    total = df_all.count()
    log.info(f"Table unifiée : {total} offres.")

    df_all.write.mode("overwrite").partitionBy("source", "pays").parquet(
        f"s3a://{BUCKET_SILVER}/unified/"
    )
    log.info(f"Table unifiée écrite dans s3a://{BUCKET_SILVER}/unified/")

    log.info("--- Distribution par source ---")
    df_all.groupBy("source").count().show()

    return total

# ─── Rapport qualité (optionnel) ──────────────────────────────────────────────

def quality_report(spark: SparkSession):
    """Affiche un rapport de qualité sur la table Silver unifiée."""
    log.info("=== Rapport qualité Silver ===")
    df = spark.read.parquet(f"s3a://{BUCKET_SILVER}/unified/")

    cols_to_check = ["titre", "entreprise", "ville", "type_contrat", "date_creation"]
    for col in cols_to_check:
        nulls = df.filter(F.col(col).isNull()).count()
        total = df.count()
        pct   = round(100 * nulls / total, 1) if total > 0 else 0
        status = "✓" if pct < 10 else "⚠"
        log.info(f"  {status} {col:20s} : {nulls:4d} nulls ({pct}%)")


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def run():
    spark = create_spark_session()
    results = {}

    try:
        # France-Travail
        try:
            results["france_travail"] = transform_france_travail(spark)
        except Exception as e:
            log.warning(f"France-Travail ignoré : {e}")
            results["france_travail"] = 0

        # Adzuna
        try:
            results["adzuna"] = transform_adzuna(spark)
        except Exception as e:
            log.warning(f"Adzuna ignoré : {e}")
            results["adzuna"] = 0

        # Emploi.ma
        try:
            results["emploima"] = transform_emploima(spark)
        except Exception as e:
            log.warning(f"Emploi.ma ignoré : {e}")
            results["emploima"] = 0

        # Table unifiée (seulement si au moins une source a des données)
        if any(v > 0 for v in results.values()):
            results["unified"] = build_silver_unified(spark)
            quality_report(spark)
        else:
            log.warning("Aucune source disponible — table unifiée non créée.")

        log.info("=" * 50)
        log.info("RÉSUMÉ PHASE 2 — COUCHE SILVER")
        log.info("=" * 50)
        for src, cnt in results.items():
            log.info(f"  {src:20s} : {cnt} offres")
        log.info("=" * 50)

    except Exception as e:
        log.error(f"Erreur fatale : {e}", exc_info=True)
        sys.exit(1)
    finally:
        spark.stop()
        log.info("SparkSession arrêtée.")

if __name__ == "__main__":
    run()
