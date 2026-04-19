import requests
import os
import json
import boto3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

APP_ID  = os.getenv("ADZUNA_APP_ID")
APP_KEY = os.getenv("ADZUNA_APP_KEY")

# ✅ Endpoint Docker correct
minio_client = boto3.client(
    's3',
    endpoint_url='http://minio:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin123',
    region_name='us-east-1'
)

BUCKET_BRONZE = 'bronze'

def collecter_offres(keyword="data engineer", nb_pages=5):
    toutes_offres = []
    base_url = "https://api.adzuna.com/v1/api/jobs/fr/search"

    for page in range(1, nb_pages + 1):
        url = f"{base_url}/{page}"
        params = {
            "app_id": APP_ID,
            "app_key": APP_KEY,
            "what": keyword,
            "results_per_page": 20,
            "content-type": "application/json"
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            resultats = response.json().get("results", [])
            toutes_offres.extend(resultats)
            print(f"  Page {page} : {len(resultats)} offres")
        else:
            print(f"  Erreur page {page} : {response.status_code}")
            break

    return toutes_offres

def sauvegarder_bronze(offres, keyword):
    # ✅ Horodatage complet
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"adzuna/{keyword}_{timestamp}.json"

    data = {
        "source": "adzuna",
        "keyword": keyword,
        "date_collecte": timestamp,
        "nb_offres": len(offres),
        "offres": offres
    }

    minio_client.put_object(
        Bucket=BUCKET_BRONZE,
        Key=filename,
        Body=json.dumps(data, ensure_ascii=False, indent=2),
        ContentType='application/json'
    )

    print(f"Sauvegarde : bronze/{filename} ✓")
    return filename

def run():
    keywords = [
        "data engineer",
        "data scientist",
        "data analyst",
        "machine learning engineer",
        "business intelligence",
        "data architect"
    ]

    print("Demarrage scraper Adzuna")
    print("=" * 50)

    for keyword in keywords:
        print(f"\nCollecte : {keyword}")
        offres = collecter_offres(keyword, nb_pages=5)
        print(f"Total : {len(offres)} offres")
        if offres:
            sauvegarder_bronze(offres, keyword.replace(" ", "_"))
        else:
            print(f"  Aucune offre trouvee pour {keyword}")

    print("\nScraper Adzuna termine !")

if __name__ == "__main__":
    run()
