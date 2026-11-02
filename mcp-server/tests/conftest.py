"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from config import Settings
from dummyjson_client import DummyJsonClient


@pytest.fixture
def settings() -> Settings:
    return Settings(
        dummyjson_base_url="https://dummyjson.test",
        http_timeout_seconds=5.0,
    )


@pytest.fixture
async def dummyjson_client(settings: Settings) -> DummyJsonClient:
    client = DummyJsonClient(settings)
    yield client
    await client.aclose()
