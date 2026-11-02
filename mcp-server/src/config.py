"""Environment-based configuration for the MCP server."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dummyjson_base_url: str = "https://dummyjson.com"
    http_timeout_seconds: float = 10.0

    host: str = "0.0.0.0"
    port: int = 8080
    streamable_http_path: str = "/mcp"

    # Disable in Docker / LAN so Host headers like mcp-server:8080 are accepted.
    enable_dns_rebinding_protection: bool = False


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
