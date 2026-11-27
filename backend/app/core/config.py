"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://ktp:ktp@localhost:5432/ktp"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "dev-only-insecure-secret-change-me"  # noqa: S105
    public_base_url: str = "http://localhost:5173"
    field_encryption_key: str = ""
    passport_signing_key: str = ""
    jobs_inline: bool = False  # run background jobs in-process (tests, e2e, single-box demo)

    # Adapter selection ("mock" or "real"); real adapters also need their keys.
    ai_provider: str = "auto"
    fallback_ai_provider: str = "auto"
    aa_provider: str = "auto"
    payments_provider: str = "auto"
    whatsapp_provider: str = "auto"
    kyc_provider: str = "auto"
    sms_provider: str = "auto"
    storage_provider: str = "local"

    sarvam_api_key: str = ""
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_vision_model: str = "sarvam-vision"
    sarvam_stt_model: str = "saaras:v3"
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_llm_model: str = "sarvam-105b"
    fallback_ai_vendor: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    ai_timeout_seconds: float = 30.0

    aa_client_id: str = ""
    aa_client_secret: str = ""
    aa_product_instance_id: str = ""
    aa_base_url: str = "https://fiu-sandbox.setu.co"

    payments_client_id: str = ""
    payments_client_secret: str = ""
    payments_base_url: str = "https://sandbox.cashfree.com"
    verification_vpa: str = "verify@sandbox"

    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""

    sms_api_key: str = ""
    kyc_api_key: str = ""
    kyc_base_url: str = ""

    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "ap-south-1"
    local_storage_dir: str = "./var/storage"

    sentry_dsn: str = ""
    metrics_token: str = ""
    fraud_alert_min_assessments: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
