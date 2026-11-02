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
    output = AgentStructuredOutput(
        status="success",
        resposta_agente="ok",
        itens=[],
    )
    assert output.status == "success"
