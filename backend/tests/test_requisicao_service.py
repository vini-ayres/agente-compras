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
    USER_CATALOG_UNAVAILABLE,
    USER_INSUFFICIENT_INFO,
    USER_NO_PRODUCTS,
    AgentInvalidOutputError,
    AgentUnavailableError,
    CatalogUnavailableBusinessError,
    InsufficientInfoError,
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

    assert result.created is True
    assert result.requisicao.id == 1
    assert result.requisicao.valor_total == "2999.97"
    assert len(result.requisicao.itens) == 1
    assert result.requisicao.itens[0].subtotal == "2999.97"
    assert [item.model_dump() for item in result.requisicao.ferramentas_utilizadas] == [
        {"nome": "buscar_produtos", "origem": "agent", "status": "success"},
        {"nome": "detalhar_produto", "origem": "agent", "status": "success"},
    ]


@pytest.mark.asyncio
async def test_no_products_does_not_persist(db_session: Session, mock_agent_runtime: MagicMock) -> None:
    llm_prose = "MacBook Pro 32 GB OLED por US$ 1.00 e processador quântico."
    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="no_products",
                resposta_agente=llm_prose,
                itens=[],
            ),
            raw_text="{}",
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")

    with pytest.raises(NoProductsError) as exc_info:
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de item raro"))

    assert str(exc_info.value) == USER_NO_PRODUCTS
    assert "32 GB" not in str(exc_info.value)
    assert "OLED" not in str(exc_info.value)
    assert "1.00" not in str(exc_info.value)
    assert "processador quântico" not in str(exc_info.value)
    listed = service.listar(limit=10, offset=0)
    assert listed.total == 0
    assert listed.items == []


@pytest.mark.asyncio
async def test_insufficient_info_uses_controlled_message(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="insufficient_info",
                resposta_agente="Compre 8 iPhones secretos a US$ 0.01 cada.",
                itens=[],
            ),
            raw_text="{}",
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")

    with pytest.raises(InsufficientInfoError) as exc_info:
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="quero coisa"))

    assert str(exc_info.value) == USER_INSUFFICIENT_INFO
    assert "iPhone" not in str(exc_info.value)
    assert "0.01" not in str(exc_info.value)
    assert service.listar(limit=10, offset=0).total == 0


@pytest.mark.asyncio
async def test_catalog_unavailable_uses_controlled_message(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="catalog_unavailable",
                resposta_agente="O DummyJSON caiu e o produto 78 custa US$ 9.99.",
                itens=[],
            ),
            raw_text="{}",
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")

    with pytest.raises(CatalogUnavailableBusinessError) as exc_info:
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de notebooks"))

    assert str(exc_info.value) == USER_CATALOG_UNAVAILABLE
    assert "DummyJSON" not in str(exc_info.value)
    assert "9.99" not in str(exc_info.value)
    assert "traceback" not in str(exc_info.value).lower()
    assert service.listar(limit=10, offset=0).total == 0


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
async def test_listar_persistence_failure(db_session: Session, mock_agent_runtime: MagicMock) -> None:
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")
    with patch.object(service._repo, "list_requisicoes", side_effect=SQLAlchemyError("db fail")):  # noqa: SLF001
        with pytest.raises(PersistenceError, match="consultar"):
            service.listar(limit=10, offset=0)


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


@pytest.mark.asyncio
async def test_persisted_response_uses_catalog_not_llm_text(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="success",
                resposta_agente=(
                    "MacBook com 32 GB de RAM e tela OLED por US$ 1.00. "
                    "Avaliação 9.9/5 e processador quântico."
                ),
                itens=[AgentItemSelection(produto_id=78, titulo="Notebook inventado", quantidade=3)],
            ),
            raw_text="{}",
            search_product_ids=frozenset({78}),
            search_observed=True,
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")
    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(
            return_value=[
                ValidatedLineItem(
                    produto_id=78,
                    titulo="Apple MacBook Pro 14 Inch Space Grey",
                    quantidade=3,
                    preco_unitario=Decimal("1999.99"),
                    subtotal=Decimal("5999.97"),
                )
            ]
        ),
    ):
        outcome = await service.criar_requisicao(
            CriarRequisicaoRequest(pedido="Preciso de 3 laptops"),
        )

    text = outcome.requisicao.resposta_agente
    assert "Apple MacBook Pro 14 Inch Space Grey" in text
    assert "1999.99" in text
    assert "5999.97" in text
    assert "32 GB" not in text
    assert "OLED" not in text
    assert "1.00" not in text
    assert "processador quântico" not in text
    assert outcome.requisicao.itens[0].titulo == "Apple MacBook Pro 14 Inch Space Grey"
    assert outcome.requisicao.itens[0].preco_unitario == "1999.99"
    assert outcome.requisicao.valor_total == "5999.97"


@pytest.mark.asyncio
async def test_search_infra_error_is_unavailable_even_if_agent_selects_products(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="success",
                resposta_agente="Selecionei um laptop por US$ 1.00.",
                itens=[AgentItemSelection(produto_id=7, titulo="Laptop", quantidade=3)],
            ),
            raw_text="{}",
            search_product_ids=frozenset(),
            search_observed=True,
            search_catalog_failed=True,
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")
    with pytest.raises(CatalogUnavailableBusinessError) as exc_info:
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de 3 laptops"))
    assert str(exc_info.value) == USER_CATALOG_UNAVAILABLE
    assert "1.00" not in str(exc_info.value)
    assert service.listar(limit=10, offset=0).total == 0


@pytest.mark.asyncio
async def test_empty_search_is_not_catalog_unavailable(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
    from app.services.catalog_validation import ProductNotInSearchError

    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="success",
                resposta_agente="Vou usar um id conhecido.",
                itens=[AgentItemSelection(produto_id=7, titulo="Laptop", quantidade=1)],
            ),
            raw_text="{}",
            search_product_ids=frozenset(),
            search_observed=True,
            search_catalog_failed=False,
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")
    with pytest.raises(ProductNotInSearchError):
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de laptop"))
    assert service.listar(limit=10, offset=0).total == 0


@pytest.mark.asyncio
async def test_empty_search_with_no_products_status_stays_no_products(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="no_products",
                resposta_agente="Nada encontrado.",
                itens=[],
            ),
            raw_text="{}",
            search_product_ids=frozenset(),
            search_observed=True,
            search_catalog_failed=False,
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")
    with pytest.raises(NoProductsError) as exc_info:
        await service.criar_requisicao(
            CriarRequisicaoRequest(pedido="Preciso comprar um reator nuclear portátil.")
        )
    assert str(exc_info.value) == USER_NO_PRODUCTS
    assert service.listar(limit=10, offset=0).total == 0


@pytest.mark.asyncio
async def test_product_not_in_current_search_is_rejected(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
    from app.services.catalog_validation import ProductNotInSearchError

    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="success",
                resposta_agente="Selecionei o produto 99.",
                itens=[AgentItemSelection(produto_id=99, titulo="Outro", quantidade=1)],
            ),
            raw_text="{}",
            search_product_ids=frozenset({78}),
            search_observed=True,
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")
    with pytest.raises(ProductNotInSearchError):
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de laptop"))
    assert service.listar(limit=10, offset=0).total == 0


@pytest.mark.asyncio
async def test_previous_search_ids_are_not_reused(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
    from app.services.catalog_validation import ProductNotInSearchError

    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="success",
                resposta_agente="Reaproveitei o item anterior.",
                itens=[AgentItemSelection(produto_id=78, titulo="MacBook", quantidade=1)],
            ),
            raw_text="{}",
            search_product_ids=frozenset({80}),
            search_observed=True,
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")
    with pytest.raises(ProductNotInSearchError):
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de outro laptop"))
    assert service.listar(limit=10, offset=0).total == 0


@pytest.mark.asyncio
async def test_empty_search_does_not_allow_arbitrary_id(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
    from app.services.catalog_validation import ProductNotInSearchError

    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="success",
                resposta_agente="Vou usar um id conhecido.",
                itens=[AgentItemSelection(produto_id=78, titulo="MacBook", quantidade=1)],
            ),
            raw_text="{}",
            search_product_ids=frozenset(),
            search_observed=True,
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")
    with pytest.raises(ProductNotInSearchError):
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de laptop"))
    assert service.listar(limit=10, offset=0).total == 0


@pytest.mark.asyncio
async def test_unobserved_search_does_not_persist(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
    from app.services.catalog_validation import ProductNotInSearchError

    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="success",
                resposta_agente="Sem busca.",
                itens=[AgentItemSelection(produto_id=78, titulo="MacBook", quantidade=1)],
            ),
            raw_text="{}",
            search_product_ids=frozenset({78}),
            search_observed=False,
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")
    with pytest.raises(ProductNotInSearchError):
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de laptop"))
    assert service.listar(limit=10, offset=0).total == 0


class _FakeCatalog:
    def __init__(self, payload: dict | Exception) -> None:
        self._payload = payload
        self.calls: list[int] = []

    async def detalhar_produto(self, product_id: int) -> dict:
        self.calls.append(product_id)
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.mark.asyncio
async def test_backend_detalhar_produto_is_recorded_on_success(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
    from app.schemas.requisicao import FerramentaExecucao

    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="success",
                resposta_agente="ok",
                itens=[AgentItemSelection(produto_id=7, titulo="Laptop", quantidade=3)],
            ),
            raw_text="{}",
            search_product_ids=frozenset({7}),
            search_observed=True,
            ferramentas_utilizadas=[
                FerramentaExecucao(nome="buscar_produtos", origem="agent", status="success"),
            ],
        )
    )
    service = RequisicaoService(db_session, mock_agent_runtime, "http://localhost:8080/mcp")
    service._mcp_catalog = _FakeCatalog(  # noqa: SLF001
        {"status": "success", "product": {"id": 7, "title": "Laptop", "price": "999.99"}}
    )
    result = await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de 3 laptops"))
    dumped = [item.model_dump() for item in result.requisicao.ferramentas_utilizadas]
    assert dumped == [
        {"nome": "buscar_produtos", "origem": "agent", "status": "success"},
        {"nome": "detalhar_produto", "origem": "backend", "status": "success"},
    ]


@pytest.mark.asyncio
async def test_backend_detalhar_failure_is_recorded_as_error() -> None:
    from app.schemas.requisicao import FerramentaExecucao
    from app.services.catalog_validation import CatalogUnavailableError, validate_and_price_items

    execucoes: list[FerramentaExecucao] = []
    client = _FakeCatalog(CatalogUnavailableError("Catálogo indisponível."))
    with pytest.raises(CatalogUnavailableError):
        await validate_and_price_items(
            selections=[AgentItemSelection(produto_id=7, titulo="Laptop", quantidade=1)],
            mcp_client=client,  # type: ignore[arg-type]
            execucoes=execucoes,
        )
    assert [item.model_dump() for item in execucoes] == [
        {"nome": "detalhar_produto", "origem": "backend", "status": "error"}
    ]


@pytest.mark.asyncio
async def test_listar_does_not_invent_ferramentas(
    db_session: Session, mock_agent_runtime: MagicMock
) -> None:
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
        await service.criar_requisicao(CriarRequisicaoRequest(pedido="Preciso de 3 notebooks"))
    listed = service.listar(limit=10, offset=0)
    assert listed.items[0].ferramentas_utilizadas == []
