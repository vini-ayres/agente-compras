"""Tests for backend-authored factual summaries."""

from decimal import Decimal

import pytest

from app.schemas.requisicao import ValidatedLineItem
from app.services.factual_response import build_factual_response


def test_factual_response_uses_validated_catalog_values() -> None:
    items = [
        ValidatedLineItem(
            produto_id=78,
            titulo="Apple MacBook Pro 14 Inch Space Grey",
            quantidade=3,
            preco_unitario=Decimal("1999.99"),
            subtotal=Decimal("5999.97"),
        )
    ]
    text = build_factual_response(items, Decimal("5999.97"))
    assert "Apple MacBook Pro 14 Inch Space Grey" in text
    assert "(id 78)" in text
    assert "3 un." in text
    assert "1999.99" in text
    assert "5999.97" in text
    assert "Total: 5999.97" in text
    assert "32 GB" not in text
    assert "tela sensível" not in text


def test_factual_response_rejects_empty_items() -> None:
    with pytest.raises(ValueError):
        build_factual_response([], Decimal("0.00"))
