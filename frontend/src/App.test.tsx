import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AreaConversacao, envioBloqueado } from "./App";
import type { Requisicao } from "./api";

const requisicao: Requisicao = {
  id: 1,
  pedido_original: "Preciso de 3 notebooks",
  resposta_agente: "Requisição validada com base no catálogo.",
  itens: [],
  valor_total: "0.00",
  created_at: "2026-11-02T12:00:00Z",
  ferramentas_utilizadas: [
    { nome: "buscar_produtos", origem: "agent", status: "success" },
    { nome: "detalhar_produto", origem: "backend", status: "success" },
  ],
};

describe("envioBloqueado", () => {
  it("desabilita o envio durante o processamento", () => {
    expect(envioBloqueado(true, "Preciso de 3 notebooks")).toBe(true);
    expect(envioBloqueado(false, "Preciso de 3 notebooks")).toBe(false);
  });
});

describe("AreaConversacao", () => {
  it("mantém a mensagem do usuário e mostra o carregamento", () => {
    const html = renderToStaticMarkup(
      <AreaConversacao
        enviando={true}
        erro={null}
        atual={null}
        pedidoEnviado="Preciso de 3 notebooks"
      />,
    );
    expect(html).toContain("Preciso de 3 notebooks");
    expect(html).toContain("Processando sua solicitação...");
    expect(html).toContain("Aguarde enquanto o pedido é analisado.");
    expect(html).toContain("processing-dots");
    expect(html).not.toContain("Requisição validada");
  });

  it("remove o carregamento e mostra a resposta após o sucesso", () => {
    const html = renderToStaticMarkup(
      <AreaConversacao
        enviando={false}
        erro={null}
        atual={requisicao}
        pedidoEnviado="Preciso de 3 notebooks"
      />,
    );
    expect(html).toContain("Preciso de 3 notebooks");
    expect(html).toContain("Requisição validada com base no catálogo.");
    expect(html).toContain("result-enter");
    expect(html).toContain("Etapas de execução");
    expect(html).not.toContain("Processando sua solicitação...");
  });

  it("remove o carregamento e mostra o erro existente", () => {
    const html = renderToStaticMarkup(
      <AreaConversacao
        enviando={false}
        erro="Catálogo indisponível."
        atual={null}
        pedidoEnviado="Preciso de 3 notebooks"
      />,
    );
    expect(html).toContain("Catálogo indisponível.");
    expect(html).toContain("role=\"alert\"");
    expect(html).not.toContain("Processando sua solicitação...");
  });

  it("não inventa etapas em listagens históricas sem execução", () => {
    const historico: Requisicao = {
      ...requisicao,
      ferramentas_utilizadas: [],
    };
    const html = renderToStaticMarkup(
      <AreaConversacao
        enviando={false}
        erro={null}
        atual={historico}
        pedidoEnviado="Preciso de 3 notebooks"
      />,
    );
    expect(html).not.toContain("Etapas de execução");
    expect(html).not.toContain("buscar_produtos");
  });
});
