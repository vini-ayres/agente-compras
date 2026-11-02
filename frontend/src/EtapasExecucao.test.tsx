import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EtapasExecucao, etapasVisiveis } from "./EtapasExecucao";

describe("etapasVisiveis", () => {
  it("aceita respostas antigas sem o campo", () => {
    expect(etapasVisiveis(undefined)).toEqual([]);
    expect(etapasVisiveis(null)).toEqual([]);
  });

  it("não inventa etapas quando o array está vazio", () => {
    expect(etapasVisiveis([])).toEqual([]);
  });

  it("mantém origem e status das execuções atuais", () => {
    expect(
      etapasVisiveis([
        { nome: "buscar_produtos", origem: "agent", status: "success" },
        { nome: "detalhar_produto", origem: "backend", status: "error" },
      ]),
    ).toEqual([
      { nome: "buscar_produtos", origem: "agent", status: "success" },
      { nome: "detalhar_produto", origem: "backend", status: "error" },
    ]);
  });

  it("exibe nomes de respostas antigas sem inventar etapas extras", () => {
    expect(etapasVisiveis(["buscar_produtos"])).toEqual([
      { nome: "buscar_produtos", origem: "agent", status: "success" },
    ]);
  });

  it("ignora objetos incompletos", () => {
    expect(
      etapasVisiveis([
        { nome: "buscar_produtos" },
        { nome: "detalhar_produto", origem: "backend", status: "success" },
      ]),
    ).toEqual([{ nome: "detalhar_produto", origem: "backend", status: "success" }]);
  });
});

describe("EtapasExecucao", () => {
  it("diferencia origem do agente e do backend e mostra o status", () => {
    const html = renderToStaticMarkup(
      <EtapasExecucao
        etapas={[
          { nome: "buscar_produtos", origem: "agent", status: "success" },
          { nome: "detalhar_produto", origem: "backend", status: "error" },
        ]}
      />,
    );
    expect(html).toContain("Etapas de execução");
    expect(html).toContain("buscar_produtos");
    expect(html).toContain("detalhar_produto");
    expect(html).toContain("Agente");
    expect(html).toContain("Validação do backend");
    expect(html).toContain("sucesso");
    expect(html).toContain("falha");
    expect(html).toContain("etapa-success");
    expect(html).toContain("etapa-error");
    expect(html).not.toContain("set_model_response");
  });

  it("não renderiza nada quando o campo está ausente ou vazio", () => {
    expect(renderToStaticMarkup(<EtapasExecucao />)).toBe("");
    expect(renderToStaticMarkup(<EtapasExecucao etapas={[]} />)).toBe("");
  });

  it("não mostra ferramentas que não foram chamadas", () => {
    const html = renderToStaticMarkup(
      <EtapasExecucao
        etapas={[{ nome: "buscar_produtos", origem: "agent", status: "success" }]}
      />,
    );
    expect(html).toContain("buscar_produtos");
    expect(html).not.toContain("detalhar_produto");
  });
});
