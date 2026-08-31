"""Q435 — every market on one Kalshi tennis match resolves to one event.

THE SPECIMEN, measured on production 2026-08-29 (US Open R128, Bublik v Wolf):

    KXATPMATCH-26AUG30BUBWOL       -> event 15293809  (odds_api,      15:00Z)
    KXATPSETWINNER-…BUBWOL-1/2/3   -> event 15295024  (kalshi_ticker, 00:00Z)
    KXATPEXACTMATCH-…BUBWOL        -> event 15295024
    KXATPGTOTAL-…BUBWOL-T22        -> (unlinked)

The draw register pins 15293809, so `/api/events/15293809/game-markets` returned
`other: 2` — the winner market twice — while the four props rendered on 15295024,
an event page with no route to it. The page was pointed at the wrong one of two
rows for one match.

Every ticker above carries Kalshi's OWN event segment `26AUG30BUBWOL`. These
tests pin the reconciliation to that segment and to nothing else: no name is
compared, no time window is opened, and no event row is absorbed into another
(ruling 048 arm A — a shared id, read from the provider, not guessed).
"""

import inspect
from datetime import datetime, timezone

import pytest
from sqlalchemy import update

from app.models.models import FuturesMarket
from app.tasks.prediction_market_matching import (
    _choose_segment_event,
    _match_prediction_markets,
    _reconcile_kalshi_match_segments,
)
from app.utils.prediction_market_matching import (
    is_kalshi_tennis_prop_ticker,
    kalshi_match_segment_key,
)

class _Matchup:
    def __init__(self, team_a, team_b):
        self.team_a = team_a
        self.team_b = team_b


class _Market:
    """The fields `_create_event_from_prediction_market` reads, and no others."""

    def __init__(self, external_id, source="kalshi"):
        self.source = source
        self.external_id = external_id
        self.name = "Alexander Bublik vs Jeffrey John Wolf"
        self.llm_sport_category = "tennis"
        self.commence_time = datetime(2026, 8, 30, tzinfo=timezone.utc)


BUBWOL_SIBLINGS = (
    "KXATPMATCH-26AUG30BUBWOL",
    "KXATPSETWINNER-26AUG30BUBWOL-1",
    "KXATPSETWINNER-26AUG30BUBWOL-2",
    "KXATPSETWINNER-26AUG30BUBWOL-3",
    "KXATPEXACTMATCH-26AUG30BUBWOL",
    "KXATPGTOTAL-26AUG30BUBWOL-T22",
    "KXATPGSPREAD-26AUG30BUBWOL",
)


# =============================================================================
# The segment key — the only thing that decides "same match"
# =============================================================================


class TestKalshiMatchSegmentKey:
    def test_every_bubwol_sibling_yields_one_key(self):
        keys = {kalshi_match_segment_key(t) for t in BUBWOL_SIBLINGS}
        assert keys == {"tennis_atp:26AUG30BUBWOL"}

    def test_wta_siblings_yield_one_key(self):
        keys = {
            kalshi_match_segment_key(t)
            for t in (
                "KXWTAMATCH-26AUG30SWIRYB",
                "KXWTASETWINNER-26AUG30SWIRYB-1",
                "KXWTAEXACTMATCH-26AUG30SWIRYB",
                "KXWTAGTOTAL-26AUG30SWIRYB-T20",
            )
        }
        assert keys == {"tennis_wta:26AUG30SWIRYB"}

    def test_tour_qualifies_the_segment(self):
        """An ATP and a WTA segment that share a token are NOT one match."""
        assert kalshi_match_segment_key(
            "KXATPMATCH-26AUG30ABCDEF"
        ) != kalshi_match_segment_key("KXWTAMATCH-26AUG30ABCDEF")

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXNBAGAME-26FEB20BOSGSW",        # another sport entirely
            "KXMLBGAME-26APR291840COLCIN",
            "KXATPGRANDSLAM-CALC26",          # a tennis FUTURE — no match segment
            "KXATPCOMPETE-26USOSIN",
            "",
            None,
        ],
    )
    def test_refuses_everything_that_is_not_a_tennis_match(self, ticker):
        assert kalshi_match_segment_key(ticker) is None

    def test_itf_is_not_in_the_set(self):
        """ITF is deliberately absent — unmeasured ticker shape (see the helper)."""
        from app.utils.prediction_market_matching import (
            _KALSHI_MATCH_SEGMENT_SPORT_KEYS,
        )

        assert not any(
            k.startswith("tennis_itf") for k in _KALSHI_MATCH_SEGMENT_SPORT_KEYS
        )


# =============================================================================
# The mapping gap — an ATP series with no WTA mirror IS the defect
# =============================================================================


class TestTennisTickerSymmetry:
    """Production census 2026-08-29, open Kalshi markets with a match segment:

        kxatpsetwinner   193 / 193 linked     kxwtasetwinner   121 /   0 linked
        kxatpexactmatch   72 /  72 linked     kxwtaexactmatch   52 /   0 linked
        kxatpgspread      54 /  54 linked     kxwtagtotal       56 /   0 linked
                                              kxatpgtotal       54 /   0 linked

    The identical ATP series link at 100%, so the WTA column is not a matching
    problem — those prefixes were simply absent from the map. That asymmetry is
    the class, and this is its guard.
    """

    def _map(self):
        from app.utils.sport_keys import KALSHI_TICKER_TO_SPORT_KEY

        return KALSHI_TICKER_TO_SPORT_KEY

    def test_every_atp_game_prefix_has_a_wta_mirror(self):
        m = self._map()
        missing = sorted(
            f"kxwta{k[len('kxatp'):]}"
            for k in m
            if k.startswith("kxatp")
            and f"kxwta{k[len('kxatp'):]}" not in m
        )
        assert missing == [], f"ATP prefixes with no WTA mirror: {missing}"

    def test_every_wta_game_prefix_has_an_atp_mirror(self):
        m = self._map()
        missing = sorted(
            f"kxatp{k[len('kxwta'):]}"
            for k in m
            if k.startswith("kxwta")
            and f"kxatp{k[len('kxwta'):]}" not in m
        )
        assert missing == [], f"WTA prefixes with no ATP mirror: {missing}"

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXWTASETWINNER-26AUG30SWIRYB-1",
            "KXWTAEXACTMATCH-26AUG30SWIRYB",
            "KXWTAGTOTAL-26AUG30SWIRYB-T20",
            "KXATPGTOTAL-26AUG30BUBWOL-T22",
            "KXATPCHALLENGERDOUBLES-26AUG30AAABBB",
        ],
    )
    def test_the_measured_unlinked_prefixes_are_now_game_tickers(self, ticker):
        """Each of these had 0 linked rows on 2026-08-29 while its ATP twin was
        at 100%. The game-level predicate is the gate that decides whether Phase 1
        even scans them.

        MIGRATED (Q462): this asserted against `is_kalshi_game_ticker`, the bare
        `startswith` predicate Q440 (#2231) deleted — a season market extending a
        game prefix read as a game under it. The replacement is
        `is_kalshi_game_level_ticker` (longest-prefix-wins), and this is a
        migration rather than a weakening: all five tickers are game-level under
        BOTH predicates, because `kxwta*`/`kxatp*` game prefixes are strictly
        longer than the `kxwta`/`kxatp` futures prefixes they extend. Q435's ship
        — every WTA prop reaching its own match — is unchanged by the
        consolidation, which is the thing this test now proves.
        """
        from app.utils.sport_keys import is_kalshi_game_level_ticker

        assert is_kalshi_game_level_ticker(ticker) is True

    def test_tour_prefixes_resolve_to_their_own_tour(self):
        from app.utils.sport_keys import get_sport_key_from_ticker

        assert get_sport_key_from_ticker("KXWTAGTOTAL-26AUG30SWIRYB-T20") == "tennis_wta"
        assert get_sport_key_from_ticker("KXATPGTOTAL-26AUG30BUBWOL-T22") == "tennis_atp"


# =============================================================================
# A prop may not invent the match it is a prop about
# =============================================================================


class TestTennisPropMayNotCreateAnEvent:
    @pytest.mark.parametrize(
        "ticker",
        [
            "KXATPSETWINNER-26AUG30BUBWOL-1",   # created event 15295024
            "KXATPEXACTMATCH-26AUG30BUBWOL",    # …and linked to it
            "KXATPGTOTAL-26AUG30BUBWOL-T22",
            "KXATPGSPREAD-26AUG30BUBWOL",
            "KXWTASETWINNER-26AUG30SWIRYB-1",
            "KXWTAGTOTAL-26AUG30SWIRYB-T20",
        ],
    )
    def test_props_are_refused(self, ticker):
        assert is_kalshi_tennis_prop_ticker(ticker) is True

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXATPMATCH-26AUG30BUBWOL",         # the match itself
            "KXWTAMATCH-26AUG30SWIRYB",
            "KXATPCHALLENGERMATCH-26AUG30AAABBB",
            "KXATPDOUBLES-26AUG30AAABBB",
            "KXWTADOUBLES-26AUG30AAABBB",
        ],
    )
    def test_match_winner_series_may_still_create(self, ticker):
        assert is_kalshi_tennis_prop_ticker(ticker) is False

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXNBAGAME-26FEB20BOSGSW",      # not tennis — untouched by this rule
            "KXNBASPREAD-26FEB20BOSGSW",
            "KXMLBGAME-26APR291840COLCIN",
            "KXATPGRANDSLAM-CALC26",        # a tennis FUTURE, not a match prop
            None,
            "",
        ],
    )
    def test_everything_else_is_untouched(self, ticker):
        assert is_kalshi_tennis_prop_ticker(ticker) is False

    @pytest.mark.asyncio
    async def test_auto_create_returns_none_for_a_prop_without_touching_the_db(
        self,
    ):
        """BEHAVIOURAL, not source-inspection. `session=None` is the assertion:
        the prop must be refused BEFORE anything reaches the registry, so a
        `None` session can never be dereferenced. A refusal that happened after
        `find_or_create_event` would already have written the twin."""
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        result = await _create_event_from_prediction_market(
            None,
            _Matchup("Alexander Bublik", "Jeffrey John Wolf"),
            _Market("KXATPSETWINNER-26AUG30BUBWOL-1"),
            datetime(2026, 8, 29, tzinfo=timezone.utc),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_the_match_winner_control_is_not_refused(self):
        """The control that makes the test above mean something: the SAME call
        with the match-winner ticker runs on past the refusal and only then
        fails on the `None` session. Without this, a function that returned
        `None` unconditionally would pass."""
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )

        with pytest.raises(AttributeError):
            await _create_event_from_prediction_market(
                None,
                _Matchup("Alexander Bublik", "Jeffrey John Wolf"),
                _Market("KXATPMATCH-26AUG30BUBWOL"),
                datetime(2026, 8, 29, tzinfo=timezone.utc),
            )


# =============================================================================
# The choice rule — which of two rows for one match survives
# =============================================================================


class TestChooseSegmentEvent:
    def test_single_candidate_wins(self):
        assert _choose_segment_event([7, 7, None], {7: "kalshi_ticker"}) == (7, "single")

    def test_no_candidate_is_not_an_anchor(self):
        assert _choose_segment_event([None, None], {}) == (None, "no_anchor")

    def test_schedule_derived_beats_ticker_derived(self):
        """THE SPECIMEN. odds_api 15293809 wins over the kalshi_ticker twin."""
        assert _choose_segment_event(
            [15293809, 15295024, None],
            {15293809: "odds_api", 15295024: "kalshi_ticker"},
        ) == (15293809, "schedule_derived")

    def test_schedule_derived_wins_regardless_of_row_order(self):
        """26AUG30YIBWAL is the SAME class pointing the other way: the WINNER
        market sat on the kalshi twin and the props on the odds_api event."""
        assert _choose_segment_event(
            [15294919, 15293803],
            {15294919: "kalshi_ticker", 15293803: "odds_api"},
        ) == (15293803, "schedule_derived")

    def test_two_ticker_derived_twins_are_refused(self):
        """26AUG30WONPAU: both rows are Kalshi auto-creates. Picking either
        would be a coin flip dressed as a reconciliation."""
        assert _choose_segment_event(
            [15295004, 15295025],
            {15295004: "kalshi_ticker", 15295025: "kalshi_ticker"},
        ) == (None, "ambiguous")

    def test_two_schedule_derived_events_are_refused(self):
        assert _choose_segment_event(
            [11, 22], {11: "odds_api", 22: "espn"},
        ) == (None, "ambiguous")

    def test_unknown_provenance_is_treated_as_ticker_derived(self):
        """A NULL commence_time_source asserts nothing, so it cannot win a
        contest against a row that names a real schedule."""
        assert _choose_segment_event(
            [11, 22], {11: None, 22: "odds_api"},
        ) == (22, "schedule_derived")

    def test_null_provenance_on_both_sides_is_refused(self):
        assert _choose_segment_event([11, 22], {11: None, 22: None}) == (
            None, "ambiguous",
        )


# =============================================================================
# The reconciliation itself, against a recording session
# =============================================================================


class _Row:
    def __init__(self, id, external_id, event_id):
        self.id = id
        self.external_id = external_id
        self.event_id = event_id


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Serves the two SELECTs the reconcile issues and records the UPDATEs."""

    def __init__(self, markets, provenance, sport_ids=None):
        self._markets = markets
        self._provenance = provenance
        self._sport_ids = sport_ids or {}
        self.updates = []
        self.commits = 0

    async def execute(self, stmt):
        if isinstance(stmt, type(update(FuturesMarket))):
            self.updates.append(stmt)
            return _Result([])
        text = str(stmt)
        if "futures_markets" in text:
            return _Result(self._markets)
        if "events" in text:
            return _Result([
                (eid, src, self._sport_ids.get(eid))
                for eid, src in self._provenance.items()
            ])
        raise AssertionError(f"unexpected statement: {text[:120]}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):  # pragma: no cover — only on the error path
        pass


def _applied(session):
    """{event_id: {market ids moved onto it}} from the recorded UPDATEs."""
    moves = {}
    for stmt in session.updates:
        values = dict(stmt._values)
        target = values[FuturesMarket.__table__.c.event_id].value
        ids = set(stmt.whereclause.right.value)
        moves.setdefault(target, set()).update(ids)
    return moves


@pytest.mark.asyncio
class TestReconcileKalshiMatchSegments:
    async def test_the_specimen_converges_onto_the_register_event(self):
        """RED BEFORE THE FIX: props stay on 15295024 and the page stays empty."""
        session = _FakeSession(
            markets=[
                _Row(59693746, "KXATPMATCH-26AUG30BUBWOL", 15293809),
                _Row(59705964, "KXATPSETWINNER-26AUG30BUBWOL-1", 15295024),
                _Row(59705963, "KXATPSETWINNER-26AUG30BUBWOL-2", 15295024),
                _Row(59705962, "KXATPSETWINNER-26AUG30BUBWOL-3", 15295024),
                _Row(59706135, "KXATPEXACTMATCH-26AUG30BUBWOL", 15295024),
                _Row(59706200, "KXATPGTOTAL-26AUG30BUBWOL-T22", None),
            ],
            provenance={15293809: "odds_api", 15295024: "kalshi_ticker"},
        )
        stats = await _reconcile_kalshi_match_segments(session)

        assert _applied(session) == {
            15293809: {59705964, 59705963, 59705962, 59706135, 59706200},
        }
        assert stats["converged"] == 4  # the four already on the twin
        assert stats["adopted"] == 1    # the game-total that had no event
        assert stats["ambiguous"] == 0

    async def test_orphans_adopt_their_segments_only_event(self):
        """The 254-market class: a linked sibling and unlinked props."""
        session = _FakeSession(
            markets=[
                _Row(1, "KXWTAMATCH-26AUG30SWIRYB", 900),
                _Row(2, "KXWTASETWINNER-26AUG30SWIRYB-1", None),
                _Row(3, "KXWTAEXACTMATCH-26AUG30SWIRYB", None),
                _Row(4, "KXWTAGTOTAL-26AUG30SWIRYB-T20", None),
            ],
            provenance={900: "kalshi_ticker"},
        )
        stats = await _reconcile_kalshi_match_segments(session)

        assert _applied(session) == {900: {2, 3, 4}}
        assert (stats["adopted"], stats["converged"]) == (3, 0)

    async def test_two_ticker_derived_twins_move_nothing(self):
        session = _FakeSession(
            markets=[
                _Row(1, "KXATPMATCH-26AUG30WONPAU", 15295004),
                _Row(2, "KXATPEXACTMATCH-26AUG30WONPAU", 15295025),
                _Row(3, "KXATPGTOTAL-26AUG30WONPAU-T22", None),
            ],
            provenance={15295004: "kalshi_ticker", 15295025: "kalshi_ticker"},
        )
        stats = await _reconcile_kalshi_match_segments(session)

        assert session.updates == []
        assert session.commits == 0
        assert stats["ambiguous"] == 1
        assert (stats["adopted"], stats["converged"]) == (0, 0)

    async def test_segment_with_no_linked_sibling_is_left_alone(self):
        session = _FakeSession(
            markets=[
                _Row(1, "KXWTASETWINNER-26SEP01AAABBB-1", None),
                _Row(2, "KXWTAGTOTAL-26SEP01AAABBB-T20", None),
            ],
            provenance={},
        )
        stats = await _reconcile_kalshi_match_segments(session)

        assert session.updates == []
        assert stats["no_anchor"] == 1

    async def test_idempotent_when_already_converged(self):
        session = _FakeSession(
            markets=[
                _Row(1, "KXATPMATCH-26AUG30BUBWOL", 15293809),
                _Row(2, "KXATPSETWINNER-26AUG30BUBWOL-1", 15293809),
            ],
            provenance={15293809: "odds_api"},
        )
        await _reconcile_kalshi_match_segments(session)

        assert session.updates == []
        assert session.commits == 0

    async def test_non_tennis_kalshi_rows_are_never_touched(self):
        """The prefix filter is a bound, not the rule — an NBA row that slipped
        through the SQL must still be refused by the segment key."""
        session = _FakeSession(
            markets=[
                _Row(1, "KXNBAGAME-26FEB20BOSGSW", 500),
                _Row(2, "KXNBASPREAD-26FEB20BOSGSW", None),
            ],
            provenance={500: "odds_api"},
        )
        stats = await _reconcile_kalshi_match_segments(session)

        assert session.updates == []
        assert stats["segments"] == 0

    async def test_writes_only_the_link_never_a_settlement(self):
        """gotcha #21 — the stored Kalshi settlements were always right; only
        the link was wrong. An UPDATE that touched them would be unrecoverable."""
        session = _FakeSession(
            markets=[
                _Row(1, "KXATPMATCH-26AUG30BUBWOL", 15293809),
                _Row(2, "KXATPSETWINNER-26AUG30BUBWOL-1", None),
            ],
            provenance={15293809: "odds_api"},
        )
        await _reconcile_kalshi_match_segments(session)

        assert len(session.updates) == 1
        written = {c.name for c in dict(session.updates[0]._values)}
        assert written == {"event_id"}
        assert "is_winner" not in written
        assert "calibration_probability" not in written
        assert "commence_time" not in written  # gotcha #14 — Kalshi's own close time stays

    async def test_the_reconcile_does_not_forge_a_poll_stamp(self):
        """#2024. `futures_markets.updated_at` is read by live consumers as
        "the poller ran" — `routes/playoffs.py` DROPS an outcome from the grid
        on a stale stamp. A link move observed no price and ran no poll, so
        stamping it would forge one. `tests/test_futures_stamp_semantics.py`
        reds on any new writer; this asserts the same thing from the other side,
        so the omission cannot be undone as a "fix" without both going red."""
        session = _FakeSession(
            markets=[
                _Row(1, "KXATPMATCH-26AUG30BUBWOL", 15293809),
                _Row(2, "KXATPSETWINNER-26AUG30BUBWOL-1", None),
            ],
            provenance={15293809: "odds_api"},
        )
        await _reconcile_kalshi_match_segments(session)

        written = {c.name for c in dict(session.updates[0]._values)}
        assert "updated_at" not in written
        assert "last_updated" not in written
        assert "volume_updated_at" not in written

    async def test_sport_id_rides_the_link_when_the_target_has_one(self):
        session = _FakeSession(
            markets=[
                _Row(1, "KXATPMATCH-26AUG30BUBWOL", 15293809),
                _Row(2, "KXATPSETWINNER-26AUG30BUBWOL-1", 15295024),
            ],
            provenance={15293809: "odds_api", 15295024: "kalshi_ticker"},
            sport_ids={15293809: 356611, 15295024: 105026},
        )
        await _reconcile_kalshi_match_segments(session)

        values = dict(session.updates[0]._values)
        written = {c.name: v.value for c, v in values.items() if hasattr(v, "value")}
        assert written["event_id"] == 15293809
        assert written["sport_id"] == 356611  # the twin's 105026 must not survive


# =============================================================================
# Wiring — an unreachable reconciliation reconciles nothing
# =============================================================================


class TestWiring:
    def test_reconcile_runs_inside_the_matching_task(self):
        assert "_reconcile_kalshi_match_segments(" in inspect.getsource(
            _match_prediction_markets
        )

    def test_the_scan_is_bounded(self):
        from app.tasks.prediction_market_matching import MAX_KALSHI_SEGMENT_ROWS

        src = inspect.getsource(_reconcile_kalshi_match_segments)
        assert "MAX_KALSHI_SEGMENT_ROWS" in src
        assert 0 < MAX_KALSHI_SEGMENT_ROWS <= 20000

    def test_the_segment_split_is_not_re_implemented_in_sql(self):
        """ONE definition of "same match". A second one in SQL is how the two
        drift, and a drifted duplicate-detector links the wrong match."""
        src = inspect.getsource(_reconcile_kalshi_match_segments)
        assert "kalshi_match_segment_key" in src
        assert "split_part" not in src
