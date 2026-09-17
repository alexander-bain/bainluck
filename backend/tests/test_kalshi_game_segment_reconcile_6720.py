"""#6720 — a fixture page serves every Kalshi market the venue priced for it.

Kalshi prices one game through several of its own events, one per series, all
carrying the same segment in the ticker. When some of those markets land on the
real, provider-anchored event and the rest land on an id-less auto-create of the
same game, the reader opens the fixture and sees a fraction of the board.

THE CONTROL IS THE SAME FIXTURE SPLIT IN HALF, measured on production
2026-09-17 (`/events/15297802`, SC Freiburg v Borussia Monchengladbach):

    KXBUNDESLIGASCORE-26SEP12SCFBMG   -> 15297802  espn, espn_id=401884796   (3)
    KXBUNDESLIGATOTAL-26SEP12SCFBMG   -> 15307870  kalshi, NO ids           (12)
    KXBUNDESLIGASPREAD-26SEP12SCFBMG  -> 15307870
    KXBUNDESLIGABTTS-26SEP12SCFBMG    -> 15307870

The page rendered a full "Additional Markets" section for the 3 and was missing
the 12 from that same frame, so the renderer was never the problem — only the
attachment was. `26SEP12SCFBMG` is identical across both rows: a shared provider
id on the candidate, which is what gotcha #32 requires before a drain, so this
re-points markets and absorbs no event into another (ruling 048 is untouched).

The population, all sports, 14-day window, measured the same day: 68 fixtures
holding 174 Kalshi markets on an id-less twin — MLB 56, NFL 40, soccer 45,
tennis 19, UFC 7.

Q435 already built this reconciliation for tennis. #6720 is two changes, and
EITHER ALONE IS INERT:

  1. the population (`KXATP%`/`KXWTA%` -> the measured sports), and
  2. the discriminator, which asked `commence_time_source != 'kalshi_ticker'`
     while only 1,199 of ~84,000 id-less events still carried that string.

`TestTheDiscriminatorWasTheInertHalf` is the guard for (2) and is the one that
fails if anyone re-grounds the choice on a provenance string.
"""

import pytest
from sqlalchemy import update

from app.models.models import FuturesMarket
from app.tasks.prediction_market_matching import (
    _KALSHI_SEGMENT_TICKER_PREFIXES,
    _choose_segment_event,
    _reconcile_kalshi_match_segments,
)
from app.utils.prediction_market_matching import (
    is_kalshi_match_segment_ticker,
    is_kalshi_tennis_prop_ticker,
    kalshi_game_segment_key,
    kalshi_match_segment_key,
)


# The four worked specimens, verbatim from production 2026-09-17. Each is
# (segment, anchored event id, id-less event id, id-less provenance, tickers).
FREIBURG_STRANDED = (
    "KXBUNDESLIGA1H-26SEP12SCFBMG",
    "KXBUNDESLIGA1HBTTS-26SEP12SCFBMG",
    "KXBUNDESLIGA1HSPREAD-26SEP12SCFBMG",
    "KXBUNDESLIGA1HTOTAL-26SEP12SCFBMG",
    "KXBUNDESLIGA2H-26SEP12SCFBMG",
    "KXBUNDESLIGA2HBTTS-26SEP12SCFBMG",
    "KXBUNDESLIGA2HSPREAD-26SEP12SCFBMG",
    "KXBUNDESLIGA2HTOTAL-26SEP12SCFBMG",
    "KXBUNDESLIGABTTS-26SEP12SCFBMG",
    "KXBUNDESLIGASPREAD-26SEP12SCFBMG",
    "KXBUNDESLIGATEAMTOTAL-26SEP12SCFBMG",
    "KXBUNDESLIGATOTAL-26SEP12SCFBMG",
)
FREIBURG_ON_THE_REAL_ROW = (
    "KXBUNDESLIGASCORE-26SEP12SCFBMG",
    "KXBUNDESLIGAFTTS-26SEP12SCFBMG",
)


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
    def __init__(self, markets, provenance, anchored, sport_ids=None):
        self._markets = markets
        self._provenance = provenance
        self._anchored = set(anchored)
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
                (
                    eid, src, self._sport_ids.get(eid),
                    f"espn-{eid}" if eid in self._anchored else None,
                    None,
                )
                for eid, src in self._provenance.items()
            ])
        raise AssertionError(f"unexpected statement: {text[:120]}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):  # pragma: no cover — error path only
        pass


def _applied(session):
    moves = {}
    for stmt in session.updates:
        values = dict(stmt._values)
        target = values[FuturesMarket.__table__.c.event_id].value
        ids = set(stmt.whereclause.right.value)
        moves.setdefault(target, set()).update(ids)
    return moves


# =============================================================================
# The segment key, widened
# =============================================================================


class TestKalshiGameSegmentKey:
    def test_every_freiburg_ticker_yields_one_key(self):
        keys = {
            kalshi_game_segment_key(t)
            for t in FREIBURG_STRANDED + FREIBURG_ON_THE_REAL_ROW
        }
        assert keys == {"soccer_germany_bundesliga:26SEP12SCFBMG"}

    @pytest.mark.parametrize("tickers,expected", [
        (("KXNFL1Q-26SEP13NODET", "KXNFLGAME-26SEP13NODET",
          "KXNFL4Q-26SEP13NODET"), "americanfootball_nfl:26SEP13NODET"),
        (("KXMLBGAME-26SEP061335BOSBAL", "KXMLBSPREAD-26SEP061335BOSBAL",
          "KXMLBTOTAL-26SEP061335BOSBAL"), "baseball_mlb:26SEP061335BOSBAL"),
        (("KXUFCMOV-26SEP12ALDTAR", "KXUFCROUNDS-26SEP12ALDTAR"),
         "mma_mixed_martial_arts:26SEP12ALDTAR"),
        (("KXLALIGAGAME-26SEP16LEVATH", "KXLALIGATOTAL-26SEP16LEVATH"),
         "soccer_spain_la_liga:26SEP16LEVATH"),
    ])
    def test_each_measured_sport_collapses_to_one_key(self, tickers, expected):
        assert {kalshi_game_segment_key(t) for t in tickers} == {expected}

    def test_the_series_the_ticker_map_does_not_list_still_resolve(self):
        """KXBUNDESLIGASCORE and KXMLBERA are absent from
        KALSHI_TICKER_TO_SPORT_KEY and reach their sport through the PREFIX
        FALLBACK. They are exactly the stranded rows, so a series-exact
        population filter would have missed the defect entirely."""
        from app.utils.sport_keys import KALSHI_TICKER_TO_SPORT_KEY

        for series, ticker in (
            ("kxbundesligascore", "KXBUNDESLIGASCORE-26SEP12SCFBMG"),
            ("kxmlbera", "KXMLBERA-26SEP082145STLSF"),
        ):
            assert series not in KALSHI_TICKER_TO_SPORT_KEY
            assert kalshi_game_segment_key(ticker) is not None

    def test_tennis_answers_are_delegated_and_unchanged(self):
        for t in ("KXATPMATCH-26AUG30BUBWOL",
                  "KXWTAGTOTAL-26AUG30SWIRYB-T20"):
            assert kalshi_game_segment_key(t) == kalshi_match_segment_key(t)

    @pytest.mark.parametrize("ticker", [
        "KXNBAGAME-26FEB20BOSGSW",      # a sport outside the measured set
        "KXNHLGAME-26FEB20BOSTOR",
        "KXATPGRANDSLAM-CALC26",        # a future, no game segment
        "KXBUNDESLIGAWINNER-CALC26",    # a soccer FUTURE, likewise
        "",
        None,
    ])
    def test_refuses_everything_outside_the_measured_population(self, ticker):
        assert kalshi_game_segment_key(ticker) is None

    def test_the_sport_is_part_of_the_key(self):
        """Two sports sharing a segment token are not one game."""
        assert (kalshi_game_segment_key("KXNFLGAME-26SEP13ABCDEF")
                != kalshi_game_segment_key("KXMLBGAME-26SEP13ABCDEF"))


class TestTheSharedHelpersOtherConsumersAreUntouched:
    """`kalshi_match_segment_key` has two consumers that encode things true of
    TENNIS only. #6720 added a separate function rather than widening the set
    underneath them; this is the guard that nobody merges the two later."""

    @pytest.mark.parametrize("ticker", FREIBURG_STRANDED[:4] + (
        "KXNFL1Q-26SEP13NODET", "KXMLBTOTAL-26SEP061335BOSBAL",
    ))
    def test_a_soccer_or_nfl_ticker_is_still_not_a_tennis_prop(self, ticker):
        """If the widening had gone into the shared helper, every one of these
        would score as a prop — `is_kalshi_tennis_prop_ticker` tests membership
        against the TENNIS match series — and would lose the right to create
        its own event."""
        assert is_kalshi_tennis_prop_ticker(ticker) is False
        assert kalshi_match_segment_key(ticker) is None

    @pytest.mark.parametrize("ticker", [
        "KXBUNDESLIGATOTAL-26SEP12SCFBMG", "KXNFL1Q-26SEP13NODET",
    ])
    def test_the_unlink_arms_still_date_check_these(self, ticker):
        """`is_kalshi_match_segment_ticker` tells the unlink arms to stop
        second-guessing a link, because a TENNIS segment's date is the draw
        date. A soccer segment's date is the fixture's own, so these must keep
        their date check."""
        assert is_kalshi_match_segment_ticker(ticker) is False


# =============================================================================
# The discriminator — the half that was inert on production
# =============================================================================


class TestTheDiscriminatorWasTheInertHalf:
    @pytest.mark.parametrize("ghost_source", [
        "kalshi", "kalshi_occurrence", "statpal",
    ])
    def test_the_anchored_row_wins_against_every_measured_ghost_string(
        self, ghost_source,
    ):
        """All three strings are measured id-less twins from #6720's specimens,
        and all three pass `!= 'kalshi_ticker'`. Under the old rule each of
        these contests had two "schedule-derived" winners and refused."""
        assert _choose_segment_event(
            [15297802, 15307870],
            {15297802: "espn", 15307870: ghost_source},
            {15297802: True, 15307870: False},
        ) == (15297802, "anchored")

    def test_the_choice_does_not_read_provenance_when_the_anchor_decides(self):
        """The anchored row wins even when its provenance is the ticker-derived
        string and the ghost's is not — the exact inversion of the old rule."""
        assert _choose_segment_event(
            [10, 20],
            {10: "kalshi_ticker", 20: "espn"},
            {10: True, 20: False},
        ) == (10, "anchored")

    def test_two_id_less_rows_are_refused_not_coin_flipped(self):
        """Brest v PSG (#6720's worst pair, 13 markets): BOTH rows are id-less
        auto-creates, so there is no id evidence and nothing moves. Under the
        old rule the 'kalshi' row would have been picked as schedule-derived
        and 13 markets would have moved ONTO a ghost."""
        assert _choose_segment_event(
            [15307680, 15312903],
            {15307680: "kalshi", 15312903: "kalshi_ticker"},
            {15307680: False, 15312903: False},
        ) == (None, "ambiguous_idless")

    def test_several_anchored_rows_are_refused(self):
        assert _choose_segment_event(
            [11, 22], {11: "espn", 22: "espn"}, {11: True, 22: True},
        ) == (None, "ambiguous")


# =============================================================================
# The reconciliation, end to end on the specimens
# =============================================================================


@pytest.mark.asyncio
class TestReconcileOnTheProductionSpecimens:
    async def test_freiburg_twelve_rejoin_the_page_that_shows_the_other_three(
        self,
    ):
        """RED BEFORE #6720: the reconcile never read a KXBUNDESLIGA row, and
        had it read them it would have refused `ambiguous`."""
        markets = [
            _Row(i, t, 15297802)
            for i, t in enumerate(FREIBURG_ON_THE_REAL_ROW, start=1)
        ] + [
            _Row(100 + i, t, 15307870)
            for i, t in enumerate(FREIBURG_STRANDED)
        ]
        session = _FakeSession(
            markets=markets,
            provenance={15297802: "espn", 15307870: "kalshi"},
            anchored={15297802},
        )
        stats = await _reconcile_kalshi_match_segments(session)

        assert _applied(session) == {
            15297802: {100 + i for i in range(len(FREIBURG_STRANDED))},
        }
        assert stats["converged"] == 12
        assert stats["adopted"] == 0
        assert (stats["ambiguous"], stats["ambiguous_idless"]) == (0, 0)

    async def test_the_four_saints_lions_quarters_leave_the_voided_twin(self):
        session = _FakeSession(
            markets=[
                _Row(1, "KXNFLGAME-26SEP13NODET", 14780145),
                _Row(2, "KXNFLSPREAD-26SEP13NODET", 14780145),
                _Row(3, "KXNFL1Q-26SEP13NODET", 15305069),
                _Row(4, "KXNFL2Q-26SEP13NODET", 15305069),
                _Row(5, "KXNFL3Q-26SEP13NODET", 15305069),
                _Row(6, "KXNFL4Q-26SEP13NODET", 15305069),
            ],
            provenance={14780145: "espn", 15305069: "kalshi_occurrence"},
            anchored={14780145},
        )
        stats = await _reconcile_kalshi_match_segments(session)

        assert _applied(session) == {14780145: {3, 4, 5, 6}}
        assert stats["converged"] == 4

    async def test_the_mlb_statpal_twin_loses_its_four(self):
        session = _FakeSession(
            markets=[
                _Row(1, "KXMLBF5-26SEP061335BOSBAL", 15305465),
                _Row(2, "KXMLBGAME-26SEP061335BOSBAL", 15298127),
                _Row(3, "KXMLBSPREAD-26SEP061335BOSBAL", 15298127),
                _Row(4, "KXMLBTOTAL-26SEP061335BOSBAL", 15298127),
                _Row(5, "KXMLBTEAMTOTAL-26SEP061335BOSBAL", 15298127),
            ],
            provenance={15305465: "espn", 15298127: "statpal"},
            anchored={15305465},
        )
        stats = await _reconcile_kalshi_match_segments(session)

        assert _applied(session) == {15305465: {2, 3, 4, 5}}
        assert stats["converged"] == 4

    async def test_brest_psg_moves_nothing_because_both_rows_are_id_less(self):
        """The refusal is the point: 13 markets stay where they are rather than
        move onto the other ghost. #6720 files that half as a second question."""
        session = _FakeSession(
            markets=[
                _Row(1, "KXLIGUE11H-26SEP13STBPSG", 15307680),
                _Row(2, "KXLIGUE11HBTTS-26SEP13STBPSG", 15307680),
                _Row(3, "KXLIGUE1GAME-26SEP13STBPSG", 15312903),
            ],
            provenance={15307680: "kalshi", 15312903: "kalshi_ticker"},
            anchored=set(),
        )
        stats = await _reconcile_kalshi_match_segments(session)

        assert session.updates == []
        assert session.commits == 0
        assert stats["ambiguous_idless"] == 1

    async def test_an_unlinked_soccer_prop_adopts_the_anchored_event(self):
        session = _FakeSession(
            markets=[
                _Row(1, "KXLALIGAGAME-26SEP16LEVATH", 15305825),
                _Row(2, "KXLALIGATOTAL-26SEP16LEVATH", None),
            ],
            provenance={15305825: "espn"},
            anchored={15305825},
        )
        stats = await _reconcile_kalshi_match_segments(session)

        assert _applied(session) == {15305825: {2}}
        assert (stats["adopted"], stats["converged"]) == (1, 0)

    async def test_a_sport_outside_the_set_is_still_refused_by_the_key(self):
        """The SQL prefixes bound the read; the key is the rule. An NBA row
        that slipped through must still move nothing."""
        session = _FakeSession(
            markets=[
                _Row(1, "KXNBAGAME-26FEB20BOSGSW", 500),
                _Row(2, "KXNBASPREAD-26FEB20BOSGSW", None),
            ],
            provenance={500: "espn"},
            anchored={500},
        )
        stats = await _reconcile_kalshi_match_segments(session)

        assert session.updates == []
        assert stats["segments"] == 0

    async def test_only_the_link_moves_never_a_settlement(self):
        """gotcha #21 — the stored Kalshi settlements were always right."""
        session = _FakeSession(
            markets=[
                _Row(1, "KXBUNDESLIGASCORE-26SEP12SCFBMG", 15297802),
                _Row(2, "KXBUNDESLIGATOTAL-26SEP12SCFBMG", 15307870),
            ],
            provenance={15297802: "espn", 15307870: "kalshi"},
            anchored={15297802},
            sport_ids={15297802: 77},
        )
        await _reconcile_kalshi_match_segments(session)

        written = set()
        for stmt in session.updates:
            written |= {c.name for c in dict(stmt._values)}
        assert written == {"event_id", "sport_id"}
        for forbidden in ("is_winner", "calibration_probability",
                          "updated_at", "commence_time"):
            assert forbidden not in written


# =============================================================================
# The population filter
# =============================================================================


class TestTheReadIsBoundedAndCoversTheMeasuredSports:
    def test_every_specimen_ticker_matches_a_prefix(self):
        """The SQL pre-filter must be a SUPERSET of the decider, or a whole
        population is dropped before the key ever sees it."""
        specimens = FREIBURG_STRANDED + FREIBURG_ON_THE_REAL_ROW + (
            "KXNFL1Q-26SEP13NODET",
            "KXMLBGAME-26SEP061335BOSBAL",
            "KXMLBERA-26SEP082145STLSF",
            "KXUFCMOV-26SEP12ALDTAR",
            "KXLALIGAGAME-26SEP16LEVATH",
            "KXEPL1H-26SEP12LFCFUL",
            "KXSERIEA1H-26SEP13SASJUV",
            "KXLIGUE11H-26SEP13STBPSG",
            "KXATPMATCH-26AUG30BUBWOL",
            "KXWTAEXACTMATCH-26AUG30SWIRYB",
        )
        bare = [p.rstrip("%") for p in _KALSHI_SEGMENT_TICKER_PREFIXES]
        for ticker in specimens:
            assert any(ticker.lower().startswith(p) for p in bare), ticker

    def test_tennis_is_still_in_the_population(self):
        """The widening must not drop what Q435 already reconciled."""
        bare = [p.rstrip("%") for p in _KALSHI_SEGMENT_TICKER_PREFIXES]
        assert "kxatp" in bare and "kxwta" in bare

    def test_a_prefix_never_admits_a_sport_the_key_would_have_to_reject(self):
        """Over-reach in SQL is safe but wasteful, and a prefix that pulls a
        whole unmeasured sport is a sign the list drifted from the key."""
        from app.utils.sport_keys import get_sport_key_from_ticker

        from app.utils.prediction_market_matching import (
            _KALSHI_GAME_SEGMENT_SPORT_KEYS,
            _KALSHI_GAME_SEGMENT_SPORT_PREFIXES,
            _KALSHI_MATCH_SEGMENT_SPORT_KEYS,
        )

        allowed = _KALSHI_GAME_SEGMENT_SPORT_KEYS | _KALSHI_MATCH_SEGMENT_SPORT_KEYS
        for prefix in (p.rstrip("%") for p in _KALSHI_SEGMENT_TICKER_PREFIXES):
            sport = get_sport_key_from_ticker(f"{prefix}game-26SEP13ABCDEF")
            if sport is None:
                continue
            assert (
                sport in allowed
                or sport.startswith(_KALSHI_GAME_SEGMENT_SPORT_PREFIXES)
            ), f"{prefix} admits {sport}, which the key rejects"

    def test_the_cap_still_refuses_rather_than_reconciling_half_a_picture(self):
        """Blowing the cap does not reconcile less — it reconciles NOTHING, so
        the widening had to be measured against it (9,498 of 20,000 on
        2026-09-17). This pins the refuse behaviour the headroom protects."""
        import inspect

        from app.tasks import prediction_market_matching as mod

        src = inspect.getsource(mod._reconcile_kalshi_match_segments)
        assert "truncated" in src
        assert "MAX_KALSHI_SEGMENT_ROWS" in src
        assert mod.MAX_KALSHI_SEGMENT_ROWS >= 20000

    def test_the_segment_split_is_not_re_implemented_in_sql(self):
        """One definition of "same game" — the pure helper, in Python."""
        import inspect

        from app.tasks import prediction_market_matching as mod

        src = inspect.getsource(mod._reconcile_kalshi_match_segments)
        assert "kalshi_game_segment_key" in src
