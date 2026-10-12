import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
_backend_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _backend_env.exists():
    load_dotenv(_backend_env)


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./cascade.db")
    upload_dir: str = os.getenv("UPLOAD_DIR", "./storage/uploads")
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "20"))
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None  # backend only
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_fallback_model: str | None = os.getenv("GEMINI_FALLBACK_MODEL") or None
    relative_tolerance: str = os.getenv("RELATIVE_TOLERANCE", "0.02")



settings = Settings()
