"""#8000 — a chart keeps its supported venue history when it draws only the top ten.

PILLARS: TRUTH / FORMATTING. SHIP: a chart keeps supported venue history even
when it displays only the top ten outcomes.

THE DEFECT, on the real route. `/history` validates a venue bank against the
WHOLE board (`_venue_field_columns` is handed `charted_outcomes`, the deduped
field — right, because the squeeze divides by the field's sum) but it hands the
validator only the rows of the legs it DRAWS: `venue.in_window(cutoff, snapshots,
outcome_ids)` narrows to the ten selected ids before anything is checked. A bank
holding every leg of a 12-leg exclusive field at one shared instant is therefore
whole at `top_n=12` and refused at the default `top_n=10` — the same bytes, the
same instants — with `exclusive_field_incomplete_at_venue_instant`, and
`_venue_points_countable_as_density` counts zero for the same reason, so the
sparse tiers widen a window that is not thin. Codex constructed the
counterexample on cdba3e9f (`8000-INDEPENDENT-REVIEW-EVIDENCE.json`); this file
runs it through the actual handler.

THE REPAIR: the validation population is the whole field's rows in the window,
each leg claim-filtered against its OWN captures; the display population is the
charted subset of the SAME rows, selected afterwards. Nothing is loosened: a hole
in an undrawn leg still refuses the series whole (R3), an undrawn leg that moves
the field off the raw scale still refuses it (R4), a squeezed printed line still
refuses it (R5), and #7954's bypass is untouched (R6).

REAL: the FastAPI app and both chart routes, PostgreSQL, Redis, the Celery task
FUNCTION, the real Kalshi client and parsing, tier planner, candle rule,
layering, compaction, identity validation and both cache tiers. CONTROLLED, and
only these: Kalshi's HTTP transport (every body SYNTHETIC, labelled), the broker,
the clock — all borrowed from the #7351 acceptance file, whose skip gate and
disposable-service guards apply here unchanged. A skip is NOT a pass.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pytest

from tests.integration import test_generic_market_history_7351_real_pg_redis as rig
from tests.integration.test_generic_market_history_7351_real_pg_redis import (
    FROZEN_NOW,
    Venue,
    _arun,
    _candle,
    _get,
    _history,
    _hours_ago,
    _iso,
    _timeline,
)

# A `pytestmark` IS NOT INHERITED THROUGH AN IMPORT, SO THIS FILE NEEDS ITS OWN.
# The rig's guard is module-scoped to the rig's module; importing its fixtures
# brings the services but not the gate. Without this line the re-bound `_world`
# fixture runs its loopback assertion on an unset `GENERIC_HISTORY_REDIS_URL`
# and raises — measured, before this was added: the #7351 file reported
# `53 skipped` with no env while this one reported `10 errors`
# ("REFUSING TO TOUCH THESE SERVICES: Redis host '' is not loopback").
#
# That is not a cosmetic difference. `scripts/ci_shard.py` ENUMERATES every
# collected file and assigns it to a shard with no path exclusions — that is the
# property `shard-completeness` exists to prove — so an ordinary shard collects
# this file on every PR, with none of the `GENERIC_HISTORY_*` vars set. A clean
# skip is inert there; a setup error is a red shard on every PR in the repo.
#
# The condition is READ OFF THE RIG'S OWN MODULE rather than re-read from the
# environment, so the gate and the services it guards can never disagree about
# whether they are configured.
pytestmark = pytest.mark.skipif(
    not (rig.DB_URL and rig.REDIS_URL and rig.NONCE),
    reason=(
        "NOT RUN — set GENERIC_HISTORY_DATABASE_URL + GENERIC_HISTORY_REDIS_URL "
        "+ GENERIC_HISTORY_NONCE to run the #8000 display-selection acceptance "
        "on disposable Postgres and Redis. A skip here is NOT a pass — the CI "
        "step that owns this file refuses a skip, a zero collection and a short "
        "count."
    ),
)

#: The #7351 rig's fixtures, re-bound here so pytest finds them in this module:
#: the module-scoped schema build and the per-test world reset (both autouse),
#: the sealed venue transport and the recorded broker.
_schema = rig._schema
_world = rig._world
venue = rig.venue
broker = rig.broker
_seed_markets = rig._seed

MARKET_ID = 59165300
#: Twelve legs, one exclusive field, raw prices summing to exactly 1.00 so the
#: squeeze is the identity wherever the field is whole. Sorted by price: the
#: default chart draws the first ten; K and L are the undrawn legs.
FIELD12 = [  # (outcome id, ticker suffix, name, current p)
    (219753001, "A", "Alder", 0.20), (219753002, "B", "Birch", 0.15),
    (219753003, "C", "Cedar", 0.12), (219753004, "D", "Dogwood", 0.10),
    (219753005, "E", "Elm", 0.09), (219753006, "F", "Fir", 0.08),
    (219753007, "G", "Ginkgo", 0.07), (219753008, "H", "Hazel", 0.06),
    (219753009, "I", "Ironwood", 0.05), (219753010, "J", "Juniper", 0.04),
    (219753011, "K", "Katsura", 0.02), (219753012, "L", "Larch", 0.02),
]
DRAWN = [row for row in FIELD12[:10]]
UNDRAWN = [row for row in FIELD12[10:]]
VENUE_HOURS = (40, 30, 12)
CAPTURE_HOURS = (50, 26, 2)


def _seed_field12(*, capture_hours=CAPTURE_HOURS, capture_scale: float = 1.0):
    captured = [FROZEN_NOW - timedelta(hours=h) for h in capture_hours]
    _arun(_seed_markets([{
        "id": MARKET_ID, "source": "kalshi", "external_id": "KXTWELVE-26",
        "name": "Which of twelve trees wins?", "mutually_exclusive": True,
        "outcomes": [{"id": oid, "external_id": f"KXTWELVE-26-{sfx}", "name": name, "p": p,
                      "captures": [(ts, round(p * capture_scale, 4)) for ts in captured]}
                     for oid, sfx, name, p in FIELD12],
    }]))


def _venue12(venue: Venue, *, omit: tuple[str, int] | None = None, shift: dict[str, float] | None = None):
    """SYNTHETIC hourly candles: every ticker at every instant, mid = its price.

    `omit` drops ONE candle (a hole in one leg at one instant); `shift` moves a
    ticker's book by a constant so the field stops summing to 1.00 at every
    venue instant (the identity half then convicts it).
    """
    shift = shift or {}
    venue.kalshi_mode = "custom"
    venue.kalshi_custom = {60: {"markets": [
        {"market_ticker": f"KXTWELVE-26-{sfx}", "candlesticks": [
            _candle(_hours_ago(h), f"{p + shift.get(sfx, 0.0) - 0.01:.2f}",
                    f"{p + shift.get(sfx, 0.0) + 0.01:.2f}")
            for h in VENUE_HOURS if omit != (sfx, h)]}
        for _oid, sfx, _name, p in FIELD12]}}


def _history_top(top_n: int, hours: int = 168) -> dict:
    return _get(f"/api/futures/{MARKET_ID}/history?hours={hours}&top_n={top_n}")[0]


def _venue_points(hist: dict) -> dict[str, dict[str, float]]:
    return {e["name"]: {p["timestamp"]: p["probability"] for p in e["history"]
                        if p.get("provenance") == "venue_history"}
            for e in hist["outcomes"]}


def _dump(payloads: dict) -> None:
    """Write the served payloads for the artifact's before/after folder, when asked."""
    import json

    target = os.environ.get("SUPPORTED_HISTORY_8000B_DUMP_DIR")
    if not target:
        return
    for name, payload in payloads.items():
        (__import__("pathlib").Path(target) / f"twelve-leg-{name}.json").write_text(json.dumps(payload, indent=1))


def _fill(venue, broker):
    _timeline(MARKET_ID)      # the cold read that asks the background lane
    broker.run_enqueued()     # the REAL task builds the bank from the synthetic bytes


# ── R1: the ship ─────────────────────────────────────────────────────────────

def test_R1_a_complete_twelve_leg_bank_is_served_at_the_default_top_ten(venue, broker):
    """RED on cdba3e9f: the same bank is whole at top_n=12 and refused at top_n=10."""
    _seed_field12()
    _venue12(venue)
    _fill(venue, broker)

    full = _history_top(12)
    assert full["venue_history"]["state"] == "warm", "the control: at full field the bank is whole"
    assert full["venue_history"]["points_served"] == 12 * len(VENUE_HOURS)

    ten = _history(MARKET_ID)  # the default: top_n=10
    _dump({"history-top10": ten, "history-top12": full, "timeline-top10": _timeline(MARKET_ID, top=10)})
    assert ten["venue_history"]["state"] == "warm", (
        "the reader discarded two undrawn legs before validating the field and "
        "refused a bank it had just served whole: "
        f"{ten['venue_history'].get('refusals')}"
    )
    assert ten["venue_history"]["points_served"] == 10 * len(VENUE_HOURS)
    assert ten["venue_history"]["outcomes_served"] == 10
    served = _venue_points(ten)
    assert set(served) == {name for _o, _s, name, _p in DRAWN}
    for _oid, _sfx, name, p in DRAWN:
        for h in VENUE_HOURS:
            assert served[name][_iso(_hours_ago(h))] == pytest.approx(p), (
                "served at the venue's RAW value; the identity was measured on all twelve")
    # The undrawn legs are validated, never drawn: no line, no point.
    assert not {name for _o, _s, name, _p in UNDRAWN} & set(served)
    assert ten["total_data_points"] == 10 * (len(CAPTURE_HOURS) + len(VENUE_HOURS))


# ── R2: the density gate reads the same population ───────────────────────────

def test_R2_the_sparse_tiers_count_the_venue_rows_the_reader_will_draw(venue, broker):
    """Twelve captures inside seven days (under the `< 20` tier) plus one stale
    capture at 20 days. RED: density is 0 for the same narrowing, `12 + 0 < 20`,
    the 30-day read is richer by one row and the chart widens to 720 h for a
    window that holds 30 supported venue points. GREEN: `12 + 30 >= 20`, no
    extension, and the reader says so with `actual_hours`."""
    _seed_field12(capture_hours=(2,))
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models as m

    async def _stale_capture():
        engine = create_async_engine(os.environ["GENERIC_HISTORY_DATABASE_URL"])
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            s.add(m.FuturesOddsSnapshot(outcome_id=FIELD12[0][0], bookmaker="kalshi",
                                        probability=FIELD12[0][3],
                                        captured_at=FROZEN_NOW - timedelta(days=20)))
            await s.commit()
        await engine.dispose()

    _arun(_stale_capture())
    _venue12(venue)
    _fill(venue, broker)
    ten = _history(MARKET_ID)
    assert ten["venue_history"]["state"] == "warm"
    assert ten["actual_hours"] == 168 and not ten.get("auto_extended"), (
        "the sparse tier widened a window that already held 30 supported venue rows")
    assert ten["venue_history"]["points_served"] == 10 * len(VENUE_HOURS)


# ── R3 / R4 / R5: nothing is loosened ────────────────────────────────────────

def test_R3_a_hole_in_an_undrawn_leg_still_refuses_the_series_whole(venue, broker):
    """🧟 kills "filter before validation" / "validate the drawn legs only":
    Larch is not drawn, Larch is missing one candle, and the field has no
    denominator at that instant — refused, exactly as C4b refuses it at full field."""
    _seed_field12()
    _venue12(venue, omit=("L", 30))
    _fill(venue, broker)
    ten = _history(MARKET_ID)
    assert ten["venue_history"]["state"] == "refused"
    assert ten["venue_history"]["refusals"][-1]["reason"] == "exclusive_field_incomplete_at_venue_instant"
    assert not any(_venue_points(ten).values())
    assert _history_top(12)["venue_history"]["state"] == "refused", "and the same at full field"


def test_R4_an_undrawn_leg_that_moves_the_field_off_raw_scale_still_refuses(venue, broker):
    """🧟 kills "normalize using only the displayed legs": the ten drawn legs sum
    to 0.96 and would pass an identity test on their own; Larch's book sits 0.10
    high, the twelve-leg field sums 1.10 at every venue instant, the squeeze is
    NOT the identity there, and the series is refused for the scale."""
    _seed_field12()
    _venue12(venue, shift={"L": 0.10})
    _fill(venue, broker)
    ten = _history(MARKET_ID)
    assert ten["venue_history"]["state"] == "refused"
    assert ten["venue_history"]["refusals"][-1]["reason"] == "printed_scale_is_not_the_venue_raw_scale"
    assert not any(_venue_points(ten).values())


def test_R5_a_squeezed_printed_line_still_refuses_at_top_ten(venue, broker):
    """🧟 kills "bypass the non-identity-scale refusal": captures at 112% of raw
    print a squeezed line; a raw venue point is not on it. Whole bank, top ten."""
    _seed_field12(capture_scale=1.12)
    _venue12(venue)
    _fill(venue, broker)
    ten = _history(MARKET_ID)
    assert ten["venue_history"]["state"] == "refused"
    assert ten["venue_history"]["refusals"][-1]["reason"] == "printed_scale_is_not_the_venue_raw_scale"


def test_R6_the_unsqueezed_board_bypass_is_untouched(venue, broker):
    """#7954: a board with a withheld leg refuses the squeeze and prints raw, so
    the completeness half is not asked. Larch observed nine days behind its board
    makes `field_complete` False; Larch's candles are also missing entirely, which
    would refuse a complete board (R3) and must NOT refuse this one."""
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models as m

    _seed_field12()

    async def _stale_larch():
        engine = create_async_engine(os.environ["GENERIC_HISTORY_DATABASE_URL"])
        async with async_sessionmaker(engine)() as s:
            await s.execute(update(m.FuturesOutcome).where(m.FuturesOutcome.id == FIELD12[-1][0])
                            .values(last_updated=FROZEN_NOW - timedelta(days=9)))
            await s.commit()
        await engine.dispose()

    _arun(_stale_larch())
    venue.kalshi_mode = "custom"
    venue.kalshi_custom = {60: {"markets": [
        {"market_ticker": f"KXTWELVE-26-{sfx}", "candlesticks": [
            _candle(_hours_ago(h), f"{p - 0.01:.2f}", f"{p + 0.01:.2f}") for h in VENUE_HOURS]}
        for _oid, sfx, _name, p in FIELD12 if sfx != "L"]}}
    _fill(venue, broker)
    ten = _history(MARKET_ID)
    assert ten["venue_history"]["state"] == "warm"
    assert ten["venue_history"]["points_served"] == 10 * len(VENUE_HOURS)


def test_R7_the_phone_reader_is_unchanged(venue, broker):
    """`/probability-timeline` never applied the scale contract (#7284 rules it
    prints raw); it must serve exactly what it served before, top ten or twelve."""
    _seed_field12()
    _venue12(venue)
    _fill(venue, broker)
    tl = _timeline(MARKET_ID, top=10)
    assert tl["venue_history"]["points_served"] == 10 * len(VENUE_HOURS)
    assert tl["venue_history"]["outcomes_served"] == 10


def test_R8_a_non_exclusive_ladder_is_served_exactly_as_before(venue, broker):
    """The 61097129 shape (a spread ladder: `mutually_exclusive=False`, more legs
    than the chart draws). No squeeze, no hole test, top ten of twelve served —
    on cdba3e9f and on the candidate alike. Its raw per-leg values are honest
    (#199) and are served unsqueezed."""
    _arun(_seed_markets([{
        "id": MARKET_ID, "source": "kalshi", "external_id": "KXTWELVE-26",
        "name": "Home wins by over N points", "mutually_exclusive": False,
        "outcomes": [{"id": oid, "external_id": f"KXTWELVE-26-{sfx}", "name": name, "p": p,
                      "captures": [(FROZEN_NOW - timedelta(hours=h), p) for h in CAPTURE_HOURS]}
                     for oid, sfx, name, p in FIELD12],
    }]))
    _venue12(venue)
    _fill(venue, broker)
    ten = _history(MARKET_ID)
    assert ten["venue_history"]["state"] == "warm"
    assert ten["venue_history"]["points_served"] == 10 * len(VENUE_HOURS)
    assert ten["venue_history"]["outcomes_served"] == 10
    served = _venue_points(ten)
    for _oid, _sfx, name, p in DRAWN:
        assert served[name][_iso(_hours_ago(30))] == pytest.approx(p)


async def _add_capture(oid: int, p: float, *, days_ago: int):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models as m

    engine = create_async_engine(os.environ["GENERIC_HISTORY_DATABASE_URL"])
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        s.add(m.FuturesOddsSnapshot(outcome_id=oid, bookmaker="kalshi", probability=p,
                                    captured_at=FROZEN_NOW - timedelta(days=days_ago)))
        await s.commit()
    await engine.dispose()


def test_R2b_the_density_gate_counts_the_drawn_rows_not_the_whole_fields(venue, broker):
    """🧟 kills "count every field row as density": nine captures (nine of the
    twelve legs, one instant) plus ONE venue instant carrying all twelve legs.
    Drawn density is 10 → `9 + 10 < 20` and the tier widens to 30 days, where a
    stale capture makes the wider read richer (`actual_hours` 720). Counting the
    two undrawn legs' rows too would read `9 + 12 = 21`, keep the window at 168 h
    and print a thinner chart than the one the reader is entitled to."""
    _arun(_seed_markets([{
        "id": MARKET_ID, "source": "kalshi", "external_id": "KXTWELVE-26",
        "name": "Which of twelve trees wins?", "mutually_exclusive": True,
        "outcomes": [{"id": oid, "external_id": f"KXTWELVE-26-{sfx}", "name": name, "p": p,
                      "captures": ([(FROZEN_NOW - timedelta(hours=2), p)] if i < 9 else [])}
                     for i, (oid, sfx, name, p) in enumerate(FIELD12)],
    }]))
    _arun(_add_capture(FIELD12[0][0], FIELD12[0][3], days_ago=20))
    venue.kalshi_mode = "custom"
    venue.kalshi_custom = {60: {"markets": [
        {"market_ticker": f"KXTWELVE-26-{sfx}",
         "candlesticks": [_candle(_hours_ago(12), f"{p - 0.01:.2f}", f"{p + 0.01:.2f}")]}
        for _oid, sfx, _name, p in FIELD12]}}
    _fill(venue, broker)
    ten = _history(MARKET_ID)
    assert ten["venue_history"]["state"] == "warm"
    assert ten["venue_history"]["points_served"] == 10
    assert ten["actual_hours"] == 720 and ten.get("auto_extended") is True, (
        "9 captures + 10 drawn venue rows is under the tier; the window must widen")


def test_R9_twelve_legs_observed_at_twelve_different_minutes_are_twelve_holes(venue, broker):
    """🧟 kills "join different instants": each ticker's hourly candle closes at
    its own minute, so no instant carries the field and the series is refused —
    at top ten and at full field — while the phone, which prints raw by ruling,
    serves every one of the 36 observations. This is the shape of the two
    Polymarket binaries in the named package (Yes and No never share an instant)
    and must stay refused; a reader that floored timestamps to the hour would
    fuse twelve observations nobody made together into one column."""
    _seed_field12()
    venue.kalshi_mode = "custom"
    venue.kalshi_custom = {60: {"markets": [
        {"market_ticker": f"KXTWELVE-26-{sfx}", "candlesticks": [
            _candle(_hours_ago(h) + (i + 1) * 120, f"{p - 0.01:.2f}", f"{p + 0.01:.2f}")
            for h in VENUE_HOURS]}
        for i, (_oid, sfx, _name, p) in enumerate(FIELD12)]}}
    _fill(venue, broker)
    for hist in (_history(MARKET_ID), _history_top(12)):
        assert hist["venue_history"]["state"] == "refused"
        assert hist["venue_history"]["refusals"][-1]["reason"] == (
            "exclusive_field_incomplete_at_venue_instant")
        assert not any(_venue_points(hist).values())
    assert _timeline(MARKET_ID, top=12)["venue_history"]["points_served"] == 12 * len(VENUE_HOURS)
