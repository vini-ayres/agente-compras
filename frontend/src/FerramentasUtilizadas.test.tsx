import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FerramentasUtilizadas, ferramentasVisiveis } from "./FerramentasUtilizadas";

describe("ferramentasVisiveis", () => {
  it("aceita respostas antigas sem o campo", () => {
    expect(ferramentasVisiveis(undefined)).toEqual([]);
    expect(ferramentasVisiveis(null)).toEqual([]);
  });

  it("não lista ferramentas quando o array está vazio", () => {
    expect(ferramentasVisiveis([])).toEqual([]);
  });
});

describe("FerramentasUtilizadas", () => {
  it("renderiza nome e indicação de execução", () => {
    const html = renderToStaticMarkup(
      <FerramentasUtilizadas nomes={["buscar_produtos", "detalhar_produto"]} />,
    );
    expect(html).toContain("buscar_produtos");
    expect(html).toContain("detalhar_produto");
    expect(html).toContain("executada");
    expect(html).not.toContain("set_model_response");
  });

  it("não renderiza nada quando o campo está ausente", () => {
    const html = renderToStaticMarkup(<FerramentasUtilizadas />);
    expect(html).toBe("");
  });

  it("não mostra ferramentas que não foram chamadas", () => {
    const html = renderToStaticMarkup(
      <FerramentasUtilizadas nomes={["buscar_produtos"]} />,
    );
    expect(html).toContain("buscar_produtos");
    expect(html).not.toContain("detalhar_produto");
  });
});
