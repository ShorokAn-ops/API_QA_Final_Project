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

    # --------------------------------------------------
    # AI Provider (OpenAI / Claude / None)
    # --------------------------------------------------
    AI_ENABLED: bool = False
    AI_PROVIDER: str = "none"  # "none" | "openai" | "claude"
    OPENAI_API_KEY: str | None = None

    # Optional: which model to use (keep default simple)
    OPENAI_MODEL: str = "gpt-4o-mini"

    class Config:
        env_file = ".env"
        extra = "ignore"   # Ignore unrelated env vars (Docker / CI friendly)

    def model_post_init(self, __context) -> None:
        """
        Fail fast ONLY when AI is enabled.
        """
        if self.AI_ENABLED and self.AI_PROVIDER == "openai":
            if not self.OPENAI_API_KEY:
                raise ValueError("AI_ENABLED=true and AI_PROVIDER=openai require OPENAI_API_KEY in .env")


settings = Settings()
