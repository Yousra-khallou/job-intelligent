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
    endpoint_url='http://localhost:9002',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin123',
    region_name='us-east-1'
)

BUCKET_BRONZE = 'bronze'

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
        params = {
            "motsCles": keyword,
            "range": f"{start}-{end}"
        }
        response = requests.get(url, headers=headers, params=params)
        if response.status_code in [200, 206]:
            resultats = response.json().get("resultats", [])
            toutes_offres.extend(resultats)
            print(f"  Collecte {start}-{end} : {len(resultats)} offres")
        elif response.status_code == 204:
            print(f"  Plus d'offres disponibles")
            break
        else:
            print(f"  Erreur {response.status_code} : {response.text[:100]}")
            break

    return toutes_offres

def sauvegarder_bronze(offres, keyword):
    date_today = datetime.now().strftime("%Y-%m-%d")
    filename = f"france_travail/{keyword}_{date_today}.json"

    data = {
        "source": "france_travail",
        "keyword": keyword,
        "date_collecte": date_today,
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

    print("Demarrage du scraper France-Travail")
    print("=" * 50)

    token = get_token()
    print("Token obtenu ✓")

    for keyword in keywords:
        print(f"\nCollecte : {keyword}")
        offres = collecter_offres(token, keyword, nb_offres=100)
        print(f"Total : {len(offres)} offres")
        if offres:
            sauvegarder_bronze(offres, keyword.replace(" ", "_"))
        else:
            print(f"  Aucune offre trouvee pour {keyword}")

    print("\nScraper termine avec succes !")

if __name__ == "__main__":
    run()