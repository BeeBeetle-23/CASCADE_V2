from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session
from app.api.deps import get_app
from app.db import models as m
from app.db.session import get_db
from app.services import report

router = APIRouter(tags=["report"])


@router.get("/applications/{application_id}/report")
def report_json(app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    return report.build_report(db, app)


@router.get("/applications/{application_id}/report.csv", response_class=PlainTextResponse)
def report_csv(app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    return PlainTextResponse(report.report_csv(report.build_report(db, app)), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{app.id}-report.csv"'})


@router.get("/applications/{application_id}/report.html", response_class=HTMLResponse)
def report_html(app: m.Application = Depends(get_app), db: Session = Depends(get_db)):
    return HTMLResponse(report.report_html(report.build_report(db, app)))
