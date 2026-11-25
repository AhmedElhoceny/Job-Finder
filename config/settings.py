from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    gemini_fallback_model: str = "gemini-3.5-flash-lite"
    gemini_max_rpm: int = 12
    gemini_request_delay_seconds: float = 4.0
    database_path: str = "data/jobs.db"
    log_level: str = "INFO"

    # Optional LinkedIn session cookie (li_at) for authenticated post access
    linkedin_li_at: str = ""

    # Wuzzuf Account Credentials (for automated job application)
    wuzzuf_email: str = ""
    wuzzuf_username: str = ""
    wuzzuf_password: str = ""

    # Base directory of the project
    base_dir: Path = Path(__file__).resolve().parent.parent

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def absolute_db_path(self) -> Path:
        return self.base_dir / self.database_path


@lru_cache
def get_settings() -> Settings:
    return Settings()
