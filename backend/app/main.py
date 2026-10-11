import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.router import api
from app.core.config import settings
from app.core.errors import DomainError
from app.db.init_db import create_schema, seed_demo
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cascade")


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    with SessionLocal() as db: seed_demo(db)
    log.info("CASCADE ready (LLM %s)", "configured" if settings.anthropic_api_key else "not configured; deterministic fallback")
    yield


app = FastAPI(title="CASCADE Underwriting Document Cascade Engine", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(DomainError)
async def domain_error(_: Request, e: DomainError):
    return JSONResponse(status_code=e.status, content={"error": e.message, "detail": e.detail})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, e: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": "Request validation failed", "detail": e.errors()})


@app.exception_handler(Exception)
async def unhandled(_: Request, e: Exception):
    log.exception("Unhandled error")          # details stay in the log; no secrets in the response
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "llm_configured": bool(settings.anthropic_api_key), "database": settings.database_url.split(":")[0]}


app.include_router(api)
