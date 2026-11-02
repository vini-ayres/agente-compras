# Purchase Agent

[![CI](https://github.com/vini-ayres/agente-compras/actions/workflows/ci.yml/badge.svg)](https://github.com/vini-ayres/agente-compras/actions/workflows/ci.yml)

Agente de compras: o usuário descreve o pedido em português no chat, o backend interpreta a solicitação com um LLM, consulta o catálogo DummyJSON via MCP e grava uma requisição no PostgreSQL.

## Arquitetura

| Componente | Tecnologia | Função |
|---|---|---|
| Chat | React + Vite | Formulário de pedido e histórico |
| API | FastAPI + SQLAlchemy | Orquestra o agente, valida o catálogo e persiste |
| Agente | Google ADK + LiteLLM | Interpreta o pedido e escolhe produtos |
| Catálogo | MCP Server (Streamable HTTP) | Expõe DummyJSON como ferramentas |
| Banco | PostgreSQL | Requisições, itens e chaves de idempotência |

O LLM decide quando chamar as ferramentas. Não há sequência fixa de `buscar_produtos` / `detalhar_produto`. Depois da escolha, o backend:

1. Aceita apenas IDs que apareceram em `buscar_produtos` na mesma execução.
2. Recalcula título, preço, subtotal e total com `detalhar_produto` e `Decimal`.
3. Persiste um resumo factual gerado no backend, sem prosa comercial do modelo.

## MCP Server

Ferramentas:

- `buscar_produtos(termo)` — pesquisa no DummyJSON.
- `detalhar_produto(id)` — detalhe de um produto, incluindo preço.

Transporte: Streamable HTTP em `/mcp`. Health: `GET /health`.

## Modelo LLM

O agente usa Google ADK + LiteLLM. O provedor é selecionado por `LLM_PROVIDER` no `.env`, sem alterar o código.

- `LLM_PROVIDER=gemini`: `GEMINI_API_KEY` + `GEMINI_MODEL` (padrão `gemini/gemini-3.6-flash`)
- `LLM_PROVIDER=openrouter`: `OPENROUTER_API_KEY` + `OPENROUTER_MODEL` (padrão `openrouter/google/gemini-3.6-flash`)
- Não há fallback automático entre chaves ou modelos dos dois provedores
- Function calling, structured outputs e tarefas agênticas
- O ADK instancia `LiteLlm`; o modelo decide quando chamar `buscar_produtos` e `detalhar_produto`
- `output_schema` (`AgentStructuredOutput`) permanece; no Gemini (direto ou via OpenRouter) o ADK aplica o workaround `set_model_response` para combinar schema e tools
- `LLM_MAX_OUTPUT_TOKENS` (padrão 4096) é enviado ao LiteLLM como `max_tokens`/`max_completion_tokens` para evitar a reserva de 65536 no OpenRouter

## Variáveis de ambiente

Copie `.env.example` para `.env` e preencha os valores reais. O exemplo contém apenas placeholders (`POSTGRES_PASSWORD=change-me`, chaves de API vazias).

Principais variáveis:

- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `DATABASE_URL` (no Docker o Compose redefine o host para o serviço `postgres`)
- `LLM_PROVIDER` (`gemini` ou `openrouter`)
- `GEMINI_API_KEY`, `GEMINI_MODEL`
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`
- `LLM_MAX_OUTPUT_TOKENS`
- `CORS_ORIGINS`
- `MCP_SERVER_URL` (no Docker: `http://mcp-server:8080/mcp`)
- `DUMMYJSON_BASE_URL`, `HTTP_TIMEOUT_SECONDS`

## Como subir

```powershell
copy .env.example .env
# preencha POSTGRES_PASSWORD e a chave do provedor escolhido (GEMINI_API_KEY ou OPENROUTER_API_KEY)
docker compose up -d --build
```

- Chat: http://localhost:5173
- API: http://localhost:8000/health
- MCP: apenas na rede Docker (`http://mcp-server:8080`); a porta 8080 não é publicada no host

## API

`POST /requisicoes` com `{"pedido": "Preciso de 3 laptops até US$ 2000 cada."}`

- 201: requisição criada
- 200: replay de idempotência (mesma chave e mesmo pedido)
- 409: `Idempotency-Key` já usada com outro pedido
- 422: pedido inválido, sem produtos, informação insuficiente ou produto fora da busca
- 503: catálogo, agente ou persistência indisponíveis

Cabeçalho opcional `Idempotency-Key`: a mesma chave com o mesmo `pedido` devolve a requisição original; a mesma chave com outro `pedido` retorna HTTP 409. Sem o cabeçalho, cada chamada cria uma nova requisição. O chat gera um UUID por envio (não pelo texto) e reutiliza a chave só no retry de falha de rede da mesma operação.

`GET /requisicoes?limit=20&offset=0` lista as requisições mais recentes (`limit` 1–100).

O backend valida os itens no catálogo, grava um resumo factual (nome, quantidade, preços e total) e ignora afirmações comerciais do texto do LLM. Erros de `no_products`, `insufficient_info` e `catalog_unavailable` devolvem mensagens controladas pelo backend.

## Testes

```powershell
cd backend
python -m pytest -q

cd ..\mcp-server
python -m pytest -q

cd ..\frontend
npm ci
npm test
npm run build
```

## Integração contínua (CI)

A pipeline em `.github/workflows/ci.yml` roda em todo push e em todo pull request para `main`. Os três jobs (`backend`, `mcp-server`, `frontend`) são independentes; falha de lint, testes ou build reprova o job.

A CI **não** usa chaves de API, **não** chama LLM, **não** acessa DummyJSON e **não** depende de PostgreSQL externo. A avaliação determinística dos cinco cenários entra no job do backend com os mesmos mocks da suíte local.

| Job | Ferramentas | O que verifica |
|---|---|---|
| Backend | Python 3.12, Ruff, Pytest | Lint, testes unitários/de API e `evaluate_agent.py` |
| MCP Server | Python 3.12, Ruff, Pytest | Lint e testes do servidor de catálogo |
| Frontend | Node.js 22, ESLint, Vitest, Vite | Lint, testes e build de produção |

Ruff cobre pycodestyle (`E`/`W`) e Pyflakes (`F`), sem `--fix`. ESLint usa as regras recomendadas de JavaScript/TypeScript e os hooks clássicos do React (`rules-of-hooks`, `exhaustive-deps`).

Para reproduzir a CI localmente:

```powershell
# Backend
cd backend
pip install -r requirements.txt
pip install ruff
ruff check .
python -m pytest -q
python scripts/evaluate_agent.py

# MCP Server
cd ..\mcp-server
pip install -e ".[dev]"
ruff check .
python -m pytest -q

# Frontend
cd ..\frontend
npm ci
npm run lint
npm test
npm run build
```

## Avaliação funcional do agente

A avaliação é uma suíte de **regressão determinística** do backend e das regras do agente. Ela **não** chama LLM, **não** usa API key, **não** acessa DummyJSON na internet e **não** mede a qualidade das respostas de um modelo real.

Cada um dos cinco cenários vale 20 pontos (20 se todos os critérios passarem, 0 se algum falhar). Aprovação geral exige 100/100.

| Cenário | Prompt | Esperado |
|---|---|---|
| Compra válida | Preciso de 3 laptops até US$ 2.000 cada. | Item da busca, quantidade 3, unitário ≤ 2000, total correto, persistido |
| Nenhum produto encontrado | Preciso comprar um reator nuclear portátil. | Sem invenção, mensagem controlada, nada persistido |
| Solicitação ambígua | Preciso comprar alguns equipamentos para meu escritório. | Pede mais informação, não persiste |
| Falha no catálogo | Preciso de 2 notebooks. | Erro amigável de catálogo, nada persistido |
| Produto fora da busca | Preciso de 2 notebooks. | ID existente no catálogo mas ausente na busca é rejeitado |

Na raiz do repositório:

```powershell
python backend/scripts/evaluate_agent.py
```

O processo termina com código diferente de zero se algum cenário for reprovado. O relatório lista o esperado, o obtido, o status e os critérios que falharam.

## Uso de inteligência artificial no desenvolvimento

O projeto foi desenvolvido com assistência de um agente de programação no Cursor. Arquitetura, contratos, testes e o conteúdo deste repositório foram revisados no código real antes de cada commit.
