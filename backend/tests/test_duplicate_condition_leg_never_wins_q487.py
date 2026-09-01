"""Q487 — a duplicate condition leg is never crowned, and never grades a field.

THE SHIP: a settled field market stops naming "No" as its winner over the real
candidates. Measured on production 2026-09-01, market 59835854 *"Which cities
face tornado risk on August 30?"* — ``0x2f2d…1733`` is **Chicago, IL** at 0.0245
and its duplicate leg ``0x2f2d…1733_no`` is at **0.974, is_winner = true**. "No"
beats 25 real cities. 235 such rows across 217 polymarket ``field`` markets.

WHAT THIS FILE CAN AND CANNOT PROVE — read before trusting it.

There is no local Postgres in this sandbox and the predicate is Postgres-only
(``regexp_replace``, ``right()``), so **no test here executes the SQL that
runs in production.** That is a real gap and it is named, not hidden. What is
provable locally is split in two, and both halves are here:

* **Semantics** — the Python mirror ``is_duplicate_condition_leg`` is exercised
  against the real production row shapes, including the two arms that matter
  most: a leg WITHOUT its bare twin on the market is a legitimate sub-market
  outcome and must survive, and a leg WITH its twin must not.
* **Reach** — the enforcement set is DERIVED BY AST from the task sources, not
  listed here. Every ``UPDATE futures_outcomes`` that writes ``is_winner`` or
  stamps a price-derived ``resolution_source`` must carry the predicate. A new
  price-crowner added tomorrow fails this test with nobody editing a list.

The reach half is the one that earns its place: a hand-maintained list of three
call sites is exactly the drift ``winner_field_coherence``'s own docstring says
caused #1527.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.utils.winner_field_coherence import (
    DUPLICATE_CONDITION_LEG_SQL,
    is_duplicate_condition_leg,
    strip_condition_leg_suffix,
)

BACKEND = Path(__file__).resolve().parents[1]
TASK_SOURCES = (
    BACKEND / "app" / "tasks" / "backfill_winners.py",
    BACKEND / "app" / "tasks" / "polymarket.py",
)

# The production specimen, verbatim from market 59835854 / 12194657.
CHICAGO = "0x2f2d3bc4ec353f3d4c789fcd38c9e6b6fb6dda2e31887b6d600fdb7bd9531733"
ZOE = "0xeda9eb14a054e234a72ab94dc45a6302ca702a6a8e5e7c270e7c91628ac8e084"


# --------------------------------------------------------------------------
# Semantics — the Python mirror, on real row shapes
# --------------------------------------------------------------------------


def test_the_contaminant_that_was_crowned_is_recognised():
    """Market 59835854: `_no` at 0.974 alongside the bare Chicago row."""
    market = [CHICAGO, f"{CHICAGO}_yes", f"{CHICAGO}_no", "0x801d…wichita"]
    assert is_duplicate_condition_leg(f"{CHICAGO}_no", market) is True
    assert is_duplicate_condition_leg(f"{CHICAGO}_yes", market) is True


def test_the_real_candidates_are_untouched():
    """The bare condition rows are the actual outcomes and must keep grading."""
    market = [CHICAGO, f"{CHICAGO}_yes", f"{CHICAGO}_no", "0x801d…wichita"]
    assert is_duplicate_condition_leg(CHICAGO, market) is False
    assert is_duplicate_condition_leg("0x801d…wichita", market) is False


def test_a_lone_leg_without_its_twin_survives():
    """🔴 The arm that stops this fix deleting working markets.

    Container_member market 13798072 carries ONLY `_yes`/`_no` — that is the
    ordinary sub-market shape, those rows are the real outcomes, and settlement
    must keep writing them. Suppressing on the suffix alone would silently
    un-grade every Polymarket binary sub-market in the database.
    """
    submarket = [f"{ZOE}_yes", f"{ZOE}_no"]
    assert is_duplicate_condition_leg(f"{ZOE}_yes", submarket) is False
    assert is_duplicate_condition_leg(f"{ZOE}_no", submarket) is False


def test_the_same_leg_flips_verdict_with_the_market_it_sits_on():
    """One external_id, two markets, two correct answers — the whole defect.

    `…e084_no` exists on BOTH markets in production. On the sub-market it is a
    real outcome; on the field market it is a duplicate of the bare Zoë row.
    A rule keyed on the id alone cannot tell them apart, which is precisely why
    the settlement UPDATE (keyed on external_id, unscoped) wrote both.
    """
    leg = f"{ZOE}_no"
    submarket = [f"{ZOE}_yes", leg]
    field_market = [ZOE, f"{ZOE}_yes", leg, "0x1f34…blake"]
    assert is_duplicate_condition_leg(leg, submarket) is False
    assert is_duplicate_condition_leg(leg, field_market) is True


@pytest.mark.parametrize(
    "external_id,expected",
    [
        (f"{CHICAGO}_no", CHICAGO),
        (f"{CHICAGO}_yes", CHICAGO),
        (CHICAGO, None),
        ("KXAISTREAMSERIES-27-AMA", None),
        ("", None),
        (None, None),
    ],
)
def test_suffix_stripping(external_id, expected):
    assert strip_condition_leg_suffix(external_id) == expected


def test_no_suffix_means_not_a_leg_not_a_missing_twin():
    """`None` distinguishes "cannot be a leg" from "leg whose twin is absent".

    Returning the input unchanged would make a bare condition id look like its
    own twin, and every real outcome would suppress itself.
    """
    assert strip_condition_leg_suffix(CHICAGO) is None
    assert is_duplicate_condition_leg(CHICAGO, [CHICAGO]) is False


# --------------------------------------------------------------------------
# Reach — the enforcement set is derived, not listed
# --------------------------------------------------------------------------

# THE IN-CLASS RULE, and it is narrow on purpose: an UPDATE that stamps
# `is_winner` and selects its rows by `external_id` against a bind parameter.
#
# That pairing IS the defect. `futures_outcomes.external_id` is NOT unique — one
# Polymarket condition sits on two markets under two conventions (verified in
# production: `0xeda9…e084_no` on both 13798072 and 12194657) — so an
# external_id-keyed write is unscoped by construction and hits every namesake.
#
# Deliberately NOT in class, each checked by hand rather than assumed:
#   * writes scoped `fm.source = 'kalshi'` (backfill_winners 413/534) — Kalshi
#     tickers are not condition ids and carry no `_yes`/`_no` twin convention;
#   * relabel-only writes that set `resolution_source` and never `is_winner`
#     (6415 / 6720 / 6980 pass2_guess upgrades) — they cannot invent a winner;
#   * writes keyed on market or event identity — already scoped to one market.
_WINNER_WRITE = re.compile(
    r"UPDATE\s+futures_outcomes\b(?P<body>.*?\bSET\b.*?)$",
    re.IGNORECASE | re.DOTALL,
)
_SETS_WINNER = re.compile(r"\bis_winner\s*=", re.IGNORECASE)
_KEYS_ON_EXTERNAL_ID = re.compile(
    r"\bexternal_id\s*=\s*(ANY\s*\(\s*)?:", re.IGNORECASE
)
_KALSHI_SCOPED = re.compile(r"fm\.source\s*=\s*'kalshi'", re.IGNORECASE)

# SECOND in-class arm — the PRICE-CROWNERS, and they did most of the damage.
# `is_winner = (fo.current_probability >= 0.95)` derives the winner from the
# field's own prices, so a contaminant leg at 0.974 IS the crown. These are
# market-keyed, so the external_id arm above cannot see them — 190 of the 235
# measured bad rows came through here (`clean_resolution`). Two arms, because
# the class has two entrances and guarding one would have left the bigger open.
_CROWNS_BY_PRICE = re.compile(
    r"is_winner\s*=\s*\([^)]*current_probability[^)]*\)", re.IGNORECASE | re.DOTALL
)


def _is_in_class(sql: str) -> bool:
    if not re.search(r"UPDATE\s+futures_outcomes\b", sql, re.IGNORECASE):
        return False
    # The Kalshi exclusion applies to BOTH arms: Kalshi external_ids are event
    # tickers, not condition ids, and carry no `_yes`/`_no` twin convention, so
    # the predicate provably cannot fire there. Q480's lesson, applied to my own
    # work: a guard that cannot fire is a vacuous guard, and this one would also
    # bolt a correlated subquery onto two hot golf/Kalshi queries for nothing.
    if _KALSHI_SCOPED.search(sql):
        return False
    if _CROWNS_BY_PRICE.search(sql):
        return True
    if not _SETS_WINNER.search(sql):
        return False
    return bool(_KEYS_ON_EXTERNAL_ID.search(sql))
# The predicate reaches the SQL by `" + DUPLICATE_CONDITION_LEG_SQL + "`
# concatenation, so the literal chunks are what the AST sees.
_PREDICATE_MARKER = "DUPLICATE_CONDITION_LEG_SQL"


def _sql_string_concats(tree: ast.AST):
    """Every string-ish expression in the file, with its concatenated names.

    Yields ``(text, names, lineno)`` where ``text`` is the joined literal parts
    and ``names`` the identifiers spliced in via ``+``. Handles the
    ``"..." + CONST + "..."`` idiom this codebase builds its SQL with.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "text"):
            continue
        if not node.args:
            continue
        parts: list[str] = []
        names: list[str] = []

        def walk(expr):
            if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
                walk(expr.left)
                walk(expr.right)
            elif isinstance(expr, ast.Constant) and isinstance(expr.value, str):
                parts.append(expr.value)
            elif isinstance(expr, ast.Name):
                names.append(expr.id)
            elif isinstance(expr, ast.JoinedStr):
                for v in expr.values:
                    walk(v)
            elif isinstance(expr, ast.FormattedValue):
                walk(expr.value)

        walk(node.args[0])
        yield "".join(parts), names, node.lineno


def _winner_writes():
    found = []
    for path in TASK_SOURCES:
        source = path.read_text()
        # 🔴 An unparsable source must RAISE, never read as "no writes here".
        tree = ast.parse(source)
        for sql, names, lineno in _sql_string_concats(tree):
            if _is_in_class(sql):
                found.append((path.name, lineno, sql, names))
    return found


def test_the_ast_scan_actually_found_the_known_writes():
    """🔴 Positive control. A scan that finds NOTHING passes every other test here.

    Pinned to the six sites classified by hand on 2026-09-01. If a refactor moves
    or merges them this fails loudly rather than silently guarding an empty set —
    the failure mode that makes a source-scan guard worthless.
    """
    writes = _winner_writes()
    by_file: dict[str, int] = {}
    for name, _, _, _ in writes:
        by_file[name] = by_file.get(name, 0) + 1
    assert by_file == {"backfill_winners.py": 5, "polymarket.py": 2}, (
        f"the in-class population changed: {by_file}. Re-classify by hand before "
        "adjusting this number — a shrinking population is how this guard goes "
        "vacuous."
    )


def test_the_scan_excludes_the_writes_ruled_out_by_hand():
    """The negative control: the classifier is not simply matching everything.

    Kalshi-ticker-scoped and relabel-only writes exist in these files and must
    NOT be demanded to carry the predicate. Without this, `_is_in_class`
    returning True unconditionally would still pass the test above.
    """
    kalshi_scoped = """
        UPDATE futures_outcomes fo SET is_winner = true FROM futures_markets fm
        WHERE fo.market_id = fm.id AND fm.source = 'kalshi'
          AND fo.external_id = ANY(:tickers)
    """
    relabel_only = """
        UPDATE futures_outcomes fo SET resolution_source = 'clean_resolution'
        WHERE fo.external_id = ANY(:t)
    """
    market_keyed = """
        UPDATE futures_outcomes fo SET is_winner = true
        WHERE fo.market_id = :market_id
    """
    assert _is_in_class(kalshi_scoped) is False
    assert _is_in_class(relabel_only) is False
    assert _is_in_class(market_keyed) is False
    # ...and both shapes that ARE the defect still classify in.
    assert _is_in_class(
        "UPDATE futures_outcomes fo SET is_winner = true "
        "WHERE fo.external_id = ANY(:cids)"
    ) is True
    assert _is_in_class(
        "UPDATE futures_outcomes fo SET is_winner = (fo.current_probability >= 0.95) "
        "WHERE fo.market_id = cr.market_id"
    ) is True


# A price-crowner is TWO filters, not one, and they stop different things:
# the CTE-side occurrence stops the leg SUPPLYING terminality, the UPDATE-side
# one stops it RECEIVING the stamp. Removing either leaves a live defect.
#
# 🔴 This count exists because the first version of this guard tested
# membership (`marker in names`) and a mutation that deleted the UPDATE-side
# filter PASSED — the CTE-side occurrence satisfied it. That is the
# "guard met by a sibling call site" class, committed in the guard written to
# catch it. Occurrences, not membership.
_CTE_FED_UPDATE = re.compile(r"\bWITH\b.*?\bAS\s*\(", re.IGNORECASE | re.DOTALL)


def _required_occurrences(sql: str) -> int:
    return 2 if _CTE_FED_UPDATE.search(sql) else 1


def test_every_winner_write_carries_the_duplicate_leg_predicate():
    """The reach guard. A NEW price-crowner fails here without a list edit."""
    missing = [
        f"{name}:{lineno} (has {names.count(_PREDICATE_MARKER)}, "
        f"needs {_required_occurrences(sql)})"
        for name, lineno, sql, names in _winner_writes()
        if names.count(_PREDICATE_MARKER) < _required_occurrences(sql)
    ]
    assert not missing, (
        "these UPDATEs stamp a winner without excluding duplicate condition "
        f"legs: {missing}. A `{{cid}}_no` leg sitting beside its bare `{{cid}}` "
        "twin is the negation of one candidate, not a candidate — crowning it "
        "puts 'No' at the top of a named field (production market 59835854)."
    )


def test_the_predicate_requires_both_halves():
    """The SQL must test the suffix AND the twin's presence, not either alone.

    A suffix-only predicate would delete every Polymarket binary sub-market
    from grading; a twin-only predicate is not expressible. Asserted on the SQL
    text because the SQL is what runs and it cannot be executed here.
    """
    sql = DUPLICATE_CONDITION_LEG_SQL
    assert "_yes" in sql and "_no" in sql, "suffix test missing"
    assert "EXISTS" in sql, "twin-presence test missing"
    assert "dup_twin.market_id = fo.market_id" in sql, (
        "the twin lookup must be scoped to the SAME market — an unscoped "
        "lookup reintroduces exactly the cross-market bug being fixed"
    )
    assert "regexp_replace" in sql, "suffix stripping missing"
    # Negated as a whole: the predicate KEEPS rows, it does not select them.
    assert sql.lstrip().startswith("NOT ("), (
        "predicate must be a NOT(...) keep-filter; un-negated it would grade "
        "ONLY the contaminants"
    )
