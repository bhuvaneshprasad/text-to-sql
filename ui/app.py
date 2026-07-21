import json
import os

import chainlit as cl
import httpx

API_URL = os.getenv("CHAT_API_URL", "http://localhost:8000/api/v1/chat/")

# I do not have a GPU, hence have set a higher timeout
TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)

MAX_CHAT_TURNS = 7

MAX_QUESTION_CHARS = 3000


@cl.set_starters
async def set_starters():
    return [
        # Simple starters
        cl.Starter(
            label="Active product count",
            message="How many active products are in the catalog?",
        ),
        cl.Starter(
            label="Most recent orders",
            message="Show the 10 most recent orders with their status and total amount.",
        ),
        cl.Starter(
            label="Categories by product count",
            message="List the top 5 categories by number of active products.",
        ),
        cl.Starter(
            label="Average review rating",
            message="What is the average product rating across all approved reviews?",
        ),
        # Multi-table
        cl.Starter(
            label="Top customers by lifetime value",
            message="Which customers have the highest lifetime value, and what are their most recent order dates?",
        ),
        cl.Starter(
            label="Top products by revenue",
            message="What are the top 10 products by revenue, along with their category names and average review ratings?",
        ),
        cl.Starter(
            label="Categories by total sales",
            message="Which categories have the highest total sales, and how many active products belong to each category?",
        ),
        # JSON
        cl.Starter(
            label="Customers using the dark theme",
            message="How many customers have dark theme, and what is their average lifetime value?",
        ),
        cl.Starter(
            label="Newsletter subscribers",
            message="How many customers have newsletter notifications enabled?",
        ),
        cl.Starter(
            label="Products with height < 1cm",
            message="Which products have height less than 1cm?",
        ),
    ]


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("history", [])

def fmt_latency(ms):
    if ms is None:
        return "n/a"
    if ms >= 1000:
        return f"{ms / 1000:.2f} s"
    return f"{ms:.0f} ms"

def to_md_table(columns, rows, max_rows=50):
    if not columns:
        return "_(no columns)_"
    if not rows:
        return "_(0 rows)_"

    def cell(v):
        v = "" if v is None else str(v)
        return v.replace("|", "\\|").replace("\n", " ")

    header = "| " + " | ".join(str(c) for c in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join(cell(r.get(c)) for c in columns) + " |" for r in rows[:max_rows]]

    table = "\n".join([header, sep, *body])
    if len(rows) > max_rows:
        table += f"\n\n_…showing first {max_rows} of {len(rows)} rows_"
    return table

def build_trace_markdown(data: dict) -> str:
    out = []
    for step in data.get("steps", []):
        out.append(f"#### {step['label']}")
        out.append(f"⏱️ {fmt_latency(step['latency_ms'])}")

        tc = step.get("tool_call")
        if tc:
            if tc.get("sql_query"):
                out.append(f"**SQL query:**\n```sql\n{tc['sql_query'].strip()}\n```")
            if tc.get("row_count") is not None:
                out.append(f"Rows returned: **{tc['row_count']}**")
            if tc.get("error"):
                out.append(f"❌ Error: `{tc['error']}`")
            if tc.get("columns"):
                total = tc.get("total_count")
                caption = f" (total {total})" if tc.get("truncated") and total is not None else ""
                out.append(f"**Result{caption}:**\n{to_md_table(tc['columns'], tc['rows'])}")
        out.append("")  # spacer between steps

    total_ms = data.get("total_latency_ms")
    if total_ms is not None:
        out.append("---")
        out.append(f"⏱️ **Total latency:** {fmt_latency(total_ms)}")

    return "\n\n".join(out)

async def render_trace(data: dict):
    for step in data.get("steps", []):
        async with cl.Step(name=step["label"], type=step["kind"]) as s:
            lines = [f"⏱️ {fmt_latency(step['latency_ms'])}"]

            tc = step.get("tool_call")
            if tc:
                if tc.get("sql_query"):
                    lines.append(f"\n**SQL query:**\n```sql\n{tc['sql_query'].strip()}\n```")

                # only show args if a tool has params beyond the SQL itself
                extra = {k: v for k, v in (tc.get("arguments") or {}).items() if k != "sql_query"}
                if extra:
                    lines.append(f"\n**Args:**\n```json\n{json.dumps(extra, indent=2)}\n```")

                if tc.get("row_count") is not None:
                    lines.append(f"\nRows returned: **{tc['row_count']}**")

                if tc.get("error"):
                    lines.append(f"\n❌ Error: `{tc['error']}`")
                
                if tc.get("columns"):
                    total = tc.get("total_count")
                    caption = f" (total {total})" if tc.get("truncated") and total is not None else ""
                    lines.append(f"\n**Result{caption}:**")
                    lines.append(to_md_table(tc["columns"], tc["rows"]))


            s.output = "\n".join(lines)


@cl.on_message
async def on_message(message: cl.Message):
    if len(message.content) > MAX_QUESTION_CHARS:
        await cl.Message(
            content=(
                f"Your message is {len(message.content)} characters long, which exceeds the "
                f"{MAX_QUESTION_CHARS}-character limit. Please shorten it and try again."
            )
        ).send()
        return

    history = cl.user_session.get("history", [])
    thinking = cl.Message(content="")
    await thinking.send()

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                API_URL,
                json={"question": message.content, "history": history},
            )
            resp.raise_for_status()
            data = resp.json()

        response = data.get("response", "(empty response)")

        # 1) build + show the answer FIRST so nothing downstream can blank it
        parts = []
        sql_queries = data.get("sql_queries", [])
        if sql_queries:
            joined = "\n\n".join(f"```sql\n{q.strip()}\n```" for q in sql_queries)
            parts.append(f"### Generated SQL\n{joined}")
        parts.append(f"### LLM Response\n{response}")
        total_ms = data.get("total_latency_ms")
        if total_ms is not None:
            parts.append(f"⏱️ **Total latency:** {fmt_latency(total_ms)}")
        thinking.content = "\n\n---\n\n".join(parts)
        await thinking.update()

        # 2) trace sidebar is best-effort — never let it break the answer
        try:
            await cl.ElementSidebar.set_title("🔍 Request trace")
            await cl.ElementSidebar.set_elements(
                [cl.Text(content=build_trace_markdown(data), name="trace")]
            )
        except Exception as exc:
            print(f"[trace sidebar failed] {exc!r}")

        history.append({"role": "user", "content": message.content})
        history.append({"role": "assistant", "content": response})
        cl.user_session.set("history", history[-MAX_CHAT_TURNS * 2:])

    except httpx.HTTPStatusError as exc:
        thinking.content = f"API error {exc.response.status_code}: {exc.response.text}"
        await thinking.update()
    except httpx.RequestError as exc:
        thinking.content = f"Could not reach the API at {API_URL}: {exc}"
        await thinking.update()
    except Exception as exc:  # anything else now shows up instead of a blank bubble
        thinking.content = f"UI error: {exc!r}"
        await thinking.update()
