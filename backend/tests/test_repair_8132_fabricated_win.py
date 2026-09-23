"""#8132: the fabricated-win retraction judges each leg by the venue's own word.

## what is being guarded, and what deliberately is not

The repair's judgment is one pure function — :func:`classify_leg` — plus a pinned
population it must agree with before it writes a byte. Those are what these tests
cover, together with the refusals that make the script safe to hand to an
operator: the wrong app, a moved row, a downgrade, a leg the pinned table has
never seen.

What they do NOT cover is the SQL. A fake session answers whatever the test author
decided it answers, so it can prove the verdict logic and nothing about whether
`jsonb_array_elements(raw_response -> 'kalshi_event' -> 'markets')` selects the
rows the docstring claims. That claim was established by measurement on production
(seven `mod(id,7)` slices, 2026-09-23 00:50-01:05Z) and is pinned here as
:data:`EXPECTED`; the producer-guard half has a real-Postgres companion in
`tests/integration/test_price_crown_protected_8132_pg.py`.

## the vocabulary, and why `yes` must be refused rather than handled

Censused over a 1/7 sample of Kalshi captures, `result` is never absent and takes
exactly four values: `no`, `scalar`, `yes`, and `''` — the last pairing only with
`status='closed'`. A repair that retracts wins must refuse `yes` (the venue says
this leg WON: not our business here, and writing it would be #8126's job done
backwards) and refuse `''` (the venue has said nothing yet). Both refusals are
asserted, because a classifier that answered "not a winner" for everything it did
not recognise would pass a test suite built only from the two arms it repairs.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

from app.utils.resolution_authority import (
    KNOWN_SOURCES,
    authority_tier,
    is_downgrade,
)

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    """Import a `scripts/` module by path.

    `scripts/` is not a package and is not on `sys.path` under pytest, so the
    script's own `sys.path.insert` of its directory is what makes the restore's
    sibling import work. Loading by path here exercises exactly that seam.
    """
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


repair = _load("repair_8132_fabricated_win")
restore = _load("restore_8132_fabricated_win")


# ---------------------------------------------------------------------------
# classify_leg — the whole judgment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "venue_result,expected",
    [
        ("no", "api_settlement"),
        ("scalar", "ungradeable_result"),
    ],
)
def test_the_two_arms_get_their_own_stamp(venue_result, expected):
    """`no` is a declared loss; `scalar` is the venue declining to declare.

    Collapsing them onto one stamp is the #1852 defect in either direction:
    `api_settlement` on a scalar leg fabricates a loss the venue never stated,
    and `ungradeable_result` on a `no` leg throws away a real result.
    """
    assert repair.classify_leg(venue_result, "finalized") == expected


@pytest.mark.parametrize("venue_result", ["yes", "", None, "void", "all_no", "NO"])
def test_refuses_everything_that_is_not_a_declared_non_winner(venue_result):
    assert repair.classify_leg(venue_result, "finalized") is None


@pytest.mark.parametrize("status", ["closed", "active", "settled", "", None])
def test_refuses_any_status_that_is_not_terminal(status):
    """A non-`finalized` leg can still move, so a banked read of it is not proof.

    This is the clause that licenses reading a MONTHS-OLD capture at all.
    """
    assert repair.classify_leg("no", status) is None
    assert repair.classify_leg("scalar", status) is None


def test_whitespace_does_not_defeat_the_match():
    assert repair.classify_leg(" no ", "finalized") == "api_settlement"


# ---------------------------------------------------------------------------
# The pinned population
# ---------------------------------------------------------------------------


def test_expected_is_the_measured_population():
    assert len(repair.EXPECTED) == 56
    assert len({row[0] for row in repair.EXPECTED}) == 56, "duplicate outcome id"
    assert len({row[1] for row in repair.EXPECTED}) == 49, "market count moved"


def test_expected_cross_tab_matches_what_was_measured():
    """29 / 10 / 17, the table in the docstring. A silently edited row shows here."""
    from collections import Counter

    tab = Counter((row[3], row[4]) for row in repair.EXPECTED)
    assert tab == {
        ("no", "clean_resolution"): 29,
        ("no", "game_score"): 10,
        ("scalar", "clean_resolution"): 17,
    }


def test_every_pinned_row_classifies_to_a_stamp():
    for oid, _market, _ticker, venue_result, _prior in repair.EXPECTED:
        assert repair.classify_leg(venue_result, "finalized") is not None, oid


def test_no_pinned_row_would_be_a_downgrade():
    """The claim "no downgrade anywhere in the population", checked not asserted.

    All 17 scalar legs carry `clean_resolution` (tier 1), so the tier-1 retraction
    never writes over `game_score` (tier 2). If a future re-measure adds a
    scalar/game_score row this fails, which is the correct outcome: that row needs
    a ruling, not a silent tier drop.
    """
    for oid, _m, _t, venue_result, prior in repair.EXPECTED:
        stamp = repair.classify_leg(venue_result, "finalized")
        assert not is_downgrade(prior, stamp), (
            f"{oid}: {prior} (tier {authority_tier(prior)}) -> "
            f"{stamp} (tier {authority_tier(stamp)})"
        )


def test_every_prior_and_target_source_is_on_the_ladder():
    for _oid, _m, _t, venue_result, prior in repair.EXPECTED:
        assert prior in KNOWN_SOURCES, prior
        assert repair.classify_leg(venue_result, "finalized") in KNOWN_SOURCES


def test_targets_are_never_the_price_derived_sources_that_caused_this():
    """The repair must not stamp the class of source it is undoing."""
    for stamp in repair.RETRACTION_FOR.values():
        assert stamp not in ("clean_resolution", "settlement_sync")


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_refuses_to_run_off_the_producer_app(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert repair.wrong_app_refusal() is not None


def test_refuses_when_the_app_name_is_absent(monkeypatch):
    """An unset variable is a laptop, not the heavy dyno — fail closed."""
    monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
    assert repair.wrong_app_refusal() is not None


def test_admits_the_producer_app(monkeypatch):
    """The ADMITTED control. Without it the refusal could be unconditional and
    every test above would still pass — a repair that can never run anywhere."""
    monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)
    assert repair.wrong_app_refusal() is None


def test_producer_app_is_the_heavy_app():
    assert repair.PRODUCER_APP == "bainluck-heavy"


def test_guard_is_live_reads_the_real_module():
    """It must see the module, not the same-named Celery task.

    `from app.tasks import backfill_winners` binds the TASK; `getsource` on it is
    427 characters and the constant is absent, so the guard would refuse for ever
    and the refusal would read exactly like "not deployed".
    """
    assert repair.guard_is_live() is True


# ---------------------------------------------------------------------------
# derive() verdicts, on a fake that answers only what it is asked
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Returns the given rows on the FIRST slice and nothing on the other six.

    Deliberately not "every query returns the corpus": the real derivation unions
    seven disjoint slices, and a fake that answered all seven would multiply the
    population by seven and hide a de-duplication bug.
    """

    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    async def execute(self, *_args, **_kwargs):
        self.calls += 1
        return _FakeResult(self._rows if self.calls == 1 else [])


def _row(oid, market, ticker, venue_result, is_winner, prior):
    return (oid, market, ticker, venue_result, is_winner, prior)


@pytest.mark.asyncio
async def test_a_pinned_row_in_its_pinned_state_is_repairable():
    pinned = repair.EXPECTED[0]
    oid, market, ticker, venue_result, prior = pinned
    session = _FakeSession([_row(oid, market, ticker, venue_result, True, prior)])
    plan = await repair.derive(session)
    assert session.calls == 7, "derivation must drive all seven slices"
    assert [p["verdict"] for p in plan] == [repair.REPAIR]
    assert plan[0]["target_source"] == repair.classify_leg(venue_result, "finalized")


@pytest.mark.asyncio
async def test_a_moved_prior_source_is_diverged_not_written():
    oid, market, ticker, venue_result, _prior = repair.EXPECTED[0]
    session = _FakeSession(
        [_row(oid, market, ticker, venue_result, True, "box_score")]
    )
    plan = await repair.derive(session)
    assert plan[0]["verdict"] == repair.DIVERGED
    assert "prior source moved" in plan[0]["why"]


@pytest.mark.asyncio
async def test_a_moved_identity_is_diverged_not_written():
    oid, market, ticker, venue_result, prior = repair.EXPECTED[0]
    session = _FakeSession(
        [_row(oid, market + 1, ticker, venue_result, True, prior)]
    )
    plan = await repair.derive(session)
    assert plan[0]["verdict"] == repair.DIVERGED


@pytest.mark.asyncio
async def test_an_unpinned_leg_is_graded_new():
    """The population GROWS — `run_settlement_sweep` banks ~3,000 boards a night."""
    session = _FakeSession(
        [_row(999_000_001, 42, "KXNEW-26SEP01-A", "no", True, "clean_resolution")]
    )
    plan = await repair.derive(session)
    assert [p["verdict"] for p in plan] == [repair.NEW]
    assert plan[0]["target_source"] == "api_settlement"


@pytest.mark.asyncio
async def test_captures_that_disagree_about_one_leg_are_refused():
    """Measured zero today. If it ever happens, the venue's answer is unusable."""
    oid, market, ticker, _venue, prior = repair.EXPECTED[0]
    session = _FakeSession(
        [
            _row(oid, market, ticker, "no", True, prior),
            _row(oid, market, ticker, "scalar", True, prior),
        ]
    )
    plan = await repair.derive(session)
    assert plan[0]["verdict"] == repair.DIVERGED
    assert "captures disagree" in plan[0]["why"]


# ---------------------------------------------------------------------------
# writable_rows — where --include-new actually acts
#
# 🪤 These assertions used to live on `derive(session, include_new=...)`, and a
# mutation that made the flag inert SURVIVED the whole suite: a NEW row came back
# from `derive` identically either way, because the switch was never read there.
# The flag was aimed at one function and tested on another. It now lives in one
# place and both of its branches are driven against a single plan.
# ---------------------------------------------------------------------------


def _plan(*verdicts):
    return [{"verdict": v, "outcome_id": i} for i, v in enumerate(verdicts)]


def test_new_rows_are_not_written_by_default():
    """A script that silently widened its blast radius between the dry-run
    somebody read and the apply would be unreviewable."""
    plan = _plan(repair.REPAIR, repair.NEW, repair.DIVERGED)
    assert [r["verdict"] for r in repair.writable_rows(plan, include_new=False)] == [
        repair.REPAIR
    ]


def test_include_new_admits_new_rows_and_only_those():
    plan = _plan(repair.REPAIR, repair.NEW, repair.DIVERGED, repair.WOULD_DOWNGRADE)
    got = [r["verdict"] for r in repair.writable_rows(plan, include_new=True)]
    assert sorted(got) == sorted([repair.REPAIR, repair.NEW])


@pytest.mark.parametrize("include_new", [True, False])
@pytest.mark.parametrize(
    "verdict", ["DIVERGED", "WOULD_DOWNGRADE", "ALREADY_REPAIRED"]
)
def test_a_refused_verdict_is_never_written_either_way(verdict, include_new):
    plan = _plan(getattr(repair, verdict))
    assert repair.writable_rows(plan, include_new=include_new) == []


# ---------------------------------------------------------------------------
# The population SQL says what the docstring says it says
# ---------------------------------------------------------------------------


def test_population_sql_reads_the_nested_payload():
    """Top-level `raw_response ? 'markets'` is clean-false on every row.

    This lane made that exact mistake and convicted nothing on 400/400 captures.
    """
    sql = repair._population_sql(0)
    assert "'kalshi_event'" in sql and "'markets'" in sql


@pytest.mark.parametrize(
    "clause",
    [
        "leg->>'status' = 'finalized'",
        "leg->>'result' IN ('no', 'scalar')",
        "fo.is_winner IS TRUE",
        "jsonb_typeof",
        "sc.source = 'kalshi'",
    ],
)
def test_population_sql_carries_each_gate(clause):
    assert clause in repair._population_sql(0)


def test_population_sql_is_sliced_seven_ways_and_covers_every_capture():
    mods = {repair._population_sql(i).count(f"mod(sc.id, 7) = {i}") for i in range(7)}
    assert mods == {1}, "each slice must pin exactly its own residue"


# ---------------------------------------------------------------------------
# The undo
# ---------------------------------------------------------------------------


def test_restore_shares_the_repair_s_backup_table_and_app():
    """A restore pointed at a different table is not an undo."""
    assert restore.BACKUP_TABLE == repair.BACKUP_TABLE
    assert restore.PRODUCER_APP == repair.PRODUCER_APP


def test_backup_table_is_a_backup_prefixed_name():
    """Notice 47(c): runtime DDL on a `backup_*` table behind an attended
    invocation is not migration class. The prefix is part of that argument."""
    assert repair.BACKUP_TABLE.startswith("backup_")


def test_restore_refuses_off_the_producer_app(monkeypatch):
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    assert restore.wrong_app_refusal() is not None


def test_pre_image_insert_never_overwrites_an_earlier_one():
    """The FIRST pre-image is the true one.

    A second run must not re-bank the state the first run produced — that would
    quietly turn the undo into a no-op while still reporting success.
    """
    source = (_SCRIPTS / "repair_8132_fabricated_win.py").read_text()
    assert "ON CONFLICT (outcome_id) DO NOTHING" in source


def test_both_write_paths_are_compare_and_set():
    """A rowcount of zero must be a named drift, never a silent overwrite."""
    repair_src = (_SCRIPTS / "repair_8132_fabricated_win.py").read_text()
    restore_src = (_SCRIPTS / "restore_8132_fabricated_win.py").read_text()
    assert "AND is_winner IS TRUE" in repair_src
    assert "COALESCE(resolution_source, '') = :prior" in repair_src
    assert "AND is_winner IS FALSE" in restore_src
    assert "COALESCE(resolution_source, '') = :target" in restore_src
    assert "concurrent_drift" in repair_src and "concurrent_drift" in restore_src


def test_apply_is_opt_in_on_both_scripts():
    for name in ("repair_8132_fabricated_win", "restore_8132_fabricated_win"):
        source = (_SCRIPTS / f"{name}.py").read_text()
        assert '"--apply", action="store_true"' in source


def test_scripts_are_not_imported_by_app_code():
    """Notice 10's scripts clause: Tier A only while nothing under `app/` imports
    it. If that ever changes this is a bus-graded change, not a self-merge."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    for path in app_dir.rglob("*.py"):
        text = path.read_text()
        assert "repair_8132_fabricated_win" not in text, path
        assert "restore_8132_fabricated_win" not in text, path
