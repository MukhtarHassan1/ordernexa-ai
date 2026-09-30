from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --------------------------------------------------------
    # Application
    # --------------------------------------------------------
    app_name: str = "OrderNexa AI"
    app_env: str = "development"
    app_debug: bool = False
    app_secret: str

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    # --------------------------------------------------------
    # PostgreSQL
    # --------------------------------------------------------
    database_url: str

    # --------------------------------------------------------
    # Redis
    # --------------------------------------------------------
    redis_url: str

    # --------------------------------------------------------
    # MinIO / object storage
    # --------------------------------------------------------
    minio_root_user: str
    minio_root_password: str

    minio_endpoint: str = "http://minio:9000"
    minio_public_endpoint: str = "http://localhost:9000"

    minio_bucket: str = "ordernexa-artifacts"

    max_upload_bytes: int = 15 * 1024 * 1024

    # --------------------------------------------------------
    # AI provider
    # --------------------------------------------------------
    ai_provider: str = "ollama"

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "granite3.2-vision:2b"
    # Optional: when unset, retain existing OLLAMA_MODEL behavior for both paths.
    # Set independently to avoid sending native-text POs to a vision-only workload.
    ollama_text_model: str = ""
    ollama_vision_model: str = ""
    # Fail clearly rather than holding HTTP file uploads open for four minutes.
    ollama_read_timeout_seconds: float = 75.0
    ollama_connect_timeout_seconds: float = 5.0
    ollama_context_length: int = 4096
    ollama_max_input_chars: int = 12000
    ollama_probe_model: str = "qwen2.5:0.5b"
    # Cold start on low-resource Windows can exceed 100s even for 0.5B Qwen.
    ollama_probe_timeout_seconds: float = 180.0
    # Local demo ONLY. For deployment, use externally authenticated identity.
    ordernexa_operator_key: str = ""
    ordernexa_operator_actor: str = "LOCAL_OPERATOR"
    ordernexa_operator_role: str = "FINANCE_MANAGER"
    ordernexa_role_keys_json: str = ""

    # Reserved future providers
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # --------------------------------------------------------
    # Opt-in automation. No external writes without explicit configuration.
    # --------------------------------------------------------
    automation_worker_enabled: bool = False
    automation_live_writes: bool = False
    automation_max_attempts: int = 5
    n8n_ingest_secret: str = ""
    graph_client_state: str = ""
    graph_subscription_id: str = ""
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_mailbox: str = ""
    graph_drive_id: str = ""
    hubspot_access_token: str = ""
    teams_approval_webhook_url: str = ""
    voice_server_secret: str = ""
    customer_email_enabled: bool = False
    # Local console; production endpoints require a separate identity solution.

    # --------------------------------------------------------
    # Odoo
    # --------------------------------------------------------
    odoo_base_url: str = "http://odoo:8069"
    ordernexa_odoo_shared_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()