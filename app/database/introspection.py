from typing import Any

from psycopg_pool import AsyncConnectionPool

from app.database.queries import fetch_all


async def get_schema_metadata(pool: AsyncConnectionPool, schema_name: str = "public"):
    rows = await fetch_all(
        pool,
        """
        SELECT
            c.table_name,
            obj_description(
                (quote_ident(c.table_schema) || '.' || quote_ident(c.table_name))::regclass,
                'pg_class'
            ) AS table_description,
            c.column_name,
            c.data_type,
            col_description(
                (quote_ident(c.table_schema) || '.' || quote_ident(c.table_name))::regclass,
                c.ordinal_position
            ) AS column_description,
            c.ordinal_position
        FROM information_schema.columns AS c
        WHERE c.table_schema = %s
        ORDER BY
            c.table_name,
            c.ordinal_position
        """,
        (schema_name,),
    )

    return rows

def format_schema_context(metadata: list[dict[str, Any]]):
    tables: dict[str, dict[str, Any]] = {}

    for row in metadata:
        table_name = row["table_name"]

        table = tables.setdefault(
            table_name,
            {
                "description": row["table_description"],
                "columns": [],
            },
        )

        table["columns"].append(
            {
                "name": row["column_name"],
                "type": row["data_type"],
                "description": row["column_description"],
            }
        )

    sections: list[str] = []

    for table_name, table in tables.items():
        lines = [f"Table: {table_name}"]

        if table["description"]:
            lines.append(f"Description: {table['description']}")

        lines.append("Columns:")

        for column in table["columns"]:
            line = f"- {column['name']}: {column['type']}"

            if column["description"]:
                line += f" — {column['description']}"

            lines.append(line)

        sections.append("\n".join(lines))

    return "\n\n".join(sections)