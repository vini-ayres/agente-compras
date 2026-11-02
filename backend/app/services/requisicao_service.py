"""Orchestration for creating and listing purchase requisitions."""

from __future__ import annotations

import hashlib
import logging
from decimal import Decimal

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.runner_factory import (
    AgentExecutionError,
    AgentInvalidResponseError,
    AgentRunResult,
    AgentRuntime,
)
from app.database.models import Requisicao
from app.database.repository import RequisicaoRepository
from app.schemas.requisicao import (
    AgentItemSelection,
    AgentStructuredOutput,
    CriarRequisicaoRequest,
    FerramentaExecucao,
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
    ProductNotInSearchError,
    validate_and_price_items,
)
from app.services.factual_response import build_factual_response
from app.services.pricing import total_from_lines

logger = logging.getLogger(__name__)

USER_NO_PRODUCTS = "Não foram encontrados produtos correspondentes à busca."
USER_INSUFFICIENT_INFO = "Informe o produto e a quantidade desejados para continuar."
USER_CATALOG_UNAVAILABLE = (
    "O catálogo está temporariamente indisponível. Tente novamente em instantes."
)


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


class IdempotencyConflictError(Exception):
    kind = "idempotency_conflict"
    http_status = 409


class CreateRequisicaoResult:
    def __init__(self, requisicao: RequisicaoOut, *, created: bool) -> None:
        self.requisicao = requisicao
        self.created = created


def hash_pedido(pedido: str) -> str:
    return hashlib.sha256(pedido.encode("utf-8")).hexdigest()


def ensure_items_were_searched(
    selections: list[AgentItemSelection],
    *,
    search_product_ids: frozenset[int],
    search_observed: bool,
) -> None:
    if not search_observed:
        raise ProductNotInSearchError(
            "Não foi possível confirmar os produtos na busca desta solicitação."
        )
    missing = [item.produto_id for item in selections if item.produto_id not in search_product_ids]
    if missing:
        raise ProductNotInSearchError(
            "Produto selecionado não apareceu na busca desta solicitação."
        )


def _to_requisicao_out(
    model: Requisicao,
    *,
    ferramentas_utilizadas: list[FerramentaExecucao] | None = None,
) -> RequisicaoOut:
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
        ferramentas_utilizadas=list(ferramentas_utilizadas or ()),
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

    async def criar_requisicao(
        self,
        body: CriarRequisicaoRequest,
        *,
        idempotency_key: str | None = None,
    ) -> CreateRequisicaoResult:
        request_hash = hash_pedido(body.pedido)
        if idempotency_key:
            replay = self._replay_if_completed(idempotency_key, request_hash)
            if replay is not None:
                return CreateRequisicaoResult(replay, created=False)

        run = await self._run_agent(body.pedido)
        structured = run.structured
        if run.search_catalog_failed:
            logger.info(
                "Busca MCP indisponível; texto interno do agente não será devolvido ao cliente"
            )
            logger.debug("Texto interno do agente: %s", structured.resposta_agente)
            raise CatalogUnavailableBusinessError(USER_CATALOG_UNAVAILABLE)
        self._ensure_agent_status(structured)
        ensure_items_were_searched(
            structured.itens,
            search_product_ids=run.search_product_ids,
            search_observed=run.search_observed,
        )

        backend_execucoes: list[FerramentaExecucao] = []
        try:
            validated_items = await validate_and_price_items(
                selections=structured.itens,
                mcp_client=self._mcp_catalog,
                execucoes=backend_execucoes,
            )
        except ProductNotFoundError:
            raise
        except ProductNotInSearchError:
            raise
        except (InvalidCatalogPriceError, InvalidCatalogTitleError, InvalidCatalogProductError):
            raise
        except CatalogUnavailableError as exc:
            raise CatalogUnavailableBusinessError(USER_CATALOG_UNAVAILABLE) from exc

        valor_total: Decimal = total_from_lines(validated_items)
        factual = build_factual_response(validated_items, valor_total)

        try:
            saved = self._repo.create(
                pedido_original=body.pedido,
                resposta_agente=factual,
                itens=validated_items,
                valor_total=valor_total,
            )
            if idempotency_key:
                saved_key = self._repo.save_idempotency(
                    idempotency_key,
                    request_hash,
                    saved.id,
                )
                if not saved_key:
                    self._db.rollback()
                    replay = self._replay_if_completed(idempotency_key, request_hash)
                    if replay is not None:
                        return CreateRequisicaoResult(replay, created=False)
                    raise IdempotencyConflictError(
                        "Idempotency-Key já utilizada com outro pedido."
                    )
            self._db.commit()
            self._db.refresh(saved)
        except IdempotencyConflictError:
            self._db.rollback()
            raise
        except SQLAlchemyError as exc:
            self._db.rollback()
            logger.exception("Erro ao persistir requisição")
            raise PersistenceError("Não foi possível salvar a requisição.") from exc

        return CreateRequisicaoResult(
            _to_requisicao_out(
                saved,
                ferramentas_utilizadas=[*run.ferramentas_utilizadas, *backend_execucoes],
            ),
            created=True,
        )

    def _replay_if_completed(self, key: str, request_hash: str) -> RequisicaoOut | None:
        record = self._repo.get_idempotency(key)
        if record is None:
            return None
        if record.request_hash != request_hash:
            raise IdempotencyConflictError("Idempotency-Key já utilizada com outro pedido.")
        if record.status == "completed" and record.requisicao_id is not None:
            existing = self._repo.get_by_id(record.requisicao_id)
            if existing is None:
                raise PersistenceError("Não foi possível recuperar a requisição original.")
            return _to_requisicao_out(existing)
        return None

    async def _run_agent(self, pedido: str) -> AgentRunResult:
        try:
            return await self._agent_runtime.run_pedido(pedido)
        except AgentExecutionError as exc:
            raise AgentUnavailableError(
                "Serviço de agente indisponível. Tente novamente em instantes."
            ) from exc
        except AgentInvalidResponseError as exc:
            raise AgentInvalidOutputError("Resposta inválida do agente.") from exc

    def _ensure_agent_status(self, structured: AgentStructuredOutput) -> None:
        if structured.status == "no_products":
            logger.info(
                "Agente status=no_products; texto interno não será devolvido ao cliente"
            )
            logger.debug("Texto interno do agente: %s", structured.resposta_agente)
            raise NoProductsError(USER_NO_PRODUCTS)
        if structured.status == "insufficient_info":
            logger.info(
                "Agente status=insufficient_info; texto interno não será devolvido ao cliente"
            )
            logger.debug("Texto interno do agente: %s", structured.resposta_agente)
            raise InsufficientInfoError(USER_INSUFFICIENT_INFO)
        if structured.status == "catalog_unavailable":
            logger.info(
                "Agente status=catalog_unavailable; texto interno não será devolvido ao cliente"
            )
            logger.debug("Texto interno do agente: %s", structured.resposta_agente)
            raise CatalogUnavailableBusinessError(USER_CATALOG_UNAVAILABLE)
        if structured.status != "success":
            raise BusinessRuleError("Não foi possível processar o pedido.")
        if not structured.itens:
            raise BusinessRuleError("Não foi possível processar o pedido.")

    def listar(self, *, limit: int, offset: int) -> RequisicaoListResponse:
        try:
            rows, total = self._repo.list_requisicoes(limit=limit, offset=offset)
        except SQLAlchemyError as exc:
            logger.exception("Erro ao listar requisições")
            raise PersistenceError("Não foi possível consultar as requisições.") from exc
        return RequisicaoListResponse(
            items=[_to_requisicao_out(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )
