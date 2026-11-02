"""Tests for extracting buscar_produtos IDs from ADK function responses."""

from types import SimpleNamespace

from app.agent.search_ids import collect_search_ids, parse_buscar_produtos_response


def test_parse_success_payload() -> None:
    ids, recognized = parse_buscar_produtos_response(
        {"status": "success", "products": [{"id": 78}, {"id": 80}]}
    )
    assert recognized is True
    assert ids == frozenset({78, 80})


def test_parse_empty_payload() -> None:
    ids, recognized = parse_buscar_produtos_response({"status": "empty", "products": []})
    assert recognized is True
    assert ids == frozenset()


def test_parse_nested_result_json() -> None:
    ids, recognized = parse_buscar_produtos_response(
        {"result": '{"status": "success", "products": [{"id": 7}]}'}
    )
    assert recognized is True
    assert ids == frozenset({7})


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
    ids, observed = collect_search_ids(responses)
    assert observed is True
    assert ids == frozenset({78, 80})
    assert 99 not in ids


def test_collect_unobserved_when_search_was_not_called() -> None:
    ids, observed = collect_search_ids(
        [SimpleNamespace(name="detalhar_produto", response={"product": {"id": 1}})]
    )
    assert observed is False
    assert ids == frozenset()


def test_parse_unrecognized_payload() -> None:
    ids, recognized = parse_buscar_produtos_response({"unexpected": True})
    assert recognized is False
    assert ids == frozenset()


def test_collect_observed_unrecognized_payload_yields_no_ids() -> None:
    ids, observed = collect_search_ids(
        [SimpleNamespace(name="buscar_produtos", response={"unexpected": True})]
    )
    assert observed is True
    assert ids == frozenset()
