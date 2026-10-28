"""All settings come from environment variables / .env. Nothing secret is hard-coded."""
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "dev"

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://docketpilot:docketpilot@127.0.0.1:5432/docketpilot"

    # Other services
    redis_url: str = "redis://127.0.0.1:6379/0"
    qdrant_url: str = "http://127.0.0.1:6333"
    # S3-compatible object storage (SeaweedFS locally; any S3 service works)
    s3_endpoint: str = "127.0.0.1:8333"
    s3_access_key: str = "docketpilot"
    s3_secret_key: SecretStr = SecretStr("docketpilot-dev-secret")
    s3_secure: bool = False
    s3_bucket: str = "docketpilot"

    # Retrieval
    qdrant_collection: str = "chunks"
    embed_model: str = "BAAI/bge-small-en-v1.5"
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"

    # Auth
    jwt_secret: SecretStr = SecretStr("change-me-in-env")
    jwt_algorithm: str = "HS256"
    # A signed-in user stays signed in for a week (the page renews the token on every visit); sign out ends it.
    access_token_minutes: int = 7 * 24 * 60
    # Google sign-in: OAuth client id from Google Cloud Console (APIs & Services > Credentials). Empty = button hidden.
    google_client_id: str | None = None
    signup_open: bool = True

    # Privacy vault (Fernet key; generate with cryptography.fernet.Fernet.generate_key())
    vault_key: SecretStr | None = None

    # LLM: single provider, Groq (team decision, see CLAUDE.md)
    groq_api_key: SecretStr | None = None
    groq_api_key_backup: SecretStr | None = None  # same model; used while the first key is rate-limited
    groq_api_key_backup_2: SecretStr | None = None  # further keys, each from a different Groq account
    groq_api_key_backup_3: SecretStr | None = None
    llm_primary_model: str = "openai/gpt-oss-120b"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = Field(default=2, ge=0)
    llm_rate_wait_seconds: float = 75.0
    # Groq free tier: 8,000 tokens per minute, counting the prompt plus the completion allowance of each request.
    llm_request_token_cap: int = 7600  # total wait for Groq's per-minute token window before giving up


@lru_cache
def get_settings() -> Settings:
    return Settings()
