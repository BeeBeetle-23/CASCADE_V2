from fastapi import APIRouter
from . import applications, claims, demo, documents, reports

api = APIRouter()
api.include_router(applications.router)
api.include_router(claims.router)
api.include_router(documents.router)
api.include_router(demo.router)
api.include_router(reports.router)
