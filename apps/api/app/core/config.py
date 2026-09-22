from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OrderNexa AI"
    app_env: str = "development"
    app_debug: bool = True
    app_secret: str

    database_url: str
    redis_url: str

    minio_endpoint: str
    minio_public_endpoint: str
    minio_root_user: str
    minio_root_password: str
    minio_bucket: str

    ai_provider: str = "ollama"
    ollama_base_url: str = "http://host.docker.internal:11434"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()