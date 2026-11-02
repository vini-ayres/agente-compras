"""Pydantic models for purchase requisition API."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CriarRequisicaoRequest(BaseModel):
    """POST /requisicoes body."""

    pedido: str = Field(..., min_length=3, max_length=4000)

    @field_validator("pedido")
    @classmethod
    def pedido_nao_vazio(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("O pedido deve conter ao menos 3 caracteres úteis.")
        return cleaned


class RequisicaoItemOut(BaseModel):
    """Line item returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    produto_id: int
    titulo: str
    quantidade: int
    preco_unitario: str
    subtotal: str


class RequisicaoOut(BaseModel):
    """Single requisition response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pedido_original: str
    resposta_agente: str
    itens: list[RequisicaoItemOut]
    valor_total: str
    created_at: datetime


class RequisicaoListResponse(BaseModel):
    """Paginated list of requisitions."""

    items: list[RequisicaoOut]
    total: int
    limit: int
    offset: int


class AgentItemSelection(BaseModel):
    """Structured item proposal from the agent (quantities/ids only are trusted after validation)."""

    produto_id: int = Field(gt=0)
    titulo: str = Field(min_length=1)
    quantidade: int = Field(gt=0)


class AgentStructuredOutput(BaseModel):
    """Final structured output enforced on the agent reply."""

    status: Literal["success", "no_products", "catalog_unavailable", "insufficient_info"]
    resposta_agente: str = Field(min_length=1)
    itens: list[AgentItemSelection] = Field(default_factory=list)


class ValidatedLineItem(BaseModel):
    """Backend-validated line with authoritative pricing."""

    produto_id: int
    titulo: str
    quantidade: int
    preco_unitario: Decimal
    subtotal: Decimal
