import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")

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

def analyser_structure(token):
    url = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "motsCles": "data engineer",
        "range": "0-0"
    }
    response = requests.get(url, headers=headers, params=params)
    offres = response.json().get("resultats", [])

    if not offres:
        print("Aucune offre trouvee")
        return

    # Afficher la premiere offre complete en JSON
    premiere_offre = offres[0]

    print("=" * 50)
    print("STRUCTURE COMPLETE D'UNE OFFRE")
    print("=" * 50)
    print(json.dumps(premiere_offre, indent=2, ensure_ascii=False))

    print("\n" + "=" * 50)
    print("LISTE DES CHAMPS DISPONIBLES")
    print("=" * 50)
    for cle, valeur in premiere_offre.items():
        type_valeur = type(valeur).__name__
        print(f"  {cle} ({type_valeur})")

if __name__ == "__main__":
    token = get_token()
    analyser_structure(token)