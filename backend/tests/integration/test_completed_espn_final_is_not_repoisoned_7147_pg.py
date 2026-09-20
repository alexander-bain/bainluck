"""#7147's refusal, executed against real Postgres rows instead of read off the source.

WHAT THE UNIT SUITE ALREADY PROVES, AND WHAT IT CANNOT
------------------------------------------------------
``tests/test_completed_espn_final_is_not_repoisoned_7147.py`` covers the
judgment — :func:`clockless_write_repoisons_a_settled_final` — in full, and no
database is needed to test a rule about two integers. Its last class,
``TestTheWriterActuallyConsultsIt``, then proves the wiring with :mod:`ast` and
:func:`inspect.getsource`: the call is in the function, it joins
``_skip_score_write``, the snapshot is gated on the same flag, the counter is
incremented, the *effective* status is passed.

That is a statement about the TEXT of ``_poll_all_odds``. **Nothing in this
repository executes it.** All five files that name ``_poll_all_odds``
(``test_odds_scores_stale_id_guard``, ``test_live_state_does_not_run_backwards_6056``,
``test_live_cadence_lat_p159``, ``test_single_flight_lease``, ``test_tasks_wiring``)
read its source or its beat entry; not one of them runs a pass. So between the
judgment and the reader's row there is a stretch that no test has ever walked:

    ``sports_needing_scores``            a JOIN over ``sports``×``events`` with a
                                         3-day window and a four-status set. A
                                         sport it does not return is a sport
                                         whose scores are never fetched.
    ``_get_espn_covered_sports()``       a GROUPed COUNT whose ``status IN
                                         ('scheduled','live')`` clause is the
                                         reason a sport full of *settled*
                                         ESPN-anchored rows is NOT "covered" —
                                         which is precisely how the specimen's
                                         sport stayed in the loop on the night
                                         it was re-poisoned.
    ``external_id_currency``             #1981's re-verification, which every
                                         write below it is downstream of.
    the write itself                     ``Event.__table__.update()`` by primary
                                         key, and ``session.add(ScoreSnapshot)``
                                         — two separate statements against two
                                         real tables, either of which can be
                                         right in the source and wrong on the row.

A guard that is correct about a row the loop never reaches protects nothing, and
a refusal that is computed and then written anyway looks identical in an ``ast``
test. This file drives a real scores pass over real rows and asserts on what the
tables HOLD afterwards.

WHAT IS SEEDED, AND WHY EACH ROW IS HERE
-----------------------------------------
Every row below states its own expected verdict in :data:`SEED`, so the
assertions are per-row equalities rather than a count: a pass that refused the
right NUMBER of the wrong rows would satisfy a count and fails this.

The specimen is the one CERT-3145 measured — Rangers–Red Sox, ESPN ``401816966``,
repaired to ``7-3`` at 22:37Z on 2026-09-19 and serving ``7-2`` again by
23:15:07Z with a freshly stamped snapshot row to match.

🔴 ``UNMATCHED`` (a ``live`` MLB row carrying no ``espn_id``) is not decoration.
``_get_espn_covered_sports()`` skips the whole sport's score fetch when every
recent ``scheduled``/``live`` row is anchored, so without that row this file
would seed its subjects, assert every verdict, and never execute a single line
of the code it exists to test — green, and vacuous.
:func:`test_the_pass_actually_reached_the_scores_loop` is the control that says
so out loud.

🔴 ``SUSPENDED_FUTURE`` is the other row that is here for a measured reason.
Every other seeded event is either settled (where the settled gate's answer is
unchanged) or unanchored (where the guard never fires), so deleting
``if event_status not in SETTLED_STATUSES_CLAIMING_A_RESULT`` — which would
freeze the score of every delayed game ESPN covers — passed this file 13/13
before that row existed. It is ``CLOSED_FUTURE``'s shape with one word changed,
so the pair isolates the gate.

WHAT WAS MEASURED ABOUT THESE ARMS
-----------------------------------
Seven mutants, run against this file on a real server; six killed, each by the
arm written for it: the refusal computed but not joined to ``_skip_score_write``,
the both-halves carve-out widened to ``and``, the payload judged instead of the
pair the row will hold, the ``espn_id`` requirement dropped, the settled gate
dropped, and the computed status passed where the effective one belongs.

The seventh — deleting the leading ``if home_score is None and away_score is
None: return False`` — SURVIVED, and it is an EQUIVALENT mutant rather than a
gap: with both payload halves ``None`` the effective pair is the stored pair, so
every remaining path returns ``False`` anyway. That line is ordering, not
behaviour. No arm is owed for it and none is written, because an arm that cannot
fail is the thing this file exists to avoid.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #7147 "
        "settled-final write gate (CI job `search-recall` provides one)"
    ),
)

SPORT_KEY = "baseball_mlb"
SPORT_ID = 993100
SPECIMEN_ESPN_ID = "401816966"

#: Ids in a range nothing else uses, so the cleanup is exact. See the fixture.
SPECIMEN = 993101
LANDING = 993102
HALF_FILLED = 993103
NO_ANCHOR = 993104
AGREEING = 993105
ONE_SIDED = 993106
UNMATCHED = 993107
ONE_SIDED_AGREEING = 993108
CLOSED_FUTURE = 993109
SUSPENDED_FUTURE = 993110


def _row(
    event_id,
    *,
    status,
    espn_id,
    stored,
    payload=None,
    expected,
    expects_snapshot=False,
    refused=False,
    hours_from_now=-4,
    end_status=None,
):
    """One seeded row and the verdict it is entitled to.

    ``payload`` of ``None`` means the provider sent no record for this event at
    all; a ``None`` INSIDE a payload pair means it sent an empty ``score``
    string for that side — which is how the one-sided specimen actually
    arrives, and is not the same thing as a zero.
    """
    return {
        "id": event_id,
        "status": status,
        "espn_id": espn_id,
        "stored": stored,
        "payload": payload,
        "expected": expected,
        "expects_snapshot": expects_snapshot,
        "refused": refused,
        "hours_from_now": hours_from_now,
        "end_status": end_status or status,
    }


SEED = [
    # ── THE SPECIMEN: settled, anchored, complete pair, conflicting write ──
    _row(
        SPECIMEN,
        status="completed",
        espn_id=SPECIMEN_ESPN_ID,
        stored=(7, 3),
        payload=(7, 2),
        expected=(7, 3),
        refused=True,
    ),
    # ── THE CARVE-OUT, KEPT INTACT: the write that LANDS a final ───────────
    # A settled anchored row holding no score is not stating a result yet.
    _row(
        LANDING,
        status="completed",
        espn_id="401816901",
        stored=(None, None),
        payload=(5, 1),
        expected=(5, 1),
        expects_snapshot=True,
    ),
    # One NULL half is still not a stated result. #7147 must let this through.
    _row(
        HALF_FILLED,
        status="completed",
        espn_id="401816902",
        stored=(4, None),
        payload=(4, 1),
        expected=(4, 1),
        expects_snapshot=True,
    ),
    # ── A ROW ESPN DOES NOT COVER: this feed is the only score writer ──────
    _row(
        NO_ANCHOR,
        status="completed",
        espn_id=None,
        stored=(7, 3),
        payload=(7, 2),
        expected=(7, 2),
        expects_snapshot=True,
    ),
    # ── AN AGREEING POLL: allowed, and must not spend a refusal ───────────
    _row(
        AGREEING,
        status="completed",
        espn_id="401816903",
        stored=(7, 3),
        payload=(7, 3),
        expected=(7, 3),
    ),
    # ── CERT-2963'S CORRECTION, BOTH DIRECTIONS ───────────────────────────
    # The provider sent only the away side. The payload alone looks harmless;
    # landing it on the stored 7 makes the row read 7-2. REFUSED.
    _row(
        ONE_SIDED,
        status="completed",
        espn_id="401816904",
        stored=(7, 3),
        payload=(None, 2),
        expected=(7, 3),
        refused=True,
    ),
    # 🔴 The other direction, and the only row that tells the two readings
    # apart. A one-sided payload that AGREES leaves the pair unchanged, so the
    # effective reading allows it; the payload reading sees ``(7, None) !=
    # (7, 3)`` and refuses. The ROW is 7-3 either way — the discriminator is
    # the counter, which is why it is asserted as a number and not as
    # "non-zero".
    _row(
        ONE_SIDED_AGREEING,
        status="completed",
        espn_id="401816905",
        stored=(7, 3),
        payload=(7, None),
        expected=(7, 3),
    ),
    # ── THE SECOND SETTLED WORD, REACHED THROUGH THE REAL CALL SITE ───────
    # `closed` is half of `SETTLED_STATUSES_CLAIMING_A_RESULT` and the writer
    # computes only "live" or "completed", so the only way this arm is reached
    # from production is the branch that leaves `event_status` None and falls
    # back to the row's OWN status: a provider record flagged `completed` whose
    # start is still in the future. #1981's 12-hour window admits it, and a
    # `closed` row is exactly the row with a result to protect.
    _row(
        CLOSED_FUTURE,
        status="closed",
        espn_id="401816906",
        stored=(7, 3),
        payload=(7, 2),
        expected=(7, 3),
        refused=True,
        hours_from_now=2,
    ),
    # ── 🔴 THE SETTLED GATE'S OWN CONTROL: unsettled, and the write LANDS ──
    # Byte-for-byte `CLOSED_FUTURE`'s shape — same anchored row, same stored
    # 7-3, same conflicting 7-2, same fall-back branch that leaves
    # `event_status` None — with one difference: the row says `suspended`, so
    # it is not CLAIMING a result. live/048 is explicit that a suspended row is
    # deliberately not refused ("it is not settled and carries no completion,
    # so the scores feed — rung 3 of the ladder — may promote it straight back
    # to live when play resumes"), and the #6056 deferral covers only `live`.
    # So this write must land, and a rain-delayed game whose score advances
    # while the row still reads `suspended` is the production case.
    #
    # It is the ONLY row that kills "drop the settled gate": every other seeded
    # row is either settled (where the guard's answer is unchanged) or
    # unanchored (where it never fires), so without this one that mutant passes
    # thirteen green assertions. Pairing it with `CLOSED_FUTURE` isolates the
    # gate itself — one status apart, opposite verdicts, same branch.
    _row(
        SUSPENDED_FUTURE,
        status="suspended",
        espn_id="401816907",
        stored=(7, 3),
        payload=(7, 2),
        expected=(7, 2),
        expects_snapshot=True,
        hours_from_now=2,
    ),
    # ── NOT A SUBJECT: the unanchored live row that keeps the sport in the
    #    scores loop at all. No payload is sent for it.
    _row(
        UNMATCHED,
        status="live",
        espn_id=None,
        stored=(None, None),
        expected=(None, None),
    ),
]

BY_ID = {row["id"]: row for row in SEED}
PAYLOAD_ROWS = [row for row in SEED if row["payload"] is not None]
SUBJECTS = [row["id"] for row in PAYLOAD_ROWS]
EXPECTED_REFUSALS = sum(1 for row in SEED if row["refused"])


def _external_id(event_id: int) -> str:
    return f"odds-7147-pg-{event_id}"


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema, function-scoped.

    The create/never-drop discipline and the reason for it are
    ``test_illegal_settled_tennis_score_recall_2772_pg``'s, unchanged: the CI
    database is SHARED across every step of the ``search-recall`` job, so
    ``drop_all`` over a subset raises on twelve foreign keys there while passing
    on a fresh local database, and ``create_all`` over the whole metadata fails
    on a developer's Postgres 14 over one ``NULLS NOT DISTINCT`` index. Create
    the tables this file needs with ``checkfirst``, drop nothing, and clean by
    id.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models import Event, ScoreSnapshot
    from app.services.database import Base

    tables = [
        Base.metadata.tables[name]
        for name in ("sports", "teams", "venues", "odds_snapshots")
    ] + [Event.__table__, ScoreSnapshot.__table__]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        await _clear(conn)
    yield engine
    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


async def _clear(conn):
    """Remove only this file's own rows, by id."""
    ids = [row["id"] for row in SEED]
    await conn.execute(
        text("DELETE FROM score_snapshots WHERE event_id = ANY(:ids)"), {"ids": ids}
    )
    await conn.execute(text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": ids})
    await conn.execute(text("DELETE FROM sports WHERE id = :i"), {"i": SPORT_ID})


async def _seed(conn, anchor):
    """Insert the sport and every seeded event. Returns the sport id in use.

    ``sports`` is reused when a sibling step already created ``baseball_mlb``,
    and otherwise created at a CHOSEN id — never ``RETURNING id`` and never
    ``ON CONFLICT (key)``. A sibling step seeds ``sports`` with explicit ids,
    which does not advance the serial, so letting the default fire raises
    ``UniqueViolationError`` on ``sports_pkey`` — a PRIMARY-key collision that
    an ``ON CONFLICT (key)`` clause does not cover and cannot.
    """
    existing = (
        await conn.execute(
            text("SELECT id FROM sports WHERE key = :k"), {"k": SPORT_KEY}
        )
    ).scalar_one_or_none()
    if existing is None:
        await conn.execute(
            text(
                "INSERT INTO sports (id, key, name, active) "
                "VALUES (:i, :k, :k, true)"
            ),
            {"i": SPORT_ID, "k": SPORT_KEY},
        )
        existing = SPORT_ID

    for row in SEED:
        stored_home, stored_away = row["stored"]
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, external_id, espn_id, "
                "home_team_name, away_team_name, commence_time, status, "
                "home_score, away_score) VALUES (:i, :s, :x, :e, :h, :a, :c, "
                ":st, :hs, :as_)"
            ),
            {
                "i": row["id"],
                "s": existing,
                "x": _external_id(row["id"]),
                "e": row["espn_id"],
                "h": "Boston Red Sox",
                "a": "Texas Rangers",
                "c": _commence(anchor, row),
                "st": row["status"],
                "hs": stored_home,
                "as_": stored_away,
            },
        )
    return existing


def _commence(anchor, row):
    """The row's own start, offset from the fixture's anchor.

    🔴 Offset FIRST and never truncate (gotcha #44): the anchor is a real
    ``now`` and every seeded time is a fixed delta from it, so no assertion in
    this file can branch on the wall clock or on which side of midnight the run
    lands.
    """
    return anchor + timedelta(hours=row["hours_from_now"])


def _score_payload(anchor):
    """The Odds API scores response, in the shape ``_poll_all_odds`` parses.

    A side the provider did not send is an EMPTY STRING, not an absent entry:
    that is the shape the one-sided specimen arrived in, and the parse treats
    ``""`` and a missing key the same way on purpose (a score of ``0`` is a
    score, so the emptiness test cannot be falsiness).

    ``commence_time`` is the ROW's own start, because #1981's
    ``external_id_currency`` compares the two and refuses anything it cannot
    verify — a payload that shared one clock for every row would be testing
    that guard by accident and this one not at all.
    """
    out = []
    for row in PAYLOAD_ROWS:
        payload_home, payload_away = row["payload"]
        out.append(
            {
                "id": _external_id(row["id"]),
                "commence_time": (
                    _commence(anchor, row).isoformat().replace("+00:00", "Z")
                ),
                "completed": True,
                "home_team": "Boston Red Sox",
                "away_team": "Texas Rangers",
                "scores": [
                    {
                        "name": "Boston Red Sox",
                        "score": "" if payload_home is None else str(payload_home),
                    },
                    {
                        "name": "Texas Rangers",
                        "score": "" if payload_away is None else str(payload_away),
                    },
                ],
            }
        )
    return out


class _FakeOddsAPIService:
    """Enough of ``OddsAPIService`` for one scores pass, and nothing more.

    ``last_requests_remaining`` is ``None`` deliberately: that is the branch
    that skips ``record_odds_api_quota``, which would reach for Redis. The odds
    half of the pass returns no events — this file is about the SCORES block,
    and an empty odds response is a state production reaches routinely.

    🔴 **The payload is answered for THIS sport only.** ``_poll_all_odds`` loops
    over every sport ``sports_needing_scores`` returns, and the CI database is
    SHARED with the other steps of the ``search-recall`` job — so a sibling step
    that leaves one ``scheduled`` row behind adds a second iteration. Answering
    every sport with the same records would then re-feed this file's own rows a
    second time (``_score_events_by_ext`` is keyed on ``external_id``, which is
    globally unique), and the refusal counter — asserted as an exact number —
    would read 6 for a correct guard. The sport a record belongs to is a
    property of the record, so the double answers per sport.
    """

    def __init__(self, payload, sport_key):
        self._payload = payload
        self._sport_key = sport_key
        self.last_requests_used = 0
        self.last_requests_remaining = None
        self.scores_calls = []

    async def get_odds(self, *args, **kwargs):
        return []

    async def get_scores(self, sport_key, **kwargs):
        self.scores_calls.append(sport_key)
        if sport_key != self._sport_key:
            return []
        return list(self._payload)

    async def close(self):
        return None


async def _run_one_pass(engine, monkeypatch, anchor):
    """Drive the real ``_poll_all_odds`` over a real session on ``engine``."""
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.tasks import odds_polling

    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _session():
        async with maker() as session:
            yield session

    service = _FakeOddsAPIService(_score_payload(anchor), SPORT_KEY)

    monkeypatch.setattr(odds_polling, "get_task_session", _session)
    monkeypatch.setattr(odds_polling, "OddsAPIService", lambda: service)
    # Quota is not this file's subject, and the real guard reads Redis.
    monkeypatch.setattr(
        odds_polling, "check_quota_guard", lambda *a, **k: (True, "ok_test")
    )
    # `r = None` is a real production state (Redis unreachable) and it is the
    # one that bypasses the two per-sport score-cadence skips, which are wall-
    # clock gates with nothing to do with the refusal under test.
    def _no_redis():
        raise RuntimeError("no redis in this gate")

    monkeypatch.setattr(odds_polling, "get_redis_client", _no_redis)

    # 🔴 NEUTRALISED FOR BLAST RADIUS, NOT FOR CONVENIENCE. The stale-event
    # closer is UNSCOPED — it sweeps every `live` row in the database — and the
    # CI database is shared with the other steps of the `search-recall` job. A
    # gate that suspends a sibling step's fixtures is a gate that reds another
    # lane's work. It runs AFTER the scores loop and writes nothing this file
    # asserts on.
    async def _no_stale_sweep(_session):
        return {"closed": 0, "suspended": 0}

    monkeypatch.setattr(
        odds_polling, "detect_and_close_stale_events", _no_stale_sweep
    )

    result = await odds_polling._poll_all_odds()
    return result, service


async def _rows(engine, ids):
    async with engine.begin() as conn:
        scores = {
            r.id: (r.home_score, r.away_score, r.status, r.espn_id)
            for r in (
                await conn.execute(
                    text(
                        "SELECT id, home_score, away_score, status, espn_id "
                        "FROM events WHERE id = ANY(:ids)"
                    ),
                    {"ids": ids},
                )
            ).all()
        }
        snaps = {}
        for r in (
            await conn.execute(
                text(
                    "SELECT event_id, home_score, away_score FROM score_snapshots "
                    "WHERE event_id = ANY(:ids)"
                ),
                {"ids": ids},
            )
        ).all():
            snaps.setdefault(r.event_id, []).append((r.home_score, r.away_score))
    return scores, snaps


@pytest.fixture
async def one_pass(pg_engine, monkeypatch):
    """Seed, run exactly one real pass, and read the tables back.

    One pass for every test in the file: the subject is what a pass DOES, and
    re-running it per test would let an assertion pass on the second pass's
    no-op (the specimen's row already holds 7-3, so a second pass would refuse
    it for free even with the guard removed).
    """
    anchor = datetime.now(timezone.utc)
    async with pg_engine.begin() as conn:
        await _seed(conn, anchor)
    result, service = await _run_one_pass(pg_engine, monkeypatch, anchor)
    ids = [row["id"] for row in SEED]
    scores, snaps = await _rows(pg_engine, ids)
    return {
        "result": result,
        "service": service,
        "scores": scores,
        "snapshots": snaps,
    }


@needs_postgres
@pytest.mark.asyncio
async def test_the_pass_actually_reached_the_scores_loop(one_pass):
    """The anti-vacuity control, and it is the whole reason the file is on PG.

    Two real SELECTs stand between a seeded row and the refusal:
    ``sports_needing_scores`` must return ``baseball_mlb``, and
    ``_get_espn_covered_sports()`` must NOT — the second only because
    ``UNMATCHED`` exists. If either moves, every other assertion in this file
    would still pass while executing none of the code it names.
    """
    service = one_pass["service"]
    assert SPORT_KEY in service.scores_calls, (
        "the scores loop never fetched this sport — every other assertion "
        f"below is then about rows nothing touched. Fetched: {service.scores_calls}"
    )
    # Membership, not equality: a sibling step's leftover row in another sport
    # adds an iteration that this file's double answers with `[]`, and failing
    # on it would red this gate for another lane's fixtures rather than for the
    # guard. What must hold is that OUR sport was reached.
    assert one_pass["result"].get("scores_updated", 0) >= len(PAYLOAD_ROWS)
    print(
        f"\n#7147 PG PASS scores_updated={one_pass['result'].get('scores_updated')} "
        f"refused={one_pass['result'].get('scores_refused_settled_repoison')} "
        f"of {len(PAYLOAD_ROWS)} payload rows; sports fetched="
        f"{service.scores_calls}"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_the_specimens_authoritative_final_is_still_on_the_row(one_pass):
    """CERT-3145's measurement, inverted: the row still reads ESPN's 7-3.

    On production the same write sequence left 7-2 behind within the hour.
    """
    assert one_pass["scores"][SPECIMEN][:2] == (7, 3)


@needs_postgres
@pytest.mark.asyncio
async def test_no_snapshot_row_records_the_score_the_pass_refused(one_pass):
    """``score_snapshots`` is the table the reversion was DIAGNOSED from, and
    the Score Differential chart reads it. A refusal that still left a row here
    would put a number on the chart the event row never held — and would make
    the next diagnosis blame the wrong writer."""
    assert one_pass["snapshots"].get(SPECIMEN, []) == []
    assert one_pass["snapshots"].get(ONE_SIDED, []) == []


@needs_postgres
@pytest.mark.asyncio
async def test_a_one_sided_payload_is_judged_on_the_pair_the_row_will_hold(one_pass):
    """CERT-2963's correction, executed. The provider sent ``away=2`` and no
    home side at all; the two score writes are INDEPENDENT statements, so
    letting it through would have stored 7-2 out of a payload that never
    mentioned 7."""
    assert one_pass["scores"][ONE_SIDED][:2] == (7, 3)


@needs_postgres
@pytest.mark.asyncio
async def test_the_status_half_of_the_write_is_never_withheld(one_pass):
    """A game that finished, finished. The refusal declines the SCORE and must
    leave the status alone — the same trade both sibling guards make, and the
    one that keeps a refusal from reading as a settled-means-settled bug."""
    for event_id in (SPECIMEN, ONE_SIDED):
        assert one_pass["scores"][event_id][2] == "completed"


@needs_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize("event_id", [LANDING, HALF_FILLED, NO_ANCHOR])
async def test_the_carve_out_still_lands_its_final_on_the_row(one_pass, event_id):
    """The three writes #7147 must NOT have cost. A settled row holding no
    score, a settled row holding one half, and a row ESPN does not cover: for
    all three this feed is the writer that lands the final, and a guard that
    took them would be a settled-means-settled regression of its own."""
    expected = BY_ID[event_id]["expected"]
    assert one_pass["scores"][event_id][:2] == expected
    assert one_pass["snapshots"].get(event_id, []) == [expected]


@needs_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize("event_id", [AGREEING, ONE_SIDED_AGREEING])
async def test_an_agreeing_poll_spends_no_refusal_and_writes_no_snapshot(
    one_pass, event_id
):
    """An agreeing write is a no-op, whether the provider sent both halves or
    one. Refusing it would make the counter unreadable — the counter is the
    only way to tell this guard holding from the population being empty — and
    snapshotting it would stamp a duplicate onto the chart every 300 seconds.

    ``ONE_SIDED_AGREEING`` is the row that distinguishes judging the PAIR THE
    ROW WILL HOLD from judging the payload, and it does so only through the
    counter: ``(7, None)`` differs from the stored ``(7, 3)`` while the pair
    the row ends up holding does not, so the row reads 7-3 under either
    reading and only the refusal count moves."""
    assert one_pass["scores"][event_id][:2] == (7, 3)
    assert one_pass["snapshots"].get(event_id, []) == []


@needs_postgres
@pytest.mark.asyncio
async def test_the_second_settled_word_is_reached_and_refused(one_pass):
    """``closed``, through the real call site rather than through a direct call.

    The writer computes ``"live"`` or ``"completed"`` and nothing else, so the
    other half of ``SETTLED_STATUSES_CLAIMING_A_RESULT`` is only ever reached
    by the fall-back arm — ``event_status`` left None by a provider record
    flagged complete whose start is still ahead, so the predicate is handed the
    ROW's own status. A unit call can pass ``"closed"`` in by hand; only a pass
    can show that the branch which does so exists.

    The status is asserted alongside the score because this row is the one
    where ``update_values`` ends up EMPTY: nothing is written at all, which is
    a different way to be correct from writing a status and declining a score.
    """
    assert one_pass["scores"][CLOSED_FUTURE][:2] == (7, 3)
    assert one_pass["scores"][CLOSED_FUTURE][2] == "closed"
    assert one_pass["snapshots"].get(CLOSED_FUTURE, []) == []


@needs_postgres
@pytest.mark.asyncio
async def test_an_unsettled_row_is_not_this_guards_business(one_pass):
    """🔴 The settled gate's control, and the only arm that can kill its removal.

    ``SUSPENDED_FUTURE`` reaches the predicate through the same fall-back branch
    as ``CLOSED_FUTURE`` — provider record flagged complete, start still ahead,
    ``event_status`` left None, so the row's OWN status is what is judged — and
    differs from it in that one word. A row that says ``suspended`` is not
    claiming a result: live/048 keeps the scores feed's promotion path open
    through exactly this row, and the #6056 deferral covers only ``live``. So
    the write lands, the snapshot is stamped, and the status is left for the
    ladder to move.

    Without this row every other seeded event is settled or unanchored, so
    deleting ``if event_status not in SETTLED_STATUSES_CLAIMING_A_RESULT`` —
    which would freeze the score of every delayed game ESPN covers — passes the
    rest of this file green. Measured: that mutant survived 13/13 before this
    arm existed.
    """
    assert one_pass["scores"][SUSPENDED_FUTURE][:2] == (7, 2)
    assert one_pass["scores"][SUSPENDED_FUTURE][2] == "suspended"
    assert one_pass["snapshots"].get(SUSPENDED_FUTURE, []) == [(7, 2)]


@needs_postgres
@pytest.mark.asyncio
async def test_the_counter_names_exactly_the_refusals_and_no_others(one_pass):
    """The returned stat is the production signal — "a long run of zeros on
    evenings with finished games is the reading to distrust" — so it is
    asserted as a number over a known fixture, never as "non-zero"."""
    assert (
        one_pass["result"]["scores_refused_settled_repoison"] == EXPECTED_REFUSALS
    )


@needs_postgres
@pytest.mark.asyncio
async def test_every_seeded_row_ended_where_its_own_verdict_says(one_pass):
    """The set comparison, stated once over the whole fixture, so a change that
    fixes one row by breaking another cannot pass the tests above one at a
    time. Status is in the tuple: a refusal that took the status with it would
    be a settled-means-settled regression that every score assertion above
    would sail past."""
    got = {
        row["id"]: one_pass["scores"][row["id"]][:3]
        for row in SEED
        if row["payload"] is not None
    }
    want = {
        row["id"]: (*row["expected"], row["end_status"])
        for row in SEED
        if row["payload"] is not None
    }
    assert got == want
