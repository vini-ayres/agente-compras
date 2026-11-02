import { FormEvent, useEffect, useState } from "react";
import { criarRequisicao, listarRequisicoes, type Requisicao } from "./api";

export default function App() {
  const [pedido, setPedido] = useState("Preciso de 3 laptops até US$ 2000 cada.");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [atual, setAtual] = useState<Requisicao | null>(null);
  const [historico, setHistorico] = useState<Requisicao[]>([]);

  async function carregarHistorico() {
    const data = await listarRequisicoes();
    setHistorico(data.items);
  }

  useEffect(() => {
    carregarHistorico().catch((err: unknown) => {
      setErro(err instanceof Error ? err.message : "Falha ao carregar requisições.");
    });
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      const criada = await criarRequisicao(pedido);
      setAtual(criada);
      await carregarHistorico();
    } catch (err: unknown) {
      setErro(err instanceof Error ? err.message : "Falha ao criar a requisição.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="page">
      <header>
        <p className="eyebrow">Purchase Agent</p>
        <h1>Solicite uma compra</h1>
        <p className="lede">
          O agente consulta o catálogo DummyJSON via MCP, escolhe os produtos e grava a
          requisição no PostgreSQL.
        </p>
      </header>

      <form onSubmit={onSubmit} className="card">
        <label htmlFor="pedido">Pedido</label>
        <textarea
          id="pedido"
          value={pedido}
          onChange={(event) => setPedido(event.target.value)}
          minLength={3}
          required
          rows={4}
        />
        <button type="submit" disabled={enviando || pedido.trim().length < 3}>
          {enviando ? "Consultando catálogo…" : "Enviar pedido"}
        </button>
      </form>

      {erro ? <p className="error" role="alert">{erro}</p> : null}

      {atual ? <RequisicaoCard titulo="Resultado" requisicao={atual} /> : null}

      <section>
        <h2>Requisições recentes</h2>
        {historico.length === 0 ? (
          <p className="muted">Nenhuma requisição gravada ainda.</p>
        ) : (
          <div className="stack">
            {historico.map((item) => (
              <RequisicaoCard key={item.id} titulo={`#${item.id}`} requisicao={item} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function RequisicaoCard({ titulo, requisicao }: { titulo: string; requisicao: Requisicao }) {
  return (
    <article className="card">
      <h3>{titulo}</h3>
      <p>
        <strong>Pedido:</strong> {requisicao.pedido_original}
      </p>
      <p>{requisicao.resposta_agente}</p>
      {requisicao.itens.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>Produto</th>
              <th>Qtd</th>
              <th>Unitário</th>
              <th>Subtotal</th>
            </tr>
          </thead>
          <tbody>
            {requisicao.itens.map((item) => (
              <tr key={`${requisicao.id}-${item.produto_id}`}>
                <td>
                  {item.titulo} <span className="muted">#{item.produto_id}</span>
                </td>
                <td>{item.quantidade}</td>
                <td>{item.preco_unitario}</td>
                <td>{item.subtotal}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <p>
        <strong>Total:</strong> {requisicao.valor_total}
      </p>
    </article>
  );
}
