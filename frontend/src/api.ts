const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export type RequisicaoItem = {
  produto_id: number;
  titulo: string;
  quantidade: number;
  preco_unitario: string;
  subtotal: string;
};

export type Requisicao = {
  id: number;
  pedido_original: string;
  resposta_agente: string;
  itens: RequisicaoItem[];
  valor_total: string;
  created_at: string;
  ferramentas_utilizadas?: Array<
    | string
    | {
        nome: string;
        origem: "agent" | "backend";
        status: "success" | "error";
      }
  >;
};

export type RequisicaoListResponse = {
  items: Requisicao[];
  total: number;
  limit: number;
  offset: number;
};

export const IDEMPOTENCY_CONFLICT_MESSAGE =
  "Esta operação já foi registrada com outro pedido. Envie o pedido novamente para criar uma nova requisição.";

export function createIdempotencyKey(): string {
  return crypto.randomUUID();
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function isNetworkError(error: unknown): boolean {
  return error instanceof TypeError;
}

async function parseError(response: Response): Promise<string> {
  if (response.status === 409) {
    return IDEMPOTENCY_CONFLICT_MESSAGE;
  }
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") {
      return payload.detail;
    }
    return JSON.stringify(payload);
  } catch {
    return `Erro HTTP ${response.status}`;
  }
}

async function postRequisicao(pedido: string, idempotencyKey: string): Promise<Requisicao> {
  const response = await fetch(`${API_BASE_URL}/requisicoes`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({ pedido }),
  });
  if (response.status === 200 || response.status === 201) {
    return response.json();
  }
  throw new ApiError(await parseError(response), response.status);
}

export async function criarRequisicao(
  pedido: string,
  idempotencyKey: string,
): Promise<Requisicao> {
  try {
    return await postRequisicao(pedido, idempotencyKey);
  } catch (error) {
    if (isNetworkError(error)) {
      return postRequisicao(pedido, idempotencyKey);
    }
    throw error;
  }
}

export async function listarRequisicoes(): Promise<RequisicaoListResponse> {
  const response = await fetch(`${API_BASE_URL}/requisicoes?limit=20&offset=0`);
  if (!response.ok) {
    throw new ApiError(await parseError(response), response.status);
  }
  return response.json();
}
