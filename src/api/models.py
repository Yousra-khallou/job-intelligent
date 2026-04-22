from pydantic import BaseModel
from typing import Optional

class CandidatCreate(BaseModel):
    nom: str
    prenom: str
    email: str

class RecommandationRequest(BaseModel):
    email: str
    top_k: Optional[int] = 10