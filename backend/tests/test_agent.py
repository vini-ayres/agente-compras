"""Tests for ADK agent configuration."""

import pytest
from google.adk.tools.mcp_tool import McpToolset

from app.agent.agent import _normalize_gemini_model, create_mcp_toolset, create_root_agent
from app.config import Settings


def test_normalize_gemini_model_adds_prefix() -> None:
    assert _normalize_gemini_model("gemini-3.6-flash") == "gemini/gemini-3.6-flash"


def test_normalize_gemini_model_keeps_prefix() -> None:
    model = "gemini/gemini-3.6-flash"
    assert _normalize_gemini_model(model) == model


def test_normalize_gemini_model_strips_whitespace() -> None:
    assert _normalize_gemini_model("  gemini-3.6-flash  ") == "gemini/gemini-3.6-flash"


def test_create_mcp_toolset_uses_streamable_http_and_filter() -> None:
    settings = Settings(
        mcp_server_url="http://mcp-server:8080/mcp",
        mcp_connect_timeout_seconds=7.0,
        mcp_sse_read_timeout_seconds=30.0,
    )
    toolset = create_mcp_toolset(settings)
    assert isinstance(toolset, McpToolset)


def test_create_root_agent_uses_gemini_via_litellm() -> None:
    settings = Settings(
        gemini_api_key="test-gemini-key",
        llm_model="gemini-3.6-flash",
        mcp_server_url="http://localhost:8080/mcp",
    )
    agent = create_root_agent(settings, create_mcp_toolset(settings))
    assert agent.name == "agente_compras"
    assert agent.model.model == "gemini/gemini-3.6-flash"
    assert agent.model._additional_args.get("api_key") == "test-gemini-key"  # noqa: SLF001
    assert "api_base" not in agent.model._additional_args  # noqa: SLF001


def test_create_root_agent_requires_gemini_api_key() -> None:
    settings = Settings(
        gemini_api_key="",
        llm_model="gemini/gemini-3.6-flash",
        mcp_server_url="http://localhost:8080/mcp",
    )
    toolset = create_mcp_toolset(settings)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        create_root_agent(settings, toolset)


def test_openrouter_settings_remain_loadable() -> None:
    settings = Settings(
        openrouter_api_key="legacy-key",
        openrouter_model="openrouter/xingchen-agi/xing4.0-29b-a4b:free",
    )
    assert settings.openrouter_api_key == "legacy-key"
    assert settings.openrouter_model.startswith("openrouter/")
