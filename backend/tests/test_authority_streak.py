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
    READ_FAILED,
)
from app.utils.authority_streak import (
    DAY_STATES_CARRY,
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


def _all_gate_states():
    """Every `GATE_*` the agreement module defines, discovered rather than typed.

    This list used to be a four-name literal, which meant a fifth gate state
    could be added upstream and neither of the two tests below would notice —
    the exact failure their docstrings promise to catch. `TOO-FEW-TO-SCORE`
    (authority/024) was that fifth state.
    """
    from app.utils import authority_agreement as aa

    return sorted(
        getattr(aa, name)
        for name in dir(aa)
        if name.startswith("GATE_") and isinstance(getattr(aa, name), str)
    )


@pytest.mark.parametrize("gate", _all_gate_states())
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


@pytest.mark.parametrize("carrier", sorted(DAY_STATES_CARRY))
def test_a_carrying_day_neither_advances_nor_resets_and_is_declared(carrier):
    """Spec rule 6 / gotcha #53: "we could not look" is not "we disagreed".

    Parametrised over `DAY_STATES_CARRY` itself, so a state added to that
    frozenset is a state this test starts covering the same day. It was a
    three-name literal, and `TOO-FEW-TO-SCORE` joined the set without it.
    """
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
    def __init__(self, status, payload=None, error=None, generation=1000):
        self.status = status
        self.error = error
        self.envelope = (
            SimpleNamespace(payload=payload, generation=generation)
            if payload is not None
            else None
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

    async def _publish(envelope, *, expected_generation=None):
        state["wrote"].append(envelope)
        state["last_expected_generation"] = expected_generation
        return state["publish"]

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(ds, "read_snapshot_standalone", _read)
    monkeypatch.setattr(ds, "publish_cas_snapshot_standalone", _publish)
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
async def test_the_ledger_read_is_not_age_bounded_the_way_a_cache_is(durable):
    """A ledger is SUPPOSED to be old.

    `read_snapshot`'s default max age is seven days; under it, one week of
    stamper downtime would type a perfectly good ledger as `stale`, which this
    module refuses to write over — so the sport would never record another day
    again. Whether a gap matters is the fold's question, not the reader's.
    """
    await authority_ledger.record_agreement_day(row(), at=NOON)
    assert durable["last_read_kwargs"]["max_age_s"] >= 365 * 24 * 3600


# ---------------------------------------------------------------------------
# CERT-952: losing the generation race (the repair, and its two named tests)
# ---------------------------------------------------------------------------


class FakeSubstrate:
    """A durable store that enforces the REAL generation guard.

    `durable_state_snapshots`' upsert applies `WHERE generation <= EXCLUDED.
    generation`, so a writer carrying an older generation writes nothing and is
    told `superseded`. The stub above cannot express that — it answers a fixed
    status — and a fixed status is exactly what let the CERT-952 defect through:
    the code read the word `superseded` and never asked what was actually stored.
    """

    def __init__(self):
        self.payload = None
        self.generation = 0
        self.publishes = []
        self.reads = 0
        # "A rival writer keeps landing between our read and our write." Set
        # explicitly rather than simulated with a huge generation, because a
        # retry legitimately bumps past whatever it read — so a big number
        # models "one old rival", not "a rival that keeps winning", and only
        # the second one exercises the give-up path.
        self.always_supersede = False
        # "This writer's read happened before the row you are about to see."
        # One-shot, so a single pass can be made to fold onto a stale copy.
        self.stale_read_once = None

    async def read(self, identity, **kwargs):
        self.reads += 1
        if self.stale_read_once is not None:
            payload, generation = self.stale_read_once
            self.stale_read_once = None
            if payload is None:
                return FakeRead("missing")
            return FakeRead("ok", payload=payload, generation=generation)
        if self.payload is None:
            return FakeRead("missing")
        return FakeRead("ok", payload=self.payload, generation=self.generation)

    async def publish(self, envelope, *, expected_generation=None):
        """`_CAS_UPSERT_SQL` / `_CAS_CREATE_SQL` in Python.

        Equality against the generation the caller READ, and a create arm that
        does nothing if a row already exists. Anything looser than this is the
        `<=` guard CERT-955 rejected.
        """
        self.publishes.append((envelope, expected_generation))
        if self.always_supersede:
            return {"status": "cas-miss", "identity": envelope.identity}
        if expected_generation is None:
            if self.payload is not None:
                return {"status": "cas-miss", "identity": envelope.identity}
        elif int(expected_generation) != int(self.generation):
            return {"status": "cas-miss", "identity": envelope.identity}
        self.payload = envelope.payload
        self.generation = envelope.generation
        return {"status": "ok", "identity": envelope.identity}

    def install(self, monkeypatch):
        import app.services.durable_snapshots as ds

        monkeypatch.setattr(ds, "read_snapshot_standalone", self.read)
        monkeypatch.setattr(ds, "publish_cas_snapshot_standalone", self.publish)
        return self


@pytest.fixture
def substrate(monkeypatch):
    return FakeSubstrate().install(monkeypatch)


@pytest.mark.asyncio
async def test_a_superseded_fold_never_publishes_its_own_clearing_count(substrate):
    """CERT-952's catching test #1: superseded older MEETS vs newer BELOW.

    A pass reads the ledger, and before it can write, a concurrent writer lands
    a NEWER generation whose day scores `BELOW`. The losing pass must not return
    its own stale fold — it computed `MEETS` on a copy the durable winner
    already contradicts, and the endpoint publishes whatever it returns, so a
    stale `meets_flip_gate: true` would be read as a real day towards a flip.
    """
    # Six clearing days already banked, then a BELOW day lands from elsewhere.
    substrate.payload = ledger_of([GATE_MEETS] * 6 + [GATE_BELOW])
    substrate.always_supersede = True

    out = await authority_ledger.record_agreement_day(row(GATE_MEETS), at=NOON)

    streak = out["streak"]
    assert streak.get("meets_flip_gate") is not True, (
        "the losing fold published a clearing count the durable winner "
        "contradicts — this is CERT-952"
    )
    assert streak["days"] == 0, "the durable winner's day is BELOW, so today scores 0"
    assert streak["publish_status"] == authority_ledger.SUPERSEDED
    assert streak["attempts"] == authority_ledger.LEDGER_FOLD_ATTEMPTS
    # It retried rather than giving up on the first loss, and it wrote nothing.
    assert substrate.reads > 1
    assert substrate.payload["days"][-1]["state"] == GATE_BELOW


@pytest.mark.asyncio
async def test_a_lost_race_on_a_day_the_winner_lacks_records_nothing(substrate):
    """The other half of #1: no count at all rather than a wrong one.

    Same loss, but the durable winner does not contain this pass's day. There is
    no true number available, so the row says UNRECORDED — never a fold computed
    on a copy that lost.
    """
    substrate.payload = ledger_of([GATE_MEETS] * 3, end=NOON - timedelta(days=2))
    substrate.always_supersede = True

    out = await authority_ledger.record_agreement_day(row(), at=NOON)

    assert out["streak"]["state"] == authority_ledger.STREAK_UNRECORDED
    assert out["streak"]["reason"] == "lost-every-generation-race"
    assert "days" not in out["streak"]
    assert utc_day(NOON) in out["streak"]["detail"]


@pytest.mark.asyncio
async def test_two_passes_across_midnight_keep_both_days(substrate):
    """CERT-952's catching test #2: cross-midnight overlap retains both days.

    The 23:59 pass reads an empty store. Before it writes, the 00:01 pass runs to
    completion and banks the new day. The late writer must not lose its own day
    to the row that appeared, and must not flatten the new day either: its create
    misses, it re-reads, it folds onto the winner, and BOTH days land.
    """
    late = NOON.replace(hour=23, minute=59)
    early_next = late + timedelta(minutes=2)  # the following UTC day

    # The 00:01 pass completes first.
    await authority_ledger.record_agreement_day(row(), at=early_next)
    assert [d["day"] for d in substrate.payload["days"]] == [utc_day(early_next)]

    # The 23:59 pass reads an EMPTY store — its read happened before the above —
    # and only then tries to write.
    substrate.stale_read_once = (None, 0)
    out = await authority_ledger.record_agreement_day(row(), at=late)

    days = [d["day"] for d in substrate.payload["days"]]
    assert days == [
        utc_day(late),
        utc_day(early_next),
    ], "the late writer lost a day to the midnight overlap"
    assert out["streak"]["recorded"] is True
    assert out["streak"]["attempts"] == 2, "it took exactly one refold"
    # And the surviving ledger is a real two-day streak, not one day twice.
    assert substrate.payload["streak"]["days"] == 2


@pytest.mark.asyncio
async def test_two_writers_that_read_the_same_generation_cannot_both_land(substrate):
    """CERT-955's catching test: both read `g`, both propose `g+1`.

    This is the case the shared `stored <= EXCLUDED.generation` guard cannot
    express. Two folds built on the same read both propose the same next
    generation; under `<=` the second passes on EQUALITY, returns `ok`, and
    overwrites a fold it never read — losing a calendar day while telling both
    callers they succeeded. Under compare-and-swap against the generation
    actually READ, exactly one lands and the other has to fold again.
    """
    # A day is already banked, at a generation AHEAD of either writer's stamp —
    # the state a previous refold leaves behind. Both writers must therefore
    # raise their proposal to `stored + 1`, and land on the same number.
    substrate.payload = ledger_of([GATE_MEETS], end=NOON - timedelta(days=2))
    substrate.generation = 10**15
    shared_generation = substrate.generation
    shared_payload = substrate.payload
    assert len(shared_payload["days"]) == 1

    # Writer A reads `g` and lands its day.
    await authority_ledger.record_agreement_day(row(), at=NOON - timedelta(days=1))
    assert substrate.generation != shared_generation
    proposed_by_a = substrate.generation

    # Writer B read the SAME `g` before A wrote, and only now publishes.
    substrate.stale_read_once = (shared_payload, shared_generation)
    out = await authority_ledger.record_agreement_day(row(), at=NOON)

    first_attempt, first_expected = substrate.publishes[-2]
    assert first_expected == shared_generation, "the CAS is against the READ generation"
    assert first_attempt.generation == proposed_by_a, "both writers proposed g+1"

    assert out["streak"]["recorded"] is True
    assert out["streak"]["attempts"] == 2, "B's first write was rejected, not accepted"
    assert [d["day"] for d in substrate.payload["days"]] == [
        utc_day(NOON - timedelta(days=2)),
        utc_day(NOON - timedelta(days=1)),
        utc_day(NOON),
    ], "a calendar day was lost to two writers proposing the same generation"
    assert substrate.payload["streak"]["days"] == 3


def test_the_ledger_write_is_a_compare_and_swap_in_the_sql_itself():
    """The predicate is the guard, so it is pinned as source text.

    There is no PostgreSQL in this sandbox, so the concurrency above is proved
    against a Python model of these two statements. That model is only worth
    something if the statements it models say what it thinks they say — and the
    difference between the CAS and the bug is four characters of SQL.
    """
    import app.services.durable_snapshots as ds

    cas = str(ds._CAS_UPSERT_SQL)
    assert "durable_state_snapshots.generation = :expected_generation" in cas
    assert "<=" not in cas, "the ledger's write must not fall back to the `<=` guard"
    assert "EXCLUDED.generation" not in cas.split("DO UPDATE SET")[1].split("WHERE")[1]

    create = str(ds._CAS_CREATE_SQL)
    assert "ON CONFLICT (identity) DO NOTHING" in create

    # And the guard the ledger must NOT be using is still there, unchanged, for
    # the callers it is right for.
    assert "durable_state_snapshots.generation <= EXCLUDED.generation" in str(
        ds._UPSERT_SQL
    )


@pytest.mark.asyncio
async def test_the_ordinary_uncontended_write_still_takes_one_attempt(substrate):
    out = await authority_ledger.record_agreement_day(row(), at=NOON)
    assert out["streak"]["recorded"] is True
    assert out["streak"]["attempts"] == 1
    assert len(substrate.publishes) == 1


@pytest.mark.asyncio
async def test_a_recorded_count_always_equals_the_one_that_is_actually_stored(
    substrate,
):
    """The general clause behind CERT-952, pinned on its own.

    Every specific race is a way of breaking one invariant: **what this function
    returns is what the endpoint publishes, so a `recorded` count must be the
    count that is durably stored.** A returned number that no row backs is worse
    than no number, because it is indistinguishable from a measurement.
    """
    outcomes = []
    for offset in range(3):
        at = NOON + timedelta(days=offset)
        out = await authority_ledger.record_agreement_day(row(), at=at)
        outcomes.append(out["streak"])
        if out["streak"].get("recorded"):
            assert out["streak"]["days"] == substrate.payload["streak"]["days"]
            assert out["streak"]["through"] == substrate.payload["streak"]["through"]

    assert [o["days"] for o in outcomes] == [1, 2, 3]

    # And once a rival starts winning every race, nothing is claimed at all.
    substrate.always_supersede = True
    late = await authority_ledger.record_agreement_day(
        row(), at=NOON + timedelta(days=4)
    )
    assert late["streak"]["state"] == authority_ledger.STREAK_UNRECORDED
    assert substrate.payload["streak"]["days"] == 3, "the store is untouched"
