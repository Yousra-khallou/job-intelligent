import requests
import os
from dotenv import load_dotenv

# Charger les clés depuis .env
load_dotenv()

CLIENT_ID = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")

# Etape 1 : Obtenir le token
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
    token = response.json().get("access_token")
    print("Token obtenu :", token[:20], "...")
    return token

# Etape 2 : Chercher des offres
def search_jobs(token, keyword="data engineer"):
    url = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "motsCles": keyword,
        "range": "0-4"
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json()

# Etape 3 : Afficher les resultats
def afficher_offres(offres):
    resultats = offres.get("resultats", [])
    print(f"\n{len(resultats)} offres trouvees :\n")
    for offre in resultats:
        print("Titre    :", offre.get("intitule"))
        print("Entreprise:", offre.get("entreprise", {}).get("nom", "Non precise"))
        print("Lieu     :", offre.get("lieuTravail", {}).get("libelle"))
        print("Contrat  :", offre.get("typeContratLibelle"))
        print("-" * 40)

# Lancer le test
if __name__ == "__main__":
    print("Test API France-Travail")
    print("=" * 40)
    token = get_token()
    offres = search_jobs(token, "data engineer")
    afficher_offres(offres)