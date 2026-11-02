"""Schema validation tests."""

import pytest
from pydantic import ValidationError

from app.schemas.requisicao import AgentStructuredOutput, CriarRequisicaoRequest


def test_criar_requisicao_request_strips_and_validates() -> None:
    req = CriarRequisicaoRequest(pedido="  Preciso de notebooks  ")
    assert req.pedido == "Preciso de notebooks"


def test_criar_requisicao_request_rejects_short_pedido() -> None:
    with pytest.raises(ValidationError):
        CriarRequisicaoRequest(pedido="ab")


def test_agent_structured_output_success_requires_items() -> None:
    with pytest.raises(ValidationError):
        AgentStructuredOutput(
            status="success",
            resposta_agente="ok",
            itens=[],
        )


def test_agent_structured_output_non_success_rejects_items() -> None:
    from app.schemas.requisicao import AgentItemSelection

    with pytest.raises(ValidationError):
        AgentStructuredOutput(
            status="no_products",
            resposta_agente="Não encontrei produtos.",
            itens=[AgentItemSelection(produto_id=1, titulo="X", quantidade=1)],
        )


def test_agent_item_quantity_has_upper_bound() -> None:
    from app.schemas.requisicao import AgentItemSelection

    with pytest.raises(ValidationError):
        AgentItemSelection(produto_id=1, titulo="X", quantidade=1001)
