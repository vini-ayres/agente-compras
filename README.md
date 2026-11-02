# Agente de Compras

[![CI](https://github.com/vini-ayres/agente-compras/actions/workflows/ci.yml/badge.svg)](https://github.com/vini-ayres/agente-compras/actions/workflows/ci.yml)

Aplicação de compras em que o usuário descreve o que precisa em um chat. Um agente de IA consulta o catálogo de produtos, seleciona as opções adequadas e registra a requisição no banco de dados.

## Tecnologias

- **Frontend:** React e Vite
- **Backend:** Python e FastAPI
- **Agente:** Google ADK e LiteLLM
- **Integração:** MCP (Model Context Protocol)
- **Banco de dados:** PostgreSQL
- **Ambiente:** Docker Compose

## Como executar

É necessário ter Docker Desktop e uma chave de API de um dos provedores suportados.

1. Clone o repositório e entre na pasta do projeto.
2. Crie o arquivo de configuração:

```powershell
copy .env.example .env
```

3. No `.env`, configure a senha do PostgreSQL e a chave do provedor de IA escolhido.

Para usar OpenRouter:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sua-chave
```

Ou Gemini:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=sua-chave
```

4. Inicie os serviços:

```powershell
docker compose up -d --build
```

A aplicação estará disponível em:

- **Chat:** http://localhost:5173
- **API:** http://localhost:8000
- **Saúde da API:** http://localhost:8000/health

O Docker Compose inicia o banco, o servidor MCP, a API e o frontend. As tabelas são criadas automaticamente na inicialização.

## Como funciona

O usuário envia uma solicitação pelo chat. O Google ADK executa o agente e permite que o modelo escolha quais ferramentas MCP utilizar para consultar o catálogo DummyJSON.

O servidor MCP disponibiliza duas ferramentas:

- `buscar_produtos(termo)`: pesquisa produtos pelo nome ou descrição.
- `detalhar_produto(id)`: consulta os dados de um produto específico.

Depois que o agente seleciona os produtos, o backend consulta novamente os detalhes no catálogo. Essa etapa é independente do agente e serve para conferir os dados antes de salvar a requisição.

Os valores são calculados no backend com `Decimal`, evitando depender dos preços ou totais informados pelo modelo. Somente produtos encontrados na busca da execução atual podem ser utilizados.

## Decisões técnicas

- **O modelo escolhe as ferramentas:** não existe uma sequência fixa de chamadas MCP no código. O agente decide quando precisa pesquisar ou consultar um produto.
- **Validação fora do LLM:** o backend revalida os produtos e calcula os valores antes da persistência. Assim, o modelo não controla diretamente os preços registrados.
- **Separação entre agente e integração:** o servidor MCP é um serviço independente, acessível pela rede interna do Docker.
- **Idempotência:** a API aceita o cabeçalho `Idempotency-Key` para evitar a criação duplicada de uma requisição quando a mesma operação é reenviada.
- **Rastreabilidade:** a resposta da API informa as ferramentas executadas pelo agente e as chamadas realizadas pelo backend, identificando suas respectivas origens.

## API

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/requisicoes` | Processa um pedido e cria uma requisição |
| GET | `/requisicoes` | Lista as requisições registradas |

Exemplo de solicitação:

```json
{
  "pedido": "Preciso de 3 laptops até US$ 2000 cada."
}
```

A API retorna os dados da requisição, os produtos selecionados, os valores calculados e as etapas de execução.

## Testes

O projeto possui testes automatizados para o backend, servidor MCP e frontend.

Para executar a suíte do backend:

```powershell
cd backend
python -m pytest -q
```

Para o servidor MCP:

```powershell
cd ..\mcp-server
python -m pytest -q
```

Para o frontend:

```powershell
cd ..\frontend
npm ci
npm test
npm run build
```

Também existe uma avaliação determinística com cinco cenários, cobrindo compra válida, produto não encontrado, pedido ambíguo, falha no catálogo e produto fora da busca.

Na raiz do projeto, execute:

```powershell
python backend/scripts/evaluate_agent.py
```

A avaliação não utiliza chamadas reais ao LLM ou ao DummyJSON.

A integração contínua, configurada no GitHub Actions, executa lint, testes e build a cada push e pull request para `main`.
