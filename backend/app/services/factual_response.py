"""Backend-authored commercial summary from validated catalog data."""

from __future__ import annotations

from decimal import Decimal

from app.schemas.requisicao import ValidatedLineItem


def format_money(value: Decimal) -> str:
    return str(value)


def build_factual_response(itens: list[ValidatedLineItem], valor_total: Decimal) -> str:
    """Build the persisted user-facing summary using only validated line items."""
    if not itens:
        raise ValueError("Resumo factual requer ao menos um item validado.")

    lines = ["Requisição validada com base no catálogo:"]
    for item in itens:
        lines.append(
            f"- {item.titulo} (id {item.produto_id}): "
            f"{item.quantidade} un. × {format_money(item.preco_unitario)} "
            f"= {format_money(item.subtotal)}"
        )
    lines.append(f"Total: {format_money(valor_total)}")
    return "\n".join(lines)
