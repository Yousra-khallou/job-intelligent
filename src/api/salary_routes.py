"""
salary_routes.py
================
Endpoints FastAPI à ajouter dans main.py pour la prédiction de salaire.

Intégration dans main.py :
    from salary_routes import router as salary_router
    app.include_router(salary_router, prefix="/api")

Placement : src/api/salary_routes.py
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

# salary_predictor.py est dans src/api/ → /app/ dans le conteneur
from salary_predictor import train, predict_salary, load_model_meta, export_predictions_to_gold

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Schémas Pydantic ─────────────────────────────────────────────────────────

class SalaryPredictRequest(BaseModel):
    titre:             str           = Field(...,        example="Data Engineer Senior")
    description:       Optional[str] = Field(default="", example="Spark, Kafka, AWS, Python")
    pays:              Optional[str] = Field(default="france",       example="france")
    type_contrat:      Optional[str] = Field(default="cdi",          example="cdi")
    source:            Optional[str] = Field(default="france_travail",example="adzuna")
    secteur:           Optional[str] = Field(default="informatique", example="banque")
    taille_entreprise: Optional[str] = Field(default="inconnu",      example="grande")


class SalaryPredictResponse(BaseModel):
    salaire_estime_eur: float
    fourchette_basse:   float
    fourchette_haute:   float
    confiance:          str           # "haute" | "moyenne" | "basse"
    features_utilisees: dict


class ModelStatusResponse(BaseModel):
    model_disponible: bool
    mae_eur:          Optional[float]
    r2_score:         Optional[float]
    cv_r2_mean:       Optional[float]
    n_train:          Optional[int]
    trained_at:       Optional[str]
    message:          str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/salary/status",
    response_model=ModelStatusResponse,
    summary="Statut du modèle de prédiction salariale",
    tags=["Salary Prediction"],
)
def salary_model_status():
    """
    Vérifie si le modèle est entraîné et retourne ses métriques.
    """
    model_path = Path("/app/cache/salary_model.pkl")

    if not model_path.exists():
        return ModelStatusResponse(
            model_disponible=False,
            mae_eur=None,
            r2_score=None,
            cv_r2_mean=None,
            n_train=None,
            trained_at=None,
            message="Modèle non entraîné — appelez POST /api/salary/train d'abord.",
        )

    meta = load_model_meta()
    return ModelStatusResponse(
        model_disponible=True,
        mae_eur=meta.get("mae_eur"),
        r2_score=meta.get("r2_score"),
        cv_r2_mean=meta.get("cv_r2_mean"),
        n_train=meta.get("n_train"),
        trained_at=meta.get("trained_at"),
        message="Modèle opérationnel ✅",
    )


@router.post(
    "/salary/train",
    summary="Entraîner / ré-entraîner le modèle salarial",
    tags=["Salary Prediction"],
)
def salary_train(
    background_tasks: BackgroundTasks,
    force_retrain: bool = False,
):
    """
    Lance l'entraînement du modèle en arrière-plan.
    - `force_retrain=true`  → ré-entraîne même si un modèle existe déjà
    - `force_retrain=false` → utilise le cache si disponible
    """
    def _train_task():
        try:
            metrics = train(force_retrain=force_retrain)
            logger.info(f"✅ Entraînement terminé — MAE={metrics.get('mae_eur')} €")
        except Exception as e:
            logger.error(f"❌ Erreur entraînement : {e}")

    background_tasks.add_task(_train_task)

    return {
        "status":  "started",
        "message": "Entraînement lancé en arrière-plan. Consultez GET /api/salary/status dans ~30s.",
        "force_retrain": force_retrain,
    }


@router.post(
    "/salary/predict",
    response_model=SalaryPredictResponse,
    summary="Prédire le salaire d'une offre",
    tags=["Salary Prediction"],
)
def salary_predict(request: SalaryPredictRequest):
    """
    Prédit le salaire mensuel estimé en EUR pour une offre donnée.

    **Exemple de requête :**
    ```json
    {
      "titre":        "Data Engineer Senior",
      "description":  "Maîtrise de Spark, Kafka, Python, AWS",
      "pays":         "france",
      "type_contrat": "cdi"
    }
    ```

    **Interprétation de la confiance :**
    - `haute`   → pays + contrat + secteur connus + description riche
    - `moyenne` → 2 features contextuelles disponibles
    - `basse`   → données minimales (titre seul)
    """
    model_path = Path("/app/cache/salary_model.pkl")
    if not model_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Modèle non disponible — appelez POST /api/salary/train d'abord.",
        )

    try:
        result = predict_salary(
            titre=request.titre,
            description=request.description or "",
            pays=request.pays or "france",
            type_contrat=request.type_contrat or "cdi",
            source=request.source or "inconnu",
            secteur=request.secteur or "inconnu",
            taille_entreprise=request.taille_entreprise or "inconnu",
        )
        return SalaryPredictResponse(**result)

    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur prédiction : {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne : {str(e)}")


@router.get(
    "/salary/predict-quick",
    response_model=SalaryPredictResponse,
    summary="Prédiction rapide par titre (GET)",
    tags=["Salary Prediction"],
)
def salary_predict_quick(
    titre: str,
    pays: str = "france",
    type_contrat: str = "cdi",
):
    """
    Version GET simplifiée — utile pour tester depuis le navigateur.

    Exemple : `/api/salary/predict-quick?titre=Data+Scientist+Senior&pays=france`
    """
    return salary_predict(SalaryPredictRequest(
        titre=titre,
        pays=pays,
        type_contrat=type_contrat,
    ))


@router.post(
    "/salary/export-gold",
    summary="Exporter les prédictions vers MinIO Gold",
    tags=["Salary Prediction"],
)
def salary_export_gold(background_tasks: BackgroundTasks):
    """
    Génère les prédictions pour toutes les offres sans salaire
    et les exporte vers `gold/salaires_predits/salaires_predits.parquet`.
    Utile pour Power BI.
    """
    background_tasks.add_task(export_predictions_to_gold)
    return {
        "status":  "started",
        "message": "Export Gold lancé en arrière-plan → gold/salaires_predits/",
    }
