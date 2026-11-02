"""Tests for extracting buscar_produtos IDs from ADK function responses."""

from types import SimpleNamespace

from app.agent.search_ids import collect_search_ids, parse_buscar_produtos_response


def test_parse_success_payload() -> None:
    parsed = parse_buscar_produtos_response(
        {"status": "success", "products": [{"id": 78}, {"id": 80}]}
    )
    assert parsed.recognized is True
    assert parsed.catalog_failed is False
    assert parsed.product_ids == frozenset({78, 80})


def test_parse_empty_payload() -> None:
    parsed = parse_buscar_produtos_response({"status": "empty", "products": []})
    assert parsed.recognized is True
    assert parsed.catalog_failed is False
    assert parsed.product_ids == frozenset()


def test_parse_infra_error_is_catalog_failure() -> None:
    parsed = parse_buscar_produtos_response(
        {
            "status": "error",
            "error_kind": "timeout",
            "message": "O catálogo está indisponível no momento.",
            "products": [],
        }
    )
    assert parsed.recognized is True
    assert parsed.catalog_failed is True
    assert parsed.product_ids == frozenset()


def test_parse_connection_error_is_catalog_failure() -> None:
    parsed = parse_buscar_produtos_response(
        {"status": "error", "error_kind": "connection", "products": []}
    )
    assert parsed.catalog_failed is True


def test_parse_bare_error_is_catalog_failure() -> None:
    parsed = parse_buscar_produtos_response({"status": "error", "products": []})
    assert parsed.recognized is True
    assert parsed.catalog_failed is True
    assert parsed.product_ids == frozenset()


def test_parse_invalid_input_is_not_catalog_failure() -> None:
    parsed = parse_buscar_produtos_response(
        {
            "status": "error",
            "error_kind": "invalid_input",
            "message": "O termo de busca não pode ser vazio.",
            "products": [],
        }
    )
    assert parsed.recognized is True
    assert parsed.catalog_failed is False
    assert parsed.product_ids == frozenset()


def test_parse_nested_result_json() -> None:
    parsed = parse_buscar_produtos_response(
        {"result": '{"status": "success", "products": [{"id": 7}]}'}
    )
    assert parsed.recognized is True
    assert parsed.catalog_failed is False
    assert parsed.product_ids == frozenset({7})


def test_parse_nested_infra_error() -> None:
    parsed = parse_buscar_produtos_response(
        {"result": '{"status": "error", "error_kind": "http_error", "products": []}'}
    )
    assert parsed.catalog_failed is True


def test_collect_ignores_other_tools_and_unions_searches() -> None:
    responses = [
        SimpleNamespace(name="detalhar_produto", response={"product": {"id": 99}}),
        SimpleNamespace(
            name="buscar_produtos",
            response={"status": "success", "products": [{"id": 78}]},
        ),
        SimpleNamespace(
            name="buscar_produtos",
            response={"status": "success", "products": [{"id": 80}]},
        ),
        SimpleNamespace(name="set_model_response", response={"status": "success"}),
    ]
    search = collect_search_ids(responses)
    assert search.observed is True
    assert search.catalog_failed is False
    assert search.product_ids == frozenset({78, 80})
    assert 99 not in search.product_ids


def test_collect_unobserved_when_search_was_not_called() -> None:
    search = collect_search_ids(
        [SimpleNamespace(name="detalhar_produto", response={"product": {"id": 1}})]
    )
    assert search.observed is False
    assert search.catalog_failed is False
    assert search.product_ids == frozenset()


def test_parse_unrecognized_payload() -> None:
    parsed = parse_buscar_produtos_response({"unexpected": True})
    assert parsed.recognized is False
    assert parsed.catalog_failed is False
    assert parsed.product_ids == frozenset()


def test_collect_observed_unrecognized_payload_yields_no_ids() -> None:
    search = collect_search_ids(
        [SimpleNamespace(name="buscar_produtos", response={"unexpected": True})]
    )
    assert search.observed is True
    assert search.catalog_failed is False
    assert search.product_ids == frozenset()


def test_collect_infra_error_marks_catalog_failed() -> None:
    search = collect_search_ids(
        [
            SimpleNamespace(
                name="buscar_produtos",
                response={"status": "error", "error_kind": "timeout", "products": []},
            )
        ]
    )
    assert search.observed is True
    assert search.catalog_failed is True
    assert search.product_ids == frozenset()


def test_collect_empty_search_is_not_catalog_failure() -> None:
    search = collect_search_ids(
        [
            SimpleNamespace(
                name="buscar_produtos",
                response={"status": "empty", "products": [], "total": 0},
            )
        ]
    )
    assert search.observed is True
    assert search.catalog_failed is False
    assert search.product_ids == frozenset()


def test_collect_success_after_infra_error_keeps_catalog_up() -> None:
    search = collect_search_ids(
        [
            SimpleNamespace(
                name="buscar_produtos",
                response={"status": "error", "error_kind": "timeout", "products": []},
            ),
            SimpleNamespace(
                name="buscar_produtos",
                response={"status": "success", "products": [{"id": 7}]},
            ),
        ]
    )
    assert search.catalog_failed is False
    assert search.product_ids == frozenset({7})
