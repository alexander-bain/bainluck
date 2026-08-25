"""Guard: a colon in a SQL comment is still a bind parameter.

THE DEFECT THIS CATCHES.

``sqlalchemy.text()`` does not strip SQL comments before it scans for ``:name``
bind parameters. So a ``--`` comment containing prose like::

    -- `clean_vms` is joined at :1684

registers a REQUIRED bind parameter named ``1684``. Every execution of that
statement then raises ``InvalidRequestError: A value is required for bind
parameter '1684'`` — before the query reaches Postgres, with a message that
names a number appearing nowhere in the caller's parameter dict.

This is gotcha #45 (``LIKE '%:x'`` inside ``text()`` parses as a bind param)
one step further out: there, the colon was at least inside the SQL. Here it is
inside a COMMENT, which is the last place a reader looks for something
load-bearing — the whole point of a comment is that it does not execute.

WHAT IT COST. `_CALIBRATION_AUDIT_POPULATION_SQL` in
``app/routes/admin_data_quality.py`` acquired exactly this on 2026-08-25, in a
comment whose subject was a LINE NUMBER. The admin calibration-audit endpoint
was dead on arrival — not slow, not wrong, raising on every call — and nothing
caught it, because the only test that executes that constant is a ``*_pg.py``
module needing a real Postgres, which is skipped everywhere except one CI job.
It surfaced only after two unrelated int32 fixture bugs in front of it were
cleared, each of which had been masking it.

WHY THE TEST IS SHAPED LIKE THIS. It compares the bind set of the raw SQL
against the bind set of the same SQL with ``--`` comments removed. A bind that
exists in the first and not the second is, by construction, a bind that lives
only in a comment — and no such bind is ever intentional. That makes the check
exact rather than heuristic: it does not guess at what a "real" parameter name
looks like, so it cannot be defeated by a legitimately numeric-ish name and it
does not have to be updated when someone adds a normal parameter.

Runs with no database, which is the entire point — the defect it catches lives
in code whose only real-Postgres reader is a job most runs never reach.

WHY IT SCANS `scripts/` AND NOT JUST `app/`. The first sweep for this defect
covered `app/` alone, on the reasoning that a script is not production. That was
wrong twice over. `scripts/audit_golf_hockey_calibration.py` carried the same
comment (`joined at :156`, same author, same sentence) — and the peers test
lifts `BUILD_TEMP_SQL` out of it and runs it through `text()`, so a "not
production" string was one CI job away from reding master again. The script's
own caller is a psycopg2 cursor, where `:156` is inert; the bug exists only for
whoever imports the constant. **SQL is at risk wherever it is DEFINED, because
the risk is created by who executes it, and that is not decided in the file that
holds it.** Scoping this guard to `app/` would have reproduced, in the guard
itself, the exact instance-not-class mistake that made the fix take two pushes.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = (BACKEND_ROOT / "app", BACKEND_ROOT / "scripts")

#: Module-level SQL held in a triple-quoted string and named as SQL. This is the
#: shape that gets passed to `text()` wholesale, which is the shape at risk.
_SQL_CONSTANT = re.compile(
    r"^([A-Z_][A-Z0-9_]*(?:SQL|QUERY))\s*=\s*r?(\"\"\"|''')(.*?)\2",
    re.S | re.M,
)

_LINE_COMMENT = re.compile(r"--[^\n]*")


def _sql_constants() -> list[tuple[Path, str, str]]:
    out: list[tuple[Path, str, str]] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            try:
                src = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):  # pragma: no cover - unreadable
                continue
            for match in _SQL_CONSTANT.finditer(src):
                out.append((path, match.group(1), match.group(3)))
    return out


def _binds(sql: str) -> set[str]:
    return set(text(sql)._bindparams)


def test_the_scan_actually_finds_sql_constants() -> None:
    """The guard's own floor — a scan matching nothing is green for free.

    57 constants at the time of writing (2026-08-25) — 35 under `app/`, 22 under
    `scripts/`. The floor sits well below that so a legitimate deletion cannot
    red it, while a regex that stops matching altogether still does.
    """
    found = _sql_constants()
    assert len(found) >= 20, (
        f"the SQL-constant scan matched only {len(found)} constants under "
        f"{[str(r) for r in SCAN_ROOTS]}; the pattern has drifted and this "
        "guard now checks nothing."
    )


def test_no_sql_constant_declares_a_bind_parameter_only_inside_a_comment() -> None:
    offenders = []
    for path, name, sql in _sql_constants():
        try:
            in_full = _binds(sql)
        except Exception:  # pragma: no cover - unparseable SQL is a different bug
            continue
        if not in_full:
            continue
        try:
            in_code = _binds(_LINE_COMMENT.sub("", sql))
        except Exception:  # pragma: no cover
            continue
        comment_only = in_full - in_code
        if comment_only:
            offenders.append((path, name, sorted(comment_only)))

    assert not offenders, "\n".join(
        [
            "These SQL constants declare bind parameters that appear ONLY inside "
            "`--` comments. `text()` does not strip comments, so each one is a "
            "REQUIRED parameter and every execution of the statement raises "
            "InvalidRequestError before reaching the database:",
            *(
                f"  {p.relative_to(BACKEND_ROOT)}  {n}  ->  {b}"
                for p, n, b in offenders
            ),
            "",
            "Almost always this is a line number, a time, or a URL written in "
            "prose. Rewrite the comment so the colon is not followed by a word "
            "character (e.g. 'at line 1684'), or double it to '::' if it must "
            "stay.",
        ]
    )
