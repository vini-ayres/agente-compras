"""HTTP client for the DummyJSON products API."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from config import Settings


def _map_price(raw: dict[str, Any]) -> str:
    if "price" not in raw or raw["price"] is None:
        raise DummyJsonInvalidResponseError("Product is missing price")
    try:
        amount = Decimal(str(raw["price"]))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DummyJsonInvalidResponseError("Invalid product price") from exc
    if not amount.is_finite() or amount < 0:
        raise DummyJsonInvalidResponseError("Invalid product price")
    return str(amount)


def map_product_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Map DummyJSON product JSON to the fields exposed by MCP tools."""
    price = _map_price(raw)

    stock_raw = raw.get("stock", 0)
    try:
        stock = int(stock_raw)
    except (TypeError, ValueError):
        stock = 0

    rating_raw = raw.get("rating")
    rating: float | None
    if rating_raw is None:
        rating = None
    else:
        try:
            rating = float(rating_raw)
        except (TypeError, ValueError):
            rating = None

    return {
        "id": raw.get("id"),
        "title": raw.get("title") or "",
        "description": raw.get("description") or "",
        "category": raw.get("category") or "",
        "price": price,
        "stock": stock,
        "rating": rating,
    }


class DummyJsonError(Exception):
    """Base error for DummyJSON communication failures."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


class DummyJsonTimeoutError(DummyJsonError):
    """Request exceeded the configured timeout."""

    def __init__(self, message: str = "DummyJSON request timed out") -> None:
        super().__init__(message, kind="timeout")


class DummyJsonConnectionError(DummyJsonError):
    """Network or transport failure reaching DummyJSON."""

    def __init__(self, message: str = "Could not connect to DummyJSON") -> None:
        super().__init__(message, kind="connection")


class DummyJsonNotFoundError(DummyJsonError):
    """Product was not found (HTTP 404)."""

    def __init__(self, product_id: int, message: str | None = None) -> None:
        msg = message or f"Product {product_id} not found"
        super().__init__(msg, kind="not_found")
        self.product_id = product_id


class DummyJsonHttpError(DummyJsonError):
    """Non-success HTTP status from DummyJSON (other than 404 on product detail)."""

    def __init__(self, status_code: int, message: str | None = None) -> None:
        msg = message or f"DummyJSON returned HTTP {status_code}"
        super().__init__(msg, kind="http_error")
        self.status_code = status_code


class DummyJsonInvalidResponseError(DummyJsonError):
    """Response body was missing expected fields or was not valid JSON."""

    def __init__(self, message: str = "Invalid response from DummyJSON") -> None:
        super().__init__(message, kind="invalid_response")


class DummyJsonClient:
    """Async HTTP client for product search and detail endpoints."""

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.dummyjson_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.http_timeout_seconds),
            headers={"Accept": "application/json"},
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search_products(self, term: str) -> dict[str, Any]:
        """GET /products/search?q={term}."""
        try:
            response = await self._client.get("/products/search", params={"q": term})
        except httpx.TimeoutException as exc:
            raise DummyJsonTimeoutError() from exc
        except httpx.RequestError as exc:
            raise DummyJsonConnectionError(str(exc)) from exc

        if response.status_code >= 400:
            raise DummyJsonHttpError(response.status_code, response.text[:200] or None)

        try:
            payload = response.json()
        except ValueError as exc:
            raise DummyJsonInvalidResponseError() from exc

        if not isinstance(payload, dict):
            raise DummyJsonInvalidResponseError("Search response must be a JSON object")

        return payload

    async def get_product(self, product_id: int) -> dict[str, Any]:
        """GET /products/{id}."""
        try:
            response = await self._client.get(f"/products/{product_id}")
        except httpx.TimeoutException as exc:
            raise DummyJsonTimeoutError() from exc
        except httpx.RequestError as exc:
            raise DummyJsonConnectionError(str(exc)) from exc

        if response.status_code == 404:
            raise DummyJsonNotFoundError(product_id)

        if response.status_code >= 400:
            raise DummyJsonHttpError(response.status_code, response.text[:200] or None)

        try:
            payload = response.json()
        except ValueError as exc:
            raise DummyJsonInvalidResponseError() from exc

        if not isinstance(payload, dict):
            raise DummyJsonInvalidResponseError("Product response must be a JSON object")

        return payload
