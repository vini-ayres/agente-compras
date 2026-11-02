"""Pytest fixtures for backend tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.database.connection as db_connection
from app.agent.runner_factory import AgentRunResult, AgentRuntime
from app.config import Settings
from app.database.connection import get_db_session
from app.database.models import Base
from app.main import create_app
from app.schemas.requisicao import AgentItemSelection, AgentStructuredOutput


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        gemini_api_key="test-gemini-key",
        llm_model="gemini/gemini-3.6-flash",
        openrouter_api_key="legacy-openrouter-key",
        openrouter_model="openrouter/xingchen-agi/xing4.0-29b-a4b:free",
        mcp_server_url="http://localhost:8080/mcp",
    )


@pytest.fixture
def db_engine(settings: Settings):
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)

    db_connection._engine = engine  # noqa: SLF001
    db_connection._SessionLocal = sessionmaker(  # noqa: SLF001
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )

    yield engine
    Base.metadata.drop_all(bind=engine)
    db_connection._engine = None  # noqa: SLF001
    db_connection._SessionLocal = None  # noqa: SLF001


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    session_local = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)
    db = session_local()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def mock_agent_runtime() -> MagicMock:
    runtime = MagicMock(spec=AgentRuntime)
    runtime.run_pedido = AsyncMock(
        return_value=AgentRunResult(
            structured=AgentStructuredOutput(
                status="success",
                resposta_agente="Encontrei uma opção compatível.",
                itens=[
                    AgentItemSelection(produto_id=7, titulo="Laptop", quantidade=3),
                ],
            ),
            raw_text="{}",
        )
    )
    runtime.close = AsyncMock()
    return runtime


@pytest.fixture
def client(db_engine, settings: Settings, mock_agent_runtime: MagicMock) -> Generator[TestClient, None, None]:
    app = create_app(settings)
    app.state.agent_runtime = mock_agent_runtime

    session_local = db_connection.get_session_factory()

    def override_db() -> Generator[Session, None, None]:
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db_session] = override_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
