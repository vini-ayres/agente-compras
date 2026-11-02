"""Orchestration for creating and listing purchase requisitions."""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.runner_factory import (
    AgentExecutionError,
    AgentInvalidResponseError,
    AgentRuntime,
)
from app.database.models import Requisicao
from app.database.repository import RequisicaoRepository
from app.schemas.requisicao import (
    AgentStructuredOutput,
    CriarRequisicaoRequest,
    RequisicaoItemOut,
    RequisicaoListResponse,
    RequisicaoOut,
)
from app.services.catalog_validation import (
    CatalogUnavailableError,
    InvalidCatalogPriceError,
    InvalidCatalogProductError,
    InvalidCatalogTitleError,
    McpCatalogClient,
    ProductNotFoundError,
    validate_and_price_items,
)
from app.services.pricing import total_from_lines

logger = logging.getLogger(__name__)


class BusinessRuleError(Exception):
    """Expected business outcome that should not persist a requisition."""

    kind = "business_rule"
    http_status = 422


class NoProductsError(BusinessRuleError):
    kind = "no_products"


class InsufficientInfoError(BusinessRuleError):
    kind = "insufficient_info"


class CatalogUnavailableBusinessError(Exception):
    """MCP/DummyJSON unavailable. Distinct from LLM/agent failures."""

    kind = "catalog_unavailable"
    http_status = 503


class AgentUnavailableError(Exception):
    """LLM/agent runtime failure. Distinct from catalog unavailability."""

    kind = "agent_unavailable"
    http_status = 503


class AgentInvalidOutputError(Exception):
    """Agent returned unstructured or invalid JSON."""

    kind = "invalid_agent_response"
    http_status = 502


class PersistenceError(Exception):
    kind = "persistence"
    http_status = 503


def _to_requisicao_out(model: Requisicao) -> RequisicaoOut:
    return RequisicaoOut(
        id=model.id,
        pedido_original=model.pedido_original,
        resposta_agente=model.resposta_agente,
        valor_total=str(model.valor_total),
        created_at=model.created_at,
        itens=[
            RequisicaoItemOut(
                produto_id=item.produto_id,
                titulo=item.titulo,
                quantidade=item.quantidade,
                preco_unitario=str(item.preco_unitario),
                subtotal=str(item.subtotal),
            )
            for item in model.itens
        ],
    )


class RequisicaoService:
    """Application service for requisitions."""

    def __init__(
        self,
        db: Session,
        agent_runtime: AgentRuntime,
        mcp_server_url: str,
        *,
        timeout_seconds: float = 10.0,
        sse_read_timeout_seconds: float = 120.0,
    ) -> None:
        self._db = db
        self._agent_runtime = agent_runtime
        self._mcp_catalog = McpCatalogClient(
            mcp_server_url,
            timeout_seconds=timeout_seconds,
            sse_read_timeout_seconds=sse_read_timeout_seconds,
        )
        self._repo = RequisicaoRepository(db)

    async def criar_requisicao(self, body: CriarRequisicaoRequest) -> RequisicaoOut:
        structured = await self._run_agent(body.pedido)
        self._ensure_agent_status(structured)

        try:
            validated_items = await validate_and_price_items(
                selections=structured.itens,
                mcp_client=self._mcp_catalog,
            )
        except ProductNotFoundError:
            raise
        except (InvalidCatalogPriceError, InvalidCatalogTitleError, InvalidCatalogProductError):
            raise
        except CatalogUnavailableError as exc:
            raise CatalogUnavailableBusinessError("Catálogo indisponível. Tente novamente em instantes.") from exc

        valor_total: Decimal = total_from_lines(validated_items)

        try:
            saved = self._repo.create(
                pedido_original=body.pedido,
                resposta_agente=structured.resposta_agente,
                itens=validated_items,
                valor_total=valor_total,
            )
        except SQLAlchemyError as exc:
            self._db.rollback()
            logger.exception("Erro ao persistir requisição")
            raise PersistenceError("Não foi possível salvar a requisição.") from exc

        return _to_requisicao_out(saved)

    async def _run_agent(self, pedido: str) -> AgentStructuredOutput:
        try:
            result = await self._agent_runtime.run_pedido(pedido)
            return result.structured
        except AgentExecutionError as exc:
            raise AgentUnavailableError(
                "Serviço de agente indisponível. Tente novamente em instantes."
            ) from exc
        except AgentInvalidResponseError as exc:
            raise AgentInvalidOutputError("Resposta inválida do agente.") from exc

    def _ensure_agent_status(self, structured: AgentStructuredOutput) -> None:
        if structured.status == "no_products":
            raise NoProductsError(structured.resposta_agente)
        if structured.status == "insufficient_info":
            raise InsufficientInfoError(structured.resposta_agente)
        if structured.status == "catalog_unavailable":
            raise CatalogUnavailableBusinessError(structured.resposta_agente)
        if structured.status != "success":
            raise BusinessRuleError("Não foi possível processar o pedido.")
        if not structured.itens:
            raise BusinessRuleError("Agente não selecionou itens para a requisição.")

    def listar(self, *, limit: int, offset: int) -> RequisicaoListResponse:
        rows, total = self._repo.list_requisicoes(limit=limit, offset=offset)
        return RequisicaoListResponse(
            items=[_to_requisicao_out(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )
