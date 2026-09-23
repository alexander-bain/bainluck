"""#8132: a price-derived crowner may not overwrite a venue-licensed grade.

## the hole this closes, and why the existing guards did not see it

`backfill_winners` holds three price-derived crowners. Each one selects ELIGIBLE
MARKETS in a CTE and then UPDATEs **every leg of those markets**, with no clause
asking what the individual leg's grade already says:

    ~1340   clean_resolution (t1)   fires when the venue returns NO markets
    ~7358   clean_resolution (t1)   fires when every leg is near-certain
    ~10579  settlement_sync  (t3)   golf, when is_winner != (prob >= 0.95)

So a tier-1 price fallback could stamp over a tier-3 venue settlement — a
downgrade `is_downgrade` forbids, executed by SQL that never consults it. The
first crowner is the measured ORIGIN of #8132's 46 `clean_resolution` rows: Kalshi
PURGES per-leg results at ~75 days (`GET /events/{ticker}` then answers 200 with an
empty `markets` array), `nested` came back empty, and `is_winner =
current_probability >= 0.95` became "won" on legs the venue had finalized `no`.

`ungradeable_result` is the second member and the more interesting one, because
`resolution_authority.TERMINAL_SOURCES` already claims it is protected:

    It is NOT in OVERWRITABLE_WINNER_SOURCES: the re-resolution HAVING guards ask
    "may a price-derived crowner supersede this?", and the answer for a row we
    have just declared unknowable is no.

That claim was false. Those HAVING guards count only rows where `fo.is_winner` is
TRUE, and a retraction is `is_winner = false` — it contributes 0 to the SUM and is
invisible to the very guard named as its defence. Every `ungradeable_result` row
the #1852 rail has ever written was exposed. These tests are where that sentence
becomes true.

## why these assertions are shaped the way they are

The set tests pin MEMBERSHIP and NON-membership, because a guard that grew to
cover everything would pass a "does it protect X" test while silently freezing
every crowner. `DETERMINISTIC_SOURCES` is asserted ABSENT for that reason: the
guard removes writes that are wrong by the ladder's own arithmetic and no others,
and a future edit that quietly adds tier 2 should fail here and be argued for.

The SQL tests anchor on the crowner's own SET clause rather than searching the
whole 10k-line module for a string. A bare `"PRICE_CROWN" in source` assertion
would pass if the constant were interpolated into an unrelated statement, or into
a comment — it cannot fail for the reason it claims to test. Each test here
extracts ONE statement by its distinctive SET expression and asserts the guard is
inside THAT statement.

The behavioural both-directions proof (a protected leg refused, an unprotected leg
still written) needs a real planner and lives in
`tests/integration/test_price_crown_protected_8132_pg.py`.
"""

from __future__ import annotations

import importlib
import inspect
import re

import pytest

from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES,
    DETERMINISTIC_SOURCES,
    GUESS_FAMILY_SOURCES,
    KNOWN_SOURCES,
    OVERWRITABLE_WINNER_SOURCES,
    PRICE_CROWN_PROTECTED_SOURCES,
    PRICE_CROWN_PROTECTED_SOURCES_SQL,
    authority_tier,
    price_crown_protected_sql,
)


# ---------------------------------------------------------------------------
# The set itself
# ---------------------------------------------------------------------------


def test_protects_every_authoritative_source():
    """The venue's own declared result is the thing being protected."""
    missing = AUTHORITATIVE_SOURCES - PRICE_CROWN_PROTECTED_SOURCES
    assert not missing, f"tier-3 sources left unprotected from price crowners: {missing}"


def test_protects_the_1852_retraction():
    """`ungradeable_result` is protected HERE, not by the HAVING guards.

    This is the assertion that makes TERMINAL_SOURCES' prose true.
    """
    assert "ungradeable_result" in PRICE_CROWN_PROTECTED_SOURCES


def test_does_not_protect_deterministic_or_guess_sources():
    """The guard is exactly as wide as the ladder justifies, and no wider.

    A same-or-higher-tier rewrite of a box-score-derived grade is permitted by
    `is_downgrade`, and nothing has measured a reason to forbid it. If a later
    change wants tier 2 in here, it should have to argue with this test rather
    than widen a set nobody re-reads.
    """
    overreach = PRICE_CROWN_PROTECTED_SOURCES & (
        DETERMINISTIC_SOURCES | GUESS_FAMILY_SOURCES
    )
    assert not overreach, f"guard reaches past the ladder's own arithmetic: {overreach}"


def test_protected_set_is_exactly_tier3_plus_the_retraction():
    """Pins the set whole, so neither direction of drift is silent."""
    assert PRICE_CROWN_PROTECTED_SOURCES == AUTHORITATIVE_SOURCES | {
        "ungradeable_result"
    }


def test_every_protected_source_is_classified():
    """An unclassified source is tier -1 and would be protected by accident."""
    for source in PRICE_CROWN_PROTECTED_SOURCES:
        assert source in KNOWN_SOURCES, f"{source} is not on the ladder"
        assert authority_tier(source) >= 1, f"{source} classifies below terminal"


def test_clean_resolution_is_not_protected_from_itself():
    """The tier-1 crowners must stay able to write ordinary price-derived rows.

    `clean_resolution` is in OVERWRITABLE_WINNER_SOURCES; if the guard swallowed
    it, the two tier-1 crowners would stop re-resolving their own population and
    the change would be a silent capability regression rather than a fix.
    """
    assert "clean_resolution" not in PRICE_CROWN_PROTECTED_SOURCES
    assert "clean_resolution" in OVERWRITABLE_WINNER_SOURCES


# ---------------------------------------------------------------------------
# The SQL fragment and the per-writer helper
# ---------------------------------------------------------------------------


def test_sql_fragment_is_a_quoted_in_list():
    frag = PRICE_CROWN_PROTECTED_SOURCES_SQL
    assert frag.startswith("(") and frag.endswith(")")
    rendered = {s.strip().strip("'") for s in frag[1:-1].split(",")}
    assert rendered == PRICE_CROWN_PROTECTED_SOURCES


def test_writer_is_subtracted_so_a_sync_pass_stays_idempotent():
    """The golf pass stamps `settlement_sync`, which is itself tier 3.

    Protecting the set wholesale would freeze that pass against its own rows and
    strand the corrections it exists to make — a tightening, not a guard.
    """
    frag = price_crown_protected_sql("settlement_sync")
    assert "'settlement_sync'" not in frag
    assert "'api_settlement'" in frag, "subtracting the writer must not drop the rest"
    assert "'ungradeable_result'" in frag


def test_subtracting_the_writer_removes_exactly_one_member():
    for writer in sorted(PRICE_CROWN_PROTECTED_SOURCES):
        frag = price_crown_protected_sql(writer)
        rendered = {s.strip().strip("'") for s in frag[1:-1].split(",")}
        assert rendered == PRICE_CROWN_PROTECTED_SOURCES - {writer}


def test_unknown_writer_raises_rather_than_widening():
    """A typo'd source name must not silently return the full set.

    `_sql_in_list(SET - {"typo"})` is the full set, so the failure mode of a
    misspelled writer is a guard that is wider than intended in a place where
    wider means "freezes a pass" — loud is the only safe answer.
    """
    with pytest.raises(ValueError, match="unknown resolution_source"):
        price_crown_protected_sql("settlemnt_sync")


# ---------------------------------------------------------------------------
# The three crowners actually carry it
# ---------------------------------------------------------------------------

# 🪤 `from app.tasks import backfill_winners` binds the TASK FUNCTION, not the
# module — `app/tasks/__init__.py` exports a Celery task of that name, and it
# shadows the module it lives in. `inspect.getsource` on it returns 427
# characters of decorator, every `in` test below reads False, and the suite
# passes as a dead instrument that examined nothing. `import_module` is the only
# form that cannot be shadowed. The repair script's `guard_is_live()` had this
# same bug and would have refused to apply for ever.
_SOURCE = inspect.getsource(importlib.import_module("app.tasks.backfill_winners"))

assert len(_SOURCE) > 100_000, (
    "backfill_winners source reads as tiny — the module name is shadowed again "
    "and every SQL assertion below is vacuous"
)

#: Each crowner named by the SET expression that makes it a PRICE crowner, so the
#: test is pinned to the statement and not to a line number or a comment.
_CROWNERS = {
    "clean_resolution (empty-venue fallback + near-certain pass)": (
        "SET is_winner = (fo.current_probability >= 0.95),\n"
    ),
    "settlement_sync (golf)": (
        "SET is_winner = (fo.current_probability >= 0.95), "
        "resolution_source = 'settlement_sync'"
    ),
}


#: A statement ends where its `text(...)` call closes. It does NOT end at the
#: first `"""`: an interpolated guard is written `NOT IN """ + CONST + """`, so
#: the first `"""` falls INSIDE the clause being tested. Cutting there truncates
#: every statement one character before the thing these tests exist to find, and
#: each assertion then fails for a reason that has nothing to do with the code.
_STATEMENT_END = re.compile(r'"""\s*\)')


def _statements_containing(set_clause: str) -> list[str]:
    """Every UPDATE statement whose SET clause is `set_clause`."""
    out = []
    for match in re.finditer(re.escape(set_clause), _SOURCE):
        tail = _SOURCE[match.start() : match.start() + 6000]
        end = _STATEMENT_END.search(tail)
        out.append(tail[: end.end()] if end else tail)
    return out


def test_every_price_crowner_statement_is_found():
    """If this fails the other SQL tests are vacuous — they would scan nothing."""
    total = sum(len(_statements_containing(c)) for c in _CROWNERS.values())
    assert total == 3, (
        f"expected 3 price-crowner UPDATE statements, found {total}. The SET "
        "expressions these tests anchor on have moved; re-anchor them rather "
        "than deleting the assertion."
    )


@pytest.mark.parametrize("name,set_clause", sorted(_CROWNERS.items()))
def test_price_crowner_guards_the_leg_it_writes(name, set_clause):
    statements = _statements_containing(set_clause)
    assert statements, f"no statement found for {name}"
    for statement in statements:
        assert "resolution_source, '') NOT IN" in statement, (
            f"{name}: the UPDATE vets the MARKET in its CTE but writes the LEG "
            "with no authority guard — this is the #8132 hole"
        )
        assert (
            "PRICE_CROWN_PROTECTED_SOURCES_SQL" in statement
            or "price_crown_protected_sql(" in statement
        ), f"{name}: guards on some other list than the shared protected set"


def test_golf_crowner_subtracts_its_own_source():
    """The tier-3 crowner must use the per-writer helper, not the bare set."""
    (statement,) = _statements_containing(_CROWNERS["settlement_sync (golf)"])
    assert 'price_crown_protected_sql("settlement_sync")' in statement


def test_guard_is_interpolated_not_quoted_as_a_literal():
    """A guard rendered as the literal STRING name would match nothing in PG.

    `NOT IN 'PRICE_CROWN_PROTECTED_SOURCES_SQL'` is valid-looking Python inside a
    triple-quoted block and a runtime error (or worse, an always-true predicate)
    in SQL. The interpolation seam is what makes it real.
    """
    for set_clause in _CROWNERS.values():
        for statement in _statements_containing(set_clause):
            assert 'NOT IN """ +' in statement, (
                "the protected list must be concatenated into the SQL, not "
                "embedded as a literal token"
            )
