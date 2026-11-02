"""Configuracion central de la aplicacion, leida desde variables de entorno."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

INSECURE_DEFAULT_SECRET = "dev-insecure-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "GeoSms911"
    app_secret: str = INSECURE_DEFAULT_SECRET
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'geosms911.db').as_posix()}"
    public_base_url: str = "http://127.0.0.1:8000"
    allow_registration: bool = True
    access_token_minutes: int = 60 * 24 * 7
    location_retention_days: int = 30
    sms_fallback_after_seconds: int = 90
    cors_origins: str = "*"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_validate_signature: bool = True
    sms_command_prefix: str = "GEOSMS911"

    @property
    def twilio_configured(self) -> bool:
        return bool(
            self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_from_number
            and self.twilio_account_sid.startswith("AC")
        )

    @property
    def using_insecure_secret(self) -> bool:
        return self.app_secret == INSECURE_DEFAULT_SECRET or len(self.app_secret) < 24

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def public_base_url_clean(self) -> str:
        return self.public_base_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
