"""Guards for D50's seven-day count (#2867, authority/021).

The thing under test is a COUNTER OF EVIDENCE THAT CANNOT BE REGENERATED. Nobody
can go back and ask StatPal what it served last Tuesday, so two classes of bug
here are unrecoverable rather than merely wrong:

  * a streak that counts across a day we never measured, and
  * a fold that overwrites a real ledger because the read of it failed.

Both have their own test below, and both are written as the failure, not as the
success: `test_a_missing_day_stops_the_streak_and_says_which_day` and
`test_a_read_we_could_not_trust_writes_nothing_at_all`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import authority_ledger
from app.utils.authority_agreement import (
    FLIP_BAR_PCT,
    GATE_BELOW,
    GATE_MEETS,
    GATE_NO_SCORE,
    GATE_PENDING,
    READ_FAILED,
)
from app.utils.authority_streak import (
    LEDGER_RETAINED_DAYS,
    REQUIRED_STREAK_DAYS,
    STOP_BELOW,
    STOP_MISSING_DAY,
    compute_streak,
    day_state,
    empty_ledger,
    fold_day,
    utc_day,
)

SPORT = "americanfootball_nfl"
NOON = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def row(gate: str = GATE_MEETS, *, pct: float = 99.69, denominator: int = 322) -> dict:
    """One agreement row of the shape `build_agreement_row` returns."""
    return {
        "sport_key": SPORT,
        "read": "READ-OK",
        "read_failures": [],
        "denominator": denominator,
        "identity": {
            "both": denominator - 1,
            "pct": pct,
            "ours_covered_pct": pct,
            "governing": {
                "numbers": ["pct", "ours_covered_pct"],
                "values": {"pct": pct, "ours_covered_pct": pct},
                "bar_pct": FLIP_BAR_PCT,
                "gate": gate,
                "why": "test row",
            },
        },
    }


def failed_row() -> dict:
    """What the stamper banks when StatPal refused: no `identity` at all."""
    return {
        "sport_key": SPORT,
        "read": READ_FAILED,
        "read_failures": ["season-schedule: 503"],
    }


def ledger_of(states: list[str], *, end: datetime = NOON) -> dict:
    """A ledger whose LAST day is `end`, one day per state, oldest first."""
    ledger = empty_ledger(SPORT)
    first = end - timedelta(days=len(states) - 1)
    for offset, state in enumerate(states):
        at = first + timedelta(days=offset)
        ledger = fold_day(
            ledger, failed_row() if state == READ_FAILED else row(state), at=at
        )
    return ledger


# ---------------------------------------------------------------------------
# What a day IS
# ---------------------------------------------------------------------------


def test_a_day_is_a_utc_calendar_date_and_naive_input_is_not_local_time():
    assert utc_day(datetime(2026, 9, 5, 23, 59, tzinfo=timezone.utc)) == "2026-09-05"
    assert utc_day(datetime(2026, 9, 6, 0, 1, tzinfo=timezone.utc)) == "2026-09-06"
    # Naive is read as UTC. Read as local time, a 5pm-Pacific pass would land on
    # the following day and split one day's passes across two ledger entries.
    assert utc_day(datetime(2026, 9, 5, 23, 59)) == "2026-09-05"
    # And an offset stamp is converted, not truncated.
    east = timezone(timedelta(hours=10))
    assert utc_day(datetime(2026, 9, 6, 8, 0, tzinfo=east)) == "2026-09-05"


@pytest.mark.parametrize("gate", [GATE_MEETS, GATE_BELOW, GATE_NO_SCORE, GATE_PENDING])
def test_every_gate_state_survives_the_trip_into_the_ledger(gate):
    assert day_state(row(gate)) == gate
    assert fold_day(empty_ledger(SPORT), row(gate), at=NOON)["days"][0]["state"] == gate


def test_a_failed_read_is_its_own_day_state_and_not_a_missing_gate():
    """A READ-FAILED row carries no `identity`, so there is no gate to read.

    Defaulting it to anything is the bug: default it to BELOW and one 503 wipes
    six good days; default it to MEETS and an outage earns credit.
    """
    assert day_state(failed_row()) == READ_FAILED
    entry = fold_day(empty_ledger(SPORT), failed_row(), at=NOON)["days"][0]
    assert entry["state"] == READ_FAILED
    assert entry["read_failures"] == ["season-schedule: 503"]


def test_a_row_whose_gate_is_missing_is_not_scored_as_a_pass():
    hollow = row()
    hollow["identity"]["governing"].pop("gate")
    assert day_state(hollow) == READ_FAILED


# ---------------------------------------------------------------------------
# Many passes, one day
# ---------------------------------------------------------------------------


def test_the_last_pass_of_the_day_is_the_days_verdict_and_the_count_is_kept():
    ledger = fold_day(empty_ledger(SPORT), row(GATE_MEETS, pct=99.6), at=NOON)
    ledger = fold_day(ledger, row(GATE_MEETS, pct=99.8), at=NOON + timedelta(hours=1))

    assert len(ledger["days"]) == 1, "an hourly stamper must not mint 24 ledger days"
    day = ledger["days"][0]
    assert day["passes"] == 2
    assert day["values"]["pct"] == 99.8, "the later look at the same day wins"
    assert day["first_pass_at"] == NOON.isoformat()
    assert day["unstable"] is False


def test_a_day_that_changed_its_mind_scores_but_says_it_was_unstable():
    ledger = fold_day(empty_ledger(SPORT), row(GATE_BELOW), at=NOON)
    ledger = fold_day(ledger, row(GATE_MEETS), at=NOON + timedelta(hours=6))

    day = ledger["days"][0]
    assert day["state"] == GATE_MEETS
    assert day["unstable"] is True
    assert sorted(day["states_seen"]) == sorted([GATE_BELOW, GATE_MEETS])
    # And the doubt reaches the streak, where a flip proposal has to read it.
    assert ledger["streak"]["unstable_days"] == [utc_day(NOON)]


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------


def test_an_empty_ledger_has_no_streak_which_is_not_a_streak_of_zero():
    assert compute_streak([]) is None
    assert empty_ledger(SPORT)["streak"] is None


def test_seven_clearing_days_meet_the_flip_gate_and_six_do_not():
    six = ledger_of([GATE_MEETS] * 6)["streak"]
    assert six["days"] == 6
    assert six["meets_flip_gate"] is False

    seven = ledger_of([GATE_MEETS] * REQUIRED_STREAK_DAYS)["streak"]
    assert seven["days"] == REQUIRED_STREAK_DAYS
    assert seven["meets_flip_gate"] is True
    assert seven["through"] == utc_day(NOON)
    assert seven["since"] == utc_day(NOON - timedelta(days=6))


def test_a_below_day_resets_the_streak_and_the_row_names_the_day_it_lost():
    streak = ledger_of([GATE_MEETS] * 5 + [GATE_BELOW, GATE_MEETS])["streak"]
    assert streak["days"] == 1, "only the day after the BELOW counts"
    assert streak["stopped_by"]["kind"] == STOP_BELOW
    assert streak["stopped_by"]["day"] == utc_day(NOON - timedelta(days=1))
    assert streak["meets_flip_gate"] is False


@pytest.mark.parametrize("carrier", [GATE_NO_SCORE, GATE_PENDING, READ_FAILED])
def test_a_carrying_day_neither_advances_nor_resets_and_is_declared(carrier):
    """Spec rule 6 / gotcha #53: "we could not look" is not "we disagreed"."""
    streak = ledger_of([GATE_MEETS] * 7 + [carrier])["streak"]
    assert streak["days"] == 7, f"{carrier} must not reset a real streak"
    assert streak["meets_flip_gate"] is True
    assert streak["carried_days"] == [utc_day(NOON)]
    # It also did not COUNT: eight days of history, seven of them scored.
    assert len(streak["carried_days"]) + streak["days"] == 8


def test_a_missing_day_stops_the_streak_and_says_which_day():
    """The guard this module exists for.

    Seven MEETS rows are not seven consecutive days if one of the days in
    between has no row at all. A missing day is the ABSENCE of evidence — unlike
    READ-FAILED, which is evidence that we looked — and a gate that counts
    across it would let a stamper outage manufacture a pass.
    """
    ledger = empty_ledger(SPORT)
    for offset in [9, 8, 7, 6, 5, 4, 2, 1, 0]:  # day 3 back is missing
        ledger = fold_day(ledger, row(GATE_MEETS), at=NOON - timedelta(days=offset))

    streak = ledger["streak"]
    assert len(ledger["days"]) == 9, "nine rows were stored"
    assert streak["days"] == 3, "but only three of them are consecutive to today"
    assert streak["meets_flip_gate"] is False
    assert streak["stopped_by"]["kind"] == STOP_MISSING_DAY
    assert streak["stopped_by"]["day"] == utc_day(NOON - timedelta(days=3))


def test_a_streak_cannot_be_longer_than_the_history_that_backs_it():
    streak = ledger_of([GATE_MEETS] * 3)["streak"]
    assert streak["days"] == 3
    assert streak["stopped_by"]["kind"] == "no-earlier-row"


def test_an_unrecognised_state_stops_the_walk_instead_of_being_carried():
    """A fifth state added upstream must not quietly extend a streak (D55)."""
    ledger = ledger_of([GATE_MEETS] * 3)
    ledger["days"][-2]["state"] = "SOMETHING-NEW"
    streak = compute_streak(ledger["days"])
    assert streak["days"] == 1
    assert "SOMETHING-NEW" in streak["stopped_by"]["detail"]


def test_the_history_is_bounded_so_the_durable_payload_cannot_grow_forever():
    ledger = empty_ledger(SPORT)
    for offset in range(LEDGER_RETAINED_DAYS + 10, -1, -1):
        ledger = fold_day(ledger, row(GATE_MEETS), at=NOON - timedelta(days=offset))
    assert len(ledger["days"]) == LEDGER_RETAINED_DAYS
    assert ledger["days"][-1]["day"] == utc_day(NOON), "the newest day is kept"
    assert ledger["streak"]["days"] == LEDGER_RETAINED_DAYS


# ---------------------------------------------------------------------------
# Persistence: what may be written, and what may never be
# ---------------------------------------------------------------------------


class FakeRead:
    def __init__(self, status, payload=None, error=None):
        self.status = status
        self.error = error
        self.envelope = (
            SimpleNamespace(payload=payload) if payload is not None else None
        )

    @property
    def ok(self):
        return self.status == "ok"

    @property
    def missing(self):
        return self.status == "missing"


@pytest.fixture
def durable(monkeypatch):
    """Stub the durable substrate; record what would be written."""
    state = {"read": FakeRead("missing"), "publish": {"status": "ok"}, "wrote": []}

    async def _read(identity, **kwargs):
        state["last_read_identity"] = identity
        state["last_read_kwargs"] = kwargs
        return state["read"]

    async def _publish(envelope):
        state["wrote"].append(envelope)
        return state["publish"]

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(ds, "read_snapshot_standalone", _read)
    monkeypatch.setattr(ds, "publish_snapshot_standalone", _publish)
    return state


@pytest.mark.asyncio
async def test_the_first_ever_day_starts_a_ledger_and_is_written(durable):
    out = await authority_ledger.record_agreement_day(row(), at=NOON)

    assert out["streak"]["recorded"] is True
    assert out["streak"]["days"] == 1
    assert len(durable["wrote"]) == 1
    envelope = durable["wrote"][0]
    assert envelope.identity == "authority-agreement-ledger:americanfootball_nfl"
    assert envelope.payload["days"][0]["day"] == utc_day(NOON)


@pytest.mark.asyncio
async def test_a_read_we_could_not_trust_writes_nothing_at_all(durable):
    """The irreversible mistake, refused.

    The row EXISTS but came back unreadable. Folding onto a fresh ledger would
    replace however many real days are in there with one, and reset a streak
    that may have been six days old. There is no undo: the previous payload is
    the only copy.
    """
    durable["read"] = FakeRead("unavailable", error="connection reset")

    out = await authority_ledger.record_agreement_day(row(), at=NOON)

    assert durable["wrote"] == [], "a failed read must never license a write"
    assert out["streak"]["state"] == authority_ledger.STREAK_UNRECORDED
    assert out["streak"]["reason"] == "durable-read-unavailable"
    assert "connection reset" in out["streak"]["detail"]
    # And it must not read as a streak of zero to anybody downstream.
    assert "days" not in out["streak"]


@pytest.mark.asyncio
async def test_an_existing_ledger_is_extended_rather_than_replaced(durable):
    stored = ledger_of([GATE_MEETS] * 3, end=NOON - timedelta(days=1))
    durable["read"] = FakeRead("ok", payload=stored)

    out = await authority_ledger.record_agreement_day(row(), at=NOON)

    assert out["streak"]["days"] == 4
    assert len(durable["wrote"][0].payload["days"]) == 4


@pytest.mark.asyncio
async def test_a_dry_run_computes_the_day_and_persists_nothing(durable):
    out = await authority_ledger.record_agreement_day(row(), at=NOON, apply=False)

    assert durable["wrote"] == [], "a rehearsal must not advance the real gate"
    assert out["streak"]["dry_run"] is True
    assert out["streak"]["days"] == 1


@pytest.mark.asyncio
async def test_a_publish_that_did_not_land_is_reported_not_assumed(durable):
    durable["publish"] = {"status": "error", "error": "deadlock detected"}

    out = await authority_ledger.record_agreement_day(row(), at=NOON)

    assert out["streak"]["state"] == authority_ledger.STREAK_UNRECORDED
    assert out["streak"]["reason"] == "durable-publish-error"
    assert "deadlock" in out["streak"]["detail"]


@pytest.mark.asyncio
async def test_a_superseded_publish_still_counts_as_recorded(durable):
    """`superseded` means a NEWER generation is already there — the durability
    requirement is satisfied, so this is success, reported distinctly."""
    durable["publish"] = {"status": "superseded"}

    out = await authority_ledger.record_agreement_day(row(), at=NOON)

    assert out["streak"]["recorded"] is True
    assert out["streak"]["publish_status"] == "superseded"


@pytest.mark.asyncio
async def test_the_ledger_read_is_not_age_bounded_the_way_a_cache_is(durable):
    """A ledger is SUPPOSED to be old.

    `read_snapshot`'s default max age is seven days; under it, one week of
    stamper downtime would type a perfectly good ledger as `stale`, which this
    module refuses to write over — so the sport would never record another day
    again. Whether a gap matters is the fold's question, not the reader's.
    """
    await authority_ledger.record_agreement_day(row(), at=NOON)
    assert durable["last_read_kwargs"]["max_age_s"] >= 365 * 24 * 3600
