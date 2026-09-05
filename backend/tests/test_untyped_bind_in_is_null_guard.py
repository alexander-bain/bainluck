"""No raw SQL in this codebase may write `:param IS NULL` untyped.

The invariant, not the feature
------------------------------
asyncpg prepares every statement with **no parameter types**, so Postgres infers
them from the query text alone — and the FIRST occurrence of a parameter fixes
its type. ``$1 IS NULL`` fixes ``$1`` as ``unknown``, a later ``col = $1`` can no
longer resolve it, and the PREPARE dies with::

    asyncpg.exceptions.AmbiguousParameterError:
    could not determine data type of parameter $1

before a single row is read, **whatever value is bound**. psycopg2 would have
interpolated and never noticed; asyncpg cannot.

The specimen (#1852 / #2528, found 2026-09-05): the fabricated-loss drain —
63,733 wrong Kalshi results, built 2026-08-14, certified twice, a large green
unit suite — had never completed one work selection through its own endpoint,
because of exactly one line::

    AND (:sport IS NULL OR fm.llm_sport_category = :sport)

Every sibling rail already wrote ``:sport::text`` on both sides
(``repair_polymarket_leg_label.py`` :457-458, :758) and the keyset predicate two
lines below it already cast both halves. One line did not, and the endpoint was
dead for three weeks with nothing red.

`tests/integration/test_kalshi_fabricated_loss_bind_contract_pg.py` proves the
specimen against a real server. This file is the CLASS, and it is deliberately
cheap and unconditional: the real-Postgres gate lives in one CI job that can be
skipped, reordered or dropped, and the next rail to make this mistake will not
be this rail.

An optional-filter bind is the shape that attracts it — `(:x IS NULL OR col =
:x)` is how every paged repair spells "no filter" — so this is not a hypothetical
class with one member.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

#: A bind used directly in a NULL test with nothing typing it. `CAST(:x AS text)
#: IS NULL` fails to match because of the intervening `AS text)`, and the
#: `(?<!:)` is load-bearing for the other spelling: without it `:sport::text IS
#: NULL` reads as a bind literally named `text` and the guard reports the FIX as
#: the defect. (It did, on first run — kept as the control below.)
UNTYPED_IS_NULL = re.compile(r"(?<!:):(\w+)\s+IS\s+(?:NOT\s+)?NULL", re.IGNORECASE)

#: A URL is not a bind, and neither is prose. `reconcile_unanchored_events.py`
#: has a comment that quotes this very pattern while explaining why it is wrong,
#: which is the one thing a source-text scan cannot tell from the real thing.
_NOT_SQL = re.compile(r"https?://")


def test_no_raw_sql_tests_an_untyped_bind_for_null():
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#") or _NOT_SQL.search(line):
                continue
            for match in UNTYPED_IS_NULL.finditer(line):
                offenders.append(
                    f"{path.relative_to(APP.parent)}:{lineno}  "
                    f":{match.group(1)} IS NULL  ->  {line.strip()[:100]}"
                )

    assert not offenders, (
        "an untyped bind in a NULL test dies at PREPARE under asyncpg, before "
        "any row is read and whatever value is bound "
        "(AmbiguousParameterError). Write `:x::text IS NULL` or "
        "`CAST(:x AS text) IS NULL` — and use the SAME cast on every other "
        "occurrence of that bind, because the first one fixes the type:\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_catches_the_specimen_it_was_written_for():
    """The over-reach control: a pattern that matches nothing proves nothing.

    This is the exact text that was on
    `repair_kalshi_fabricated_loss.py:513` until 2026-09-05, and the two
    spellings that fix it.
    """
    broken = "      AND (:sport IS NULL OR fm.llm_sport_category = :sport)"
    assert [m.group(1) for m in UNTYPED_IS_NULL.finditer(broken)] == ["sport"]

    # The first version of this pattern reported `:sport::text IS NULL` as a
    # bind named `text` — it called the FIX a defect, which would have made the
    # guard unfixable and then deleted. Named here so it cannot come back.
    for fixed in (
        "AND (:sport::text IS NULL OR fm.llm_sport_category = :sport::text)",
        "AND (CAST(:sport AS text) IS NULL OR fm.llm_sport_category = CAST(:sport AS text))",
        "AND (:after_id::bigint IS NOT NULL OR fo.id > :after_id::bigint)",
    ):
        assert not UNTYPED_IS_NULL.findall(fixed), fixed
