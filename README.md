# Purchase Agent

Agente de compras: o usuário descreve o pedido em um chat, o backend consulta o catálogo DummyJSON via MCP e grava uma requisição no PostgreSQL.

## Como subir

```powershell
copy .env.example .env
# preencha GEMINI_API_KEY e POSTGRES_PASSWORD
docker compose up -d --build
```

- Chat: http://localhost:5173
- API: http://localhost:8000/health
- MCP: http://localhost:8080/health

`POST /requisicoes` com `{"pedido": "Preciso de 3 laptops até US$ 2000 cada."}`

## Modelo LLM

O agente usa **Google AI Studio** via LiteLLM, sem substituir o Google ADK.

- Modelo: `gemini/gemini-3.6-flash`
- Variável: `GEMINI_API_KEY` (somente no `.env`)
- Function calling, structured outputs e tarefas agênticas
- O ADK instancia `LiteLlm`; o modelo decide quando chamar `buscar_produtos` e `detalhar_produto`
- `output_schema` (`AgentStructuredOutput`) permanece; no Gemini AI Studio o ADK aplica o workaround `set_model_response` para combinar schema e tools

A configuração OpenRouter permanece no ambiente como legado e não é usada pelo agente ativo.

O agente decide sozinho quando chamar `buscar_produtos` e `detalhar_produto`. Preços e totais são recalculados no backend com `Decimal`.
