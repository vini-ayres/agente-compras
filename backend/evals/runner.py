"""Run isolated evaluation scenarios against RequisicaoService."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.runner_factory import AgentRuntime
from app.database.models import Base
from app.schemas.requisicao import CriarRequisicaoRequest
from app.services.catalog_validation import ProductNotInSearchError
from app.services.requisicao_service import (
    USER_CATALOG_UNAVAILABLE,
    USER_INSUFFICIENT_INFO,
    USER_NO_PRODUCTS,
    CatalogUnavailableBusinessError,
    InsufficientInfoError,
    NoProductsError,
    RequisicaoService,
)
from evals.catalog import SIMULATED_PRODUCTS, SimulatedCatalogClient
from evals.scenarios import Scenario, build_scenarios

POINTS_PER_SCENARIO = 20
TOTAL_POINTS = POINTS_PER_SCENARIO * 5


@dataclass
class CriterionResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ScenarioResult:
    scenario: Scenario
    obtained: str
    criteria: list[CriterionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.criteria) and all(item.passed for item in self.criteria)

    @property
    def score(self) -> int:
        return POINTS_PER_SCENARIO if self.passed else 0


@dataclass
class EvaluationReport:
    results: list[ScenarioResult]

    @property
    def score(self) -> int:
        return sum(item.score for item in self.results)

    @property
    def passed(self) -> bool:
        return len(self.results) == 5 and all(item.passed for item in self.results)


def _criterion(name: str, passed: bool, detail: str) -> CriterionResult:
    return CriterionResult(name=name, passed=passed, detail=detail)


def _session() -> tuple[Session, object]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory(), engine


def _runtime_for(scenario: Scenario) -> MagicMock:
    runtime = MagicMock(spec=AgentRuntime)
    runtime.run_pedido = AsyncMock(return_value=scenario.agent_result)
    runtime.close = AsyncMock()
    return runtime


def _user_text(error: BaseException | None) -> str:
    return str(error) if error is not None else ""


async def _execute(scenario: Scenario) -> tuple[object | None, BaseException | None, int, SimulatedCatalogClient]:
    db, engine = _session()
    catalog = SimulatedCatalogClient(unavailable=scenario.catalog_unavailable)
    service = RequisicaoService(db, _runtime_for(scenario), "http://eval.local/mcp")
    service._mcp_catalog = catalog  # noqa: SLF001 — eval harness only
    error: BaseException | None = None
    outcome = None
    try:
        try:
            outcome = await service.criar_requisicao(CriarRequisicaoRequest(pedido=scenario.prompt))
        except Exception as exc:  # noqa: BLE001 — captured as scenario outcome
            error = exc
        persisted = service.listar(limit=10, offset=0).total
    finally:
        db.close()
        engine.dispose()
    return outcome, error, persisted, catalog


def _evaluate_compra_valida(
    scenario: Scenario, outcome: object | None, error: BaseException | None, persisted: int
) -> tuple[str, list[CriterionResult]]:
    from app.services.requisicao_service import CreateRequisicaoResult

    if not isinstance(outcome, CreateRequisicaoResult) or error is not None:
        return (
            f"falhou: {type(error).__name__ if error else 'sem resultado'}: {_user_text(error)}",
            [
                _criterion("requisição persistida", False, "criar_requisicao não concluiu com sucesso"),
            ],
        )
    req = outcome.requisicao
    items = req.itens
    item = items[0] if items else None
    unit = Decimal(item.preco_unitario) if item else Decimal("-1")
    total = Decimal(req.valor_total)
    expected_total = (unit * Decimal(item.quantidade)).quantize(Decimal("0.01")) if item else Decimal("0")
    search_ids = scenario.agent_result.search_product_ids
    criteria = [
        _criterion(
            "produtos encontrados no catálogo simulado",
            item is not None and item.produto_id in SIMULATED_PRODUCTS,
            f"produto_id={item.produto_id if item else None}",
        ),
        _criterion(
            "produto pertence à busca da execução",
            item is not None and item.produto_id in search_ids,
            f"id={item.produto_id if item else None} busca={sorted(search_ids)}",
        ),
        _criterion(
            "quantidade respeitada",
            item is not None and item.quantidade == scenario.expected_quantity,
            f"quantidade={item.quantidade if item else None} esperada={scenario.expected_quantity}",
        ),
        _criterion(
            "preço unitário dentro do limite",
            item is not None and scenario.max_unit_price is not None and unit <= scenario.max_unit_price,
            f"unitário={unit} limite={scenario.max_unit_price}",
        ),
        _criterion(
            "total calculado corretamente",
            item is not None and total == expected_total,
            f"total={total} esperado={expected_total}",
        ),
        _criterion(
            "requisição persistida com sucesso",
            outcome.created is True and persisted == 1,
            f"created={outcome.created} persistidas={persisted}",
        ),
    ]
    obtained = (
        f"persistida id={req.id}, produto={item.produto_id if item else None}, "
        f"qtd={item.quantidade if item else None}, unitário={unit}, total={total}"
    )
    return obtained, criteria


def _evaluate_nenhum_produto(
    error: BaseException | None, persisted: int
) -> tuple[str, list[CriterionResult]]:
    text = _user_text(error)
    criteria = [
        _criterion(
            "catálogo sem produtos compatíveis",
            isinstance(error, NoProductsError),
            f"erro={type(error).__name__ if error else None}",
        ),
        _criterion(
            "não inventa produtos",
            "reator" not in text.lower() and "1.00" not in text,
            f"mensagem={text!r}",
        ),
        _criterion(
            "nenhuma requisição persistida",
            persisted == 0,
            f"persistidas={persisted}",
        ),
        _criterion(
            "informa que não foram encontrados produtos",
            text == USER_NO_PRODUCTS,
            f"mensagem={text!r}",
        ),
    ]
    return f"{type(error).__name__ if error else 'sucesso'}: {text}", criteria


def _evaluate_ambigua(
    error: BaseException | None, persisted: int
) -> tuple[str, list[CriterionResult]]:
    text = _user_text(error)
    criteria = [
        _criterion(
            "não inventa especificações ou quantidades",
            "cadeira" not in text.lower() and "0.01" not in text,
            f"mensagem={text!r}",
        ),
        _criterion(
            "solicita informações adicionais",
            isinstance(error, InsufficientInfoError) and text == USER_INSUFFICIENT_INFO,
            f"erro={type(error).__name__ if error else None} mensagem={text!r}",
        ),
        _criterion(
            "não persiste requisição incompleta",
            persisted == 0,
            f"persistidas={persisted}",
        ),
    ]
    return f"{type(error).__name__ if error else 'sucesso'}: {text}", criteria


def _evaluate_falha_catalogo(
    error: BaseException | None, persisted: int
) -> tuple[str, list[CriterionResult]]:
    text = _user_text(error)
    lowered = text.lower()
    criteria = [
        _criterion(
            "resposta de erro amigável",
            isinstance(error, CatalogUnavailableBusinessError) and text == USER_CATALOG_UNAVAILABLE,
            f"erro={type(error).__name__ if error else None} mensagem={text!r}",
        ),
        _criterion(
            "não persiste requisição inválida",
            persisted == 0,
            f"persistidas={persisted}",
        ),
        _criterion(
            "não expõe traceback nem detalhes internos",
            "traceback" not in lowered
            and "integrityerror" not in lowered
            and "dummyjson" not in lowered
            and "sqlalchemy" not in lowered,
            f"mensagem={text!r}",
        ),
    ]
    return f"{type(error).__name__ if error else 'sucesso'}: {text}", criteria


def _evaluate_fora_da_busca(
    scenario: Scenario,
    error: BaseException | None,
    persisted: int,
    catalog: SimulatedCatalogClient,
) -> tuple[str, list[CriterionResult]]:
    illicit = scenario.illicit_catalog_id
    criteria = [
        _criterion(
            "backend rejeita seleção fora da busca",
            isinstance(error, ProductNotInSearchError),
            f"erro={type(error).__name__ if error else None}",
        ),
        _criterion(
            "nenhuma requisição persistida",
            persisted == 0,
            f"persistidas={persisted}",
        ),
        _criterion(
            "não contorna a busca via produto existente no catálogo",
            illicit is not None
            and illicit in SIMULATED_PRODUCTS
            and illicit not in scenario.agent_result.search_product_ids
            and illicit not in catalog.detalhar_calls
            and persisted == 0,
            f"id={illicit} detalhar_chamadas={catalog.detalhar_calls}",
        ),
    ]
    return (
        f"{type(error).__name__ if error else 'sucesso'}: {_user_text(error)}",
        criteria,
    )


async def run_scenario(scenario: Scenario) -> ScenarioResult:
    outcome, error, persisted, catalog = await _execute(scenario)
    if scenario.id == "compra_valida":
        obtained, criteria = _evaluate_compra_valida(scenario, outcome, error, persisted)
    elif scenario.id == "nenhum_produto":
        obtained, criteria = _evaluate_nenhum_produto(error, persisted)
    elif scenario.id == "solicitacao_ambigua":
        obtained, criteria = _evaluate_ambigua(error, persisted)
    elif scenario.id == "falha_catalogo":
        obtained, criteria = _evaluate_falha_catalogo(error, persisted)
    elif scenario.id == "fora_da_busca":
        obtained, criteria = _evaluate_fora_da_busca(scenario, error, persisted, catalog)
    else:
        obtained, criteria = "cenário desconhecido", [
            _criterion("cenário conhecido", False, scenario.id)
        ]
    return ScenarioResult(scenario=scenario, obtained=obtained, criteria=criteria)


async def run_evaluation(scenarios: list[Scenario] | None = None) -> EvaluationReport:
    selected = scenarios if scenarios is not None else build_scenarios()
    results = [await run_scenario(item) for item in selected]
    return EvaluationReport(results=results)


def format_report(report: EvaluationReport) -> str:
    lines = [
        "Avaliação funcional do agente de compras",
        "Suíte determinística de regressão. Não mede a qualidade de um LLM real.",
        "",
    ]
    for result in report.results:
        status = "aprovado" if result.passed else "reprovado"
        lines.append(f"Cenário: {result.scenario.name}")
        lines.append(f"  Esperado: {result.scenario.expected}")
        lines.append(f"  Obtido:   {result.obtained}")
        lines.append(f"  Status:   {status}")
        lines.append(f"  Pontos:   {result.score}/{POINTS_PER_SCENARIO}")
        for criterion in result.criteria:
            mark = "ok" if criterion.passed else "falhou"
            lines.append(f"    [{mark}] {criterion.name} — {criterion.detail}")
        lines.append("")
    overall = "aprovado" if report.passed else "reprovado"
    lines.append(f"Pontuação final: {report.score}/{TOTAL_POINTS}")
    lines.append(f"Resultado geral: {overall}")
    return "\n".join(lines)
