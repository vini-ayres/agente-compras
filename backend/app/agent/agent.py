"""Google ADK LlmAgent definition (synchronous factory)."""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

from app.agent.instructions import AGENT_INSTRUCTIONS
from app.config import Settings
from app.schemas.requisicao import AgentStructuredOutput


def _normalize_gemini_model(model: str) -> str:
    cleaned = model.strip()
    if cleaned.startswith("gemini/"):
        return cleaned
    return f"gemini/{cleaned}"


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


def create_root_agent(settings: Settings, toolset: McpToolset) -> LlmAgent:
    """Create the purchase agent (must remain synchronous for ADK deployment rules)."""
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is required to initialize the agent.")

    os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

    model = LiteLlm(
        model=_normalize_gemini_model(settings.llm_model),
        api_key=settings.gemini_api_key,
    )

    return LlmAgent(
        name="agente_compras",
        model=model,
        instruction=AGENT_INSTRUCTIONS,
        tools=[toolset],
        output_schema=AgentStructuredOutput,
    )
