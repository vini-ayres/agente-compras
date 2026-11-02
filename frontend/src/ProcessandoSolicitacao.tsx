export function ProcessandoSolicitacao() {
  return (
    <article className="card processing" aria-live="polite" aria-busy="true">
      <div className="processing-row">
        <span className="processing-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <div>
          <p className="processing-title">Processando sua solicitação...</p>
          <p className="muted">Aguarde enquanto o pedido é analisado.</p>
        </div>
      </div>
    </article>
  );
}
