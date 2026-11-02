"""Application configuration from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/agente_compras",
        alias="DATABASE_URL",
    )
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(
        default="gemini/gemini-3.6-flash",
        alias="GEMINI_MODEL",
    )
    # Legado: usado pelo Gemini somente se GEMINI_MODEL estiver vazio.
    llm_model: str = Field(
        default="gemini/gemini-3.6-flash",
        alias="LLM_MODEL",
    )
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="openrouter/google/gemini-3.6-flash",
        alias="OPENROUTER_MODEL",
    )
    llm_max_output_tokens: int = Field(default=4096, ge=1, alias="LLM_MAX_OUTPUT_TOKENS")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )
    mcp_server_url: str = Field(
        default="http://localhost:8080/mcp",
        alias="MCP_SERVER_URL",
    )
    mcp_connect_timeout_seconds: float = Field(default=10.0, alias="MCP_CONNECT_TIMEOUT_SECONDS")
    mcp_sse_read_timeout_seconds: float = Field(
        default=120.0,
        alias="MCP_SSE_READ_TIMEOUT_SECONDS",
    )

    app_name: str = "agente_compras"
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


def get_settings() -> Settings:
    return Settings()
