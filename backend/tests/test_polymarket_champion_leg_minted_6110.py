"""#6110 — a settled field that lost its champion at ingest gets him back.

THE SPECIMEN, READ AT THE VENUE. Polymarket's Vuelta a España 2026 winner field
(Gamma event ``815313``, our market ``58675941``) closed on 09/14 with 71 legs:
70 named riders settled at ``outcomePrices[0] == 0`` and exactly ONE leg at
``1.0`` — ``groupItemTitle "Other"``, "Will any other rider win the 2026 Vuelta a
Espana?". Kalshi agrees and names him: ``KXCYCLING-26VLTA-EMAS`` settled
``result=yes``, 1 of 184 — Enric Mas Nicolau, who was not one of Polymarket's 30
named riders.

We stored 30 riders and no champion. The winning leg was filtered at ingest as a
reserved slot (#6110's forward fix), and then **no rail could put it back**:
Phase 3's negRisk branch walks the venue's sub-markets and ``UPDATE``\\s the
outcome whose ``condition_id`` matches, so a leg we never stored matched nothing
and was skipped in silence; ``clob_resolve`` re-grades rows that exist;
``_sync_polymarket_resolved_status`` only selects markets that are not yet
resolved. ``all_losers`` graded the whole field down and said so in the column —
"the winning outcome isn't in our DB" — and the page led with
"Tadej Pogacar RESOLVED" above a first row reading "Tadej Pogacar · Lost · 0%",
because the hero falls back to the top probability when nothing carries
``is_winner``.

WHAT THESE TESTS ARE. The executing ones drive the REAL
``_backfill_polymarket_winners_from_api`` against a reconstruction of that Gamma
payload and a recording session — not the helper in isolation, and not
``inspect.getsource``. The mint is one ``elif`` inside a loop five levels deep;
a source scan can prove the text is present and proves nothing about whether the
loop ever reaches it (gotcha #152, and the sibling file
``test_gamma_cursor_after_work_p086a`` says the same thing about the same
function).

The refusals are tested on the pure decision, where each one is a single fact,
and the two controls that matter most are executed end to end: **a field that
already crowns someone gains nothing**, and **a loser is never minted** — the
second is load-bearing, because a 71-leg event against 30 stored legs produces
41 zero-row updates on every single run and only one of them may ever become a
row.
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

import app.services.polymarket_api as poly_api_mod
import app.tasks.backfill_winners as bw
import app.tasks.redis_state as redis_state
from app.utils.polymarket_champion_mint import (
    MAX_NAME_LEN,
    MINTED,
    MIN_FIELD_LEGS,
    MINT_TERMINAL_PRICE,
    REFUSED_ALREADY_HELD,
    REFUSED_ANONYMOUS_SLOT,
    REFUSED_FIELD_HAS_WINNER,
    REFUSED_NAME_TOO_LONG,
    REFUSED_NOT_A_FIELD,
    REFUSED_NOT_CLOSED,
    REFUSED_NOT_TERMINAL,
    REFUSED_UNNAMED,
    is_anonymous_slot,
    mint_verdict,
    venue_has_closed_the_leg,
)

EVENT_ID = "815313"
MARKET_ID = 58675941
WINNER_CID = "0x7ea6d1b641377841e13d0a7e5b6fa5fc70692704b212f47ad616fd2a3de0d543"
WINNER_TITLE = "Other"
WINNER_QUESTION = "Will any other rider win the 2026 Vuelta a Espana?"

#: Three of the 30 rider legs we really hold, by their real condition ids.
STORED_RIDERS = [
    ("0x2ad7f15bff306142ee3559aaaa4df045a60bcb0f0bcc1860b60fcc27d90fe3f4",
     "Tadej Pogacar"),
    ("0x6190a11f8be1610b652c08b6e7774878f1572159c7cdc761f3236eac61c2f409",
     "Mads Pedersen"),
    ("0x58984d7d91cd4f88a4fa07ef797faf6f0e4049ebcb5375cf85349590659461ad",
     "Wout van Aert"),
]

#: A leg the venue carries and we never stored, settled at 0 — the shape that
#: outnumbers the champion 40:1 on this event and must never be minted.
UNHELD_LOSER_CID = "0x06756fcd16d0aaaa0000000000000000000000000000000000000000000000ab"


def _leg(condition_id, title, yes_price, *, question=None, closed=True):
    """One Gamma sub-market, in the venue's own wire shape.

    ``outcomePrices`` is a JSON-encoded STRING, which is how Gamma sends it —
    a list here would test a payload the venue does not produce. ``closed`` is a
    native JSON boolean, which is how Gamma sends THAT: measured over all 71
    legs of event 815313 on 2026-09-15, every one ``true``.
    """
    return {
        "conditionId": condition_id,
        "groupItemTitle": title,
        "question": question or f"Will {title} win the 2026 Vuelta a Espana?",
        "outcomePrices": json.dumps([f"{yes_price}", f"{1 - yes_price}"]),
        "closed": closed,
    }


def _vuelta_event(
    *, winner_title=WINNER_TITLE, winner_price=1.0, winner_closed=True
):
    return {
        "id": EVENT_ID,
        "title": "Vuelta a Espana 2026: Winner",
        "negRisk": True,
        "closed": True,
        "markets": (
            [_leg(cid, name, 0.0) for cid, name in STORED_RIDERS]
            + [_leg(UNHELD_LOSER_CID, "Brady Gilmore", 0.0)]
            + [_leg(WINNER_CID, winner_title, winner_price,
                    question=WINNER_QUESTION, closed=winner_closed)]
        ),
    }


class _Row:
    def __init__(self, id, external_id, group_type, poly_event_id):
        self.id = id
        self.external_id = external_id
        self.group_type = group_type
        self.poly_event_id = poly_event_id


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows


class _Shape:
    """What the mint's shape SELECT returns, with attribute access."""

    def __init__(self, legs, winners, held):
        self.legs = legs
        self.winners = winners
        self.held = held


class _ShapeResult:
    def __init__(self, shape):
        self._shape = shape

    def one(self):
        return self._shape


class _FakeRedis:
    def __init__(self, initial=None):
        self.store = dict(initial or {})

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = str(value)

    def delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0

    def sadd(self, key, *vals):
        return None

    def smembers(self, key):
        return set()

    def expire(self, key, ttl):
        return True


class _Recorder:
    """The database, reduced to what this rail can observe about it."""

    def __init__(self, stored_legs, *, stored_winner=False):
        # condition_id -> name, exactly the rows the market holds
        self.stored = dict(stored_legs)
        self.stored_winner = stored_winner
        self.inserts = []
        # The compiled statements beside the bound values: `func.now()` is a SQL
        # function, not a bind, so a params-only recorder cannot see the two
        # timestamp columns at all.
        self.insert_sql = []
        # (sql, binds) for every population SELECT the rail issued.
        self.selects = []

    @property
    def legs(self):
        return len(self.stored)

    @property
    def winners(self):
        return 1 if self.stored_winner else 0


OFFSET_KEY = "bainluck:pm_winner_backfill_offset"


def _install(monkeypatch, recorder, event_payload, *, universe=None, rc=None):
    """Drive the real Phase-3 rail against one event and one market.

    The fake SELECT honours the task's OWN binds — `last_id`, `limit` and, when
    the run is targeted, `target_ids` — so the selection semantics under test
    are the task's and not the double's.
    """
    rc = rc or _FakeRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: rc)
    rows = universe if universe is not None else [
        _Row(MARKET_ID, EVENT_ID, "negrisk", EVENT_ID)
    ]

    async def _execute(stmt, params=None):
        # A Core INSERT is the write under test; read it back off the statement
        # rather than off a string, so the assertion sees the values SQLAlchemy
        # would actually send.
        cls = type(stmt).__name__
        if cls == "Insert":
            recorder.inserts.append(dict(stmt.compile().params))
            recorder.insert_sql.append(str(stmt))
            return MagicMock(rowcount=1)
        if cls == "Update":
            bound = stmt.compile().params
            cid = bound.get("external_id_1")
            return MagicMock(rowcount=1 if cid in recorder.stored else 0)

        sql = str(getattr(stmt, "text", stmt))
        if "FROM futures_markets fm" in sql:
            p = params or {}
            recorder.selects.append((sql, dict(p)))
            picked = [r for r in rows if r.id > (p.get("last_id") or 0)]
            if "target_ids" in p:
                picked = [r for r in picked if r.id in set(p["target_ids"])]
            return _Result(picked[: (p.get("limit") or len(picked))])
        if "COUNT(*) FILTER (WHERE fo.is_winner)" in sql:
            cid = (params or {}).get("cid")
            return _ShapeResult(
                _Shape(recorder.legs, recorder.winners,
                       1 if cid in recorder.stored else 0)
            )
        # the price-sync UPDATE, which is a text() statement here
        if "UPDATE futures_outcomes" in sql:
            cid = (params or {}).get("cid")
            return MagicMock(rowcount=1 if cid in recorder.stored else 0)
        return MagicMock(rowcount=0)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())

    class _Service:
        def __init__(self, *a, **k):
            pass

        async def get_market_by_condition(self, cid):
            return None

        async def get_event_by_id(self, eid):
            return event_payload if str(eid) == EVENT_ID else None

        async def close(self):
            return None

    monkeypatch.setattr(poly_api_mod, "PolymarketAPIService", _Service)


# ---------------------------------------------------------------------------
# The specimen, executed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheVueltaGetsItsChampion:
    async def test_the_missing_winner_is_stored_once_with_the_venues_name(
        self, monkeypatch
    ):
        recorder = _Recorder(STORED_RIDERS)
        _install(monkeypatch, recorder, _vuelta_event())

        stats = await bw._backfill_polymarket_winners_from_api(limit=10)

        assert stats["champions_minted"] == 1, stats
        assert stats["champion_mint"].get(MINTED) == 1, stats["champion_mint"]
        assert len(recorder.inserts) == 1, recorder.inserts

        row = recorder.inserts[0]
        assert row["market_id"] == MARKET_ID
        assert row["external_id"] == WINNER_CID
        # The venue's own label, not a parse of the question — a champion under
        # a guessed name is worse on the page than one under none.
        assert row["name"] == WINNER_TITLE
        assert row["is_winner"] is True
        assert row["resolution_source"] == "api_settlement"

    async def test_the_minted_champion_carries_a_settled_price_not_a_quote(
        self, monkeypatch
    ):
        # #5246: a settlement writer writes the verdict AND the terminal price,
        # or it stores a number no poll can ever correct (the venue quotes
        # nothing on a finalized market).
        recorder = _Recorder(STORED_RIDERS)
        _install(monkeypatch, recorder, _vuelta_event())

        await bw._backfill_polymarket_winners_from_api(limit=10)

        row = recorder.inserts[0]
        assert float(row["current_probability"]) == 1.0
        assert row["current_american_odds"] is None
        # `price_changed_at` is `now()`, a SQL function rather than a bind, so
        # it is only visible in the compiled statement. Asserting on the bound
        # values alone would have passed with the column absent.
        sql = recorder.insert_sql[0]
        assert "price_changed_at" in sql, sql
        assert "last_updated" in sql, sql

    async def test_no_forecast_is_invented_for_a_leg_we_never_priced(
        self, monkeypatch
    ):
        # gotcha #144: the curve price is
        # COALESCE(calibration_probability, opening_probability). We hold no
        # forecast for a leg we never ingested, and writing the settlement into
        # either column would publish a point we never made.
        recorder = _Recorder(STORED_RIDERS)
        _install(monkeypatch, recorder, _vuelta_event())

        await bw._backfill_polymarket_winners_from_api(limit=10)

        row = recorder.inserts[0]
        assert "opening_probability" not in row or row["opening_probability"] is None
        assert (
            "calibration_probability" not in row
            or row["calibration_probability"] is None
        )

    async def test_a_loser_we_do_not_hold_is_never_minted(self, monkeypatch):
        # THE CONTROL THAT MATTERS. This event carries a leg we never stored and
        # the venue settled at 0 — on the real payload there are 40 of them
        # against one champion. Every run produces a zero-row update for each,
        # and only the winner may ever become a row.
        recorder = _Recorder(STORED_RIDERS)
        _install(monkeypatch, recorder, _vuelta_event())

        await bw._backfill_polymarket_winners_from_api(limit=10)

        assert [r["external_id"] for r in recorder.inserts] == [WINNER_CID]

    async def test_a_field_that_already_crowns_someone_gains_nothing(
        self, monkeypatch
    ):
        # A single-winner partition has exactly one champion; a second is the
        # two-winner corruption #999 was filed for, not a repair.
        recorder = _Recorder(STORED_RIDERS, stored_winner=True)
        _install(monkeypatch, recorder, _vuelta_event())

        stats = await bw._backfill_polymarket_winners_from_api(limit=10)

        assert recorder.inserts == []
        assert stats["champions_minted"] == 0
        assert stats["champion_mint"] == {REFUSED_FIELD_HAS_WINNER: 1}

    async def test_an_anonymous_reserved_slot_is_never_crowned(self, monkeypatch):
        # #953: Polymarket pre-creates "Player AD" slots. One settling at 1.0 is
        # the shape the ingest filter exists for, and it must not arrive here
        # through the back door.
        recorder = _Recorder(STORED_RIDERS)
        _install(monkeypatch, recorder, _vuelta_event(winner_title="Player AD"))

        stats = await bw._backfill_polymarket_winners_from_api(limit=10)

        assert recorder.inserts == []
        assert stats["champion_mint"] == {REFUSED_ANONYMOUS_SLOT: 1}

    async def test_a_run_that_mints_nothing_says_which_refusal_it_hit(
        self, monkeypatch
    ):
        # gotcha #53: "0 minted" must not be the same report for "no holes
        # found" and "found one and refused it".
        quiet = _Recorder(STORED_RIDERS + [(WINNER_CID, WINNER_TITLE)])
        _install(monkeypatch, quiet, _vuelta_event())

        stats = await bw._backfill_polymarket_winners_from_api(limit=10)

        assert stats["champions_minted"] == 0
        # Nothing was refused because nothing was a candidate: the leg is held,
        # so the UPDATE above the mint matched it and the mint was never asked.
        assert stats["champion_mint"] == {}
        assert stats["winners_set"] >= 1


# ---------------------------------------------------------------------------
# CERT-2893's counterexample: the defect, inverted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("open_price", [0.96, 1.0])
async def test_open_high_price_leg_is_never_minted_6110(monkeypatch, open_price):
    """An OPEN leg is a quote, however high, and a quote is never crowned.

    THE COUNTEREXAMPLE. CERT-2893 drove this same rail with an open child at
    0.96 and it was inserted with ``is_winner=True``: a runaway favourite made
    champion while the race was still being run. That is #6110 running
    backwards — the shipped defect lost a champion, this one invents one, and
    inventing is worse because no later rail contradicts a row that already
    says it won.

    Neither condition that reaches the mint is evidence of settlement. The
    ``is_winner`` gate above it is ``price >= 0.90``, and on an open leg the
    price is the market's opinion; the SELECT above THAT is our own
    ``futures_markets.status = 'resolved'``, which can be written from an
    elapsed resolution date with no winner behind it. Only Gamma's per-leg
    ``closed`` says the venue is finished, which is the same discriminator
    #6110's forward half is keyed on.

    1.0 is in the parameters on purpose: a reader may assume the terminal price
    makes the flag redundant, and an open leg at 1.0 is precisely the shape
    (fully-priced, untraded, not yet closed) that ``_is_placeholder_outcome``
    suppresses at ingest. If the price alone were enough, this arm would mint.
    """
    recorder = _Recorder(STORED_RIDERS)
    _install(
        monkeypatch,
        recorder,
        _vuelta_event(winner_price=open_price, winner_closed=False),
    )

    stats = await bw._backfill_polymarket_winners_from_api(limit=10)

    assert recorder.inserts == [], recorder.inserts
    assert stats["champions_minted"] == 0, stats
    # And it says WHY, rather than reporting a silent zero (gotcha #53).
    assert stats["champion_mint"] == {REFUSED_NOT_CLOSED: 1}, stats["champion_mint"]


@pytest.mark.asyncio
async def test_the_closed_vuelta_arm_still_mints_beside_that_control(monkeypatch):
    """The positive arm of the same test, on the same rig.

    A refusal rule proves nothing on its own: a mint function that refused
    everything would pass the control above. This is the specimen as the venue
    really sends it — measured 2026-09-15, all 71 legs of event 815313 carry
    ``closed: true`` as a native boolean and the winner is one of them — so the
    repair costs the ship nothing.
    """
    recorder = _Recorder(STORED_RIDERS)
    _install(monkeypatch, recorder, _vuelta_event())

    stats = await bw._backfill_polymarket_winners_from_api(limit=10)

    assert stats["champions_minted"] == 1, stats
    assert [r["external_id"] for r in recorder.inserts] == [WINNER_CID]


@pytest.mark.asyncio
async def test_a_leg_with_no_closed_flag_at_all_is_refused_not_assumed(monkeypatch):
    """Absence is not consent — and a payload can simply omit the field.

    Fail-closed is load-bearing for a CREATE specifically: a refusal is a
    counted fact a later run can revisit once the venue does close the leg,
    while a row wrongly minted is a champion nobody is looking for.
    """
    recorder = _Recorder(STORED_RIDERS)
    event = _vuelta_event()
    event["markets"][-1].pop("closed")
    _install(monkeypatch, recorder, event)

    stats = await bw._backfill_polymarket_winners_from_api(limit=10)

    assert recorder.inserts == []
    assert stats["champion_mint"] == {REFUSED_NOT_CLOSED: 1}


# ---------------------------------------------------------------------------
# Reaching the named row — the targeted form
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestATargetedRepairReachesTheRowWithoutMovingTheSweep:
    """Why targeting exists at all.

    The scheduled form is cursor-paced over 353,473 eligible rows ascending by
    id (measured on production 2026-09-15), and the Vuelta market sits 281,813
    rows in. The Settled Sentinel files ONE market id; "wait for the cursor" is
    not a repair for it. These pin the two properties that make a targeted run
    safe to hand anyone: it selects only what it was given, and it leaves the
    sweep's cursor exactly where it found it.
    """

    UNIVERSE = [
        _Row(10, "10", "negrisk", "10"),
        _Row(MARKET_ID, EVENT_ID, "negrisk", EVENT_ID),
        _Row(99_000_000, "99000000", "negrisk", "99000000"),
    ]

    async def test_only_the_named_market_is_selected(self, monkeypatch):
        recorder = _Recorder(STORED_RIDERS)
        _install(monkeypatch, recorder, _vuelta_event(), universe=self.UNIVERSE)

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=10, market_ids=[MARKET_ID]
        )

        sql, binds = recorder.selects[0]
        assert "AND fm.id = ANY(:target_ids)" in sql
        assert binds["target_ids"] == [MARKET_ID]
        # The two other eligible rows were never fetched from the venue.
        assert stats["markets_checked"] == 1, stats
        assert stats["champions_minted"] == 1

    async def test_a_targeted_run_leaves_the_sweeps_cursor_alone(self, monkeypatch):
        # CAL-P086A's lesson through a new door: a targeted run that advanced
        # the shared cursor would skip every row between it and the target.
        rc = _FakeRedis({OFFSET_KEY: "4242"})
        recorder = _Recorder(STORED_RIDERS)
        _install(
            monkeypatch, recorder, _vuelta_event(),
            universe=self.UNIVERSE, rc=rc,
        )

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=10, market_ids=[MARKET_ID]
        )

        assert rc.store[OFFSET_KEY] == "4242"
        assert stats["cursor_op"] == "skipped_targeted"
        # And it ignored the cursor on the way IN, or a target below it would be
        # unreachable — which is the whole point on a row 281,813 deep.
        assert recorder.selects[0][1]["last_id"] == 0

    async def test_a_targeted_run_that_matches_nothing_does_not_reset_the_sweep(
        self, monkeypatch
    ):
        # The untargeted `if not markets` branch DELETES the cursor to wrap.
        # Reaching it from a targeted miss would restart a 353k-row drain.
        rc = _FakeRedis({OFFSET_KEY: "4242"})
        recorder = _Recorder(STORED_RIDERS)
        _install(
            monkeypatch, recorder, _vuelta_event(),
            universe=self.UNIVERSE, rc=rc,
        )

        stats = await bw._backfill_polymarket_winners_from_api(
            limit=10, market_ids=[123_456_789]
        )

        assert rc.store[OFFSET_KEY] == "4242"
        assert stats.get("targeted_no_match") is True
        assert recorder.inserts == []

    async def test_the_scheduled_form_is_untouched(self, monkeypatch):
        # No target clause, no target bind, and the cursor decision still runs.
        rc = _FakeRedis()
        recorder = _Recorder(STORED_RIDERS)
        _install(
            monkeypatch, recorder, _vuelta_event(),
            universe=self.UNIVERSE, rc=rc,
        )

        stats = await bw._backfill_polymarket_winners_from_api(limit=10)

        sql, binds = recorder.selects[0]
        assert "target_ids" not in sql
        assert "target_ids" not in binds
        assert stats["cursor_op"] in ("set", "delete")

    async def test_the_target_list_is_capped(self, monkeypatch):
        recorder = _Recorder(STORED_RIDERS)
        _install(monkeypatch, recorder, _vuelta_event(), universe=self.UNIVERSE)

        await bw._backfill_polymarket_winners_from_api(
            limit=10, market_ids=list(range(1, bw._TARGETED_MARKET_CAP + 50))
        )

        assert len(recorder.selects[0][1]["target_ids"]) == bw._TARGETED_MARKET_CAP


# ---------------------------------------------------------------------------
# The decision, in isolation — one fact per test
# ---------------------------------------------------------------------------


class TestMintVerdict:
    def _ask(self, **over):
        kwargs = dict(
            venue_closed=True,
            price=1.0,
            group_item_title=WINNER_TITLE,
            question=WINNER_QUESTION,
            stored_legs=30,
            stored_winners=0,
            leg_already_held=False,
        )
        kwargs.update(over)
        return mint_verdict(**kwargs)

    def test_the_specimen_mints_under_the_venues_own_name(self):
        assert self._ask() == (MINTED, WINNER_TITLE)

    def test_a_held_leg_belongs_to_the_update_above_us(self):
        assert self._ask(leg_already_held=True) == (REFUSED_ALREADY_HELD, None)

    def test_an_open_leg_is_refused_whatever_it_is_quoted_at(self):
        assert self._ask(venue_closed=False, price=0.96)[0] == REFUSED_NOT_CLOSED
        assert self._ask(venue_closed=False, price=1.0)[0] == REFUSED_NOT_CLOSED

    def test_the_closed_test_runs_before_the_price_test(self):
        # An open leg at 0.5 fails both. It must be reported as the venue not
        # having finished, not as a threshold miss — the two send a reader after
        # very different things, and only one of them will ever resolve itself.
        assert self._ask(venue_closed=None, price=0.5)[0] == REFUSED_NOT_CLOSED

    def test_a_held_leg_is_still_the_callers_row_even_when_open(self):
        assert self._ask(leg_already_held=True, venue_closed=False) == (
            REFUSED_ALREADY_HELD,
            None,
        )

    def test_the_flag_is_required_so_a_new_call_site_cannot_omit_it(self):
        # A default would let the CERT-2893 defect be re-inherited by silence:
        # "the caller forgot" and "the venue settled it" would arrive as one
        # argument.
        kwargs = dict(
            price=1.0,
            group_item_title=WINNER_TITLE,
            question=WINNER_QUESTION,
            stored_legs=30,
            stored_winners=0,
            leg_already_held=False,
        )
        with pytest.raises(TypeError):
            mint_verdict(**kwargs)

    def test_a_price_below_the_mint_threshold_is_refused(self):
        # Grading uses 0.90 and creation uses 0.95: a row that does not exist
        # has no ingest history behind it, so it needs the venue's terminal
        # price and not merely a high one.
        assert self._ask(price=0.94)[0] == REFUSED_NOT_TERMINAL
        assert self._ask(price=MINT_TERMINAL_PRICE)[0] == MINTED

    def test_a_missing_price_is_refused_rather_than_read_as_zero(self):
        assert self._ask(price=None)[0] == REFUSED_NOT_TERMINAL

    def test_an_unnamed_leg_is_refused_rather_than_parsed(self):
        assert self._ask(group_item_title=None)[0] == REFUSED_UNNAMED
        assert self._ask(group_item_title="   ")[0] == REFUSED_UNNAMED

    def test_a_name_longer_than_the_column_is_refused_not_truncated(self):
        # A DataError raised here costs the batch its other 200 events
        # (gotcha #42); a refusal is one counted fact.
        assert self._ask(group_item_title="x" * (MAX_NAME_LEN + 1))[0] == (
            REFUSED_NAME_TOO_LONG
        )
        assert self._ask(group_item_title="x" * MAX_NAME_LEN)[0] == MINTED

    def test_a_market_with_a_winner_is_refused(self):
        assert self._ask(stored_winners=1)[0] == REFUSED_FIELD_HAS_WINNER

    def test_a_market_too_small_to_be_a_field_is_refused(self):
        assert self._ask(stored_legs=MIN_FIELD_LEGS - 1)[0] == REFUSED_NOT_A_FIELD
        assert self._ask(stored_legs=MIN_FIELD_LEGS)[0] == MINTED

    def test_the_held_test_runs_before_every_other(self):
        # A leg we already hold is the caller's row whatever else is true of it;
        # reporting it as "not a field" or "anonymous" would send the reader
        # after the wrong thing.
        assert self._ask(
            leg_already_held=True,
            venue_closed=False,
            price=None,
            group_item_title=None,
            stored_legs=0,
            stored_winners=9,
        ) == (REFUSED_ALREADY_HELD, None)


class TestTheVenueClosedFlagIsReadStrictly:
    """A CREATE may not be authorised by a value we had to interpret.

    Gamma sends a native boolean here (all 71 legs of event 815313, measured
    2026-09-15). The string arm exists because the same field is a string on
    Gamma's query side — ``polymarket_api`` writes ``params["closed"] =
    str(closed).lower()`` — so a caller reading it back off a filtered response
    is foreseeable rather than hypothetical.
    """

    def test_the_venues_own_boolean_is_accepted(self):
        assert venue_has_closed_the_leg(True) is True

    def test_the_string_form_gamma_uses_on_the_query_side_is_accepted(self):
        assert venue_has_closed_the_leg("true") is True
        assert venue_has_closed_the_leg(" True ") is True

    def test_the_string_false_is_not_truthy_here(self):
        # The whole reason this is a function and not `bool(closed)`: a
        # truthiness test reads "false" as closed, which would crown a leg the
        # venue explicitly says is open.
        assert venue_has_closed_the_leg("false") is False

    @pytest.mark.parametrize(
        "value", [None, False, 0, 1, "", "yes", "closed", [], {}, object()]
    )
    def test_everything_else_refuses_without_guessing(self, value):
        assert venue_has_closed_the_leg(value) is False


# ---------------------------------------------------------------------------
# Anti-drift: two copies of one rule
# ---------------------------------------------------------------------------


class TestTheSlotPatternsDoNotDrift:
    """`is_anonymous_slot` carries the ingest filter's patterns verbatim.

    They are a copy — the ingest filter takes a parsed DTO and this takes two
    strings — so the only thing that can stop them becoming two opinions is a
    test that asks both the same questions. A shared corpus, and both must
    answer identically on every item.
    """

    CORPUS = [
        # (group_item_title, question)
        ("Player A", "Will Player A win?"),
        ("Player AD", "Will Player AD win?"),
        ("Player ZZZ", "Will Player ZZZ win?"),
        ("Other", WINNER_QUESTION),
        ("Enric Mas Nicolau", "Will Enric Mas Nicolau win?"),
        ("Tadej Pogacar", "Will Tadej Pogacar win the 2026 Vuelta a Espana?"),
        # A real name that merely CONTAINS the word, and a lowercase suffix that
        # must not match the anchored pattern.
        ("Player One", "Will Player One win?"),
        ("player ad", "Will player ad win?"),
        (None, "Will Player Q be named?"),
        (None, "Will the field be expanded?"),
        ("", ""),
    ]

    def test_both_copies_agree_on_every_item(self):
        from app.tasks.polymarket import _is_placeholder_outcome

        class _DTO:
            """Only the two fields the NAME half of the filter reads.

            The price half is deliberately given a shape it cannot fire on
            (no prices, so the last heuristic short-circuits), because the
            question here is whether the two NAME rules agree.
            """

            def __init__(self, title, question):
                self.group_item_title = title
                self.question = question
                self.outcome_prices = []
                self.best_bid = None
                self.last_trade_price = None
                self.closed = False

        for title, question in self.CORPUS:
            mine = is_anonymous_slot(title, question)
            theirs = _is_placeholder_outcome(_DTO(title, question))
            assert mine == theirs, (
                f"the two copies disagree on {title!r} / {question!r}: "
                f"is_anonymous_slot={mine}, _is_placeholder_outcome={theirs}"
            )

    def test_the_corpus_exercises_both_answers(self):
        # A positive control on the agreement test: a corpus that is all-True or
        # all-False proves agreement vacuously.
        answers = {is_anonymous_slot(t, q) for t, q in self.CORPUS}
        assert answers == {True, False}
