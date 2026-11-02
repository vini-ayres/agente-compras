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

    enable_dns_rebinding_protection: bool = True
    # Host headers accepted when DNS rebinding protection is on.
    # Docker Compose adds mcp-server:8080 for the backend/ADK client.
    mcp_allowed_hosts: str = "127.0.0.1:8080,localhost:8080"

    def allowed_hosts_list(self) -> list[str]:
        return [host.strip() for host in self.mcp_allowed_hosts.split(",") if host.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
