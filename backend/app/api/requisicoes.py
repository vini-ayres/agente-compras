"""Requisition REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database.connection import get_db_session
from app.schemas.requisicao import CriarRequisicaoRequest, RequisicaoListResponse, RequisicaoOut
from app.services.catalog_validation import (
    CatalogUnavailableError,
    InvalidCatalogPriceError,
    InvalidCatalogProductError,
    InvalidCatalogTitleError,
    ProductNotFoundError,
)
from app.services.requisicao_service import (
    AgentInvalidOutputError,
    AgentUnavailableError,
    BusinessRuleError,
    CatalogUnavailableBusinessError,
    InsufficientInfoError,
    NoProductsError,
    PersistenceError,
    RequisicaoService,
)

router = APIRouter(prefix="/requisicoes", tags=["requisicoes"])


def get_requisicao_service(
    request: Request,
    db: Session = Depends(get_db_session),
) -> RequisicaoService:
    runtime = request.app.state.agent_runtime
    settings = request.app.state.settings
    return RequisicaoService(
        db,
        runtime,
        settings.mcp_server_url,
        timeout_seconds=settings.mcp_connect_timeout_seconds,
        sse_read_timeout_seconds=settings.mcp_sse_read_timeout_seconds,
    )


@router.post("", response_model=RequisicaoOut, status_code=201)
async def criar_requisicao(
    body: CriarRequisicaoRequest,
    service: RequisicaoService = Depends(get_requisicao_service),
) -> RequisicaoOut:
    try:
        return await service.criar_requisicao(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Pedido inválido.") from exc
    except NoProductsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InsufficientInfoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (InvalidCatalogPriceError, InvalidCatalogTitleError, InvalidCatalogProductError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AgentInvalidOutputError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except AgentUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CatalogUnavailableBusinessError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CatalogUnavailableError:
        raise HTTPException(status_code=503, detail="Catálogo indisponível. Tente novamente em instantes.") from None
    except BusinessRuleError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=RequisicaoListResponse)
def listar_requisicoes(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: RequisicaoService = Depends(get_requisicao_service),
) -> RequisicaoListResponse:
    return service.listar(limit=limit, offset=offset)
