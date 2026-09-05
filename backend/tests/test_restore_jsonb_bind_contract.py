"""Every restore's `:row` bind must reach asyncpg as a STRING. CERT-932.

The real proof of this lives in `tests/integration/test_restore_3026_jsonb_roundtrip_pg.py`,
which drives backup → delete → restore against a live PostgreSQL. That gate runs
only in CI's `search-recall` job, because there is no Postgres in the agent
sandbox. This file is the cheap half that runs everywhere: it asks SQLAlchemy's
own asyncpg dialect what value each restore statement would hand the driver, and
fails if the answer is a dict.

WHY THE CHEAP HALF IS WORTH HAVING ANYWAY. The defect is a missing TYPE, and
losing it again is a one-token edit — dropping `.bindparams(...)`, or writing a
new `INSERT ... jsonb_populate_record` without it. A lane that makes that edit
locally should not have to wait for a real-Postgres job in CI to find out, and
`_populate_insert` is small enough that inlining it back looks harmless.

WHAT IT CANNOT DO, so it is not mistaken for the gate. It does not execute
anything. It proves the bind processor exists and produces a string; it cannot
prove the resulting row reconstructs, that the JSONB content survives, or that
the FKs line up. Those need the server. A green here with a red there means the
type is right and something else is wrong.

BOTH FILES ARE COVERED. `restore_2993_bracket_events.py` shipped the identical
untyped bind and is already on master — with `bak_2993_bracket_events` live on
production, so that repair has been applied and stood behind an undo that would
have raised. Discovering the pair by scan rather than by name is deliberate: a
third restore script written the same way joins this test automatically.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

#: Any `restore_*.py` that rebuilds rows from a banked jsonb snapshot. Found by
#: scanning for the call rather than by a hand-kept list, so a new one cannot be
#: added without this test noticing.
_POPULATE_RE = re.compile(r"jsonb_populate_record")


def _restore_scripts_using_jsonb_populate():
    return sorted(
        p
        for p in SCRIPTS.glob("restore_*.py")
        if _POPULATE_RE.search(p.read_text())
    )


def _load(path):
    spec = importlib.util.spec_from_file_location(f"_bindcheck_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _value_handed_to_asyncpg(stmt, row):
    """What the asyncpg driver would actually receive for `:row`."""
    from sqlalchemy.dialects.postgresql.asyncpg import dialect as asyncpg_dialect

    d = asyncpg_dialect()
    bind = stmt.compile(dialect=d).binds["row"]
    processor = bind.type.dialect_impl(d).bind_processor(d)
    return processor(row) if processor is not None else row


def test_at_least_one_restore_script_is_being_checked():
    """The scan must find something, or this file is green over nothing."""
    found = _restore_scripts_using_jsonb_populate()
    assert found, (
        "no restore_*.py under backend/scripts uses jsonb_populate_record. Either "
        "they all stopped restoring that way, or the scan broke — a bind-type "
        "check that inspects zero statements passes for free."
    )
    # Both known offenders, so a rename cannot quietly halve the coverage.
    names = {p.name for p in found}
    assert {
        "restore_3026_question_events.py",
        "restore_2993_bracket_events.py",
    } <= names, f"expected both known restores in the scan, found {sorted(names)}"


@pytest.mark.parametrize(
    "path", _restore_scripts_using_jsonb_populate(), ids=lambda p: p.name
)
@pytest.mark.parametrize("table", ["events", "event_provider_anchors"])
def test_restore_row_bind_is_typed_jsonb(path, table):
    """A dict must be serialised before it reaches the driver.

    `NullType` — what an unannotated `text()` bind compiles to — has no bind
    processor, so the dict passes through and asyncpg's jsonb codec calls
    `.encode()` on it.
    """
    module = _load(path)
    assert hasattr(module, "_populate_insert"), (
        f"{path.name} builds a jsonb_populate_record INSERT but exposes no "
        "`_populate_insert`. Route it through one so its bind type is checkable "
        "from here rather than only from a real-Postgres job."
    )

    stmt = module._populate_insert(table, on_conflict_nothing=(table != "events"))
    row = {"id": 1, "win_probability_sources": {"kalshi": 0.5}}
    handed = _value_handed_to_asyncpg(stmt, row)

    assert isinstance(handed, str), (
        f"{path.name} would hand asyncpg a {type(handed).__name__} for "
        f"{table}'s :row bind. asyncpg's jsonb codec calls .encode() on it and "
        "the restore dies on its first insert — the exact CERT-932 defect. Type "
        "the bind: .bindparams(bindparam('row', type_=JSONB))."
    )
    # And it must be the row, not a repr of it: `str(dict)` is a string too and
    # would satisfy the assertion above while producing invalid JSON.
    import json

    assert json.loads(handed) == row, (
        f"{path.name} serialised {table}'s :row to something that is not this "
        f"row's JSON: {handed!r}"
    )


@pytest.mark.parametrize(
    "path", _restore_scripts_using_jsonb_populate(), ids=lambda p: p.name
)
def test_the_untyped_form_would_fail_this_check(path):
    """THE RED ARM: the check is capable of failing.

    Without it, `test_restore_row_bind_is_typed_jsonb` could be green because
    the dialect started serialising everything, and nobody would know the
    assertion had stopped discriminating.
    """
    from sqlalchemy import text

    stmt = text(
        "INSERT INTO events SELECT (jsonb_populate_record(NULL::events, :row)).*"
    )
    handed = _value_handed_to_asyncpg(stmt, {"id": 1})
    assert isinstance(handed, dict), (
        "an untyped text() :row bind no longer passes a raw dict through to the "
        "driver. If SQLAlchemy started serialising it, the positive check above "
        "cannot fail any more and this whole file needs re-deriving."
    )
