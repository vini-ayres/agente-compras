"""Tests for ADK agent configuration."""

import pytest
from google.adk.tools.mcp_tool import McpToolset

from app.agent.agent import (
    _lite_llm_completion_kwargs,
    _normalize_gemini_model,
    _normalize_openrouter_model,
    create_mcp_toolset,
    create_root_agent,
    resolve_llm_config,
)
from app.config import Settings
from app.schemas.requisicao import AgentStructuredOutput


def test_normalize_gemini_model_adds_prefix() -> None:
    assert _normalize_gemini_model("gemini-3.6-flash") == "gemini/gemini-3.6-flash"


def test_normalize_gemini_model_keeps_prefix() -> None:
    model = "gemini/gemini-3.6-flash"
    assert _normalize_gemini_model(model) == model


def test_normalize_gemini_model_strips_whitespace() -> None:
    assert _normalize_gemini_model("  gemini-3.6-flash  ") == "gemini/gemini-3.6-flash"


def test_normalize_openrouter_model_adds_prefix() -> None:
    assert (
        _normalize_openrouter_model("google/gemini-3.6-flash")
        == "openrouter/google/gemini-3.6-flash"
    )


def test_normalize_openrouter_model_keeps_prefix() -> None:
    model = "openrouter/google/gemini-3.6-flash"
    assert _normalize_openrouter_model(model) == model


def test_create_mcp_toolset_uses_streamable_http_and_filter() -> None:
    settings = Settings(
        mcp_server_url="http://mcp-server:8080/mcp",
        mcp_connect_timeout_seconds=7.0,
        mcp_sse_read_timeout_seconds=30.0,
    )
    toolset = create_mcp_toolset(settings)
    assert isinstance(toolset, McpToolset)


def test_resolve_llm_selects_gemini_model_and_key() -> None:
    settings = Settings(
        llm_provider="gemini",
        gemini_api_key="test-gemini-key",
        gemini_model="gemini-3.6-flash",
        openrouter_api_key="test-openrouter-key",
        openrouter_model="openrouter/google/gemini-3.6-flash",
    )
    llm = resolve_llm_config(settings)
    assert llm.provider == "gemini"
    assert llm.model == "gemini/gemini-3.6-flash"
    assert llm.api_key == "test-gemini-key"


def test_resolve_llm_selects_openrouter_model_and_key() -> None:
    settings = Settings(
        llm_provider="openrouter",
        gemini_api_key="test-gemini-key",
        gemini_model="gemini/gemini-3.6-flash",
        openrouter_api_key="test-openrouter-key",
        openrouter_model="openrouter/google/gemini-3.6-flash",
    )
    llm = resolve_llm_config(settings)
    assert llm.provider == "openrouter"
    assert llm.model == "openrouter/google/gemini-3.6-flash"
    assert llm.api_key == "test-openrouter-key"


def test_resolve_llm_rejects_invalid_provider() -> None:
    settings = Settings(
        llm_provider="openai",
        gemini_api_key="test-gemini-key",
        openrouter_api_key="test-openrouter-key",
    )
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        resolve_llm_config(settings)


def test_gemini_does_not_fallback_to_openrouter_key() -> None:
    settings = Settings(
        llm_provider="gemini",
        gemini_api_key="",
        openrouter_api_key="test-openrouter-key",
        gemini_model="gemini/gemini-3.6-flash",
        mcp_server_url="http://localhost:8080/mcp",
    )
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        resolve_llm_config(settings)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        create_root_agent(settings, create_mcp_toolset(settings))


def test_openrouter_does_not_fallback_to_gemini_key() -> None:
    settings = Settings(
        llm_provider="openrouter",
        gemini_api_key="test-gemini-key",
        openrouter_api_key="",
        openrouter_model="openrouter/google/gemini-3.6-flash",
        mcp_server_url="http://localhost:8080/mcp",
    )
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        resolve_llm_config(settings)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        create_root_agent(settings, create_mcp_toolset(settings))


def test_create_root_agent_uses_gemini_via_litellm() -> None:
    settings = Settings(
        llm_provider="gemini",
        gemini_api_key="test-gemini-key",
        gemini_model="gemini-3.6-flash",
        openrouter_api_key="test-openrouter-key",
        mcp_server_url="http://localhost:8080/mcp",
    )
    agent = create_root_agent(settings, create_mcp_toolset(settings))
    assert agent.name == "agente_compras"
    assert agent.model.model == "gemini/gemini-3.6-flash"
    assert agent.model._additional_args.get("api_key") == "test-gemini-key"  # noqa: SLF001
    assert "api_base" not in agent.model._additional_args  # noqa: SLF001
    assert agent.output_schema is AgentStructuredOutput
    assert agent.model.capabilities.output_schema_and_tools is False
    assert agent.model._additional_args.get("max_tokens") == 4096  # noqa: SLF001
    assert agent.model._additional_args.get("max_completion_tokens") == 4096  # noqa: SLF001


def test_create_root_agent_uses_openrouter_via_litellm() -> None:
    settings = Settings(
        llm_provider="openrouter",
        gemini_api_key="test-gemini-key",
        gemini_model="gemini/gemini-3.6-flash",
        openrouter_api_key="test-openrouter-key",
        openrouter_model="openrouter/google/gemini-3.6-flash",
        mcp_server_url="http://localhost:8080/mcp",
    )
    agent = create_root_agent(settings, create_mcp_toolset(settings))
    assert agent.name == "agente_compras"
    assert agent.model.model == "openrouter/google/gemini-3.6-flash"
    assert agent.model._additional_args.get("api_key") == "test-openrouter-key"  # noqa: SLF001
    assert "api_base" not in agent.model._additional_args  # noqa: SLF001
    assert agent.output_schema is AgentStructuredOutput
    assert agent.model.capabilities.output_schema_and_tools is False
    assert agent.model._additional_args.get("max_tokens") == 4096  # noqa: SLF001
    assert agent.model._additional_args.get("max_completion_tokens") == 4096  # noqa: SLF001


def test_create_root_agent_requires_gemini_api_key() -> None:
    settings = Settings(
        llm_provider="gemini",
        gemini_api_key="",
        gemini_model="gemini/gemini-3.6-flash",
        mcp_server_url="http://localhost:8080/mcp",
    )
    toolset = create_mcp_toolset(settings)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        create_root_agent(settings, toolset)


def test_gemini_falls_back_to_legacy_llm_model_when_gemini_model_blank() -> None:
    settings = Settings(
        llm_provider="gemini",
        gemini_api_key="test-gemini-key",
        gemini_model="",
        llm_model="gemini-3.6-flash",
    )
    llm = resolve_llm_config(settings)
    assert llm.model == "gemini/gemini-3.6-flash"


def test_lite_llm_token_limit_reaches_additional_args() -> None:
    settings = Settings(
        llm_provider="openrouter",
        openrouter_api_key="test-openrouter-key",
        openrouter_model="openrouter/google/gemini-3.6-flash",
        llm_max_output_tokens=4096,
        mcp_server_url="http://localhost:8080/mcp",
    )
    kwargs = _lite_llm_completion_kwargs(settings)
    assert kwargs == {"max_tokens": 4096, "max_completion_tokens": 4096}

    agent = create_root_agent(settings, create_mcp_toolset(settings))
    additional_args = agent.model._additional_args  # noqa: SLF001
    assert additional_args["max_tokens"] == 4096
    assert additional_args["max_completion_tokens"] == 4096
    assert additional_args["api_key"] == "test-openrouter-key"
    assert agent.output_schema is AgentStructuredOutput


def test_lite_llm_token_limit_uses_configured_value() -> None:
    settings = Settings(
        llm_provider="gemini",
        gemini_api_key="test-gemini-key",
        gemini_model="gemini/gemini-3.6-flash",
        llm_max_output_tokens=2048,
        mcp_server_url="http://localhost:8080/mcp",
    )
    agent = create_root_agent(settings, create_mcp_toolset(settings))
    additional_args = agent.model._additional_args  # noqa: SLF001
    assert additional_args["max_tokens"] == 2048
    assert additional_args["max_completion_tokens"] == 2048


def test_openrouter_settings_remain_loadable() -> None:
    settings = Settings(
        openrouter_api_key="legacy-key",
        openrouter_model="openrouter/google/gemini-3.6-flash",
    )
    assert settings.openrouter_api_key == "legacy-key"
    assert settings.openrouter_model.startswith("openrouter/")
    assert settings.llm_provider == "gemini"
