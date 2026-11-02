"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.runner_factory import build_agent_runtime
from app.api.requisicoes import router as requisicoes_router
from app.config import Settings, get_settings
from app.database.connection import get_engine, init_engine
from app.database.models import Base

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = getattr(app.state, "bootstrap_settings", None) or get_settings()
    app.state.settings = settings
    logging.basicConfig(level=settings.log_level)

    init_engine(settings)
    Base.metadata.create_all(bind=get_engine())

    if getattr(app.state, "agent_runtime", None) is None:
        app.state.agent_runtime = build_agent_runtime(settings)
    agent_runtime = app.state.agent_runtime

    logger.info("Backend iniciado (app=%s model=%s)", settings.app_name, settings.llm_model)
    try:
        yield
    finally:
        await agent_runtime.close()
        logger.info("Backend encerrado; conexões MCP finalizadas.")


def _cors_origins(settings: Settings) -> list[str]:
    return [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Purchase Agent API", lifespan=lifespan)
    cors_settings = settings or get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(cors_settings),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(requisicoes_router)

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    if settings is not None:
        app.state.bootstrap_settings = settings
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    cfg = get_settings()
    uvicorn.run(
        "app.main:app",
        host=cfg.api_host,
        port=cfg.api_port,
        reload=False,
    )
