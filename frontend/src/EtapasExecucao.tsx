export type OrigemFerramenta = "agent" | "backend";
export type StatusFerramenta = "success" | "error";

export type FerramentaExecucao = {
  nome: string;
  origem: OrigemFerramenta;
  status: StatusFerramenta;
};

const ORIGEM_LABEL: Record<OrigemFerramenta, string> = {
  agent: "Agente",
  backend: "Validação do backend",
};

const STATUS_LABEL: Record<StatusFerramenta, string> = {
  success: "sucesso",
  error: "falha",
};

function isOrigem(value: unknown): value is OrigemFerramenta {
  return value === "agent" || value === "backend";
}

function isStatus(value: unknown): value is StatusFerramenta {
  return value === "success" || value === "error";
}

export function etapasVisiveis(raw: unknown): FerramentaExecucao[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const etapas: FerramentaExecucao[] = [];
  for (const item of raw) {
    if (typeof item === "string") {
      const nome = item.trim();
      if (!nome) {
        continue;
      }
      etapas.push({ nome, origem: "agent", status: "success" });
      continue;
    }
    if (!item || typeof item !== "object") {
      continue;
    }
    const record = item as Record<string, unknown>;
    if (typeof record.nome !== "string" || !record.nome.trim()) {
      continue;
    }
    if (!isOrigem(record.origem) || !isStatus(record.status)) {
      continue;
    }
    etapas.push({
      nome: record.nome.trim(),
      origem: record.origem,
      status: record.status,
    });
  }
  return etapas;
}

export function EtapasExecucao({ etapas }: { etapas?: unknown }) {
  const visiveis = etapasVisiveis(etapas);
  if (visiveis.length === 0) {
    return null;
  }

  return (
    <section className="etapas" aria-label="Etapas de execução">
      <h4 className="etapas-title">Etapas de execução</h4>
      <ol className="etapas-list">
        {visiveis.map((etapa, index) => (
          <li
            key={`${etapa.origem}-${etapa.nome}-${index}`}
            className={`etapa-item etapa-${etapa.status}`}
          >
            <span className={`etapa-status etapa-status-${etapa.status}`} aria-hidden="true" />
            <span className="tool-name">{etapa.nome}</span>
            <span className="etapa-origem">{ORIGEM_LABEL[etapa.origem]}</span>
            <span className="etapa-state">{STATUS_LABEL[etapa.status]}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
