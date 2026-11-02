"""In-memory catalog used by the evaluation harness (no DummyJSON/MCP)."""

from __future__ import annotations

from typing import Any

from app.services.catalog_validation import CatalogUnavailableError

# Product 99 exists in the simulated DummyJSON catalog but is withheld from
# search results in scenario 5, so persistence must not succeed via detalhar_produto.
SIMULATED_PRODUCTS: dict[int, dict[str, Any]] = {
    7: {"id": 7, "title": "Laptop", "price": "1999.99"},
    80: {"id": 80, "title": "Laptop Premium", "price": "2499.00"},
    99: {"id": 99, "title": "Smartphone", "price": "549.90"},
}

UNIT_PRICE_LIMIT = "2000.00"


class SimulatedCatalogClient:
    """Minimal stand-in for McpCatalogClient.detalhar_produto."""

    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.detalhar_calls: list[int] = []

    async def detalhar_produto(self, product_id: int) -> dict[str, Any]:
        self.detalhar_calls.append(product_id)
        if self.unavailable:
            raise CatalogUnavailableError("Catálogo indisponível.")
        product = SIMULATED_PRODUCTS.get(product_id)
        if product is None:
            return {"status": "not_found"}
        return {"status": "success", "product": dict(product)}
