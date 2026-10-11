import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./cascade.db")
    upload_dir: str = os.getenv("UPLOAD_DIR", "./storage/uploads")
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "20"))
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None  # backend only
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    relative_tolerance: str = os.getenv("RELATIVE_TOLERANCE", "0.02")


settings = Settings()
