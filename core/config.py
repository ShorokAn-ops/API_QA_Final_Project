from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application configuration.

    - Secrets are NEVER stored in code.
    - All sensitive values are injected via environment variables (.env).
    - Validation happens at startup (fail fast).
    """

    # --------------------------------------------------
    # ERPNext
    # --------------------------------------------------
    ERPNEXT_BASE_URL: str = "http://localhost:8080"
    ERPNEXT_API_KEY: str
    ERPNEXT_API_SECRET: str

    # --------------------------------------------------
    # Database
    # --------------------------------------------------
    DATABASE_URL: str = "sqlite:///./app.db"

    # --------------------------------------------------
    # Sync / Scheduler
    # --------------------------------------------------
    SYNC_ENABLED: bool = True
    SYNC_INTERVAL_SECONDS: int = 5
    SYNC_MAX_CHANGED_PER_CYCLE: int = 50

    # --------------------------------------------------
    # Internal Cache (seconds)
    # --------------------------------------------------
    DASHBOARD_TTL_SECONDS: int = 15

    class Config:
        env_file = ".env"
        extra = "ignore"   # Ignore unrelated env vars (Docker / CI friendly)


settings = Settings()
