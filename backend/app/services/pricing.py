"""Monetary calculations using Decimal."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.schemas.requisicao import ValidatedLineItem

MONEY_QUANT = Decimal("0.01")


def decimal_from_catalog(value: object) -> Decimal:
    """Convert a catalog price to Decimal without float arithmetic.

    Accepts int, Decimal and numeric strings (including ``0``).
    Rejects None, empty values, bool, float, negatives and non-numeric input.
    """
    if value is None:
        raise ValueError("Preço ausente no catálogo.")
    if isinstance(value, bool):
        raise ValueError("Preço em formato inválido.")
    if isinstance(value, float):
        raise ValueError("Preço em formato inválido.")
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Preço ausente no catálogo.")
        raw = cleaned
    elif isinstance(value, Decimal):
        raw = value
    elif isinstance(value, int):
        raw = value
    else:
        raise ValueError("Preço em formato inválido.")

    try:
        amount = raw if isinstance(raw, Decimal) else Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Preço em formato inválido.") from exc

    if not amount.is_finite():
        raise ValueError("Preço em formato inválido.")
    if amount < 0:
        raise ValueError("Preço não pode ser negativo.")
    return amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def line_subtotal(quantidade: int, preco_unitario: Decimal) -> Decimal:
    if quantidade <= 0:
        raise ValueError("Quantidade deve ser positiva.")
    if not isinstance(preco_unitario, Decimal):
        raise TypeError("preco_unitario deve ser Decimal.")
    return (preco_unitario * Decimal(quantidade)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def total_from_lines(itens: list[ValidatedLineItem]) -> Decimal:
    total = Decimal("0.00")
    for item in itens:
        total += item.subtotal
    return total.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
