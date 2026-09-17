#!/usr/bin/env python3
"""Prove :mod:`app.utils.calibration_paired_prestart`'s SQL and Python agree. #6176.

WHY THIS EXISTS. The module carries the pairing rule twice — once as the
statement the feasibility walk runs on production, once as a pure-Python twin
the unit tests can reach without a database. The unit tests can only assert the
Python half and the TEXT of the SQL half. Nothing in CI executes the statement,
so the SQL could be wrong in a way that reads perfectly: an ``EXTRACT(SECOND …)``
that does not mean what the Python ``second == 0 and microsecond == 0`` means, a
LATERAL that cannot see ``fo.id``, a ``timestamp``/``timestamptz`` subtraction
resolved at the session timezone. Each of those returns rows. None of them
returns the right ones.

So this runs the REAL statement against a throwaway local Postgres holding a
synthetic fixture, runs the Python twin over the same fixture, and asserts the
``pair_class`` per outcome is identical. Every number here is INVENTED; nothing
is read from production and nothing is written anywhere but the scratch
database, which is dropped and recreated on every run.

The fixture is the control set from
``artifacts/other-model-paired-accuracy/paired_accuracy_example.py`` (C1-C6, E7,
E4, E5, G1), plus the four classes this module added that the example predates:
``start_provenance_unknown``, ``unanchored_boundary``, ``start_contradicted`` and
the poll-clock-minted start.

THE FIXTURE IS NOT ENOUGH, AND THE MODULE'S OWN HISTORY SAYS SO. Both #6176
defects found on 2026-09-16/17 were found by EXECUTING the rule on a named
boundary specimen and reading the output; neither was visible in review, and one
had a green SQL-text guard sitting on the defective expression. A hand-written
fixture only ever contains the boundaries somebody already thought of, so
``--fuzz`` generates outcomes whose timestamps land ON the two instants the rule
turns on (``S`` and ``S − lead``) and one microsecond either side of them, with
``valid_until`` runs that start before and end after each, and asserts the SQL
and the Python twin agree on every one. It is the fixture's method, applied to
the boundaries nobody enumerated.

``--fuzz`` asserts AGREEMENT ONLY — never a named class. An expectation written
by the same hand that wrote the generator proves nothing; the two independent
implementations disagreeing is the finding. The run prints a per-class coverage
table for exactly that reason: a fuzz that never reached ``paired`` has proved
nothing about pairing, and you can see it.

DELIBERATELY NOT GENERATED: bid/ask spreads exactly equal to
``FEED_PHANTOM_MIN_SPREAD``, and prices exactly ``_PHANTOM_MIDPOINT_TOLERANCE``
from a book's midpoint. Those two ties are decided in exact decimal by Postgres
and in binary float by Python, so they disagree by construction — a real hair's
breadth of divergence, but it belongs to ``feed_market_quality``'s shipped mirror
rather than to this module, and generating it would bury this instrument's real
findings under a known artifact. Every TIME boundary is exact in both engines and
IS generated.

Usage::

    python3 -m scripts.probe_paired_prestart_sql --dry-run   # no DB, renders only
    python3 -m scripts.probe_paired_prestart_sql             # needs local Postgres
    python3 -m scripts.probe_paired_prestart_sql --fuzz 400  # + 400 random outcomes
    python3 -m scripts.probe_paired_prestart_sql --fuzz 400 --seed 7

    PROBE_DSN=postgresql://user@host:5432/postgres python3 -m scripts.probe_paired_prestart_sql

Exit 0 = SQL and Python agreed on every row. A failure prints the offending
outcome's whole input — event row, market row and every snapshot — so the
disagreement is re-buildable as a named fixture case without re-running the
generator. Imported by nothing under ``app/``; it is a developer tool, not a task.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.calibration_paired_prestart import (  # noqa: E402
    DEFAULT_EARLY_MAX_STALE_SECONDS,
    DEFAULT_FINAL_MAX_STALE_SECONDS,
    DEFAULT_LEAD_SECONDS,
    PAIR_CLASSES,
    PAIR_RESULT_NOT_INDEPENDENT,
    PAIRED_CLASSES,
    START_CONTRADICTION_TOLERANCE_SECONDS,
    _poll_clock_fallback_sources,
    classify_pair,
    paired_legs_sql,
)
from app.utils.event_completion import DERIVED_COMMENCE_SOURCES  # noqa: E402
from app.utils.feed_market_quality import (  # noqa: E402
    FEED_PHANTOM_MIN_SPREAD,
    _PHANTOM_MIDPOINT_TOLERANCE,
)
from app.utils.resolution_authority import (  # noqa: E402
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES,
    CALIBRATION_TRUTH_INELIGIBLE_SOURCES,
)

H = timedelta(hours=1)
D = timedelta(days=1)
T0 = datetime(2026, 1, 10, 20, 0, tzinfo=timezone.utc)
SCRATCH_DB = "cal6176_probe"

SCHEMA = """
DROP TABLE IF EXISTS futures_odds_snapshots, futures_outcomes, futures_markets, events;
CREATE TABLE events (
  id BIGINT PRIMARY KEY,
  commence_time TIMESTAMPTZ,
  commence_time_source TEXT,
  created_at TIMESTAMP,
  completed_at TIMESTAMPTZ
);
CREATE TABLE futures_markets (
  id BIGINT PRIMARY KEY,
  event_id BIGINT,
  source TEXT,
  status TEXT,
  resolution_date TIMESTAMPTZ,
  llm_sport_category TEXT
);
CREATE TABLE futures_outcomes (
  id BIGINT PRIMARY KEY,
  market_id BIGINT,
  is_winner BOOLEAN,
  resolution_source TEXT
);
CREATE TABLE futures_odds_snapshots (
  id BIGINT PRIMARY KEY,
  outcome_id BIGINT,
  bookmaker TEXT,
  probability NUMERIC(7,6),
  yes_bid NUMERIC(5,4),
  yes_ask NUMERIC(5,4),
  captured_at TIMESTAMPTZ,
  valid_until TIMESTAMPTZ,
  reading_count INT
);
CREATE INDEX idx_fos_outcome_captured
    ON futures_odds_snapshots (outcome_id, captured_at);
"""


@dataclass
class Ev:
    id: int
    commence_time: Optional[datetime]
    commence_time_source: Optional[str]
    created_at: Optional[datetime]
    completed_at: Optional[datetime]


@dataclass
class Out:
    id: int
    name: str
    event: Optional[Ev]
    source: str
    resolution_date: Optional[datetime]
    is_winner: Optional[bool]
    resolution_source: str


@dataclass
class Snap:
    id: int
    outcome_id: int
    bookmaker: str
    probability: float
    captured_at: datetime
    valid_until: Optional[datetime] = None
    yes_bid: Optional[float] = None
    yes_ask: Optional[float] = None


EVENTS: list[Ev] = []
OUTCOMES: list[Out] = []
SNAPS: list[Snap] = []
_next_ids = {"event": 1, "outcome": 1, "snap": 1}


def reset_fixture() -> None:
    """Empty the three collections and the id counter.

    ``main`` builds the fixture exactly once, so it never needs this; a CALLER
    that builds twice (the CI guard that asserts the generator is not vacuous)
    would otherwise accumulate rows from the previous build and read a coverage
    table that no single run produces.
    """
    EVENTS.clear()
    OUTCOMES.clear()
    SNAPS.clear()
    PY_LEGS.clear()
    _next_ids.update({"event": 1, "outcome": 1, "snap": 1})


def _take(kind: str) -> int:
    value = _next_ids[kind]
    _next_ids[kind] = value + 1
    return value


def game(
    *,
    commence: Optional[datetime] = T0,
    source: Optional[str] = "espn",
    created: Optional[datetime] = None,
    completed: Optional[datetime] = None,
) -> Ev:
    ev = Ev(
        _take("event"),
        commence,
        source,
        created if created is not None else (T0 - 30 * D).replace(tzinfo=None),
        completed if completed is not None else T0 + 3 * H,
    )
    EVENTS.append(ev)
    return ev


def outcome(
    name: str,
    ev: Optional[Ev],
    *,
    won: Optional[bool] = True,
    source: str = "kalshi",
    res: str = "api_settlement",
    resolution_date: Optional[datetime] = None,
) -> Out:
    out = Out(
        _take("outcome"),
        name,
        ev,
        source,
        resolution_date if resolution_date is not None else (T0 + 3 * H),
        won,
        res,
    )
    OUTCOMES.append(out)
    return out


def snap(out: Out, book: str, at: datetime, p: float, **kw: Any) -> None:
    SNAPS.append(Snap(_take("snap"), out.id, book, p, at, **kw))


def standard_pair(
    out: Out, early: float, final: float, *, book: Optional[str] = None
) -> None:
    """The ordinary shape: one look 26h out (re-confirmed at 25h), one an hour before."""
    book = book or out.source
    snap(out, book, T0 - 26 * H, early, valid_until=T0 - 25 * H)
    snap(out, book, T0 - 1 * H, final, yes_bid=final - 0.01, yes_ask=final + 0.01)


def build_fixture() -> dict[int, str]:
    """Returns ``{outcome_id: expected pair_class}``. Every value is invented."""
    expected: dict[int, str] = {}

    # -- four games observed at BOTH instants: the only rows a fair comparison may use
    e1, e2, e3 = game(), game(), game()
    for ev, legs in (
        (e1, [("E1-A", True, 0.55, 0.70), ("E1-B", False, 0.45, 0.30)]),
        (e2, [("E2-A", True, 0.60, 0.50), ("E2-B", False, 0.40, 0.50)]),
        (e3, [("E3-A", True, 0.50, 0.65), ("E3-B", False, 0.50, 0.35)]),
    ):
        for name, won, pe, pf in legs:
            o = outcome(name, ev, won=won)
            standard_pair(o, pe, pf)
            expected[o.id] = "paired"

    # E1-A was ALSO seen 30 days out. "First snapshot ever" would use that 0.40.
    unequal_lead = OUTCOMES[0]
    snap(unequal_lead, "kalshi", T0 - 30 * D, 0.40, valid_until=T0 - 29 * D)

    # E7: ONE collapsed row covers both instants (looked repeatedly, never
    # moved). CAL-P1331 moved the capture from 3 days out to 30 hours out: the
    # run must PROVE a look before each instant, and a 3-day-old capture proves
    # nothing about the early one. The 3-day variant is now C12 below.
    e7 = game()
    for name, won, p in (("E7-A", True, 0.70), ("E7-B", False, 0.30)):
        o = outcome(name, e7, won=won)
        snap(o, "kalshi", T0 - 30 * H, p, valid_until=T0 - 1 * H)
        expected[o.id] = "paired_unchanged"

    # -- early-ONLY: 3% longshots watched a week out, then polling stopped
    e4 = game()
    for i in range(3):
        o = outcome(f"E4-{i}", e4, won=False)
        snap(o, "kalshi", T0 - 7 * D, 0.03, valid_until=T0 - 6 * D)
        expected[o.id] = "no_final_stale"

    # -- final-ONLY: coin flips first polled two hours before kickoff
    e5 = game()
    for name, won in (("E5-A", True), ("E5-B", False)):
        o = outcome(name, e5, won=won)
        snap(o, "kalshi", T0 - 1 * H, 0.50, yes_bid=0.49, yes_ask=0.51)
        expected[o.id] = "no_early_none_before"

    # -- REJECTION CONTROLS ------------------------------------------------
    # C1 missing close: only the early look exists; the writer's opening
    # fallback is never consulted by this rule.
    c1 = outcome("C1-A", game())
    snap(c1, "kalshi", T0 - 26 * H, 0.35, valid_until=T0 - 25 * H)
    expected[c1.id] = "no_final_stale"

    # C2 after-start: the only late look is 20 minutes INTO the game, at 0.97.
    c2 = outcome("C2-A", game())
    snap(c2, "kalshi", T0 - 26 * H, 0.55, valid_until=T0 - 25 * H)
    snap(c2, "kalshi", T0 + timedelta(minutes=20), 0.97)
    expected[c2.id] = "no_final_stale"

    # C3 price-derived winner: excluded by the POPULATION, so the statement
    # never emits a class for it. Asserted by absence.
    c3 = outcome("C3-A", game(), res="settlement_sync")
    standard_pair(c3, 0.55, 0.90)
    expected[c3.id] = "__absent__"

    # C3b ungraded truth: is_winner NULL is never a loss.
    c3b = outcome("C3-B", game(), won=None)
    standard_pair(c3b, 0.55, 0.90)
    expected[c3b.id] = "__absent__"

    # C4 stand-in start: commence_time is midnight UTC parsed from a ticker date.
    c4 = outcome("C4-A", game(commence=T0.replace(hour=0), source="kalshi_ticker"))
    standard_pair(c4, 0.55, 0.70)
    expected[c4.id] = "start_not_reported"

    # C5 two sportsbooks: early is DraftKings, late is FanDuel.
    c5 = outcome("C5-A", game(), source="odds_api", res="game_score")
    snap(c5, "draftkings", T0 - 26 * H, 0.52, valid_until=T0 - 25 * H)
    snap(c5, "fanduel", T0 - 1 * H, 0.58, yes_bid=0.57, yes_ask=0.59)
    expected[c5.id] = "legs_from_different_books"

    # C6 fabricated midpoint: empty book (bid .001 / ask 1.0) averages to .5005.
    c6 = outcome("C6-A", game())
    snap(c6, "kalshi", T0 - 26 * H, 0.55, valid_until=T0 - 25 * H)
    snap(c6, "kalshi", T0 - 1 * H, 0.5005, yes_bid=0.001, yes_ask=1.0)
    expected[c6.id] = "no_final_stale"

    # C7 provenance unknown: a start nobody can vouch for.
    c7 = outcome("C7-A", game(source=None))
    standard_pair(c7, 0.55, 0.70)
    expected[c7.id] = "start_provenance_unknown"

    # C8 no linked event at all: the boundary would silently be the SETTLEMENT date.
    c8 = outcome("C8-A", None)
    standard_pair(c8, 0.55, 0.70)
    expected[c8.id] = "unanchored_boundary"

    # C9 our own columns contradict the start (gotcha #46).
    c9 = outcome("C9-A", game(completed=T0 - 1 * H))
    standard_pair(c9, 0.55, 0.70)
    expected[c9.id] = "start_contradicted"

    # C9b settlement long before the start: the wrong-game-in-a-series specimen.
    c9b = outcome("C9-B", game(), resolution_date=T0 - 1 * D)
    standard_pair(c9b, 0.55, 0.70)
    expected[c9b.id] = "start_contradicted"

    # C9c CAL-P1333: settlement SHORTLY before the start — inside the old 6h
    # tolerance, so `start_contradicted` does not fire and `completed_at` is
    # healthy (after the start). This is the band where `LEAST` silently
    # re-anchored the measure on the settlement timestamp, and a wrong-LATE
    # start then puts the "final pre-event" leg inside the game.
    c9c = outcome("C9-C", game(), resolution_date=T0 - 1 * H)
    standard_pair(c9c, 0.55, 0.70)
    expected[c9c.id] = "settlement_precedes_start"

    # C9d the boundary control for C9c: settling AT the start is not settling
    # BEFORE it, and must still pair. Without this, a `<=` typo in either half
    # would pass C9c and silently empty the cohort.
    c9d = outcome("C9-D", game(), resolution_date=T0)
    standard_pair(c9d, 0.55, 0.70)
    expected[c9d.id] = "paired"

    # C10 the start IS the clock of the poll that minted the row.
    minted_at = (T0 - 2 * D).replace(second=17, microsecond=316804)
    c10 = outcome(
        "C10-A",
        game(
            commence=minted_at, source="kalshi", created=minted_at.replace(tzinfo=None)
        ),
        resolution_date=minted_at + 3 * H,
    )
    snap(c10, "kalshi", minted_at - 26 * H, 0.55, valid_until=minted_at - 25 * H)
    snap(c10, "kalshi", minted_at - 1 * H, 0.70, yes_bid=0.69, yes_ask=0.71)
    expected[c10.id] = "start_not_reported"

    # C11 a REAL fixture merely discovered near its start: the positive control
    # for C10. Same source, same nearness, but a minute-boundary kickoff.
    real_at = (T0 - 2 * D).replace(second=0, microsecond=0)
    c11 = outcome(
        "C11-A",
        game(commence=real_at, source="kalshi", created=real_at.replace(tzinfo=None)),
        resolution_date=real_at + 3 * H,
    )
    snap(c11, "kalshi", real_at - 26 * H, 0.55, valid_until=real_at - 25 * H)
    snap(c11, "kalshi", real_at - 1 * H, 0.70, yes_bid=0.69, yes_ask=0.71)
    expected[c11.id] = "paired"

    # C12 CAL-P1331, the FINAL leg: one run first seen 3 days before the start
    # and last seen 2 hours AFTER it. The old clamp scored this staleness zero
    # and published it as a flat pair; the only evidence promoting it over an
    # identical stale row came from after the event began.
    c12 = outcome("C12-A", game())
    snap(c12, "kalshi", T0 - 3 * D, 0.62, valid_until=T0 + 2 * H)
    expected[c12.id] = "no_final_unconfirmed_span"

    # C13 the same defect at the EARLY boundary, reachable with no after-start
    # evidence at all: a 30-day-old price whose only confirmation lands 22 hours
    # after the instant it is being offered as the market's view of.
    c13 = outcome("C13-A", game())
    snap(c13, "kalshi", T0 - 30 * D, 0.20, valid_until=T0 - 2 * H)
    snap(c13, "kalshi", T0 - 1 * H, 0.80, yes_bid=0.79, yes_ask=0.81)
    expected[c13.id] = "no_early_unconfirmed_span"

    # C14 the positive control for both: identical shape to C13, confirmed an
    # hour BEFORE the early instant rather than after it, and it pairs.
    c14 = outcome("C14-A", game())
    snap(c14, "kalshi", T0 - 30 * D, 0.20, valid_until=T0 - 25 * H)
    snap(c14, "kalshi", T0 - 1 * H, 0.80, yes_bid=0.79, yes_ask=0.81)
    expected[c14.id] = "paired"

    # G1 DataGolf: a valid pair, but a MODEL forecast — its own set, never pooled.
    g1 = outcome("G1-A", game(), won=False, source="datagolf", res="game_score")
    standard_pair(g1, 0.12, 0.10)
    expected[g1.id] = "paired"

    return expected


# ---------------------------------------------------------------------------
# The fuzz half. Agreement only — see the header for why there are no expected
# classes here, and why the coverage table is printed rather than summarised.
# ---------------------------------------------------------------------------


#: Offsets from ``T0`` (the start) at which a snapshot may be captured, in
#: seconds. DERIVED from the module's own constants rather than typed out, so a
#: change to the lead or either staleness bound moves the generator with it —
#: which is the whole point, since the boundaries are what this is testing.
#:
#: ``0`` and ``-DEFAULT_LEAD_SECONDS`` are the two instants the rule turns on,
#: and ``±1`` microsecond either side of each is what tells a ``<`` from a
#: ``<=``. The staleness bounds get the same treatment: a leg exactly
#: ``max_stale`` old is fresh, one microsecond older is not.
def _fuzz_offsets() -> tuple[int, ...]:
    lead = DEFAULT_LEAD_SECONDS
    anchors = [
        0,
        -lead,
        -DEFAULT_FINAL_MAX_STALE_SECONDS,
        -(lead + DEFAULT_EARLY_MAX_STALE_SECONDS),
    ]
    out: set[int] = set()
    for a in anchors:
        out.update((a - 1, a, a + 1))
    out.update(
        (
            -30 * 86400,
            -7 * 86400,
            -3 * 86400,
            -(lead + 86400),
            -(lead + 3600),
            -(lead - 3600),
            -43200,
            -3600,
            -60,
            1200,
            3 * 3600,
        )
    )
    return tuple(sorted(out))


FUZZ_OFFSETS = _fuzz_offsets()

#: The offsets that sit around ONE of the two instants. A purely uniform draw
#: over :data:`FUZZ_OFFSETS` almost never lands an eligible row on both sides at
#: once, so the generator seeds a plausible pair from these two pools before it
#: adds noise — otherwise the run reaches ``start_contradicted`` three hundred
#: times and ``paired`` never, which the coverage table showed on the first
#: attempt. The pools are still all boundary offsets: seeding a pair biases WHICH
#: rows exist, never what the rule is asked about them.
#:
#: IT IS A BUDGET, NOT A REACHABILITY REQUIREMENT, and the difference is measured
#: rather than assumed: with the seeding removed the generator still reaches all
#: fifteen classes at 800 outcomes, but scorable pairs fall from 7.8% of the set
#: to 2.6% — the same database run then spends five sixths of its rows re-proving
#: the refusal ladder. That is why the CI guard asserts reachability and does not
#: assert this, and why deleting this phase would quietly make every later
#: agreement run weaker without turning anything red.
FUZZ_EARLY_SIDE = tuple(
    o
    for o in FUZZ_OFFSETS
    if -(DEFAULT_LEAD_SECONDS + DEFAULT_EARLY_MAX_STALE_SECONDS + 3600)
    <= o
    <= -DEFAULT_LEAD_SECONDS + 1
)
FUZZ_FINAL_SIDE = tuple(
    o for o in FUZZ_OFFSETS if -(DEFAULT_FINAL_MAX_STALE_SECONDS + 3600) <= o <= 1
)

#: Microsecond jitters applied on top of an offset. A whole-second boundary and
#: a boundary missed by one microsecond are different questions, and Postgres
#: and Python both hold microseconds exactly, so this arm is safe to assert on.
FUZZ_MICROS = (0, 0, 0, 1, -1)

#: Books. The market's own source is added per outcome, so the native-book
#: preference arm (``ORDER BY (b.bookmaker <> fm.source)``) is exercised.
FUZZ_BOOKS = ("draftkings", "fanduel", "betmgm", "kalshi", "polymarket")

FUZZ_MARKET_SOURCES = ("kalshi", "polymarket", "odds_api", "datagolf")

#: Start provenance, DERIVED from the two house sets this module delegates to,
#: so a source added to either reaches the generator without anybody editing
#: this line. ``None`` is the ``start_provenance_unknown`` arm.
FUZZ_COMMENCE_SOURCES = (
    (None, "espn", "statpal")
    + tuple(sorted(DERIVED_COMMENCE_SOURCES))
    + tuple(sorted(_poll_clock_fallback_sources()))
)


def _fuzz_probability(rng: random.Random) -> float:
    """A stored probability, rounded to the column's own ``NUMERIC(7,6)``.

    Unrounded values would be re-rounded by Postgres and not by Python, which is
    a storage artifact rather than a rule disagreement.
    """
    choice = rng.random()
    if choice < 0.10:
        return rng.choice((0.0, 1.0, 0.000001, 0.999999))
    return round(rng.uniform(0.01, 0.99), 6)


def _fuzz_quote(
    rng: random.Random, p: float
) -> tuple[Optional[float], Optional[float]]:
    """A ``(yes_bid, yes_ask)`` pair, rounded to the column's ``NUMERIC(5,4)``.

    Stays clear of the two exact ties named in the header — the spread equal to
    ``FEED_PHANTOM_MIN_SPREAD`` and the price exactly
    ``_PHANTOM_MIDPOINT_TOLERANCE`` off the midpoint — by a margin wider than
    float noise at six decimal places and narrower than either constant.
    """
    step = _PHANTOM_MIDPOINT_TOLERANCE / 10.0
    kind = rng.choice(
        ("none", "none", "tight", "phantom_in", "phantom_just_out", "wide_off_mid")
    )
    if kind == "none":
        return None, None
    if kind == "tight":
        half = FEED_PHANTOM_MIN_SPREAD / 4.0
        return round(max(p - half, 0.0), 4), round(min(p + half, 1.0), 4)
    # A spread comfortably wider than the phantom floor, centred so that `p` is
    # or is not that book's midpoint.
    half = (FEED_PHANTOM_MIN_SPREAD + 0.02) / 2.0
    mid = min(max(p, half), 1.0 - half)
    bid, ask = round(mid - half, 4), round(mid + half, 4)
    if kind == "phantom_in":
        return bid, ask  # p may or may not sit at the midpoint; both are useful
    if kind == "phantom_just_out":
        # Shift the book so the midpoint misses `p` by a hair MORE than the
        # tolerance — the "not fabricated" side of that test.
        shift = _PHANTOM_MIDPOINT_TOLERANCE + step
        return round(bid + shift, 4), round(ask + shift, 4)
    return round(max(bid - 0.10, 0.0), 4), round(min(ask - 0.05, 1.0), 4)


def build_fuzz(n: int, seed: int) -> list[int]:
    """``n`` randomly shaped outcomes. Returns their ids; asserts nothing itself.

    Every field is invented and every timestamp is derived from ``T0``. Nothing
    is read from production.
    """
    rng = random.Random(seed)
    ids: list[int] = []
    ineligible = sorted(CALIBRATION_TRUTH_INELIGIBLE_SOURCES)
    eligible = sorted(CALIBRATION_TRUTH_ELIGIBLE_SOURCES)
    for _ in range(n):
        # -- the event row -------------------------------------------------
        has_event = rng.random() > 0.08
        commence: Optional[datetime] = None
        ev: Optional[Ev] = None
        if has_event:
            commence = T0
            if rng.random() < 0.25:
                # A sub-minute stamp: the poll-clock fingerprint's first arm.
                commence = T0.replace(
                    second=rng.choice((0, 17, 43)),
                    microsecond=rng.choice((0, 316804)),
                )
            created_choice = rng.random()
            if created_choice < 0.15:
                created = None
            elif created_choice < 0.45:
                # Inside or straddling POLL_CLOCK_STAMP_TOLERANCE of the start.
                created = commence - timedelta(
                    seconds=rng.choice((30, 599, 600, 601, 1800))
                )
            else:
                created = T0 - 30 * D
            # Weighted toward healthy: `completed_at <= commence_time` is a
            # refusal on its own, and an even draw spends the whole run there.
            completed = rng.choice(
                (None, None, None, T0 + 3 * H, T0 + 3 * H)
                if rng.random() > 0.12
                else (T0 - 1 * H, T0, T0 - timedelta(microseconds=1))
            )
            ev = Ev(
                _take("event"),
                commence,
                rng.choice(FUZZ_COMMENCE_SOURCES),
                None if created is None else created.replace(tzinfo=None),
                completed,
            )
            EVENTS.append(ev)

        # -- the market row ------------------------------------------------
        tol = START_CONTRADICTION_TOLERANCE_SECONDS
        resolution_date = rng.choice(
            (None, T0 + 3 * H, T0 + 3 * H, T0)
            if rng.random() > 0.22
            else (
                T0 - timedelta(microseconds=1),
                T0 - 1 * H,
                T0 - timedelta(seconds=tol),
                T0 - timedelta(seconds=tol + 1),
                T0 - 1 * D,
            )
        )
        source = rng.choice(FUZZ_MARKET_SOURCES)
        res_source = (
            rng.choice(eligible)
            if rng.random() > 0.10
            else rng.choice(ineligible + [None])
        )
        out = Out(
            _take("outcome"),
            f"F{len(ids)}",
            ev,
            source,
            resolution_date,
            rng.choice((True, True, True, False, False, False, None)),
            res_source,
        )
        OUTCOMES.append(out)
        ids.append(out.id)

        # -- the snapshots -------------------------------------------------
        books = [source] + rng.sample(FUZZ_BOOKS, rng.randint(0, 2))

        def _emit(book: str, offsets: tuple[int, ...]) -> None:
            at = T0 + timedelta(
                seconds=rng.choice(offsets),
                microseconds=rng.choice(FUZZ_MICROS),
            )
            p = _fuzz_probability(rng)
            bid, ask = _fuzz_quote(rng, p)
            valid_until: Optional[datetime] = None
            if rng.random() < 0.55:
                # A third of runs end near or past the START rather than
                # anywhere at all. A uniform draw makes a LONG run — one
                # collapsed row standing at both instants, which is
                # `paired_unchanged` and both `*_unconfirmed_span` classes —
                # vanishingly rare, and those are the shapes retention actually
                # produces (`tasks/retention.py` collapses a flat run into its
                # two ends).
                pool = FUZZ_FINAL_SIDE if rng.random() < 0.35 else FUZZ_OFFSETS
                candidate = T0 + timedelta(
                    seconds=rng.choice(pool),
                    microseconds=rng.choice(FUZZ_MICROS),
                )
                # `valid_until` is the LAST look at a run that began at
                # `captured_at`; a run cannot end before it started.
                valid_until = candidate if candidate >= at else None
            snap(out, book, at, p, valid_until=valid_until, yes_bid=bid, yes_ask=ask)

        if rng.random() < 0.75:
            # Seed one candidate leg on each side. Same book most of the time —
            # the pairing rule's whole subject — and two different books
            # otherwise, which is the `legs_from_different_books` arm.
            early_book = rng.choice(books)
            final_book = early_book if rng.random() < 0.7 else rng.choice(books)
            _emit(early_book, FUZZ_EARLY_SIDE)
            _emit(final_book, FUZZ_FINAL_SIDE)
        for _ in range(rng.randint(0, 3)):
            _emit(rng.choice(books), FUZZ_OFFSETS)
    return ids


def describe_outcome(oid: int) -> str:
    """Everything that decided one outcome's class, as a re-buildable dump."""
    out = next(o for o in OUTCOMES if o.id == oid)
    lines = [
        f"  outcome {out.id} ({out.name}) source={out.source!r} "
        f"resolution_date={out.resolution_date} is_winner={out.is_winner!r} "
        f"resolution_source={out.resolution_source!r}",
        f"    event: {out.event}",
    ]
    for s in sorted(
        (s for s in SNAPS if s.outcome_id == oid), key=lambda s: s.captured_at
    ):
        lines.append(
            f"    snap {s.id} book={s.bookmaker!r} at={s.captured_at.isoformat()} "
            f"p={s.probability} bid={s.yes_bid} ask={s.yes_ask} "
            f"valid_until={s.valid_until.isoformat() if s.valid_until else None}"
        )
    return "\n".join(lines)


#: ``{outcome_id: (early_probability, final_probability)}`` from the Python twin.
#:
#: The class alone is NOT the whole answer and a class-only comparison is how a
#: wrong ANSWER hides behind a right VERDICT: picking the wrong book still yields
#: ``paired``, and the two numbers that pair carries are what the page would
#: publish. Proven by mutant M5 — dropping the native-book preference from the
#: SQL's ``ORDER BY`` leaves every ``pair_class`` untouched.
PY_LEGS: dict[int, tuple[Optional[float], Optional[float]]] = {}


def python_classes() -> dict[int, str]:
    """The Python twin's verdict on the same fixture."""
    by_outcome: dict[int, list[tuple]] = {}
    for s in SNAPS:
        by_outcome.setdefault(s.outcome_id, []).append(
            (
                s.captured_at,
                s.probability,
                s.yes_bid,
                s.yes_ask,
                s.bookmaker,
                s.valid_until,
            )
        )
    out: dict[int, str] = {}
    for o in OUTCOMES:
        klass, early, final = classify_pair(
            by_outcome.get(o.id, []),
            event=o.event,
            market_source=o.source,
            resolution_date=o.resolution_date,
            is_winner=o.is_winner,
            resolution_source=o.resolution_source,
            eligible_sources=CALIBRATION_TRUTH_ELIGIBLE_SOURCES,
        )
        out[o.id] = klass
        PY_LEGS[o.id] = (early, final)
    return out


def load(conn) -> None:
    cur = conn.cursor()
    cur.execute(SCHEMA)
    for e in EVENTS:
        cur.execute(
            "INSERT INTO events VALUES (%s,%s,%s,%s,%s)",
            (
                e.id,
                e.commence_time,
                e.commence_time_source,
                e.created_at,
                e.completed_at,
            ),
        )
    for o in OUTCOMES:
        cur.execute(
            "INSERT INTO futures_markets VALUES (%s,%s,%s,%s,%s,%s)",
            (
                o.id,
                o.event.id if o.event else None,
                o.source,
                "resolved",
                o.resolution_date,
                "test",
            ),
        )
        cur.execute(
            "INSERT INTO futures_outcomes VALUES (%s,%s,%s,%s)",
            (o.id, o.id, o.is_winner, o.resolution_source),
        )
    for s in SNAPS:
        cur.execute(
            "INSERT INTO futures_odds_snapshots VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                s.id,
                s.outcome_id,
                s.bookmaker,
                s.probability,
                s.yes_bid,
                s.yes_ask,
                s.captured_at,
                s.valid_until,
                1,
            ),
        )
    conn.commit()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="render the statement and the Python verdicts; touch no database",
    )
    ap.add_argument(
        "--fuzz",
        type=int,
        default=0,
        metavar="N",
        help="also generate N random outcomes on the rule's boundaries and "
        "assert the SQL and the Python twin agree on every one",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=6176,
        help="seed for --fuzz, so a disagreement is reproducible (default 6176)",
    )
    args = ap.parse_args()

    expected = build_fixture()
    fuzz_ids = build_fuzz(args.fuzz, args.seed) if args.fuzz > 0 else []
    statement = paired_legs_sql(cursor="0", scan="1000000")
    py = python_classes()

    mismatched_python = {
        oid: (py[oid], want)
        for oid, want in expected.items()
        if want != "__absent__" and py[oid] != want
    }
    if mismatched_python:
        print("PYTHON TWIN DISAGREES WITH THE FIXTURE:")
        for oid, (got, want) in sorted(mismatched_python.items()):
            print(f"  outcome {oid}: got {got!r}, expected {want!r}")
        return 1
    print(f"python twin: {len(expected)} outcomes classified as the fixture expects")
    if fuzz_ids:
        print(
            f"fuzz: {len(fuzz_ids)} generated outcomes (seed {args.seed}), "
            f"{len(FUZZ_OFFSETS)} capture offsets"
        )
        print(_coverage_table(fuzz_ids, py))

    if args.dry_run:
        print(f"--dry-run: rendered {len(statement)} chars of SQL, no database touched")
        return 0

    try:
        import psycopg2
    except ImportError:
        print("psycopg2 is not installed; nothing to execute", file=sys.stderr)
        return 2

    dsn = os.environ.get("PROBE_DSN", "postgresql://localhost:5432/postgres")
    admin = psycopg2.connect(dsn)
    admin.autocommit = True
    admin.cursor().execute(f"DROP DATABASE IF EXISTS {SCRATCH_DB}")
    admin.cursor().execute(f"CREATE DATABASE {SCRATCH_DB}")
    admin.close()

    conn = psycopg2.connect(dsn.rsplit("/", 1)[0] + "/" + SCRATCH_DB)
    try:
        load(conn)
        cur = conn.cursor()
        cur.execute(statement)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()

    sql_classes = {r["outcome_id"]: r["pair_class"] for r in rows}
    sql_legs = {
        r["outcome_id"]: (r["early_probability"], r["final_probability"]) for r in rows
    }
    failures = []

    def _leg_mismatch(oid: int) -> Optional[str]:
        """The two numbers the pair CARRIES, not merely the verdict on it.

        Only for the classes that yield a scorable pair: outside them the
        statement still emits whatever ``pair_book`` found while the CASE
        refuses the row, and the twin returns ``None`` by contract.
        """
        if sql_classes.get(oid) not in PAIRED_CLASSES:
            return None
        got = tuple(None if v is None else round(float(v), 6) for v in sql_legs[oid])
        want = tuple(None if v is None else round(float(v), 6) for v in PY_LEGS[oid])
        if got == want:
            return None
        return f"  outcome {oid}: SQL legs {got} != Python legs {want}"

    for oid, want in sorted(expected.items()):
        got = sql_classes.get(oid, "__absent__")
        if got != want:
            failures.append(
                f"  outcome {oid}: SQL said {got!r}, fixture expects {want!r}"
            )
        if want != "__absent__" and got != py[oid]:
            failures.append(f"  outcome {oid}: SQL {got!r} != Python {py[oid]!r}")
        legs = _leg_mismatch(oid)
        if legs:
            failures.append(legs)

    # The fuzz half asserts AGREEMENT and nothing else. The one translation it
    # needs: the population predicate lives in the statement's WHERE, so a row
    # the Python twin calls `result_not_independent` is one the SQL never emits.
    for oid in fuzz_ids:
        got = sql_classes.get(oid, "__absent__")
        want = "__absent__" if py[oid] == PAIR_RESULT_NOT_INDEPENDENT else py[oid]
        if got != want:
            failures.append(
                f"  FUZZ outcome {oid}: SQL {got!r} != Python {py[oid]!r}\n"
                + describe_outcome(oid)
            )
            continue
        legs = _leg_mismatch(oid)
        if legs:
            failures.append(f"  FUZZ{legs[1:]}\n" + describe_outcome(oid))

    extra = set(sql_classes) - set(expected) - set(fuzz_ids)
    if extra:
        failures.append(f"  SQL emitted rows for unknown outcomes: {sorted(extra)}")

    for r in sorted(rows, key=lambda r: r["outcome_id"]):
        if r["outcome_id"] in expected:
            print(
                f"  {r['outcome_id']:>3}  {r['pair_class']:<26} "
                f"{r['forecast_kind']:<7} {r['bookmaker']}"
            )

    if failures:
        print("\nSQL / PYTHON DISAGREE:")
        print("\n".join(failures))
        return 1
    fixture_rows = sum(1 for r in rows if r["outcome_id"] in expected)
    print(
        f"\nAGREED on all {len(expected)} fixture outcomes "
        f"({fixture_rows} emitted, {len(expected) - fixture_rows} "
        "excluded by the population)"
    )
    if fuzz_ids:
        print(f"AGREED on all {len(fuzz_ids)} fuzz outcomes (seed {args.seed})")
    return 0


def _coverage_table(fuzz_ids: list[int], py: dict[int, str]) -> str:
    """Which classes the generated set actually reached, and which it did not.

    Printed rather than asserted: a class this generator cannot reach is a fact
    about the generator, and hiding it behind a pass would make the whole run
    read as proof of something it never tested.
    """
    counts: dict[str, int] = {}
    for oid in fuzz_ids:
        counts[py[oid]] = counts.get(py[oid], 0) + 1
    lines = []
    for klass in PAIR_CLASSES:
        n = counts.get(klass, 0)
        lines.append(f"    {'—' if n == 0 else ' '} {klass:<28} {n:>5}")
    missed = [k for k in PAIR_CLASSES if k not in counts]
    if missed:
        lines.append(f"    NOT REACHED by this seed/size: {', '.join(missed)}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
