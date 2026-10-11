from fastapi import Depends
from sqlalchemy.orm import Session
from app.core.errors import DomainError
from app.db import models as m
from app.db.session import get_db


def get_app(application_id: str, db: Session = Depends(get_db)) -> m.Application:
    app = db.get(m.Application, application_id)
    if app is None: raise DomainError(404, f"Application {application_id} not found")
    return app
