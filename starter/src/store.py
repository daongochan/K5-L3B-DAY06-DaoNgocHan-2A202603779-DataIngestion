"""Persistent vector store on PostgreSQL + pgvector.

Design notes that matter for the experiment:

* One table holds all strategies, keyed by ``strategy``. Chunk IDs are already
  namespaced by strategy, and the primary key is the chunk ID, so re-ingesting
  the same corpus updates rows instead of duplicating them.
* Cosine distance (``<=>``) is used because the embedder L2-normalizes vectors;
  ``score`` returned to callers is ``1 - distance`` so higher is better.
* Filters are resolved against an allow-list of columns and always passed as
  bound parameters. No filter key or value is ever interpolated into SQL.
* Filter values that the store does not know are rejected rather than ignored:
  silently dropping a filter would return out-of-scope rows while claiming the
  filter was applied.
"""
from __future__ import annotations

from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from .models import Chunk

# Only these columns may be filtered. Anything else is a caller bug.
FILTER_COLUMNS = {
    "document_id": "text",
    "page": "int",
    "printed_page": "int",
    "page_type": "text",
    "article": "text",
    "chapter": "text",
    "section": "text",
    "form": "text",
}


def _quote_ident(name: str) -> str:
    """Quote an identifier after validating it against the allow-list."""
    if name not in FILTER_COLUMNS:
        raise ValueError(f"unknown filter field: {name}")
    return '"' + name.replace('"', '""') + '"'


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.database_url = database_url
        self.dimensions = dimensions

    def _connect(self) -> psycopg.Connection:
        connection = psycopg.connect(self.database_url)
        register_vector(connection)
        return connection

    def create_schema(self) -> None:
        """Create the table and the indexes the queries rely on."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id     text PRIMARY KEY,
                    strategy     text NOT NULL,
                    document_id  text NOT NULL,
                    source       text NOT NULL,
                    page         int  NOT NULL,
                    printed_page int,
                    page_type    text,
                    article      text,
                    chapter      text,
                    section      text,
                    form         text,
                    text         text NOT NULL,
                    char_count   int  NOT NULL,
                    embedding    vector({self.dimensions}) NOT NULL
                )
                """
            )
            cursor.execute(
                "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS form text"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS chunks_strategy_idx ON chunks (strategy)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS chunks_page_idx ON chunks (page)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS chunks_article_idx ON chunks (article)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS chunks_page_type_idx ON chunks (page_type)"
            )
            # Exact search is used on purpose: the corpus is ~200 chunks, where an
            # HNSW index would add approximation error without any real speedup.
            # Cosine is the operator class the experiment reports.
            connection.commit()

    def upsert(
        self,
        strategy: str,
        chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> dict[str, int]:
        """Insert or update chunks for one strategy.

        Returns counts so the caller can prove re-ingestion did not duplicate
        rows. Obsolete chunks (same strategy, chunk IDs no longer produced) are
        deleted in the same transaction, which is what makes a re-run after a
        corpus or chunking change converge instead of accumulating.
        """
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks/vectors length mismatch: {len(chunks)} vs {len(vectors)}"
            )
        for index, vector in enumerate(vectors):
            if len(vector) != self.dimensions:
                raise ValueError(
                    f"vector {index} has {len(vector)} dimensions, expected {self.dimensions}"
                )

        ids = [chunk.chunk_id for chunk in chunks]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate chunk_id in batch")

        deleted = 0
        with self._connect() as connection, connection.cursor() as cursor:
            if ids:
                cursor.execute(
                    "DELETE FROM chunks WHERE strategy = %s AND chunk_id <> ALL(%s)",
                    (strategy, ids),
                )
            else:
                cursor.execute("DELETE FROM chunks WHERE strategy = %s", (strategy,))
            deleted = cursor.rowcount

            rows = [
                (
                    chunk.chunk_id,
                    strategy,
                    chunk.document_id,
                    chunk.source,
                    chunk.page,
                    chunk.metadata.get("printed_page"),
                    chunk.metadata.get("page_type"),
                    chunk.metadata.get("article"),
                    chunk.metadata.get("chapter"),
                    chunk.metadata.get("section"),
                    chunk.metadata.get("form"),
                    chunk.text,
                    chunk.metadata.get("char_count", len(chunk.text)),
                    vector,
                )
                for chunk, vector in zip(chunks, vectors)
            ]
            cursor.executemany(
                """
                INSERT INTO chunks (
                    chunk_id, strategy, document_id, source, page, printed_page,
                    page_type, article, chapter, section, form, text, char_count, embedding
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    strategy     = EXCLUDED.strategy,
                    document_id  = EXCLUDED.document_id,
                    source       = EXCLUDED.source,
                    page         = EXCLUDED.page,
                    printed_page = EXCLUDED.printed_page,
                    page_type    = EXCLUDED.page_type,
                    article      = EXCLUDED.article,
                    chapter      = EXCLUDED.chapter,
                    section      = EXCLUDED.section,
                    form         = EXCLUDED.form,
                    text         = EXCLUDED.text,
                    char_count   = EXCLUDED.char_count,
                    embedding    = EXCLUDED.embedding
                """,
                rows,
            )
            connection.commit()

        return {"written": len(rows), "deleted": deleted}

    def count(self, strategy: str | None = None) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            if strategy is None:
                cursor.execute("SELECT count(*) FROM chunks")
            else:
                cursor.execute("SELECT count(*) FROM chunks WHERE strategy = %s", (strategy,))
            return int(cursor.fetchone()[0])

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Rank by cosine distance and return the top-k chunks.

        Filter values are bound parameters, and unknown filter keys raise instead
        of being dropped, so a filtered run cannot silently return unfiltered
        results.
        """
        if len(query_vector) != self.dimensions:
            raise ValueError(
                f"query vector has {len(query_vector)} dimensions, expected {self.dimensions}"
            )
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        clauses = ["strategy = %s"]
        params: list[Any] = [strategy]

        for key, value in (filters or {}).items():
            column = _quote_ident(key)
            if value is None:
                clauses.append(f"{column} IS NULL")
            else:
                clauses.append(f"{column} = %s")
                params.append(value)

        where = " AND ".join(clauses)
        # Parameter order follows the placeholders in the statement text:
        # the distance in the SELECT list first, then the WHERE clause, then
        # the ORDER BY distance and the limit.
        statement = f"""
            SELECT chunk_id, source, page, printed_page, page_type, article,
                   chapter, section, form, text,
                   1 - (embedding <=> %s::vector) AS score
            FROM chunks
            WHERE {where}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(statement, [query_vector, *params, query_vector, top_k])
            rows = cursor.fetchall()

        return [
            {
                "chunk_id": row[0],
                "source": row[1],
                "page": row[2],
                "printed_page": row[3],
                "page_type": row[4],
                "article": row[5],
                "chapter": row[6],
                "section": row[7],
                "form": row[8],
                "text": row[9],
                "score": float(row[10]),
            }
            for row in rows
        ]
