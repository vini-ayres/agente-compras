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
};

export type RequisicaoListResponse = {
  items: Requisicao[];
  total: number;
  limit: number;
  offset: number;
};

async function parseError(response: Response): Promise<string> {
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

export async function criarRequisicao(pedido: string): Promise<Requisicao> {
  const response = await fetch(`${API_BASE_URL}/requisicoes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pedido }),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

export async function listarRequisicoes(): Promise<RequisicaoListResponse> {
  const response = await fetch(`${API_BASE_URL}/requisicoes?limit=20&offset=0`);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}
