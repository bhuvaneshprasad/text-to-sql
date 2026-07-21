# Technical Report

This is a short walk-through of how the Text-to-SQL assistant is built and why the main decisions were made. For setup and how to run it, see the [README](README.md); for the data model, see [SCHEMA.md](SCHEMA.md).

## Solution approach

The assistant is a small agent that turns a natural-language question into a read-only PostgreSQL query, runs it, and answers from the result. It is a custom tool-calling loop built directly on the OpenAI client rather than a framework like LangChain. Keeping it explicit makes the safety and validation boundaries easy to reason about.

The pieces fit together like this:

- **Chainlit UI** (`ui/app.py`) - the chat surface. It sends the question plus the recent conversation to the API and renders the answer, the generated SQL, latency, and a trace of each step along with per step latency.
- **FastAPI backend** (`app/api/chat.py`) - one `/chat` endpoint that runs the agent.
- **The agent** (`app/agents/text_to_sql.py`) - calls the model with two tools and loops until the model returns a final answer or max turns(15) are exceeded.
- **PostgreSQL** - queried through a dedicated read-only role, never the owner.

Alongside the business tables we build a metadata catalogue (`text_to_sql_catalog`) describing the schema, the foreign-key relationships, the keys inside JSONB columns, and the distinct values stored in text columns. The model is instructed to look identifiers and filter values up in this catalogue *before* writing the real query. This is what keeps it from inventing a column
name or guessing column data. It trades a couple of cheap lookup queries for a large drop in hallucinated SQL.

## Prompting strategy

There is a single system prompt (`app/prompts/text_to_sql_agent.py`) that sets the rules.
It is deliberately structured into sections rather than written as one long paragraph, so each concern is easy to find and tune. The parts that matter most:

- **A mandatory workflow.** Every data question follows the same order: interpret the request, validate identifiers and values against the catalogue, then write and run one business query. The prompt is explicit that the catalogue step comes first and is not optional.
- **A conversational gate.** Greetings, thanks, and "what can you do" are answered
  directly without touching the database, so small talk doesn't trigger pointless queries.
- **Interpretation rules.** How to map everyday language onto the schema, how to read ranking words ("top" → descending), when to use monetary vs. count metrics, and sensible defaults for limits and ordering.
- **SQL correctness rules.** Explicit joins, and `ILIKE` for case-insensitive matching.
- **Answer formatting.** Scalars as a sentence, multiple rows as a Markdown table, a fixed "No matching records were found." for empty results.

The current date is injected into the prompt at request time so relative dates ("last month", "past 7 days") resolve correctly.

## SQL validation and safety

Safety is layered on purpose, so that no single mistake - in the model, the prompt, or the validator - can result in a write reaching the data.

1. **A read-only database role.** The app never connects as the table owner. Bootstrap provisions a least-privilege role (`NOSUPERUSER`, no create rights) and grants it `SELECT` on only the approved business and catalogue relations; everything else is revoked. This is the real guarantee.
2. **Read-only transactions.** Every query runs inside a transaction opened with `SET TRANSACTION READ ONLY`, with a statement timeout applied.
3. **Parse-level validation.** Before execution, `sqlglot` parses the SQL (`app/database/validator.py`). Anything that is not a read-only `SELECT` / `WITH … SELECT` is rejected.
4. **Result bounds.** A count query and an injected `LIMIT` cap how much data comes back, and the per-query statement timeout stops runaway queries.


## Conversation management

The assistant supports follow-up questions. The prompt is written to resolve a new message against the whole conversation first - carrying forward the entity, metric, filters, and ordering already established - and only then decide what to do.

The conversation lives in the **Chainlit UI session**. The UI keeps the running history and sends it with each request; the backend is stateless and treats the
history as an input to the current turn. This keeps the API simple.

## Query clarification

When a request is genuinely vague - an ambiguous question, a missing filter, or a ranking with no stated metric - the assistant asks one focused question instead of guessing.

This is implemented as a real tool, `request_clarification`, sitting next to
`execute_sql`. That design choice matters: with a prompt alone, "asking" means the model has to *not* call a tool and instead write prose, which fights its tool-calling instinct, so it tends to guess. Making clarification its own tool puts asking and querying on equal footing. When the model calls it, the agent returns the question and stops - no SQL runs that turn. The prompt defines the decision procedure: resolve against history first, ask only if the gap truly blocks a correct query, and never ask about things a sensible default (direction, limit, spelling) already settles.

## Explainability

Each response is transparent about what happened. The UI shows the generated SQL, the query results, and both per-step and total latency.

## Assumptions

- The system is for **read-only analytical questions**. Writing data is out of scope by design.
- The seeded QueryPilot dataset is the source of truth, and the schema is **static while the app runs** (it is fetched once at startup and cached).
- The LLM endpoint is **OpenAI-compatible and supports tool calling**.

## Limitations

- **The API does not persist conversation history.** Conversation memory is held by the Chainlit UI and passed in per request; the backend itself is stateless. Any other client calling the API must send the history it wants remembered - there is no server-side session or storage.
- **History is capped at the last 7 turns (from UI).** Older context is dropped, so very long conversations can lose details established early on.
- **No Compact** of chat history is implemented to keep the earlier context.
- **Schema is cached at startup.** Re-seeding or changing the schema requires restarting the API to pick up the change.
- **Single dataset, single database.** There is no multi-tenant or multi-database support.
- **User input is capped at 3000 characters per message.** The API rejects longer questions (HTTP 422) and the UI blocks them before sending, so very long prompts or pasted documents must be trimmed.
- **Latency** can be high on reasoning models or CPU-only local inference, since a single question may take several model calls (catalogue lookups plus the business query). For openai models I got latency of 4-12 seconds based on the query complexity.
