"""MCP tool handlers for catalog operations."""

from tools.buscar_produtos import execute_buscar_produtos
from tools.detalhar_produto import execute_detalhar_produto

__all__ = ["execute_buscar_produtos", "execute_detalhar_produto"]
