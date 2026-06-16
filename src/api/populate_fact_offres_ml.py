#!/usr/bin/env python3
"""
populate_fact_offres_ml.py
Utilise salary_predictor.py EXISTANT pour prédire et écrire dans fact_offres.
À exécuter DANS le conteneur fastapi_nlp.
"""

import psycopg2
import logging
from salary_predictor import load_offres_from_db, predict_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PG_CONFIG = {
    "host":     "postgres_db",
    "port":     5432,
    "dbname":   "dwh_job_intelligent",
    "user":     "admin",
    "password": "admin123",
}

def main():
    log.info("1️⃣  Chargement des offres depuis raw_offres…")
    df = load_offres_from_db()
    log.info(f"   → {len(df)} offres chargées")

    log.info("2️⃣  Prédiction ML via predict_batch()…")
    df = predict_batch(df)

    # Garder uniquement les offres qui ont reçu une prédiction
    df_pred = df[df["salaire_predit_eur"].notna()][["offre_id", "salaire_predit_eur"]]
    n_pred = len(df_pred)
    log.info(f"   → {n_pred} prédictions générées")

    if n_pred == 0:
        log.warning("⚠️  Aucune prédiction — vérifie que le modèle est entraîné (GET /api/salary/status)")
        return

    log.info("3️⃣  Écriture dans fact_offres…")
    conn = psycopg2.connect(**PG_CONFIG)
    cur = conn.cursor()

    updated = 0
    for _, row in df_pred.iterrows():
        cur.execute("""
            UPDATE fact_offres
            SET salaire_predit_eur = %s,
                salaire_confiance  = 'moyenne',
                date_prediction    = NOW()
            WHERE offre_id = %s
              AND salaire_min IS NULL
              AND (salaire_predit_eur IS NULL OR salaire_confiance = 'basse (fallback)')
        """, (float(row["salaire_predit_eur"]), str(row["offre_id"])))
        updated += cur.rowcount

    conn.commit()
    cur.close()
    conn.close()

    log.info("=" * 50)
    log.info(f"✅ {updated}/{n_pred} offres mises à jour dans fact_offres")
    log.info("=" * 50)

if __name__ == "__main__":
    main()
