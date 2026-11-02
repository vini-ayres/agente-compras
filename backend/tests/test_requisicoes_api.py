"""API tests for /requisicoes."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.schemas.requisicao import ValidatedLineItem


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_post_requisicao_success(client) -> None:
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
        response = client.post(
            "/requisicoes",
            json={"pedido": "Preciso de 3 notebooks com 16 GB de RAM"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["valor_total"] == "2999.97"
    assert body["itens"][0]["produto_id"] == 7
    assert body["itens"][0]["subtotal"] == "2999.97"
    assert body["ferramentas_utilizadas"] == ["buscar_produtos", "detalhar_produto"]


def test_get_requisicoes_pagination(client) -> None:
    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(
            return_value=[
                ValidatedLineItem(
                    produto_id=1,
                    titulo="A",
                    quantidade=1,
                    preco_unitario=Decimal("10.00"),
                    subtotal=Decimal("10.00"),
                )
            ]
        ),
    ):
        client.post("/requisicoes", json={"pedido": "Preciso de um item A"})
        client.post("/requisicoes", json={"pedido": "Preciso de um item B"})

    page = client.get("/requisicoes", params={"limit": 1, "offset": 0})
    assert page.status_code == 200
    data = page.json()
    assert data["total"] == 2
    assert data["limit"] == 1
    assert len(data["items"]) == 1


def test_post_invalid_pedido(client) -> None:
    response = client.post("/requisicoes", json={"pedido": "  "})
    assert response.status_code == 422


def test_post_agent_failure_returns_503(client, mock_agent_runtime) -> None:
    from app.agent.runner_factory import AgentExecutionError

    mock_agent_runtime.run_pedido = AsyncMock(side_effect=AgentExecutionError("down"))

    response = client.post("/requisicoes", json={"pedido": "Preciso de notebooks"})
    assert response.status_code == 503
    assert "detail" in response.json()


def test_post_invalid_agent_response_returns_502(client, mock_agent_runtime) -> None:
    from app.agent.runner_factory import AgentInvalidResponseError

    mock_agent_runtime.run_pedido = AsyncMock(side_effect=AgentInvalidResponseError("bad json"))

    response = client.post("/requisicoes", json={"pedido": "Preciso de notebooks"})
    assert response.status_code == 502


def test_post_invalid_catalog_price_returns_422(client) -> None:
    from app.services.catalog_validation import InvalidCatalogPriceError

    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(side_effect=InvalidCatalogPriceError("Preço ausente no catálogo.")),
    ):
        response = client.post("/requisicoes", json={"pedido": "Preciso de notebooks"})
    assert response.status_code == 422


def test_get_requisicoes_persistence_failure_returns_503(client) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    with patch(
        "app.services.requisicao_service.RequisicaoRepository.list_requisicoes",
        side_effect=SQLAlchemyError("db down"),
    ):
        response = client.get("/requisicoes")
    assert response.status_code == 503
    assert "consultar" in response.json()["detail"]


def test_post_product_not_in_search_returns_422(client, mock_agent_runtime) -> None:
    from app.agent.runner_factory import AgentRunResult
    from app.schemas.requisicao import AgentItemSelection, AgentStructuredOutput

    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="success",
                resposta_agente="Item fora da busca.",
                itens=[AgentItemSelection(produto_id=99, titulo="X", quantidade=1)],
            ),
            raw_text="{}",
            search_product_ids=frozenset({7}),
            search_observed=True,
        )
    )
    response = client.post("/requisicoes", json={"pedido": "Preciso de notebooks"})
    assert response.status_code == 422
    assert "busca" in response.json()["detail"]


def test_post_search_infra_error_returns_503_even_if_agent_selects_products(
    client, mock_agent_runtime
) -> None:
    from app.agent.runner_factory import AgentRunResult
    from app.schemas.requisicao import AgentItemSelection, AgentStructuredOutput
    from app.services.requisicao_service import USER_CATALOG_UNAVAILABLE

    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="success",
                resposta_agente="Selecionei um laptop inventado.",
                itens=[AgentItemSelection(produto_id=7, titulo="Laptop", quantidade=3)],
            ),
            raw_text="{}",
            search_product_ids=frozenset(),
            search_observed=True,
            search_catalog_failed=True,
        )
    )
    response = client.post("/requisicoes", json={"pedido": "Preciso de 3 laptops"})
    assert response.status_code == 503
    assert response.json()["detail"] == USER_CATALOG_UNAVAILABLE
    assert client.get("/requisicoes").json()["total"] == 0


def test_post_empty_search_with_selected_product_returns_422_not_503(
    client, mock_agent_runtime
) -> None:
    from app.agent.runner_factory import AgentRunResult
    from app.schemas.requisicao import AgentItemSelection, AgentStructuredOutput
    from app.services.requisicao_service import USER_CATALOG_UNAVAILABLE

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
    response = client.post("/requisicoes", json={"pedido": "Preciso de laptop"})
    assert response.status_code == 422
    assert response.json()["detail"] != USER_CATALOG_UNAVAILABLE
    assert "busca" in response.json()["detail"]
    assert client.get("/requisicoes").json()["total"] == 0


def test_post_catalog_unavailable_returns_503(client) -> None:
    from app.services.catalog_validation import CatalogUnavailableError
    from app.services.requisicao_service import USER_CATALOG_UNAVAILABLE

    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(side_effect=CatalogUnavailableError("Catálogo indisponível.")),
    ):
        response = client.post("/requisicoes", json={"pedido": "Preciso de notebooks"})
    assert response.status_code == 503
    assert response.json()["detail"] == USER_CATALOG_UNAVAILABLE


def test_post_no_products_returns_controlled_message(client, mock_agent_runtime) -> None:
    from app.agent.runner_factory import AgentRunResult
    from app.schemas.requisicao import AgentStructuredOutput
    from app.services.requisicao_service import USER_NO_PRODUCTS

    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="no_products",
                resposta_agente="Encontrei um Galaxy Fold 32 GB por US$ 1.00.",
                itens=[],
            ),
            raw_text="{}",
        )
    )
    response = client.post("/requisicoes", json={"pedido": "Preciso de um item raro"})
    assert response.status_code == 422
    assert response.json()["detail"] == USER_NO_PRODUCTS
    assert "Galaxy" not in response.json()["detail"]
    assert "1.00" not in response.json()["detail"]
    assert client.get("/requisicoes").json()["total"] == 0


def test_post_insufficient_info_returns_controlled_message(client, mock_agent_runtime) -> None:
    from app.agent.runner_factory import AgentRunResult
    from app.schemas.requisicao import AgentStructuredOutput
    from app.services.requisicao_service import USER_INSUFFICIENT_INFO

    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="insufficient_info",
                resposta_agente="Peça 12 notebooks secretos a US$ 0.50.",
                itens=[],
            ),
            raw_text="{}",
        )
    )
    response = client.post("/requisicoes", json={"pedido": "quero"})
    assert response.status_code == 422
    assert response.json()["detail"] == USER_INSUFFICIENT_INFO
    assert "notebooks secretos" not in response.json()["detail"]
    assert client.get("/requisicoes").json()["total"] == 0


def test_post_agent_catalog_unavailable_returns_controlled_message(
    client, mock_agent_runtime
) -> None:
    from app.agent.runner_factory import AgentRunResult
    from app.schemas.requisicao import AgentStructuredOutput
    from app.services.requisicao_service import USER_CATALOG_UNAVAILABLE

    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="catalog_unavailable",
                resposta_agente="SQLAlchemy IntegrityError no host postgres.",
                itens=[],
            ),
            raw_text="{}",
        )
    )
    response = client.post("/requisicoes", json={"pedido": "Preciso de notebooks"})
    assert response.status_code == 503
    assert response.json()["detail"] == USER_CATALOG_UNAVAILABLE
    assert "IntegrityError" not in response.json()["detail"]
    assert "postgres" not in response.json()["detail"]
    assert client.get("/requisicoes").json()["total"] == 0


def test_post_serializes_empty_ferramentas_when_agent_used_none(
    client, mock_agent_runtime
) -> None:
    from app.agent.runner_factory import AgentRunResult
    from app.schemas.requisicao import AgentItemSelection, AgentStructuredOutput

    mock_agent_runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="success",
                resposta_agente="ok",
                itens=[AgentItemSelection(produto_id=7, titulo="Laptop", quantidade=1)],
            ),
            raw_text="{}",
            search_product_ids=frozenset({7}),
            search_observed=True,
            ferramentas_utilizadas=[],
        )
    )
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
    ):
        response = client.post("/requisicoes", json={"pedido": "Preciso de notebooks"})
    assert response.status_code == 201
    assert response.json()["ferramentas_utilizadas"] == []
