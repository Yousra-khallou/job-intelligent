"""
salary_predictor.py
===================
Prédiction de salaire pour Job Intelligent
Modèle : Random Forest Regressor (sklearn — pas de dépendance externe)

Pipeline :
  1. Chargement des offres depuis PostgreSQL (raw_offres + joins)
  2. Feature engineering (TF-IDF titre+description, variables catégorielles)
  3. Entraînement sur les offres avec salaire connu
  4. Prédiction sur les offres sans salaire
  5. Sauvegarde du modèle en cache (.pkl)

Placement : src/ml/salary_predictor.py
Auteur    : Job Intelligent — Khallou Yousra
"""

import os
import re
import pickle
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.impute import SimpleImputer

# ─── Configuration ────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Connexion PostgreSQL
DB_CONFIG = {
    "host":     os.getenv("POSTGRES_HOST",     "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", "5433")),
    "dbname":   os.getenv("POSTGRES_DB",       "dwh_job_intelligent"),
    "user":     os.getenv("POSTGRES_USER",     "admin"),
    "password": os.getenv("POSTGRES_PASSWORD", "admin123"),
}

# Chemin de sauvegarde du modèle
CACHE_DIR  = Path(os.getenv("CACHE_DIR", "./cache"))
MODEL_PATH = CACHE_DIR / "salary_model.pkl"
META_PATH  = CACHE_DIR / "salary_model_meta.pkl"

CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ─── 1. Chargement des données ────────────────────────────────────────────────

def load_offres_from_db() -> pd.DataFrame:
    """
    Charge les offres depuis raw_offres avec jointures sur les dimensions.
    Retourne un DataFrame avec toutes les colonnes utiles à la prédiction.
    """
    query = """
        SELECT
            r.offre_id,
            r.titre,
            r.description,
            r.type_contrat,
            r.source,
            r.salaire_min,
            r.salaire_max,
            r.salaire_texte,
            r.date_publication,
            l.ville,
            l.region,
            l.pays,
            e.secteur,
            e.taille AS taille_entreprise
        FROM raw_offres r
        LEFT JOIN dim_lieu      l ON r.lieu_id       = l.lieu_id
        LEFT JOIN dim_entreprise e ON r.entreprise_id = e.entreprise_id
    """
    logger.info("📥 Chargement des offres depuis PostgreSQL…")
    with psycopg2.connect(**DB_CONFIG) as conn:
        df = pd.read_sql(query, conn)
    logger.info(f"   → {len(df)} offres chargées")
    return df


# ─── 2. Feature Engineering ───────────────────────────────────────────────────

# Mots-clés qui boostent le salaire dans les titres Data
SENIOR_KEYWORDS  = r"\b(senior|lead|principal|architect|head|director|chief|expert|sr\.?)\b"
JUNIOR_KEYWORDS  = r"\b(junior|jr\.?|intern|stagiaire|apprenti|débutant)\b"
TECH_MULTIPLIERS = r"\b(spark|kubernetes|kafka|airflow|mlops|llm|gpt|cloud|aws|azure|gcp)\b"


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Construit les features à partir des colonnes brutes.
    """
    df = df.copy()

    # — Cible : salaire mensuel moyen en EUR ——————————————————————————
    df["salaire_cible"] = _extract_salary_target(df)

    # — Texte combiné titre + début de description ————————————————————
    df["texte"] = (
        df["titre"].fillna("") + " " +
        df["description"].fillna("").str[:500]   # 500 chars suffisent pour TF-IDF
    ).str.lower()

    # — Features binaires extraites du titre ——————————————————————————
    df["is_senior"]  = df["titre"].str.lower().str.contains(SENIOR_KEYWORDS,  na=False, regex=True).astype(int)
    df["is_junior"]  = df["titre"].str.lower().str.contains(JUNIOR_KEYWORDS,  na=False, regex=True).astype(int)
    df["has_tech"]   = df["texte"].str.contains(TECH_MULTIPLIERS, na=False, regex=True).astype(int)

    # — Nettoyage catégorielles ———————————————————————————————————————
    df["pays"]          = df["pays"].fillna("inconnu").str.lower().str.strip()
    df["type_contrat"]  = df["type_contrat"].fillna("inconnu").str.lower().str.strip()
    df["source"]        = df["source"].fillna("inconnu").str.lower().str.strip()
    df["secteur"]       = df["secteur"].fillna("inconnu").str.lower().str.strip()
    df["taille_entreprise"] = df["taille_entreprise"].fillna("inconnu").str.lower().str.strip()

    logger.info(f"   → Features construites · {df['salaire_cible'].notna().sum()} offres avec salaire connu")
    return df


def _extract_salary_target(df: pd.DataFrame) -> pd.Series:
    """
    Construit la cible numérique (salaire mensuel EUR) depuis salaire_min / salaire_max / salaire_texte.
    Règles :
      - Si salaire_min ET salaire_max connus → moyenne
      - Si un seul → utiliser celui-là
      - Si valeur > 15 000 → supposé annuel → diviser par 12
      - Sinon → parser salaire_texte avec regex
    """
    targets = []

    for _, row in df.iterrows():
        val = _parse_salary_row(row)
        targets.append(val)

    return pd.Series(targets, index=df.index)


def _parse_salary_row(row) -> float | None:
    s_min = _to_float(row.get("salaire_min"))
    s_max = _to_float(row.get("salaire_max"))

    if s_min is not None and s_max is not None:
        raw = (s_min + s_max) / 2
        return raw / 12 if raw > 15_000 else raw

    if s_min is not None:
        return s_min / 12 if s_min > 15_000 else s_min

    if s_max is not None:
        return s_max / 12 if s_max > 15_000 else s_max

    # Tenter de parser le texte
    texte = str(row.get("salaire_texte", "") or "")
    return _parse_salary_text(texte)


def _parse_salary_text(texte: str) -> float | None:
    """Extrait un montant numérique depuis un texte de salaire."""
    if not texte or texte.lower() in ("none", "nan", ""):
        return None

    # Supprimer séparateurs de milliers
    texte = texte.replace(" ", "").replace(",", ".")
    numbers = re.findall(r"\d+(?:\.\d+)?", texte)
    if not numbers:
        return None

    values = [float(n) for n in numbers if float(n) > 500]
    if not values:
        return None

    avg = sum(values) / len(values)
    return avg / 12 if avg > 15_000 else avg


def _to_float(val) -> float | None:
    try:
        f = float(val)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


# ─── 3. Construction du Pipeline sklearn ─────────────────────────────────────

def build_pipeline() -> Pipeline:
    """
    Pipeline sklearn complet :
      - TF-IDF sur le texte (titre + description)
      - OneHotEncoder sur les variables catégorielles
      - GradientBoosting Regressor
    """
    text_features = "texte"
    cat_features  = ["pays", "type_contrat", "source", "secteur", "taille_entreprise"]
    num_features  = ["is_senior", "is_junior", "has_tech"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("tfidf", TfidfVectorizer(
                max_features=300,
                ngram_range=(1, 2),
                sublinear_tf=True,
                strip_accents="unicode",
            ), text_features),

            ("cat", Pipeline([
                ("imputer", SimpleImputer(strategy="constant", fill_value="inconnu")),
                ("ohe",     OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
            ]), cat_features),

            ("num", StandardScaler(), num_features),
        ],
        remainder="drop"
    )

    model = Pipeline([
        ("preprocessor", preprocessor),
        ("regressor", GradientBoostingRegressor(
            n_estimators=200,
            learning_rate=0.08,
            max_depth=5,
            min_samples_leaf=5,
            subsample=0.8,
            random_state=42,
        )),
    ])

    return model


# ─── 4. Entraînement ──────────────────────────────────────────────────────────

def train(force_retrain: bool = False) -> dict:
    """
    Charge les données, entraîne le modèle, sauvegarde en cache.
    Retourne les métriques d'évaluation.
    """
    if MODEL_PATH.exists() and not force_retrain:
        logger.info("✅ Modèle déjà en cache — utilisation du cache (force_retrain=False)")
        return load_model_meta()

    # Chargement et préparation
    df_raw = load_offres_from_db()
    df     = engineer_features(df_raw)

    # Séparer offres avec salaire connu (train) et sans (à prédire)
    df_known   = df[df["salaire_cible"].notna()].copy()
    df_unknown = df[df["salaire_cible"].isna()].copy()

    n_known   = len(df_known)
    n_unknown = len(df_unknown)
    logger.info(f"   → {n_known} offres avec salaire · {n_unknown} sans salaire")

    if n_known < 30:
        logger.warning(f"⚠️  Seulement {n_known} offres avec salaire — modèle peu fiable")

    X = df_known[["texte", "pays", "type_contrat", "source", "secteur", "taille_entreprise",
                  "is_senior", "is_junior", "has_tech"]]
    y = df_known["salaire_cible"]

    # Filtrer les valeurs aberrantes (< 500 € ou > 25 000 €/mois)
    mask = (y >= 500) & (y <= 25_000)
    X, y = X[mask], y[mask]
    logger.info(f"   → {len(y)} offres après filtrage des valeurs aberrantes")

    if len(y) < 20:
        raise ValueError("Pas assez de données d'entraînement après filtrage.")

    # Split train / test
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Construction et entraînement
    logger.info("🚀 Entraînement du modèle…")
    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    # Évaluation
    y_pred = pipeline.predict(X_test)
    mae    = mean_absolute_error(y_test, y_pred)
    r2     = r2_score(y_test, y_pred)

    # Cross-validation 5-fold
    cv_scores = cross_val_score(pipeline, X, y, cv=5, scoring="r2", n_jobs=-1)

    metrics = {
        "mae_eur":        round(mae, 2),
        "r2_score":       round(r2, 4),
        "cv_r2_mean":     round(cv_scores.mean(), 4),
        "cv_r2_std":      round(cv_scores.std(), 4),
        "n_train":        len(X_train),
        "n_test":         len(X_test),
        "n_offres_total": len(df),
        "n_sans_salaire": n_unknown,
        "trained_at":     datetime.now().isoformat(),
    }

    logger.info(f"📊 MAE : {mae:.0f} € | R² : {r2:.3f} | CV R² : {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

    # Sauvegarde
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(pipeline, f)
    with open(META_PATH, "wb") as f:
        pickle.dump(metrics, f)

    logger.info(f"💾 Modèle sauvegardé → {MODEL_PATH}")
    return metrics


def load_model_meta() -> dict:
    if META_PATH.exists():
        with open(META_PATH, "rb") as f:
            return pickle.load(f)
    return {}


# ─── 5. Prédiction ────────────────────────────────────────────────────────────

def load_model() -> Pipeline:
    """Charge le modèle depuis le cache."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError("Modèle non trouvé — lancez train() d'abord.")
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def predict_salary(
    titre: str,
    description: str = "",
    pays: str = "france",
    type_contrat: str = "cdi",
    source: str = "france_travail",
    secteur: str = "informatique",
    taille_entreprise: str = "inconnu",
) -> dict:
    """
    Prédit le salaire mensuel estimé pour une offre donnée.

    Retourne :
      {
        "salaire_estime_eur": 3800.0,
        "fourchette_basse":   3420.0,   # ± 10%
        "fourchette_haute":   4180.0,
        "confiance":          "moyenne",
        "features_utilisees": { ... }
      }
    """
    model = load_model()

    texte = (titre + " " + description[:500]).lower()

    row = pd.DataFrame([{
        "texte":            texte,
        "pays":             pays.lower().strip(),
        "type_contrat":     type_contrat.lower().strip(),
        "source":           source.lower().strip(),
        "secteur":          secteur.lower().strip(),
        "taille_entreprise":taille_entreprise.lower().strip(),
        "is_senior":        int(bool(re.search(SENIOR_KEYWORDS, titre, re.I))),
        "is_junior":        int(bool(re.search(JUNIOR_KEYWORDS,  titre, re.I))),
        "has_tech":         int(bool(re.search(TECH_MULTIPLIERS, texte, re.I))),
    }])

    prediction = float(model.predict(row)[0])
    prediction = max(500.0, prediction)   # floor raisonnable

    # Niveau de confiance basé sur le contexte
    confiance = _get_confiance(row.iloc[0])

    return {
        "salaire_estime_eur": round(prediction, 2),
        "fourchette_basse":   round(prediction * 0.90, 2),
        "fourchette_haute":   round(prediction * 1.10, 2),
        "confiance":          confiance,
        "features_utilisees": {
            "is_senior":  bool(row["is_senior"].iloc[0]),
            "is_junior":  bool(row["is_junior"].iloc[0]),
            "has_tech":   bool(row["has_tech"].iloc[0]),
            "pays":       pays,
            "type_contrat": type_contrat,
        },
    }


def _get_confiance(row) -> str:
    """Niveau de confiance basé sur la richesse des features."""
    score = 0
    if row["pays"] not in ("inconnu", ""):
        score += 1
    if row["type_contrat"] not in ("inconnu", ""):
        score += 1
    if row["secteur"] not in ("inconnu", ""):
        score += 1
    if len(str(row.get("texte", ""))) > 100:
        score += 1

    if score >= 3:
        return "haute"
    elif score >= 2:
        return "moyenne"
    else:
        return "basse"


def predict_batch(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prédit le salaire pour toutes les offres d'un DataFrame.
    Utile pour enrichir raw_offres ou la couche Gold.
    """
    model = load_model()
    df = engineer_features(df)

    feature_cols = ["texte", "pays", "type_contrat", "source", "secteur",
                    "taille_entreprise", "is_senior", "is_junior", "has_tech"]

    df["salaire_predit_eur"] = model.predict(df[feature_cols]).round(2)
    df["salaire_predit_eur"] = df["salaire_predit_eur"].clip(lower=500)

    # Ne garder la prédiction que pour les offres SANS salaire connu
    df.loc[df["salaire_cible"].notna(), "salaire_predit_eur"] = None

    return df


# ─── 6. Export Gold MinIO ─────────────────────────────────────────────────────

def export_predictions_to_gold():
    """
    Exporte les prédictions de salaire vers MinIO Gold
    → gold/salaires_predits/salaires_predits.parquet
    """
    try:
        import boto3
        from io import BytesIO
    except ImportError:
        logger.error("boto3 non disponible — export ignoré")
        return

    df_raw = load_offres_from_db()
    df     = predict_batch(df_raw)

    export_df = df[["offre_id", "titre", "pays", "type_contrat",
                    "salaire_cible", "salaire_predit_eur"]].copy()
    export_df["source_prediction"] = "gradient_boosting_v1"
    export_df["generated_at"]      = datetime.now().isoformat()

    # Sauvegarde Parquet en mémoire
    buffer = BytesIO()
    export_df.to_parquet(buffer, index=False)
    buffer.seek(0)

    # Upload MinIO
    s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://localhost:9002"),
        aws_access_key_id=os.getenv("MINIO_USER", "minioadmin"),
        aws_secret_access_key=os.getenv("MINIO_PASSWORD", "minioadmin123"),
    )

    s3.put_object(
        Bucket="gold",
        Key="salaires_predits/salaires_predits.parquet",
        Body=buffer,
        ContentType="application/octet-stream",
    )

    n_pred = export_df["salaire_predit_eur"].notna().sum()
    logger.info(f"✅ {n_pred} prédictions exportées → gold/salaires_predits/")


# ─── Point d'entrée standalone ────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Job Intelligent — Salary Predictor")
    parser.add_argument("--train",   action="store_true", help="Entraîner le modèle")
    parser.add_argument("--retrain", action="store_true", help="Forcer le ré-entraînement")
    parser.add_argument("--export",  action="store_true", help="Exporter les prédictions vers MinIO Gold")
    parser.add_argument("--predict", type=str,            help="Titre de l'offre à tester")
    args = parser.parse_args()

    if args.train or args.retrain:
        metrics = train(force_retrain=args.retrain)
        print("\n📊 Métriques d'entraînement :")
        for k, v in metrics.items():
            print(f"   {k:25s} : {v}")

    if args.export:
        export_predictions_to_gold()

    if args.predict:
        metrics = train(force_retrain=False)
        result = predict_salary(
            titre=args.predict,
            pays="france",
            type_contrat="cdi",
        )
        print(f"\n💰 Prédiction pour : « {args.predict} »")
        print(f"   Salaire estimé   : {result['salaire_estime_eur']:,.0f} €/mois")
        print(f"   Fourchette       : {result['fourchette_basse']:,.0f} – {result['fourchette_haute']:,.0f} €")
        print(f"   Confiance        : {result['confiance']}")
