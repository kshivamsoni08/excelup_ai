from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

# The .env lives at the project root (skillsetu/.env); resolve it absolutely so
# the backend works regardless of the process working directory.
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Runtime settings loaded exclusively from the environment / .env.

    No secret is ever hardcoded here; everything comes from .env which is
    gitignored. The app must boot (and fully function) with empty LLM keys.
    """

    database_url: str = ""
    secret_key: str = "dev-only-insecure-secret"
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    frontend_origins: str = "http://localhost:3000"

    model_config = {"env_file": [str(_ROOT_ENV), ".env"], "extra": "ignore"}

    @property
    def frontend_origin_list(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    @property
    def sync_url(self) -> str:
        return _psycopg_compatible(self.database_url)

    @property
    def async_url(self) -> str:
        """asyncpg-compatible URL with sslmode stripped from the query string
        (SSL is enforced via engine connect_args instead)."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if "+psycopg" in url:
            url = url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # strip sslmode/ssl/channel_binding params; asyncpg takes SSL via connect_args
        if "?" in url:
            base, qs = url.split("?", 1)
            kept = [p for p in qs.split("&")
                    if not p.lower().startswith(("sslmode=", "ssl=", "channel_binding="))]
            url = base + ("?" + "&".join(kept) if kept else "")
        return url


def _psycopg_compatible(url: str) -> str:
    """Normalize any postgres URL variant to the psycopg3 sync dialect.

    SSL params (sslmode/channel_binding) are kept - psycopg3 understands them
    natively, which is exactly what Neon's pooled strings rely on.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    for driver in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if url.startswith(driver):
            url = "postgresql://" + url[len(driver) :]
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
