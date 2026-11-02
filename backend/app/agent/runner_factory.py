"""Agent runtime: Runner singleton, MCP lifecycle, per-request sessions.

Session strategy
----------------
- One ``Runner``, one ``McpToolset`` and one ``InMemorySessionService`` are created at
  application startup and reused for all HTTP requests.
- Each ``POST /requisicoes`` creates a **new** ADK session (unique ``session_id`` and
  ``user_id`` scoped to the request) so conversation history is never shared across
  purchase requests.
- ``McpToolset.close()`` is invoked on FastAPI shutdown to release MCP connections.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset
from google.genai import types
from pydantic import ValidationError

from app.agent.agent import create_mcp_toolset, create_root_agent
from app.agent.search_ids import collect_search_ids
from app.config import Settings
from app.schemas.requisicao import AgentStructuredOutput

logger = logging.getLogger(__name__)


class AgentExecutionError(Exception):
    """Agent could not complete (LLM/MCP/runtime)."""

    kind = "agent_execution"


class AgentInvalidResponseError(Exception):
    """Agent returned text that is not valid structured output."""

    kind = "invalid_agent_response"


@dataclass
class AgentRunResult:
    structured: AgentStructuredOutput
    raw_text: str
    search_product_ids: frozenset[int] = field(default_factory=frozenset)
    search_observed: bool = False


class AgentRuntime:
    """Long-lived ADK runner with managed MCP toolset lifecycle."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._toolset: McpToolset = create_mcp_toolset(settings)
        self._agent = create_root_agent(settings, self._toolset)
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            agent=self._agent,
            app_name=settings.app_name,
            session_service=self._session_service,
        )

    @property
    def toolset(self) -> McpToolset:
        return self._toolset

    @property
    def runner(self) -> Runner:
        return self._runner

    async def close(self) -> None:
        await self._toolset.close()

    async def run_pedido(self, pedido: str) -> AgentRunResult:
        """Execute the agent for a single purchase request."""
        session_id = str(uuid.uuid4())
        user_id = f"req-{session_id}"

        await self._session_service.create_session(
            app_name=self._settings.app_name,
            user_id=user_id,
            session_id=session_id,
        )

        message = types.Content(
            role="user",
            parts=[types.Part(text=pedido)],
        )

        final_text = ""
        function_responses: list[object] = []
        try:
            async for event in self._runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message,
            ):
                function_responses.extend(event.get_function_responses())
                if not event.content:
                    continue
                for part in event.content.parts or []:
                    function_call = getattr(part, "function_call", None)
                    if function_call and getattr(function_call, "name", None):
                        logger.info("ADK tool call: %s", function_call.name)
                    if event.is_final_response() and part.text and not part.thought:
                        final_text += part.text
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha ao executar agente ADK")
            raise AgentExecutionError("Falha ao executar o agente de compras.") from exc

        search_product_ids, search_observed = collect_search_ids(function_responses)

        if not final_text.strip():
            raise AgentInvalidResponseError("Agente não retornou resposta final.")

        try:
            structured = AgentStructuredOutput.model_validate(json.loads(final_text))
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Resposta estruturada inválida do agente")
            raise AgentInvalidResponseError("Resposta do agente em formato inválido.") from exc

        return AgentRunResult(
            structured=structured,
            raw_text=final_text,
            search_product_ids=search_product_ids,
            search_observed=search_observed,
        )


def build_agent_runtime(settings: Settings) -> AgentRuntime:
    return AgentRuntime(settings)
