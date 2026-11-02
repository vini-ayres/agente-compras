"""Canonical evaluation scenarios. Agent outputs are fixtures, not live LLM calls."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.agent.runner_factory import AgentRunResult
from app.schemas.requisicao import AgentItemSelection, AgentStructuredOutput
from evals.catalog import UNIT_PRICE_LIMIT


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    prompt: str
    expected: str
    agent_result: AgentRunResult
    catalog_unavailable: bool = False
    expected_quantity: int | None = None
    expected_product_id: int | None = None
    max_unit_price: Decimal | None = None
    illicit_catalog_id: int | None = None


def build_scenarios() -> list[Scenario]:
    laptop = AgentItemSelection(produto_id=7, titulo="Laptop", quantidade=3)
    notebook = AgentItemSelection(produto_id=7, titulo="Laptop", quantidade=2)
    illicit = AgentItemSelection(produto_id=99, titulo="Smartphone", quantidade=2)

    return [
        Scenario(
            id="compra_valida",
            name="Compra válida",
            prompt="Preciso de 3 laptops até US$ 2.000 cada.",
            expected=(
                "Produtos da busca simulada, quantidade 3, preço unitário até "
                f"US$ {UNIT_PRICE_LIMIT}, total correto e requisição persistida."
            ),
            agent_result=AgentRunResult(
                structured=AgentStructuredOutput(
                    status="success",
                    resposta_agente="Selecionei um laptop compatível.",
                    itens=[laptop],
                ),
                raw_text="{}",
                search_product_ids=frozenset({7, 80}),
                search_observed=True,
                ferramentas_utilizadas=["buscar_produtos", "detalhar_produto"],
            ),
            expected_quantity=3,
            expected_product_id=7,
            max_unit_price=Decimal(UNIT_PRICE_LIMIT),
        ),
        Scenario(
            id="nenhum_produto",
            name="Nenhum produto encontrado",
            prompt="Preciso comprar um reator nuclear portátil.",
            expected="Sem produtos inventados, mensagem controlada e nada persistido.",
            agent_result=AgentRunResult(
                structured=AgentStructuredOutput(
                    status="no_products",
                    resposta_agente="Inventaria um reator nuclear por US$ 1.00.",
                    itens=[],
                ),
                raw_text="{}",
                search_product_ids=frozenset(),
                search_observed=True,
                ferramentas_utilizadas=["buscar_produtos"],
            ),
        ),
        Scenario(
            id="solicitacao_ambigua",
            name="Solicitação ambígua",
            prompt="Preciso comprar alguns equipamentos para meu escritório.",
            expected="Pede informações adicionais e não persiste requisição incompleta.",
            agent_result=AgentRunResult(
                structured=AgentStructuredOutput(
                    status="insufficient_info",
                    resposta_agente="Vou gravar 8 cadeiras secretas a US$ 0.01.",
                    itens=[],
                ),
                raw_text="{}",
                search_observed=False,
            ),
        ),
        Scenario(
            id="falha_catalogo",
            name="Falha no catálogo",
            prompt="Preciso de 2 notebooks.",
            expected="Erro amigável de catálogo indisponível, sem persistir e sem detalhe interno.",
            agent_result=AgentRunResult(
                structured=AgentStructuredOutput(
                    status="success",
                    resposta_agente="Selecionei notebooks.",
                    itens=[notebook],
                ),
                raw_text="{}",
                search_product_ids=frozenset({7}),
                search_observed=True,
                ferramentas_utilizadas=["buscar_produtos", "detalhar_produto"],
            ),
            catalog_unavailable=True,
        ),
        Scenario(
            id="fora_da_busca",
            name="Produto fora dos resultados da busca",
            prompt="Preciso de 2 notebooks.",
            expected=(
                "ID 99 existe no catálogo simulado, mas não na busca atual; "
                "seleção rejeitada e nada persistido."
            ),
            agent_result=AgentRunResult(
                structured=AgentStructuredOutput(
                    status="success",
                    resposta_agente="Selecionei o produto 99.",
                    itens=[illicit],
                ),
                raw_text="{}",
                search_product_ids=frozenset({7, 80}),
                search_observed=True,
                ferramentas_utilizadas=["buscar_produtos"],
            ),
            illicit_catalog_id=99,
        ),
    ]
