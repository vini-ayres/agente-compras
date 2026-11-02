"""Idempotency tests for POST /requisicoes."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.database.repository import RequisicaoRepository
from app.schemas.requisicao import CriarRequisicaoRequest, ValidatedLineItem
from app.services.requisicao_service import IdempotencyConflictError, RequisicaoService


def _validated_item() -> list[ValidatedLineItem]:
    return [
        ValidatedLineItem(
            produto_id=7,
            titulo="Laptop",
            quantidade=3,
            preco_unitario=Decimal("999.99"),
            subtotal=Decimal("2999.97"),
        )
    ]


def test_idempotency_first_call_creates(client) -> None:
    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(return_value=_validated_item()),
    ):
        response = client.post(
            "/requisicoes",
            json={"pedido": "Preciso de 3 notebooks"},
            headers={"Idempotency-Key": "key-create-1"},
        )
    assert response.status_code == 201
    assert response.json()["id"] == 1


def test_idempotency_replay_same_payload(client) -> None:
    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(return_value=_validated_item()),
    ):
        first = client.post(
            "/requisicoes",
            json={"pedido": "Preciso de 3 notebooks"},
            headers={"Idempotency-Key": "key-replay"},
        )
        second = client.post(
            "/requisicoes",
            json={"pedido": "Preciso de 3 notebooks"},
            headers={"Idempotency-Key": "key-replay"},
        )
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["ferramentas_utilizadas"] == [
        {"nome": "buscar_produtos", "origem": "agent", "status": "success"},
        {"nome": "detalhar_produto", "origem": "agent", "status": "success"},
    ]
    assert second.json()["ferramentas_utilizadas"] == []
    listed = client.get("/requisicoes")
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["ferramentas_utilizadas"] == []


def test_idempotency_same_key_different_payload(client) -> None:
    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(return_value=_validated_item()),
    ):
        first = client.post(
            "/requisicoes",
            json={"pedido": "Preciso de 3 notebooks"},
            headers={"Idempotency-Key": "key-conflict"},
        )
        second = client.post(
            "/requisicoes",
            json={"pedido": "Preciso de 1 smartphone"},
            headers={"Idempotency-Key": "key-conflict"},
        )
    assert first.status_code == 201
    assert second.status_code == 409


def test_idempotency_different_keys_create_two(client) -> None:
    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(return_value=_validated_item()),
    ):
        first = client.post(
            "/requisicoes",
            json={"pedido": "Preciso de 3 notebooks"},
            headers={"Idempotency-Key": "key-a"},
        )
        second = client.post(
            "/requisicoes",
            json={"pedido": "Preciso de 3 notebooks"},
            headers={"Idempotency-Key": "key-b"},
        )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    listed = client.get("/requisicoes")
    assert listed.json()["total"] == 2


def test_idempotency_without_header_creates_duplicates(client) -> None:
    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(return_value=_validated_item()),
    ):
        first = client.post("/requisicoes", json={"pedido": "Preciso de 3 notebooks"})
        second = client.post("/requisicoes", json={"pedido": "Preciso de 3 notebooks"})
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_save_idempotency_is_unique(db_session) -> None:
    repo = RequisicaoRepository(db_session)
    requisicao = repo.create(
        pedido_original="pedido",
        resposta_agente="resumo",
        itens=_validated_item(),
        valor_total=Decimal("2999.97"),
    )
    assert repo.save_idempotency("same-key", "hash-a", requisicao.id) is True
    assert repo.save_idempotency("same-key", "hash-a", requisicao.id) is False
    db_session.commit()


def test_idempotency_failed_persist_does_not_lock_key(client) -> None:
    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(return_value=_validated_item()),
    ), patch(
        "app.services.requisicao_service.RequisicaoRepository.create",
        side_effect=SQLAlchemyError("db fail"),
    ):
        failed = client.post(
            "/requisicoes",
            json={"pedido": "Preciso de 3 notebooks"},
            headers={"Idempotency-Key": "key-retry"},
        )
    assert failed.status_code == 503

    with patch(
        "app.services.requisicao_service.validate_and_price_items",
        new=AsyncMock(return_value=_validated_item()),
    ):
        retry = client.post(
            "/requisicoes",
            json={"pedido": "Preciso de 3 notebooks"},
            headers={"Idempotency-Key": "key-retry"},
        )
    assert retry.status_code == 201
    assert client.get("/requisicoes").json()["total"] == 1


@pytest.mark.asyncio
async def test_idempotency_concurrent_same_key_persists_once(
    db_engine, mock_agent_runtime
) -> None:
    session_local = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)
    db1 = session_local()
    db2 = session_local()
    try:
        service1 = RequisicaoService(db1, mock_agent_runtime, "http://localhost:8080/mcp")
        service2 = RequisicaoService(db2, mock_agent_runtime, "http://localhost:8080/mcp")
        body = CriarRequisicaoRequest(pedido="Preciso de 3 notebooks")
        with patch(
            "app.services.requisicao_service.validate_and_price_items",
            new=AsyncMock(return_value=_validated_item()),
        ):
            results = await asyncio.gather(
                service1.criar_requisicao(body, idempotency_key="key-concurrent"),
                service2.criar_requisicao(body, idempotency_key="key-concurrent"),
                return_exceptions=True,
            )
        outcomes = [item for item in results if not isinstance(item, BaseException)]
        errors = [item for item in results if isinstance(item, BaseException)]
        for error in errors:
            assert isinstance(error, IdempotencyConflictError)
        assert len(outcomes) >= 1
        assert sum(1 for item in outcomes if item.created) <= 1
        for item in outcomes:
            if item.created:
                assert item.requisicao.ferramentas_utilizadas
            else:
                assert item.requisicao.ferramentas_utilizadas == []
        inspector = session_local()
        try:
            _rows, total = RequisicaoRepository(inspector).list_requisicoes(limit=10, offset=0)
            assert total == 1
        finally:
            inspector.close()
    finally:
        db1.close()
        db2.close()
