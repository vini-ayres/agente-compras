"""MCP server exposing DummyJSON catalog tools over Streamable HTTP."""

from __future__ import annotations

import logging

import uvicorn
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from config import Settings, get_settings
from dummyjson_client import DummyJsonClient
from tools.buscar_produtos import execute_buscar_produtos
from tools.detalhar_produto import execute_detalhar_produto

logger = logging.getLogger(__name__)

settings: Settings = get_settings()
dummyjson_client = DummyJsonClient(settings)

mcp = MCPServer("purchase-agent-catalog")


def _transport_security(settings: Settings) -> TransportSecuritySettings:
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=settings.enable_dns_rebinding_protection,
        allowed_hosts=settings.allowed_hosts_list(),
    )


@mcp.tool(name="buscar_produtos")
async def buscar_produtos(termo: str) -> dict:
    """
    Busca produtos no catálogo DummyJSON pelo termo informado.

    Args:
        termo: Texto de busca (ex.: laptop, phone).
    """
    logger.info("MCP tool buscar_produtos termo=%s", termo)
    return await execute_buscar_produtos(termo, dummyjson_client)


@mcp.tool(name="detalhar_produto")
async def detalhar_produto(id: int) -> dict:
    """
    Retorna detalhes de um produto pelo identificador numérico.

    Args:
        id: Identificador do produto no catálogo DummyJSON.
    """
    logger.info("MCP tool detalhar_produto id=%s", id)
    return await execute_detalhar_produto(id, dummyjson_client)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request):
    """Liveness probe for Docker and orchestrators."""
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok"})


app = mcp.streamable_http_app(
    streamable_http_path=settings.streamable_http_path,
    transport_security=_transport_security(settings),
)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info(
        "Starting MCP server on %s:%s%s",
        settings.host,
        settings.port,
        settings.streamable_http_path,
    )
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
