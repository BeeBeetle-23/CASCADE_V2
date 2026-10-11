from collections.abc import Iterator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine as SAEngine
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import settings


def make_engine(url: str | None = None) -> SAEngine:
    url = url or settings.database_url
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}   # FastAPI threadpool
        if ":memory:" in url or url == "sqlite://":
            from sqlalchemy.pool import StaticPool
            kwargs["poolclass"] = StaticPool                    # share one in-memory DB
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _fk(dbapi_conn, _):
            cur = dbapi_conn.cursor(); cur.execute("PRAGMA foreign_keys=ON"); cur.close()
    return eng


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
