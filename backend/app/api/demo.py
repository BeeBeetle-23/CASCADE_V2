from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.db import models as m
from app.db.init_db import DEMO_APP_ID, seed_demo, seed_scenario
from app.db.session import get_db
from app.schemas import GraphPayload
from app.services import workflow

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoRequest(BaseModel):
    scenario: Literal["A", "B", "C"] = "A"


def _reload(db: Session, key: str) -> GraphPayload:
    app = seed_demo(db)
    seed_scenario(db, app, key, reset_documents=True)   # wipes uploads/corrections; audit history is preserved
    db.execute(delete(m.SimulationRun).where(m.SimulationRun.application_id == app.id))
    db.commit()
    return workflow.graph_payload(db, app)


@router.post("/load", response_model=GraphPayload)
def load(body: DemoRequest, db: Session = Depends(get_db)):
    return _reload(db, body.scenario)


@router.post("/reset", response_model=GraphPayload)
def reset(body: DemoRequest = DemoRequest(), db: Session = Depends(get_db)):
    """Reset to the original synthetic state of the chosen scenario (default A)."""
    return _reload(db, body.scenario)
