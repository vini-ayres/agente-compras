"""Tests for MCP server transport security settings."""

from config import Settings


def test_allowed_hosts_include_local_defaults() -> None:
    settings = Settings()
    assert settings.enable_dns_rebinding_protection is True
    assert "127.0.0.1:8080" in settings.allowed_hosts_list()
    assert "localhost:8080" in settings.allowed_hosts_list()


def test_allowed_hosts_parse_docker_hostname() -> None:
    settings = Settings(mcp_allowed_hosts="mcp-server:8080,127.0.0.1:8080")
    assert settings.allowed_hosts_list() == ["mcp-server:8080", "127.0.0.1:8080"]
