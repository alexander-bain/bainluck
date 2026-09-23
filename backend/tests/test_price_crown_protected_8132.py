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
`tests/integration/test_price_crown_leg_guard_8132_real_postgres.py`.

## the +6h survival read, and why this file grew a second half

The guard above shipped covering the three crowners the issue had traced, all of
them PRICE-derived. Six hours after the 56-row repair applied, the watcher read
the cohort back: the 46 legs stamped over a `clean_resolution` held, and all 10
stamped over a prior `game_score` were back at `game_score / is_winner = true`.

They were rewritten by a crowner nobody had guarded. `_resolve_kalshi_from_scores`
and `_resolve_kalshi_spread_total_from_scores` derive a verdict from
`events.home_score/away_score` rather than from a price — a different route into
exactly the same hole. Their candidate scan is the same `HAVING SUM(CASE WHEN
fo.is_winner AND ...)` that cannot see an `is_winner = false` retraction, and
their UPDATEs asked the leg nothing either. `game_score` is tier 2 and
`api_settlement` tier 3, so the write was the downgrade `is_downgrade` forbids.

Measured on the repaired cohort: 43 of the 56 legs were structurally ineligible
for a score crowner (no `event_id`, or an event carrying no scores) and 3 were
spared by the grader's own question refusals. Of the 10 the guard was actually
tested on, it protected 0.

So the second half of this file pins the SCORE crowners the same way — and it
cannot reuse the extractor above, for a reason worth stating: `_STATEMENT_END`
looks for `\"\"\")`, and a statement assembled by CONCATENATION
(`"UPDATE … NOT IN " + GUARD`) has no triple quote to find. The search then falls
through to a 6,000-character window, which on this module spans several later
statements — so an UNGUARDED concatenated statement would pass by borrowing the
guard of a neighbour. `_text_call_containing` balances the `text(` parentheses
instead, and `test_score_crowner_extractor_stops_at_its_own_call` is what proves
it did not run away.
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


# ---------------------------------------------------------------------------
# The SCORE-derived crowners carry it too (#8132's +6h survival read)
# ---------------------------------------------------------------------------

#: A `session.execute(...)` call is never this long in this module — measured
#: 2026-09-23 over all 161 of them, the longest is 3,576 characters. If the
#: balancer runs past this something is unbalanced and the window has started
#: swallowing neighbouring statements, which is the exact vacuity the
#: concatenated form invites; a hard stop, never a truncation. The tighter
#: runaway check is `test_the_execute_extractor_is_alive`'s one-UPDATE-per-call
#: assertion — this bound only stops a scan to end-of-file.
_MAX_EXECUTE_CALL_CHARS = 6000


def _balanced_call(open_at: int) -> str:
    """The whole parenthesised call starting at `open_at`.

    Parenthesis-balanced rather than delimiter-sniffed. These statements are
    built three different ways — a single-line literal, a concatenation, and a
    triple-quoted block — and no one closing token ends all three. The
    concatenated form is the dangerous one: it has no `\"\"\")` for a
    delimiter-based search to stop on, so a search that misses runs on into the
    NEXT statement and reports an unguarded write as guarded.
    """
    i = _SOURCE.index("(", open_at)
    depth = 0
    while i < len(_SOURCE):
        if _SOURCE[i] == "(":
            depth += 1
        elif _SOURCE[i] == ")":
            depth -= 1
            if depth == 0:
                return _SOURCE[open_at : i + 1]
        i += 1
        assert i - open_at < _MAX_EXECUTE_CALL_CHARS, (
            f"call at {open_at} never closed within {_MAX_EXECUTE_CALL_CHARS} "
            "chars — the balancer has run away and every assertion below would "
            "be reading a neighbour's guard"
        )
    raise AssertionError("unterminated call")


#: Every `session.execute(...)` in the module, whole, each carrying the text of
#: its own line up to the call so the assignment target is visible. Anchoring on
#: the EXECUTE rather than the inner `text()` is what lets a bound-parameter
#: write be classified: `resolution_source = :src` says nothing on its own, and
#: the literal that decides which crowner it is lives in the params dict beside
#: it. The line prefix is needed for the rowcount assertion — `x = await
#: session.execute(` puts the only evidence that a result was kept OUTSIDE the
#: parentheses.
_EXECUTE_CALLS = [
    _SOURCE[_SOURCE.rfind("\n", 0, m.start()) + 1 : m.start()] + _balanced_call(m.start())
    for m in re.finditer(r"session\.execute\(", _SOURCE)
]

#: The SET clause and nothing else. 🪤 A bare `"resolution_source = 'game_score'"
#: substring test over the whole statement also matches the WHERE clause of the
#: repair rails that EXIST to clear a bad `game_score` — two of them, and both
#: read as unguarded crowners and demand a guard that would stop them repairing
#: anything. A write is decided by the SET clause; a predicate is not a write.
_SET_CLAUSE = re.compile(r"\bSET\b(.*?)(?:\bFROM\b|\bWHERE\b)", re.S)


def _writes_source(call: str, source: str) -> bool:
    """True if this UPDATE STAMPS `source` on `futures_outcomes`."""
    if "UPDATE futures_outcomes" not in call:
        return False
    match = _SET_CLAUSE.search(call)
    if not match:
        return False
    set_clause = match.group(1)
    if f"resolution_source = '{source}'" in set_clause:
        return True
    return "resolution_source = :src" in set_clause and f'"src": "{source}"' in call


_GAME_SCORE_WRITES = [c for c in _EXECUTE_CALLS if _writes_source(c, "game_score")]


def test_the_execute_extractor_is_alive():
    """If the balancer found nothing, every assertion below is vacuous."""
    assert len(_EXECUTE_CALLS) > 100, (
        f"only {len(_EXECUTE_CALLS)} session.execute calls found in a 10k-line "
        "module — the extractor is broken, not the module"
    )
    for call in _EXECUTE_CALLS:
        assert call.count("UPDATE futures_outcomes") <= 1, (
            "an extracted call holds two UPDATEs — it has run past its own "
            "statement and can borrow a neighbour's guard"
        )


def test_every_game_score_write_is_found():
    """Eight writes. If this moves, the assertions below scan the wrong set.

    One golf H2H, one BTTS (the only market-WIDE one in the module), one
    moneyline — that one binds its source as `:src`, which is how it stayed out
    of a grep for the literal — and five in the spread/total resolver
    (team-total, spread, total, and the two name-token fallbacks).
    """
    assert len(_GAME_SCORE_WRITES) == 8, (
        f"expected 8 game_score writes, found {len(_GAME_SCORE_WRITES)}. A new "
        "score crowner has appeared — guard it rather than relaxing this count."
    )


def test_every_game_score_write_guards_the_leg_it_writes():
    """The #8132 hole, closed on the route the survival read found it on."""
    for call in _GAME_SCORE_WRITES:
        assert "resolution_source, '') NOT IN" in call, (
            "a score-derived verdict is written onto the leg with no authority "
            "guard — this is what handed 10 fabricated wins back six hours "
            f"after the #8132 repair:\n{call}"
        )
        assert "_GAME_SCORE_LEG_GUARD_SQL" in call, (
            f"guards on some other list than the shared protected set:\n{call}"
        )


def test_the_guard_is_interpolated_not_a_literal_token():
    """`NOT IN '_GAME_SCORE_LEG_GUARD_SQL'` is valid Python and dead SQL."""
    for call in _GAME_SCORE_WRITES:
        assert (
            'NOT IN " + _GAME_SCORE_LEG_GUARD_SQL' in call
            or 'NOT IN """ + _GAME_SCORE_LEG_GUARD_SQL' in call
        ), f"the protected list must be concatenated into the SQL:\n{call}"


def test_every_game_score_write_reads_its_own_rowcount():
    """A refused write must not report a verdict it did not store.

    The subtle version of this bug counts the refusal AND still claims the
    grade, so `spread + total` keeps rising while nothing reaches the database.
    """
    for call in _GAME_SCORE_WRITES:
        assert re.search(r"\b\w+ = await session\.execute\(", call), (
            "the result of this game_score write is discarded, so a refusal is "
            f"indistinguishable from a write:\n{call}"
        )


def test_the_score_guard_is_the_shared_protected_set():
    """One definition, not a second list that can drift away from the first."""
    module = importlib.import_module("app.tasks.backfill_winners")
    assert module._GAME_SCORE_LEG_GUARD_SQL == price_crown_protected_sql("game_score")
    rendered = {
        s.strip().strip("'")
        for s in module._GAME_SCORE_LEG_GUARD_SQL[1:-1].split(",")
    }
    assert rendered == PRICE_CROWN_PROTECTED_SOURCES


def test_the_score_guard_protects_the_two_sources_the_repair_writes():
    """#8132's repair stamps exactly these two; both must survive a 6h pass."""
    frag = importlib.import_module(
        "app.tasks.backfill_winners"
    )._GAME_SCORE_LEG_GUARD_SQL
    assert "'api_settlement'" in frag
    assert "'ungradeable_result'" in frag


def test_the_score_guard_does_not_freeze_the_pass_against_itself():
    """`game_score` over `game_score` must stay writable.

    Not a softening. A score correction re-grading its own prior row is a
    same-source rewrite `is_downgrade` permits by name, and blocking it would
    turn a guard into a capability regression nobody asked for. The clause must
    also leave `clean_resolution` — the tier-1 price fallback these passes
    legitimately supersede — writable, or the passes stop doing their job.
    """
    frag = importlib.import_module(
        "app.tasks.backfill_winners"
    )._GAME_SCORE_LEG_GUARD_SQL
    assert "'game_score'" not in frag
    assert "'clean_resolution'" not in frag


#: The DERIVED writes in this module that are deliberately NOT guarded by this
#: ship, pinned so the scope boundary is a test rather than a memory.
#:
#: Both are DataGolf passes and both are the same CLASS of hole — a derived
#: verdict written onto a leg with no reference to what that leg already says.
#: Neither is guarded here because neither is what the +6h survival read
#: measured: this ship closes the route that handed #8132's rows back, and
#: widening into golf settlement on the same commit would put an unmeasured
#: population behind a change whose evidence is entirely about Kalshi spreads
#: and totals.
_KNOWN_UNGUARDED_DERIVED_SOURCES = ("leaderboard", "did_not_play")


def test_the_unguarded_derived_writers_are_exactly_the_two_named():
    """Fails in BOTH directions, which is the point.

    A third unguarded derived writer appearing is a regression. These two
    becoming guarded is progress — and should delete its own name from the list
    rather than leave a stale exemption nobody re-reads.
    """
    unguarded = {
        source
        for source in _KNOWN_UNGUARDED_DERIVED_SOURCES
        for call in _EXECUTE_CALLS
        if _writes_source(call, source) and "NOT IN" not in call
    }
    assert unguarded == set(_KNOWN_UNGUARDED_DERIVED_SOURCES), (
        "the deliberately-unguarded derived writers have changed: "
        f"{unguarded} vs {set(_KNOWN_UNGUARDED_DERIVED_SOURCES)}"
    )


@pytest.mark.parametrize(
    "func",
    [
        "_resolve_kalshi_from_scores",
        "_resolve_kalshi_spread_total_from_scores",
        "_resolve_kalshi_golf_from_datagolf",
    ],
)
def test_a_refused_write_is_counted_and_reaches_the_phase_summary(func):
    """A refusal that is not counted is a refusal nobody finds.

    Without this, a guard that came unwired and a guard with nothing to refuse
    print the same phase summary — and the #8132 cohort is precisely a
    population that stays refused for ever, because an `is_winner = false`
    retraction never drops the board out of the candidate scan.
    """
    body = inspect.getsource(
        getattr(importlib.import_module("app.tasks.backfill_winners"), func)
    )
    assert '"protected_legs_refused": 0' in body, f"{func}: counter not initialised"
    assert 'stats["protected_legs_refused"] += 1' in body, (
        f"{func}: nothing ever increments it"
    )
    assert 'stats["protected_legs_refused"],' in body, (
        f"{func}: incremented but never reaches the phase summary — the number "
        "exists and no operator can ever see it"
    )
