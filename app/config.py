from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret_key: str = "dev-secret-change-in-production"
    admin_email: str = "admin@ecomm-guru.com"
    admin_password: str = "admin123"
    database_url: str = "sqlite:///./ecomm_guru.db"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"
    openai_max_tokens: int = 2500
    wp_site_url: str = "https://www.ecomm-guru.com"
    wp_username: str = ""
    wp_app_password: str = ""


settings = Settings()
