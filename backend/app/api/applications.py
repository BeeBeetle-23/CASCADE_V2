import re
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.api.deps import get_app
from app.db import models as m
from app.db.init_db import seed_scenario
from app.db.session import get_db
from app.schemas import (ApplicationCreate, ApplicationOut, ApplicationSummary, AuditEventOut, ClaimOut, GraphPayload,
                         CascadeResult, SimulationRequest, SimulationResult)
from app.services import workflow
from app.services.state_store import current_claims, load_engine, persist_snapshot, record_audit

router = APIRouter(tags=["applications"])
ATTENTION = ("unverified", "unsupported", "unavailable", "red", "amber", "needs_review", "incomplete", "stale")


def _summary(db: Session, app: m.Application) -> dict:
    nodes = db.scalars(select(m.GraphNode).where(m.GraphNode.application_id == app.id)).all()
    rec = next((n for n in nodes if n.node_id == "recommendation"), None)
    return dict(**ApplicationOut.model_validate(app).model_dump(),
                document_count=db.scalar(select(func.count()).select_from(m.Document).where(m.Document.application_id == app.id)) or 0,
                outstanding_review_items=sum(1 for n in nodes if n.status in ATTENTION and n.node_type != "decision"),
                recommendation=rec.value if rec else None, recommendation_status=rec.status if rec else None)


@router.get("/applications", response_model=list[ApplicationSummary])
def list_applications(db: Session = Depends(get_db)):
    return [_summary(db, a) for a in db.scalars(select(m.Application).order_by(m.Application.created_at))]


@router.post("/applications", response_model=ApplicationSummary, status_code=201)
def create_application(body: ApplicationCreate, db: Session = Depends(get_db)):
    slug = re.sub(r"[^a-z0-9]+", "-", body.company_name.lower()).strip("-") or "entity"
    app = m.Application(company_name=body.company_name, entity_id=slug, requested_amount=body.requested_amount,
                        currency=body.currency, reporting_period=body.reporting_period)
    db.add(app); db.flush()
    if body.scenario: seed_scenario(db, app, body.scenario)       # explicit synthetic data
    else:
        persist_snapshot(db, app, load_engine(db, app))
        record_audit(db, app.id, "application_created", "analyst", app.id, None, {"company": app.company_name},
                     "Application created", [], [], None, "REFER_FOR_REVIEW")
    db.commit()
    return _summary(db, app)


@router.get("/applications/{application_id}", response_model=ApplicationSummary)
def get_application(app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    return _summary(db, app)


@router.get("/applications/{application_id}/summary")
def dashboard_summary(app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    eng = load_engine(db, app); st = eng.state
    return dict(application=_summary(db, app), recommendation=st["recommendation"],
                checks={k: dict(status=v["status"], explanation=v["explanation"]) for k, v in eng.check_details().items()},
                metrics={k: dict(value=st[k]["value"], status=st[k]["status"]) for k in ("m_dscr", "m_cr")})


@router.get("/applications/{application_id}/graph", response_model=GraphPayload)
def get_graph(app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    return workflow.graph_payload(db, app)


@router.get("/applications/{application_id}/checks")
def get_checks(app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    eng = load_engine(db, app)
    return [dict(node=k, **v) for k, v in eng.check_details().items()]


@router.get("/applications/{application_id}/claims", response_model=list[ClaimOut])
def get_claims(include_history: bool = Query(False), app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    if include_history:
        return list(db.scalars(select(m.Claim).where(m.Claim.application_id == app.id).order_by(m.Claim.created_at, m.Claim.id)))
    return current_claims(db, app.id)


@router.post("/applications/{application_id}/recalculate", response_model=CascadeResult)
def recalculate(app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    return workflow.recalculate(db, app)


@router.get("/applications/{application_id}/audit", response_model=list[AuditEventOut])
def get_audit(limit: int = Query(200, ge=1, le=1000), app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    return list(db.scalars(select(m.AuditEvent).where(m.AuditEvent.application_id == app.id).order_by(m.AuditEvent.id).limit(limit)))


@router.post("/applications/{application_id}/simulate", response_model=SimulationResult)
def simulate(body: SimulationRequest, app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    return workflow.simulate(db, app, body.excluded_node_id, body.actor)


@router.get("/applications/{application_id}/simulations")
def list_simulations(app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    runs = db.scalars(select(m.SimulationRun).where(m.SimulationRun.application_id == app.id).order_by(m.SimulationRun.id.desc()))
    return [dict(id=r.id, excluded_node_id=r.excluded_node_id, created_at=r.created_at, original=r.original, simulated=r.simulated,
                 recommendation_changed=r.original != r.simulated, changes=r.changes) for r in runs]


@router.get("/applications/{application_id}/simulations/{sim_id}")
def get_simulation(sim_id: int, app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    from app.core.errors import DomainError
    r = db.get(m.SimulationRun, sim_id)
    if r is None or r.application_id != app.id: raise DomainError(404, "Simulation not found")
    return dict(id=r.id, excluded_node_id=r.excluded_node_id, created_at=r.created_at, original=r.original, simulated=r.simulated,
                recommendation_changed=r.original != r.simulated, changes=r.changes)
