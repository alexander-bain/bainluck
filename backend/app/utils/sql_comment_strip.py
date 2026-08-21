"""Strip SQL comments from a statement — the one tool that made #2076's premise testable.

Why this exists
---------------
``POST /api/admin/db-query`` refuses a statement whose body contains more than
one semicolon (``Multi-statement queries not allowed``). The guard counts
semicolons **lexically**, so a semicolon inside a ``--`` comment counts (gotcha
#149). ``_calibration_population_ctes()`` — the frozen calibration population
builder — carries **15 semicolons, every one of them inside a comment**, so the
published-twin fold could not be sent to the read rail at all, not even
plan-only.

CAL-P084 recorded that as a hard wall and shipped a decision without the
measurement behind it (module header of
``app/tasks/calibration_published_twin_worker.py``: *"the pushdown question is
the whole decision"*). It is not a wall. It is a tooling obstacle, and this is
the tool: a **read-only copy** of the statement with its comments removed. The
copy is never executed against a writer, never stored, and never replaces the
frozen builder — it exists so the planner can be asked a question about the SQL
the builder produces.

What it is careful about, and why each case is real here
--------------------------------------------------------
A naive ``re.sub(r'--.*$', '')`` is wrong in three ways that all appear in
production SQL:

1. **A ``--`` inside a string literal is data, not a comment.** The calibration
   builder is full of literals like ``'odds_api'``; a literal containing ``--``
   would be silently truncated and the statement would still parse, which is the
   worst outcome — a *different query* that runs.
2. **``''`` is an escaped quote inside a literal**, not the end of one. Getting
   this wrong flips the in-string state for the whole rest of the statement.
3. **Block comments nest in PostgreSQL.** ``/* a /* b */ c */`` is one comment;
   a non-nesting scanner ends it at the first ``*/`` and then treats ``c */`` as
   SQL.

Dollar-quoted bodies (``$$ ... $$``, ``$tag$ ... $tag$``) are handled for the
same reason as (1): everything inside one is data.

This module is **pure** — no session, no I/O, no clock — so the whole of it is
testable in the sandbox, which is the standard this program holds readers to.
"""

from __future__ import annotations

import re

__all__ = ["strip_sql_comments", "count_statement_separators"]

_DOLLAR_TAG_RE = re.compile(r"\$[A-Za-z_][A-Za-z_0-9]*\$|\$\$")


def strip_sql_comments(sql: str) -> str:
    """Return ``sql`` with ``--`` and ``/* */`` comments removed.

    String literals, quoted identifiers and dollar-quoted bodies are preserved
    **verbatim**, including any comment markers inside them. Newlines outside
    literals are preserved so line numbers in a planner error still point
    somewhere useful; a stripped line comment leaves its newline behind.
    """
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]

        # ---- line comment: consume to (but not including) the newline -------
        if ch == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j
            continue

        # ---- block comment: PostgreSQL nests these -------------------------
        if ch == "/" and sql.startswith("/*", i):
            depth = 1
            i += 2
            while i < n and depth:
                if sql.startswith("/*", i):
                    depth += 1
                    i += 2
                elif sql.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            continue

        # ---- single-quoted literal: '' is an escaped quote ------------------
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        out.append("''")
                        i += 2
                        continue
                    out.append("'")
                    i += 1
                    break
                out.append(sql[i])
                i += 1
            continue

        # ---- double-quoted identifier: "" is an escaped quote ---------------
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n:
                if sql[i] == '"':
                    if i + 1 < n and sql[i + 1] == '"':
                        out.append('""')
                        i += 2
                        continue
                    out.append('"')
                    i += 1
                    break
                out.append(sql[i])
                i += 1
            continue

        # ---- dollar-quoted body --------------------------------------------
        if ch == "$":
            m = _DOLLAR_TAG_RE.match(sql, i)
            if m:
                tag = m.group(0)
                end = sql.find(tag, m.end())
                if end == -1:
                    out.append(sql[i:])
                    i = n
                    continue
                out.append(sql[i : end + len(tag)])
                i = end + len(tag)
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def count_statement_separators(sql: str) -> int:
    """Semicolons that a lexical multi-statement guard would count.

    Provided so a caller can *prove* the stripped copy is single-statement
    before sending it, rather than discovering it from a 400. A trailing
    semicolon still counts — the read rail counts it too.
    """
    return sql.count(";")
