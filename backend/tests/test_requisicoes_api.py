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


def test_post_catalog_unavailable_returns_503(client) -> None:
    from app.services.catalog_validation import CatalogUnavailableError

    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(side_effect=CatalogUnavailableError("Catálogo indisponível.")),
    ):
        response = client.post("/requisicoes", json={"pedido": "Preciso de notebooks"})
    assert response.status_code == 503
