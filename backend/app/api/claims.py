from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import models as m
from app.db.session import get_db
from app.schemas import AuditEventOut, CascadeResult, ClaimCorrectionRequest, ClaimOut, ClaimVerifyRequest
from app.services import workflow

router = APIRouter(tags=["claims"])


def _app(db, claim_id):
    c = workflow.get_claim(db, claim_id)
    return c, db.get(m.Application, c.application_id)


@router.get("/claims/{claim_id}", response_model=ClaimOut)
def get_claim(claim_id: str, db: Session = Depends(get_db)):
    return workflow.get_claim(db, claim_id)


@router.post("/claims/{claim_id}/verify", response_model=CascadeResult)
def verify_claim(claim_id: str, body: ClaimVerifyRequest, db: Session = Depends(get_db)):
    _, app = _app(db, claim_id)
    return workflow.set_claim_verification(db, app, claim_id, body.status.value, body.actor, body.reason)


@router.post("/claims/{claim_id}/correct", response_model=CascadeResult)
def correct_claim(claim_id: str, body: ClaimCorrectionRequest, db: Session = Depends(get_db)):
    _, app = _app(db, claim_id)
    return workflow.correct_claim(db, app, claim_id, body.new_value, body.actor, body.reason)


@router.get("/claims/{claim_id}/history")
def claim_history(claim_id: str, db: Session = Depends(get_db)):
    c, app = _app(db, claim_id)
    versions = db.scalars(select(m.Claim).where(m.Claim.application_id == app.id, m.Claim.node_id == c.node_id).order_by(m.Claim.created_at, m.Claim.id)).all()
    events = db.scalars(select(m.AuditEvent).where(m.AuditEvent.application_id == app.id, m.AuditEvent.target_entity == c.node_id).order_by(m.AuditEvent.id)).all()
    return dict(values=[ClaimOut.model_validate(v) for v in versions], events=[AuditEventOut.model_validate(e) for e in events])
