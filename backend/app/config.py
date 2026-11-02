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
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    llm_model: str = Field(
        default="gemini/gemini-3.6-flash",
        alias="LLM_MODEL",
    )
    # Preservados para compatibilidade de ambiente; o agente ativo usa Gemini.
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="openrouter/xingchen-agi/xing4.0-29b-a4b:free",
        alias="OPENROUTER_MODEL",
    )
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
