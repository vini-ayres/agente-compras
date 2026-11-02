"""Tests for executed MCP tool collection."""

from types import SimpleNamespace

from app.agent.tool_names import collect_executed_tools


def _as_dicts(executions) -> list[dict[str, str]]:
    return [item.model_dump() for item in executions]


def test_captures_buscar_produtos() -> None:
    executions = collect_executed_tools(
        [SimpleNamespace(name="buscar_produtos", response={"status": "success"})]
    )
    assert _as_dicts(executions) == [
        {"nome": "buscar_produtos", "origem": "agent", "status": "success"}
    ]


def test_captures_detalhar_produto() -> None:
    executions = collect_executed_tools(
        [SimpleNamespace(name="detalhar_produto", response={"status": "success"})]
    )
    assert _as_dicts(executions) == [
        {"nome": "detalhar_produto", "origem": "agent", "status": "success"}
    ]


def test_records_error_status_from_payload() -> None:
    executions = collect_executed_tools(
        [
            SimpleNamespace(
                name="buscar_produtos",
                response={"status": "error", "error_kind": "timeout", "products": []},
            )
        ]
    )
    assert executions[0].status == "error"
    assert executions[0].origem == "agent"


def test_empty_search_is_success() -> None:
    executions = collect_executed_tools(
        [SimpleNamespace(name="buscar_produtos", response={"status": "empty", "products": []})]
    )
    assert executions[0].status == "success"


def test_filters_set_model_response() -> None:
    executions = collect_executed_tools(
        [
            SimpleNamespace(name="buscar_produtos", response={}),
            SimpleNamespace(name="set_model_response", response={"status": "success"}),
            SimpleNamespace(name="detalhar_produto", response={}),
        ]
    )
    names = [item.nome for item in executions]
    assert names == ["buscar_produtos", "detalhar_produto"]
    assert "set_model_response" not in names


def test_absence_of_executed_tools() -> None:
    assert collect_executed_tools([]) == []
    assert collect_executed_tools([SimpleNamespace(response={})]) == []
    assert collect_executed_tools([SimpleNamespace(name="  ", response={})]) == []


def test_keeps_repeated_executions_in_order() -> None:
    executions = collect_executed_tools(
        [
            SimpleNamespace(name="buscar_produtos", response={"status": "success"}),
            SimpleNamespace(name="detalhar_produto", response={"status": "success"}),
            SimpleNamespace(name="buscar_produtos", response={"status": "empty"}),
        ]
    )
    assert [item.nome for item in executions] == [
        "buscar_produtos",
        "detalhar_produto",
        "buscar_produtos",
    ]


def test_is_error_flag_marks_failure() -> None:
    executions = collect_executed_tools(
        [
            SimpleNamespace(
                name="detalhar_produto",
                is_error=True,
                isError=True,
                response={"status": "error"},
            )
        ]
    )
    assert executions[0].status == "error"
