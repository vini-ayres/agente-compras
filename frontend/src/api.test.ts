import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createIdempotencyKey,
  criarRequisicao,
  IDEMPOTENCY_CONFLICT_MESSAGE,
  type Requisicao,
} from "./api";

const sample: Requisicao = {
  id: 1,
  pedido_original: "Preciso de 3 notebooks",
  resposta_agente: "Requisição validada com base no catálogo:",
  itens: [
    {
      produto_id: 7,
      titulo: "Laptop",
      quantidade: 3,
      preco_unitario: "999.99",
      subtotal: "2999.97",
    },
  ],
  valor_total: "2999.97",
  created_at: "2026-11-02T12:00:00Z",
};

function jsonResponse(status: number, body: unknown): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("createIdempotencyKey", () => {
  it("gera uma chave nova a cada operação", () => {
    const first = createIdempotencyKey();
    const second = createIdempotencyKey();
    expect(first).not.toEqual(second);
    expect(first).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  });

  it("não deriva a chave do texto do pedido", () => {
    const pedido = "Preciso de 3 notebooks";
    const keys = [createIdempotencyKey(), createIdempotencyKey()];
    expect(keys[0]).not.toEqual(keys[1]);
    expect(keys[0]).not.toContain(pedido);
    expect(keys[1]).not.toContain(pedido);
  });
});

describe("criarRequisicao", () => {
  it("envia Idempotency-Key no cabeçalho", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, sample));
    vi.stubGlobal("fetch", fetchMock);

    await criarRequisicao("Preciso de 3 notebooks", "op-key-1");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toBe("op-key-1");
    expect(JSON.parse(String(init.body))).toEqual({ pedido: "Preciso de 3 notebooks" });
  });

  it("trata HTTP 201 como sucesso", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(201, sample)));
    const result = await criarRequisicao("Preciso de 3 notebooks", "op-201");
    expect(result.id).toBe(1);
    expect(result.valor_total).toBe("2999.97");
  });

  it("trata HTTP 200 como sucesso", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, sample)));
    const result = await criarRequisicao("Preciso de 3 notebooks", "op-200");
    expect(result.id).toBe(1);
  });

  it("reutiliza a mesma chave no retry de falha de rede", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse(201, sample));
    vi.stubGlobal("fetch", fetchMock);

    const result = await criarRequisicao("Preciso de 3 notebooks", "op-retry");
    expect(result.id).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const firstHeaders = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    const secondHeaders = (fetchMock.mock.calls[1][1] as RequestInit).headers as Record<string, string>;
    expect(firstHeaders["Idempotency-Key"]).toBe("op-retry");
    expect(secondHeaders["Idempotency-Key"]).toBe("op-retry");
  });

  it("trata HTTP 409 com mensagem amigável", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(409, { detail: "Idempotency-Key já utilizada com outro pedido." }),
      ),
    );
    try {
      await criarRequisicao("Preciso de 3 notebooks", "op-conflict");
      throw new Error("deveria ter falhado com 409");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).status).toBe(409);
      expect((error as ApiError).message).toBe(IDEMPOTENCY_CONFLICT_MESSAGE);
    }
  });
});
