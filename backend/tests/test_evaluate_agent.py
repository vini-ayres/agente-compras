"""Tests for the deterministic evaluation harness."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from app.agent.runner_factory import AgentRunResult
from app.schemas.requisicao import AgentItemSelection, AgentStructuredOutput
from evals.runner import (
    POINTS_PER_SCENARIO,
    TOTAL_POINTS,
    format_report,
    run_evaluation,
    run_scenario,
)
from evals.scenarios import build_scenarios


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_all_canonical_scenarios_pass() -> None:
    report = await run_evaluation()
    assert len(report.results) == 5
    assert report.passed is True
    assert report.score == TOTAL_POINTS
    for result in report.results:
        assert result.passed is True
        assert result.score == POINTS_PER_SCENARIO


@pytest.mark.asyncio
async def test_negative_scenarios_do_not_persist() -> None:
    report = await run_evaluation()
    by_id = {item.scenario.id: item for item in report.results}
    for scenario_id in ("nenhum_produto", "solicitacao_ambigua", "falha_catalogo", "fora_da_busca"):
        assert "persistidas=0" in by_id[scenario_id].obtained or "persistidas=0" in " ".join(
            criterion.detail for criterion in by_id[scenario_id].criteria
        )
        assert all(
            criterion.passed
            for criterion in by_id[scenario_id].criteria
            if "persist" in criterion.name
        )


@pytest.mark.asyncio
async def test_valid_purchase_uses_search_and_price_limit() -> None:
    scenario = next(item for item in build_scenarios() if item.id == "compra_valida")
    result = await run_scenario(scenario)
    assert result.passed is True
    assert "unitário=1999.99" in result.obtained
    assert "total=5999.97" in result.obtained
    assert scenario.expected_product_id in scenario.agent_result.search_product_ids
    assert Decimal("1999.99") <= scenario.max_unit_price


@pytest.mark.asyncio
async def test_scenario_fails_when_quantity_is_wrong() -> None:
    original = next(item for item in build_scenarios() if item.id == "compra_valida")
    broken = AgentRunResult(
        structured=AgentStructuredOutput(
            status="success",
            resposta_agente="Selecionei um laptop.",
            itens=[AgentItemSelection(produto_id=7, titulo="Laptop", quantidade=1)],
        ),
        raw_text="{}",
        search_product_ids=original.agent_result.search_product_ids,
        search_observed=True,
    )
    mutated = replace(original, agent_result=broken)
    result = await run_scenario(mutated)
    assert result.passed is False
    assert result.score == 0
    failed = [item.name for item in result.criteria if not item.passed]
    assert "quantidade respeitada" in failed


@pytest.mark.asyncio
async def test_illicit_id_existing_in_catalog_is_still_rejected() -> None:
    scenario = next(item for item in build_scenarios() if item.id == "fora_da_busca")
    result = await run_scenario(scenario)
    assert result.passed is True
    assert scenario.illicit_catalog_id not in scenario.agent_result.search_product_ids


def test_report_lists_failed_criteria() -> None:
    from evals.runner import CriterionResult, EvaluationReport, ScenarioResult
    from evals.scenarios import build_scenarios

    scenario = build_scenarios()[1]
    result = ScenarioResult(
        scenario=scenario,
        obtained="persistiu indevidamente",
        criteria=[
            CriterionResult("nenhuma requisição persistida", False, "persistidas=1"),
            CriterionResult("informa que não foram encontrados produtos", True, "ok"),
        ],
    )
    text = format_report(EvaluationReport(results=[result]))
    assert scenario.name in text
    assert "[falhou] nenhuma requisição persistida" in text
    assert "0/100" in text or "Pontuação final: 0/" in text


def test_evaluate_script_exits_zero() -> None:
    script = _repo_root() / "backend" / "scripts" / "evaluate_agent.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=_repo_root(),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Pontuação final: 100/100" in completed.stdout
    assert "Não mede a qualidade de um LLM real" in completed.stdout
    assert "Compra válida" in completed.stdout
    assert "Nenhum produto encontrado" in completed.stdout
    assert "Solicitação ambígua" in completed.stdout
    assert "Falha no catálogo" in completed.stdout
    assert "Produto fora dos resultados da busca" in completed.stdout
