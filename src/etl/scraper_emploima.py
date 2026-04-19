import requests
import json
import boto3
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ✅ Endpoint Docker correct
minio_client = boto3.client(
    's3',
    endpoint_url='http://minio:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin123',
    region_name='us-east-1'
)

BUCKET_BRONZE = 'bronze'

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

def collecter_offres(keyword="data", nb_pages=5):
    toutes_offres = []
    base_url = f"https://www.emploi.ma/recherche-jobs-maroc/{keyword}"

    for page in range(1, nb_pages + 1):
        url = f"{base_url}/page-{page}" if page > 1 else base_url
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code != 200:
                print(f"  Erreur page {page} : {response.status_code}")
                break

            soup = BeautifulSoup(response.text, 'lxml')
            cartes = soup.find_all('div', class_='card-job-detail')

            if not cartes:
                print(f"  Page {page} : aucune offre")
                break

            for carte in cartes:
                try:
                    titre_tag = carte.find('h3')
                    titre = titre_tag.text.strip() if titre_tag else "Non precise"

                    entreprise_tag = carte.find('a', class_='card-job-company')
                    entreprise = entreprise_tag.text.strip() if entreprise_tag else "Non precise"

                    lis = carte.find_all('li')
                    niveau_etudes = "Non precise"
                    experience    = "Non precise"
                    contrat       = "Non precise"
                    region        = "Non precise"
                    competences   = "Non precise"

                    for li in lis:
                        texte = li.text.strip()
                        strong = li.find('strong')
                        valeur = strong.text.strip() if strong else ""
                        if "études" in texte:
                            niveau_etudes = valeur
                        elif "expérience" in texte:
                            experience = valeur
                        elif "Contrat" in texte:
                            contrat = valeur
                        elif "Région" in texte:
                            region = valeur
                        elif "Compétences" in texte:
                            competences = valeur

                    date_tag = carte.find('time')
                    date_pub = date_tag.text.strip() if date_tag else "Non precise"

                    lien_tag = titre_tag.find('a') if titre_tag else None
                    url_offre = "https://www.emploi.ma" + lien_tag['href'] if lien_tag and lien_tag.get('href') else ""

                    offre = {
                        "titre": titre,
                        "entreprise": entreprise,
                        "niveau_etudes": niveau_etudes,
                        "experience": experience,
                        "type_contrat": contrat,
                        "region": region,
                        "competences": competences,
                        "date_publication": date_pub,
                        "url_offre": url_offre,
                        "source": "emploima",
                        "pays": "Maroc",
                        "ville": region
                    }
                    toutes_offres.append(offre)

                except Exception:
                    continue

            print(f"  Page {page} : {len(cartes)} offres")

        except Exception as e:
            print(f"  Erreur : {e}")
            break

    return toutes_offres

def sauvegarder_bronze(offres, keyword):
    # ✅ Horodatage complet
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"emploima/{keyword}_{timestamp}.json"

    data = {
        "source": "emploima",
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
        "data",
        "data-engineer",
        "data-scientist",
        "data-analyst",
        "business-intelligence",
        "data-architect"
    ]

    print("Demarrage scraper Emploi.ma")
    print("=" * 50)

    for keyword in keywords:
        print(f"\nCollecte : {keyword}")
        offres = collecter_offres(keyword, nb_pages=5)
        print(f"Total : {len(offres)} offres")
        if offres:
            sauvegarder_bronze(offres, keyword)
        else:
            print(f"  Aucune offre trouvee pour {keyword}")

    print("\nScraper Emploi.ma termine !")

if __name__ == "__main__":
    run()
