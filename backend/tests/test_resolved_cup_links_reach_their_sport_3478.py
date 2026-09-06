"""A cup tie that RESOLVED on the wrong sport still finds its own game (#3478).

CERT-2102 blocked the first half of #3478 on a real hole, and the hole is not the
one the cert text names. Arming eight cup-moneyline prefixes fixes matching for
rows that are still `open`. It does nothing for rows that already resolved while
linked to the wrong sport, because **nothing can reach them**:

* Phase 1.5 revalidates linked markets but `_phase15_eligible_where` requires
  `status == 'open'`;
* the historical backfill only ever selects UNLINKED rows.

A wrong link that survives to resolution is therefore permanent. Measured on
production 2026-09-06, across all eight armed prefixes:

    KXUECLGAME  resolved  baseball_other          11
    KXUECLGAME  resolved  americanfootball_other   3
    KXUELGAME   resolved  baseball_other           1     -> 15 wrong, all resolved
    KXUECLGAME  resolved  soccer_other             3
    KXUELGAME   resolved  soccer_other             1     -> 4 correct, must survive

THE PART BOTH THE CERT AND THE BLOCK GOT WRONG, and the reason this file exists
rather than a detach script: **the team names match exactly and the event is the
right game.** `KXUECLGAME-26JUL09CATLEV` "Caernarfon vs Levadia Tallinn" sits on
event 15169279 "Caernarfon v Levadia Tallinn" — filed under `baseball_other`.
These are not wrong-game links. They are TWINS: for each mis-filed event there is
a `soccer_other` event of the same fixture, e15169516 at 19:20:03 against
e15169279 at 19:20:35 — thirty-two seconds apart.

So "remove the cross-sport attachment" is the wrong remedy: unlinking would strip
fifteen markets off their own games and leave the user with less than they have
now. The right remedy is the one Phase 1.5 already implements — RELINK to the
soccer twin — and the only thing missing is that the row never gets offered to
it. Hence a selector, not a new actor.

These tests therefore pin the two halves that can each fail silently:
  1. the wrong row is REACHED and lands on its soccer twin, with a receipt;
  2. the correct `soccer_other` qualifier beside it is NOT swept (#3605 filed
     those under `soccer_other`, and a sweep that "fixed" them would be a
     regression wearing a fix's counters).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles


# `Event` carries Postgres JSONB/ARRAY columns sqlite cannot render as DDL.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


# The real production rows, 2026-09-06. Kept verbatim so this file keeps naming
# the thing it was written for rather than an invented specimen.
WRONG_TICKER = "KXUECLGAME-26JUL09CATLEV"
WRONG_NAME = "Caernarfon vs Levadia Tallinn"
CONTROL_TICKER = "KXUECLGAME-26JUL09PENFCC"
CONTROL_NAME = "Pen-y-Bont vs FC Coloma"
TIE_DATE = datetime(2026, 7, 9, 19, 20, tzinfo=timezone.utc)


class _AsyncShim:
    """Async surface over a real sync session (no aiosqlite in this sandbox).

    The statements executed are production's own; nothing is reimplemented.
    """

    def __init__(self, session):
        self._s = session

    async def execute(self, statement):
        return self._s.execute(statement)

    def add(self, obj):
        self._s.add(obj)

    async def commit(self):
        self._s.commit()

    async def flush(self):
        self._s.flush()


@pytest.fixture
def rail():
    """The four rows that matter, on a real engine.

    Returns a dict of ids plus the live session. The `soccer_other` twin is
    created BEFORE the `baseball_other` event so that "the relink found the
    twin" cannot be an artifact of insertion order being the same as id order.
    """
    from sqlalchemy import create_engine
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    from app.models.models import (
        Base, Event, FuturesMarket, Sport, WinProbSnapshot,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Sport.__table__, Event.__table__,
            FuturesMarket.__table__, WinProbSnapshot.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    soccer = Sport(key="soccer_other", name="Soccer (other)")
    baseball = Sport(key="baseball_other", name="Baseball (other)")
    session.add_all([soccer, baseball])
    session.flush()

    twin = Event(
        sport_id=soccer.id, home_team_name="Caernarfon",
        away_team_name="Levadia Tallinn",
        commence_time=TIE_DATE, status="closed",
    )
    control_event = Event(
        sport_id=soccer.id, home_team_name="Pen-y-Bont",
        away_team_name="FC Coloma",
        commence_time=TIE_DATE, status="closed",
    )
    misfiled = Event(
        sport_id=baseball.id, home_team_name="Caernarfon",
        away_team_name="Levadia Tallinn",
        commence_time=TIE_DATE + timedelta(seconds=32), status="closed",
    )
    session.add_all([twin, control_event, misfiled])
    session.flush()

    wrong = FuturesMarket(
        source="kalshi", external_id=WRONG_TICKER, name=WRONG_NAME,
        category="sports", status="resolved", event_id=misfiled.id,
        sport_id=baseball.id, llm_sport_category="baseball",
        commence_time=TIE_DATE,
    )
    control = FuturesMarket(
        source="kalshi", external_id=CONTROL_TICKER, name=CONTROL_NAME,
        category="sports", status="resolved", event_id=control_event.id,
        sport_id=soccer.id, llm_sport_category="soccer",
        commence_time=TIE_DATE,
    )
    session.add_all([wrong, control])
    session.commit()

    return {
        "session": session,
        "twin_id": twin.id,
        "misfiled_id": misfiled.id,
        "control_event_id": control_event.id,
        "wrong_market_id": wrong.id,
        "control_market_id": control.id,
    }


async def _run_phase15(session, now):
    """Run the ACTUAL entry point, with the caller's own stats shape."""
    from app.tasks import prediction_market_matching as task_mod

    stats = {
        "orphaned_snapshots_deleted": 0,
        "funnel": {"stale_relinked": 0, "mislink_fixed": 0},
    }
    link_changes = []
    await task_mod._phase15_revalidate(
        _AsyncShim(session), stats, now, lambda: 600.0, link_changes,
    )
    session.commit()
    return stats, link_changes


class TestTheSelectorReachesTheResolvedRow:
    """Half one: the row Phase 1.5 structurally cannot see."""

    def test_phase15_eligibility_still_excludes_the_resolved_row(self, rail):
        """The hole is real — executed, not read off the SQL text.

        Asserting on a rendered WHERE clause would pass on a comment. This runs
        Phase 1.5's own eligibility against the rail and shows the wrong row
        genuinely absent while an `open` row would be present.
        """
        from sqlalchemy import select

        from app.models.models import Event, FuturesMarket
        from app.tasks.prediction_market_matching import _phase15_eligible_where

        eligible = rail["session"].execute(
            select(FuturesMarket.id)
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(*_phase15_eligible_where())
        ).scalars().all()

        assert rail["wrong_market_id"] not in eligible, (
            "if Phase 1.5 can already see this row, the sweep is unnecessary — "
            "the premise of #3478's repair is that it cannot"
        )
        assert eligible == [], "both rail markets are resolved, so none qualify"

    def test_the_sweep_selects_the_resolved_wrong_row(self, rail):
        from app.tasks.prediction_market_matching import (
            _resolved_cross_sport_candidate_query,
        )

        rows = rail["session"].execute(
            _resolved_cross_sport_candidate_query()
        ).all()
        ids = {market.id for market, _event, _key in rows}
        assert rail["wrong_market_id"] in ids, (
            "the resolved cross-sport row must be selectable — this is the "
            "population Phase 1.5's status=='open' filter excludes"
        )

    def test_the_predicate_spares_a_soccer_other_qualifier(self):
        """`soccer_fa_cup` ticker on a `soccer_other` event is NOT cross-sport.

        This is the #3605 taxonomy gap, and it is the single discrimination that
        keeps the sweep from eating the four correct rows.
        """
        from app.tasks.prediction_market_matching import _is_cross_sport_link

        assert _is_cross_sport_link("soccer", "baseball_other") is True
        assert _is_cross_sport_link("soccer", "americanfootball_other") is True
        assert _is_cross_sport_link("soccer", "soccer_other") is False
        assert _is_cross_sport_link("soccer", "soccer_uefa_europa_league") is False
        # An absent side is never evidence of a mismatch.
        assert _is_cross_sport_link(None, "baseball_other") is False
        assert _is_cross_sport_link("soccer", None) is False

    def test_a_precise_cup_key_does_not_fight_the_unclassified_bucket(self):
        """The regression #3478 introduces if this carve-out is absent.

        `get_sport_prefix_from_ticker` returns a FULL key, so before the
        `_other` carve-out every correct cup row in the `soccer_other` bucket
        read as a cross-sport mislink the moment #3478 armed its prefix — 4
        resolved rows and 1 OPEN one on production.
        """
        from app.tasks.prediction_market_matching import _is_cross_sport_link

        ucl = "soccer_uefa_europa_conference_league"
        assert _is_cross_sport_link(ucl, "soccer_other") is False
        assert _is_cross_sport_link("soccer_fa_cup", "soccer_other") is False
        assert _is_cross_sport_link(ucl, "baseball_other") is True

    def test_the_forward_path_keeps_the_strict_reject(self):
        """The carve-out is opt-in, and the forward scorer must not opt in.

        Relaxing the wrong-sport reject when CREATING a link costs four
        adjudicated `no-event` golden pairs (`KXNCAAFGAME-26AUG27METOWS` and
        friends start matching `americanfootball_other` events two days off
        their ticker date, because the sport reject was the only thing refusing
        them). Breaking a link and making one are different questions; this pins
        that they keep different answers.
        """
        import inspect

        from app.tasks.prediction_market_matching import (
            _find_historical_event, _is_cross_sport_link, _score_candidates,
        )

        ncaaf, bucket = "americanfootball_ncaaf", "americanfootball_other"
        # The bare call answers the revalidation question — "is this link wrong
        # enough to BREAK?" — and the bucket is not.
        assert _is_cross_sport_link(ncaaf, bucket) is False
        assert _is_cross_sport_link(
            ncaaf, bucket, allow_unclassified_bucket=True
        ) is False
        # Forward path: strict. "Is this candidate right enough to CREATE?"
        assert _is_cross_sport_link(
            ncaaf, bucket, allow_unclassified_bucket=False
        ) is True

        for fn in (_score_candidates, _find_historical_event):
            default = inspect.signature(fn).parameters[
                "allow_unclassified_bucket"
            ].default
            assert default is False, (
                f"{fn.__name__} must default to the STRICT forward behaviour; "
                f"flipping this default silently relaxes every link the matcher "
                f"creates"
            )

    def test_a_genuine_same_family_mislink_is_still_caught(self):
        """The `_other` carve-out must not become "any soccer event will do".

        Two DIFFERENT precise keys remain a mislink; only the family's own
        unclassified bucket is spared.
        """
        from app.tasks.prediction_market_matching import _is_cross_sport_link

        assert _is_cross_sport_link(
            "americanfootball_nfl", "americanfootball_ncaaf"
        ) is True
        assert _is_cross_sport_link("soccer_epl", "soccer_serie_a") is True


class TestTheBehaviourEndToEnd:
    """Half two: run the real entry point and read what it did."""

    @pytest.mark.asyncio
    async def test_the_resolved_cup_market_lands_on_its_soccer_twin(self, rail):
        """Relink, not detach. Unlinking would strip it off its own game."""
        from app.models.models import FuturesMarket

        session = rail["session"]
        await _run_phase15(session, TIE_DATE + timedelta(hours=2))

        moved = session.get(FuturesMarket, rail["wrong_market_id"])
        session.refresh(moved)
        assert moved.event_id == rail["twin_id"], (
            f"expected the market to relink onto its soccer twin "
            f"{rail['twin_id']}, got {moved.event_id}. If this is None the "
            f"sweep DETACHED a correct pairing — strictly worse than the bug."
        )

    @pytest.mark.asyncio
    async def test_it_still_relinks_when_swept_months_later(self, rail):
        """THE PRODUCTION CLOCK. The rows are July ties; the sweep runs in September.

        `_find_matching_event` will only consider an event that is `scheduled`/
        `live` OR started within `MAX_PAST_GAME_DELTA` (6h) of `now`. Every twin
        here is `closed` and two months old, so under the real clock the twin is
        not a candidate at all — and a relink that finds nothing falls through to
        the UNLINK arm, which would strip fifteen markets off their own games.

        A version of this test that only ever runs `now = tie + 2h` passes while
        production does the opposite thing. That is the instrument that cannot
        see the failure it is meant to catch.
        """
        from app.models.models import FuturesMarket

        session = rail["session"]
        september = TIE_DATE + timedelta(days=59)
        await _run_phase15(session, september)

        moved = session.get(FuturesMarket, rail["wrong_market_id"])
        session.refresh(moved)
        assert moved.event_id is not None, (
            "swept two months after the tie, the relink found no candidate and "
            "the market was DETACHED from its own game — strictly worse than "
            "leaving the wrong link in place"
        )
        assert moved.event_id == rail["twin_id"]

    @pytest.mark.asyncio
    async def test_a_wrong_row_with_no_twin_is_left_alone_not_detached(self, rail):
        """`KXUECLGAME-26JUL16INTFKS` has no soccer twin on production.

        Three of the fifteen are like this — `americanfootball_other`, status
        `voided`, no soccer event of that fixture anywhere. The sweep must
        decline them. Detaching would trade a mis-filed link for NO link, and a
        resolved row is never re-offered by the forward path, so that loss is
        permanent.
        """
        from app.models.models import Event, FuturesMarket, Sport

        session = rail["session"]
        gridiron = Sport(key="americanfootball_other", name="AF (other)")
        session.add(gridiron)
        session.flush()
        orphan_event = Event(
            sport_id=gridiron.id, home_team_name="Inter Turku",
            away_team_name="Sarajevo",
            commence_time=datetime(2026, 7, 16, 16, 55, tzinfo=timezone.utc),
            status="voided",
        )
        session.add(orphan_event)
        session.flush()
        orphan = FuturesMarket(
            source="kalshi", external_id="KXUECLGAME-26JUL16INTFKS",
            name="Inter Turku vs Sarajevo", category="sports",
            status="resolved", event_id=orphan_event.id,
            sport_id=gridiron.id, llm_sport_category="americanfootball",
            commence_time=datetime(2026, 7, 16, 16, 55, tzinfo=timezone.utc),
        )
        session.add(orphan)
        session.commit()

        stats, _ = await _run_phase15(session, TIE_DATE + timedelta(days=59))

        session.refresh(orphan)
        assert orphan.event_id == orphan_event.id, (
            "no twin exists, so the only options are 'leave it' and 'destroy "
            "it'; the sweep must leave it"
        )
        assert stats["funnel"].get("resolved_cross_sport_left_alone", 0) >= 1, (
            "and it must SAY it declined — a silent no-op is indistinguishable "
            "from a sweep that never ran (gotcha #53)"
        )

    @pytest.mark.asyncio
    async def test_the_move_writes_a_receipt(self, rail):
        session = rail["session"]
        _stats, link_changes = await _run_phase15(
            session, TIE_DATE + timedelta(hours=2)
        )

        moved = [
            r for r in link_changes
            if getattr(r, "market_id", None) == rail["wrong_market_id"]
        ]
        assert moved, (
            "a link that MOVES must publish a receipt (LINKLOSS-02) — a silent "
            "relink is unauditable"
        )

    @pytest.mark.asyncio
    async def test_the_correct_qualifier_control_is_untouched(self, rail):
        """The regression this sweep could most easily become."""
        from app.models.models import FuturesMarket

        session = rail["session"]
        await _run_phase15(session, TIE_DATE + timedelta(hours=2))

        control = session.get(FuturesMarket, rail["control_market_id"])
        session.refresh(control)
        assert control.event_id == rail["control_event_id"], (
            "a resolved cup market already on a soccer event must not move; "
            "sweeping the #3605 qualifiers would be a regression wearing a "
            "fix's counters"
        )

    @pytest.mark.asyncio
    async def test_the_sweep_reports_what_it_scanned_and_selected(self, rail):
        """A zero-yield sweep must be legible, not silent (gotcha #53)."""
        session = rail["session"]
        stats, _ = await _run_phase15(session, TIE_DATE + timedelta(hours=2))

        funnel = stats["funnel"]
        assert funnel["phase15_resolved_cross_sport_scanned"] >= 2, (
            "both resolved cup rows are in the scanned population"
        )
        assert funnel["phase15_resolved_cross_sport_candidates"] == 1, (
            "exactly one of them is cross-sport; the qualifier control is not"
        )
