# Text-to-SQL Assistant

A Text-to-SQL assistant that lets users query a relational database
in plain English. It uses an LLM agent to generate **read-only** PostgreSQL, validates and executes it safely, and answers from the results, with multi-turn context and clarifying questions when a request is ambiguous.

The dataset used is the [QueryPilot](https://github.com/QueryPilot/studio) **Sales / e-commerce** schema (customers, addresses, categories, suppliers, products, inventory, orders, order items, reviews) with primary/foreign-key relationships, views, JSONB, and HSTORE fields.

## Overview

- **Natural language to SQL** via an agentic tool-calling loop (custom, no framework).
- **Catalogue-grounded accuracy** - the agent validates every table, column, JSON key, and filter value against a metadata catalogue before writing the business query.
- **Safe by construction** - read-only database role, read-only transactions, `sqlglot` validation, statement timeout, and row caps (see [Safety](#safety)).
- **Clarification** - asks a focused question (via a dedicated tool) when a request is vague or incomplete instead of guessing.
- **Multi-turn** - retains conversation context (last 7 conversations) for follow-up questions.
- **Transparent** - the UI shows the generated SQL, results, and per-step + total latency.

## Prerequisites

- **Python 3.12** and **[uv](https://docs.astral.sh/uv/)**
- **PostgreSQL** (a reachable server; the app creates its own database)
- **`psql`** client on your `PATH` (database seeding shells out to it)
- An **OpenAI-compatible LLM endpoint** - OpenAI (default below) or a local
  [Ollama](https://ollama.com/) server

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at least your PostgreSQL **admin** credentials
(`POSTGRES_ADMIN_USER` / `POSTGRES_ADMIN_PASSWORD`) and the LLM settings below.
See the [Configuration](#configuration) reference for all variables.

### 3. Choose an LLM backend

**OpenAI (default / recommended)** - set in `.env`:

```dotenv
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...             # your OpenAI API key
LLM_CHAT_MODEL=gpt-5.4-mini    # tested model; any capable chat model works
```

> This project was developed and tested against **`gpt-5.4-mini`** and **`qwen-3.5:9b`** (a few questions).

**Ollama (local)** - the `/v1` endpoint ignores per-request `num_ctx`, so the large context window must be baked into the model. Create it once from the provided Modelfile:

```bash
ollama create qwen3.5-128k -f Modelfile.qwen35-128k
```

Then in `.env`:

```dotenv
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama            # any non-empty placeholder
LLM_CHAT_MODEL=qwen3.5-128k
```

> Note: on CPU-only machines local inference can take minutes per request. The UI read timeout is set high to accommodate this.

### 4. Bootstrap the database

```bash
uv run bootstrap
```

This creates the database, downloads and loads the QueryPilot seed, applies column
descriptions and the metadata catalogue, and provisions the least-privilege read-only role the app connects as. It is safe to re-run. It skips work that is already done.

## Running

The backend API and the chat UI run as two processes.

**1. Start the API** (http://localhost:8000 - the entrypoint is declared in
`pyproject.toml`, so no path is needed):

```bash
uv run fastapi run          # or: uv run fastapi dev  (auto-reload)
```

**2. Start the UI** (http://localhost:8501):

```bash
uv run chainlit run ui/app.py -w --port 8501
```

Then open http://localhost:8501 and ask a question, e.g. *"What are the top 10 products by revenue?"* or one of the starter prompts.

> The UI reaches the API at `CHAT_API_URL` (default `http://localhost:8000/api/v1/chat/`).
> Set it if you run the API on a different host or port.

## Configuration

All settings are read from `.env` (see `.env.example`).

| Variable | Description | Default |
|---|---|---|
| `LOG_LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` | `INFO` |
| `POSTGRES_HOST` / `POSTGRES_PORT` | PostgreSQL server location | `localhost` / `5432` |
| `POSTGRES_ADMIN_DATABASE` | Admin database used to create the app database | `postgres` |
| `POSTGRES_DATABASE` | Application database name | `querypilot` |
| `POSTGRES_ADMIN_USER` / `POSTGRES_ADMIN_PASSWORD` | Admin credentials (bootstrap only) | - |
| `POSTGRES_READ_ONLY_USER` / `POSTGRES_READ_ONLY_PASSWORD` | Least-privilege role the app queries as | `querypilot_reader` / … |
| `POSTGRES_POOL_MIN_SIZE` / `POSTGRES_POOL_MAX_SIZE` | Connection pool bounds | `1` / `5` |
| `POSTGRES_CONNECT_TIMEOUT_SECONDS` | Connection timeout | `10` |
| `QUERYPILOT_SEED_BASE_URL` | Source for the seed SQL files | QueryPilot GitHub |
| `QUERYPILOT_SEED_CACHE_DIR` | Local cache for downloaded seed files | `.cache/querypilot` |
| `LLM_BASE_URL` | OpenAI-compatible base URL | Ollama local |
| `LLM_API_KEY` | API key (or placeholder for Ollama) | `ollama` |
| `LLM_CHAT_MODEL` | Chat model name | `qwen3.5:9b` |
| `LLM_TIMEOUT_SECONDS` | LLM request timeout | `120` |
| `SQL_MAX_ROWS` | Max rows returned per query | `100` |
| `SQL_STATEMENT_TIMEOUT_MS` | Per-query statement timeout | `10000` |

## Project structure

```
app/
  api/          FastAPI routes (chat, health)
  agents/       Text-to-SQL agent loop (LLM + tools)
  database/     Pool, executor, sqlglot validator, introspection, roles, seed
  llm/          OpenAI-compatible client
  models/       Pydantic request/response and tool schemas
  prompts/      System prompt
  tools/        Tool definitions (execute_sql, request_clarification)
  bootstrap.py  Database provisioning entrypoint (`uv run bootstrap`)
  main.py       FastAPI app + lifespan
ui/
  app.py        Chainlit chat interface
```

## Safety

Read-only access is enforced in layers, so a write can never reach the data even if one layer is bypassed:

- **Database role** - the app connects as a least-privilege role with `SELECT` granted only on approved relations; everything else is revoked.
- **Read-only transactions** - every query runs under `SET TRANSACTION READ ONLY`.
- **Statement validation** - `sqlglot` parses the SQL and rejects anything that is not a read-only `SELECT` / `WITH … SELECT`; only the parsed statement is executed, so smuggled extra statements are dropped.

## Documentation

- [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md) - approach, prompting, SQL validation, conversation management, assumptions, and limitations.
- [SCHEMA.md](SCHEMA.md) - the data model the assistant queries.

## Acknowledgements

Dataset and seed data from the [QueryPilot](https://github.com/QueryPilot/studio) project.
