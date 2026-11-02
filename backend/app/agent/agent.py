"""Google ADK LlmAgent definition (synchronous factory)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

from app.agent.instructions import AGENT_INSTRUCTIONS
from app.config import Settings
from app.schemas.requisicao import AgentStructuredOutput

PROVIDER_GEMINI = "gemini"
PROVIDER_OPENROUTER = "openrouter"
SUPPORTED_LLM_PROVIDERS = frozenset({PROVIDER_GEMINI, PROVIDER_OPENROUTER})


@dataclass(frozen=True)
class ResolvedLlmConfig:
    provider: str
    model: str
    api_key: str


def _normalize_gemini_model(model: str) -> str:
    cleaned = model.strip()
    if cleaned.startswith("gemini/"):
        return cleaned
    return f"gemini/{cleaned}"


def _normalize_openrouter_model(model: str) -> str:
    cleaned = model.strip()
    if cleaned.startswith("openrouter/"):
        return cleaned
    return f"openrouter/{cleaned}"


def resolve_llm_config(settings: Settings) -> ResolvedLlmConfig:
    """Select model and API key from LLM_PROVIDER without cross-provider fallback."""
    provider = settings.llm_provider.strip().lower()
    if provider not in SUPPORTED_LLM_PROVIDERS:
        raise ValueError(
            "LLM_PROVIDER inválido: "
            f"{settings.llm_provider!r}. Use 'gemini' ou 'openrouter'."
        )

    if provider == PROVIDER_GEMINI:
        api_key = settings.gemini_api_key.strip()
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini.")
        model = (settings.gemini_model or settings.llm_model).strip()
        if not model:
            raise ValueError("GEMINI_MODEL is required when LLM_PROVIDER=gemini.")
        return ResolvedLlmConfig(
            provider=provider,
            model=_normalize_gemini_model(model),
            api_key=api_key,
        )

    api_key = settings.openrouter_api_key.strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter.")
    model = settings.openrouter_model.strip()
    if not model:
        raise ValueError("OPENROUTER_MODEL is required when LLM_PROVIDER=openrouter.")
    return ResolvedLlmConfig(
        provider=provider,
        model=_normalize_openrouter_model(model),
        api_key=api_key,
    )


def create_mcp_toolset(settings: Settings) -> McpToolset:
    """Build a shared McpToolset for Streamable HTTP MCP."""
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=settings.mcp_server_url,
            timeout=settings.mcp_connect_timeout_seconds,
            sse_read_timeout=settings.mcp_sse_read_timeout_seconds,
        ),
        tool_filter=["buscar_produtos", "detalhar_produto"],
    )


def _lite_llm_completion_kwargs(settings: Settings) -> dict[str, int]:
    """Explicit output cap for LiteLLM. OpenRouter bills the requested max_tokens."""
    return {
        "max_tokens": settings.llm_max_output_tokens,
        "max_completion_tokens": settings.llm_max_output_tokens,
    }


def create_root_agent(settings: Settings, toolset: McpToolset) -> LlmAgent:
    """Create the purchase agent (must remain synchronous for ADK deployment rules)."""
    llm = resolve_llm_config(settings)

    if llm.provider == PROVIDER_GEMINI:
        os.environ["GEMINI_API_KEY"] = llm.api_key
    else:
        os.environ["OPENROUTER_API_KEY"] = llm.api_key

    model = LiteLlm(
        model=llm.model,
        api_key=llm.api_key,
        **_lite_llm_completion_kwargs(settings),
    )

    return LlmAgent(
        name="agente_compras",
        model=model,
        instruction=AGENT_INSTRUCTIONS,
        tools=[toolset],
        output_schema=AgentStructuredOutput,
    )
