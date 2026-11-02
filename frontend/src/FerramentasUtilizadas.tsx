export function ferramentasVisiveis(raw: unknown): string[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const seen = new Set<string>();
  const names: string[] = [];
  for (const item of raw) {
    if (typeof item !== "string") {
      continue;
    }
    const name = item.trim();
    if (!name || seen.has(name)) {
      continue;
    }
    seen.add(name);
    names.push(name);
  }
  return names;
}

export function FerramentasUtilizadas({ nomes }: { nomes?: string[] | null }) {
  const visiveis = ferramentasVisiveis(nomes);
  if (visiveis.length === 0) {
    return null;
  }

  return (
    <ul className="tool-list" aria-label="Ferramentas utilizadas">
      {visiveis.map((nome) => (
        <li key={nome} className="tool-item">
          <span className="tool-name">{nome}</span>
          <span className="tool-state">executada</span>
        </li>
      ))}
    </ul>
  );
}
