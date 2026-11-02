"""Tests for executed MCP tool name collection."""

from types import SimpleNamespace

from app.agent.tool_names import collect_executed_tool_names


def test_captures_buscar_produtos() -> None:
    names = collect_executed_tool_names(
        [SimpleNamespace(name="buscar_produtos", response={"status": "success"})]
    )
    assert names == ["buscar_produtos"]


def test_captures_detalhar_produto() -> None:
    names = collect_executed_tool_names(
        [SimpleNamespace(name="detalhar_produto", response={"status": "success"})]
    )
    assert names == ["detalhar_produto"]


def test_filters_set_model_response() -> None:
    names = collect_executed_tool_names(
        [
            SimpleNamespace(name="buscar_produtos", response={}),
            SimpleNamespace(name="set_model_response", response={"status": "success"}),
            SimpleNamespace(name="detalhar_produto", response={}),
        ]
    )
    assert names == ["buscar_produtos", "detalhar_produto"]
    assert "set_model_response" not in names


def test_absence_of_executed_tools() -> None:
    assert collect_executed_tool_names([]) == []
    assert collect_executed_tool_names([SimpleNamespace(response={})]) == []
    assert collect_executed_tool_names([SimpleNamespace(name="  ", response={})]) == []


def test_deduplicates_preserving_first_execution_order() -> None:
    names = collect_executed_tool_names(
        [
            SimpleNamespace(name="buscar_produtos", response={}),
            SimpleNamespace(name="detalhar_produto", response={}),
            SimpleNamespace(name="buscar_produtos", response={}),
            SimpleNamespace(name="detalhar_produto", response={}),
        ]
    )
    assert names == ["buscar_produtos", "detalhar_produto"]
