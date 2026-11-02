"""Unit tests for requisition service and pricing."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.runner_factory import AgentExecutionError, AgentInvalidResponseError, AgentRunResult
from app.schemas.requisicao import AgentItemSelection, AgentStructuredOutput, CriarRequisicaoRequest
from app.services.pricing import decimal_from_catalog, line_subtotal, total_from_lines
from app.services.requisicao_service import (
    AgentInvalidOutputError,
    AgentUnavailableError,
    NoProductsError,
    PersistenceError,
    RequisicaoService,
)
from app.schemas.requisicao import ValidatedLineItem


def test_decimal_from_catalog_rejects_negative() -> None:
    with pytest.raises(ValueError):
        decimal_from_catalog("-1.00")


def test_line_subtotal_with_decimal() -> None:
    price = decimal_from_catalog("999.99")
    assert line_subtotal(3, price) == Decimal("2999.97")


def test_total_from_lines() -> None:
    items = [
        ValidatedLineItem(
            produto_id=1,
            titulo="A",
            quantidade=2,
            preco_unitario=Decimal("10.00"),
            subtotal=Decimal("20.00"),
        ),
        ValidatedLineItem(
            produto_id=2,
            titulo="B",
            quantidade=1,
            preco_unitario=Decimal("5.50"),
            subtotal=Decimal("5.50"),
        ),
    ]
    assert total_from_lines(items) == Decimal("25.50")


@pytest.mark.asyncio
async def test_criar_requisicao_success(db_session: Session, mock_agent_runtime: MagicMock) -> None:
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")

    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(
            return_value=[
                ValidatedLineItem(
                    produto_id=7,
                    titulo="Laptop",
                    quantidade=3,
                    preco_unitario=Decimal("999.99"),
                    subtotal=Decimal("2999.97"),
                )
            ]
        ),
    ):
        result = await service.criar_requisicao(
            CriarRequisicaoRequest(pedido="Preciso de 3 notebooks"),
        )

    assert result.id == 1
    assert result.valor_total == "2999.97"
    assert len(result.itens) == 1
    assert result.itens[0].subtotal == "2999.97"


@pytest.mark.asyncio
async def test_no_products_does_not_persist(db_session: Session, mock_agent_runtime: MagicMock) -> None:
    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="no_products",
                resposta_agente="Não encontrei produtos.",
                itens=[],
            ),
            raw_text="{}",
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")

    with pytest.raises(NoProductsError):
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de item raro"))

    listed = service.listar(limit=10, offset=0)
    assert listed.total == 0
    assert listed.items == []


@pytest.mark.asyncio
async def test_agent_failure_does_not_persist(db_session: Session, mock_agent_runtime: MagicMock) -> None:
    mock_agent_runtime.run_pedido = AsyncMock(side_effect=AgentExecutionError("fail"))
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")

    with pytest.raises(AgentUnavailableError):
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de notebooks"))

    listed = service.listar(limit=10, offset=0)
    assert listed.total == 0


@pytest.mark.asyncio
async def test_invalid_agent_response(db_session: Session, mock_agent_runtime: MagicMock) -> None:
    mock_agent_runtime.run_pedido = AsyncMock(side_effect=AgentInvalidResponseError("bad"))
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")

    with pytest.raises(AgentInvalidOutputError):
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de notebooks"))


@pytest.mark.asyncio
async def test_persistence_rollback(db_session: Session, mock_agent_runtime: MagicMock) -> None:
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")

    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(
            return_value=[
                ValidatedLineItem(
                    produto_id=7,
                    titulo="Laptop",
                    quantidade=1,
                    preco_unitario=Decimal("10.00"),
                    subtotal=Decimal("10.00"),
                )
            ]
        ),
    ), patch.object(service._repo, "create", side_effect=SQLAlchemyError("db fail")):  # noqa: SLF001
        with pytest.raises(PersistenceError):
            await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de notebook"))

    listed = service.listar(limit=10, offset=0)
    assert listed.total == 0


@pytest.mark.asyncio
async def test_invalid_catalog_price_does_not_persist(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
    from app.services.catalog_validation import InvalidCatalogPriceError

    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")
    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(side_effect=InvalidCatalogPriceError("Preço ausente no catálogo.")),
    ):
        with pytest.raises(InvalidCatalogPriceError):
            await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de notebooks"))

    listed = service.listar(limit=10, offset=0)
    assert listed.total == 0
