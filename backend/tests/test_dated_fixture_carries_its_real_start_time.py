"""#3562 — a league fixture stops advertising the wrong DAY.

## the bug, as a user met it on 2026-09-06

    Pumas UNAM v Leon        our page said  2026-09-06 00:00Z
                             the venue says 2026-09-09 (published)
    Angers v Stade Rennais   our page said  2026-09-06 00:00Z
                             the venue says 2026-09-08 21:15Z

Not the wrong hour — the wrong DAY, on a page a user opens to find out when to
watch. #3488 fixed exactly this for tennis and stopped there, because its gate
was a MATCH/DOUBLES ticker shape. Both gates missed everything else::

    KXLIGUE1GAME-26SEP20OLMPSG    is_game=None   dated fixture=False
    KXLIGAMXGAME-26SEP19AMECDG    is_game=None   dated fixture=False
    KXNFLRACE-26SEP14DENKC-35     is_game=None   dated fixture=False
    KXNFLGAME-26SEP07KCPHI        is_game=NFL    (market already correct)
    KXATPMATCH-26SEP07ZVEDAR      dated fixture=True  (#3488)

## what this file pins

The fix is one token of vocabulary wider, not one regex looser. Three
independent things have to stay true, and each has its own section below:

1. **Everything #3488 admitted is still admitted.** The widening is a strict
   superset by construction; a test says so, because "by construction" is a
   claim about a regex two people will edit.
2. **The reach is a decision.** 96 series / 896 open rows on production
   2026-09-06, of which 16 series / 366 rows were already game tickers and
   change nothing. The behaviour change is 80 series / 530 rows. A series
   joining or leaving that set fails here rather than silently re-timing rows.
3. **The refuted widening stays refuted.** Dropping the vocabulary and keeping
   only the bare date shape reaches 178 series / 1,927 open rows and swallows
   Billboard chart positions and CFP poll rankings. Those specimens are
   parametrised so the cheap "just loosen the regex" fix cannot land green.

## the venue read behind it (notice 26)

Every one of the 80 behaviour-changing series was read at Kalshi's own
`/markets?status=open&series_ticker=...` on 2026-09-06: **2,348 open markets,
100% date-shaped, 100% carrying an `occurrence_datetime`, ZERO with
`occ > close`, offsets +9.00h..+30.00h from their own ticker midnight and none
negative.** That is inside `_STAND_IN_REFINEMENT_MAX` (36h) with 6h of margin —
measured, not inherited from #3488's tennis table.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.kalshi import (
    _DATED_FIXTURE_MARKET_TYPES,
    _STAND_IN_REFINEMENT_MAX,
    _TENNIS_MATCH_SERIES_RE,
    _is_dated_fixture_ticker,
    _is_kalshi_game_ticker,
    _kalshi_commence_time,
    _stand_in_refinement_target,
)

UTC = timezone.utc


class _M:
    """The two fields `_kalshi_commence_time` reads."""

    def __init__(self, close, occ=None):
        self.close_time = close
        self.occurrence_datetime = occ


# ---------------------------------------------------------------------------
# 1. the widening is a superset — #3488 cannot be narrowed by widening it
# ---------------------------------------------------------------------------

class TestNothingTennisLoses:
    #: Every distinct shape #3488's own tests assert is admitted.
    TENNIS_SPECIMENS = (
        "KXATPMATCH-26SEP07ZVEDAR",
        "KXWTAMATCH-26SEP07OSARYB",
        "KXITFMATCH-26SEP07OLIGRO",
        "KXITFWMATCH-26SEP06MORGAL",
        "KXATPCHALLENGERMATCH-26SEP06NAKLIU",
        "KXWTACHALLENGERMATCH-26SEP06ZAATSY",
        "KXATPDOUBLES-26SEP04KRAPUTFARWAL",
        "KXWTADOUBLES-26SEP03MUHSTOPARSHY",
        "KXITFDOUBLES-26SEP04CESMENAGUDEL",
        "KXITFWDOUBLES-26SEP04CESMENAGUDEL",
        "KXATPEXACTMATCH-26SEP06SHETSI",
        "KXWTAEXACTMATCH-26SEP06JOVGAU",
        "KXRUGBYNRLMATCH-26SEP13PENSYD",
        "KXSQUASHMATCH-26SEP07ABCDEF",
    )

    @pytest.mark.parametrize("ticker", TENNIS_SPECIMENS)
    def test_every_shipped_admission_survives(self, ticker):
        assert _TENNIS_MATCH_SERIES_RE.match(ticker)
        assert _is_dated_fixture_ticker(ticker) is True

    def test_the_two_shipped_tokens_are_the_first_two_of_the_vocabulary(self):
        """Containment is claimed "by construction" in the source. The
        construction is: the tennis tokens are IN the vocabulary and the league
        character class only widened. If someone removes MATCH from the tuple
        to tidy it, the tennis half dies silently — here instead."""
        assert "MATCH" in _DATED_FIXTURE_MARKET_TYPES
        assert "DOUBLES" in _DATED_FIXTURE_MARKET_TYPES

    def test_the_second_half_still_reads_its_own_narrower_shape(self):
        """`_tennis_commence_target` deliberately keeps
        `_TENNIS_MATCH_SERIES_RE`, so the market-side ticker-date fix-up did NOT
        widen with the classifier. A newly-admitted series' market therefore
        holds the venue hour and nothing re-dates it to a midnight — the
        divergence is safe only in this direction, and only while the narrow
        shape is a subset of the wide one."""
        import inspect

        from app.tasks.kalshi import _tennis_commence_target

        src = inspect.getsource(_tennis_commence_target)
        assert "_TENNIS_MATCH_SERIES_RE" in src
        assert "_DATED_FIXTURE_SERIES_RE" not in src


# ---------------------------------------------------------------------------
# 2. the reach is a decision, not an accident
# ---------------------------------------------------------------------------

class TestTheReachIsPinned:
    """Measured on production 2026-09-06 with `POST /api/admin/db-query`:
    open Kalshi rows whose `external_id` the widened shape admits and the
    shipped shape did not, grouped by series."""

    #: The behaviour change. None of these is a game ticker, so for every one
    #: of them this predicate is what opens the occurrence preference.
    NOT_GAME_TICKERS = {
        "kxnflrace": 80, "kxncaafteamtd": 25, "kxncaaf2q": 24,
        "kxncaaf3q": 24, "kxncaaf4q": 24, "kxncaafdsttd": 24, "kxncaaf1q": 17,
        "kxnfl1q": 16, "kxnfl1qbtts": 16, "kxnfl2q": 16, "kxnfl2qbtts": 16,
        "kxnfl3q": 16, "kxnfl3qbtts": 16, "kxnfl4q": 16, "kxnfl4qbtts": 16,
        "kxnfleqbtts": 16, "kxnfltd": 16, "kxknvbcupadvance": 9,
        "kxserieagame": 8, "kxbrasileirogame": 7, "kxlaligagame": 7,
        "kxligamxgame": 7, "kxeerstedivgame": 6, "kxligue1game": 6,
        "kxfacupadvance": 5, "kxfacupgame": 5, "kxligue2game": 5,
        "kxbundesligagame": 4, "kxczefnlgame": 4, "kxsvkcupadvance": 4,
        "kxsvkcupgame": 4, "kxeliteseriengame": 3, "kxeplgame": 3,
        "kxsaudiplgame": 3, "kxserieccupadvance": 3, "kxbrasileirobgame": 2,
        "kxbundesliga2game": 2, "kxcopadobrasiladvance": 2,
        "kxcoppaitaliaadvance": 2, "kxettangame": 2, "kxidnslgame": 2,
        "kxk2leaguegame": 2, "kxligaportugalgame": 2, "kxligue1btts": 2,
        "kxligue1spread": 2, "kxligue1total": 2, "kxmyslgame": 2,
        "kxperliga1game": 2, "kxuaeplgame": 2, "kxatpgtotal": 1,
        "kxbelgianplgame": 1, "kxbundesligabtts": 1, "kxbundesligaspread": 1,
        "kxbundesligatotal": 1, "kxdensuperligagame": 1,
        "kxekstraklasagame": 1, "kxengnlgame": 1, "kxeplbtts": 1,
        "kxeplspread": 1, "kxepltotal": 1, "kxeredivisiegame": 1,
        "kxfinylgame": 1, "kxger3lgame": 1, "kxhnlgame": 1,
        "kxlaliga2game": 1, "kxlaligabtts": 1, "kxlaligaspread": 1,
        "kxlaligatotal": 1, "kxlvavirgame": 1, "kxserieabtts": 1,
        "kxserieaspread": 1, "kxserieatotal": 1, "kxsrbslgame": 1,
        "kxsvk2lgame": 1, "kxsvnplgame": 1, "kxthail1game": 1,
        "kxurypdgame": 1, "kxuslgame": 1, "kxvleague1game": 1,
        "kxwtagtotal": 1,
    }

    #: Admitted too, and already `is_game`, so the MARKET side changes nothing
    #: for them. They are listed because the EVENT side does change: gate 2 of
    #: `_stand_in_refinement_target` used to refuse these, which is why an NFL
    #: game's market held the venue kick-off while its event page still said
    #: midnight. Dropping them from the count would understate the ship.
    ALREADY_GAME_TICKERS = {
        "kxncaafgame": 160, "kxnflgame": 32, "kxmlsgame": 18,
        "kxnfl1hspread": 16, "kxnfl1htotal": 16, "kxnfl2hspread": 16,
        "kxnfl2htotal": 16, "kxnfldsttd": 16, "kxnflfirsttd": 16,
        "kxnflspread": 16, "kxnfltotal": 16, "kxncaafspread": 11,
        "kxncaaftotal": 11, "kxnbagame": 3, "kxnflteamtotal": 2,
        "kxatpgspread": 1,
    }

    def test_the_measured_totals_are_what_the_source_claims(self):
        """The docstring on `_is_dated_fixture_ticker` quotes these numbers to
        justify the widening. If the dicts are edited the prose goes stale, and
        a reader trusting it would mis-size the next change."""
        assert len(self.NOT_GAME_TICKERS) == 80
        assert sum(self.NOT_GAME_TICKERS.values()) == 530
        assert len(self.ALREADY_GAME_TICKERS) == 16
        assert sum(self.ALREADY_GAME_TICKERS.values()) == 366

    @pytest.mark.parametrize("series", sorted(NOT_GAME_TICKERS))
    def test_each_behaviour_changing_series_is_admitted_and_is_not_a_game(
        self, series
    ):
        ticker = f"{series.upper()}-26SEP07ABCDEF"
        assert _is_dated_fixture_ticker(ticker) is True, ticker
        # The real behaviour change: for these, `is_game` contributes nothing,
        # so without this predicate they keep Kalshi's settlement close.
        assert _is_kalshi_game_ticker(ticker) is None, ticker
        # ...and #3488 did not reach them, so this IS the widening's work.
        assert not _TENNIS_MATCH_SERIES_RE.match(ticker), ticker

    @pytest.mark.parametrize("series", sorted(ALREADY_GAME_TICKERS))
    def test_the_already_game_series_are_admitted_and_the_market_is_unchanged(
        self, series
    ):
        ticker = f"{series.upper()}-26SEP07ABCDEF"
        assert _is_dated_fixture_ticker(ticker) is True, ticker
        assert _is_kalshi_game_ticker(ticker) is not None, ticker
        # `is_game` alone already opened the occurrence preference, so the
        # market-side answer is identical with the new gate on or off.
        occ = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
        close = datetime(2026, 9, 21, 6, 5, tzinfo=UTC)
        assert _kalshi_commence_time(
            [_M(close, occ)], is_game=True, is_dated_fixture=False
        ) == _kalshi_commence_time(
            [_M(close, occ)], is_game=True, is_dated_fixture=True
        )


# ---------------------------------------------------------------------------
# 3. the refuted widening stays refuted
# ---------------------------------------------------------------------------

class TestTheBareDateShapeIsNotTheFix:
    """Measured 2026-09-06 and rejected: `^KX[A-Z0-9]+-\\d{2}[A-Z]{3}\\d{2}...`
    reaches 178 series / 1,927 open rows for ~96 series of wanted reach. These
    are the specimens that killed it. They are parametrised rather than prose
    so the cheap fix cannot land green."""

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXBBCHARTPOSITIONALBUM-26SEP08TAYSWI",
            "KXBBCHARTPOSITIONSONG-26SEP08TAYSWI",
            "KXNCAAFCFPPOLL-26SEP16ALABAMA",
            "KXNCAAFTOPCFPPOLL-26SEP16ALABAMA",
            "KXVOTESAXANH-26OCT02ABCDEF",
        ],
        ids=["chart_album", "chart_song", "poll", "top_poll", "votes"],
    )
    def test_a_chart_position_or_a_poll_is_not_a_fixture(self, ticker):
        """Their `occurrence_datetime` is a publication instant, not a
        kick-off, and re-timing a market on it would be a fresh bug."""
        assert _is_dated_fixture_ticker(ticker) is False

    def test_the_tail_length_rescue_is_the_one_that_dies(self):
        """The tempting narrowing of the bare shape — "a matchup tail is 5-6
        characters" — has a counterexample inside the band, so length can never
        be the discriminator. `AGORDON` is 7, which is why the vocabulary and
        not the tail is what does the work here."""
        ticker = "KXJOINCLUB-26OCT02AGORDON"
        assert len("AGORDON") == 7
        assert _is_dated_fixture_ticker(ticker) is False

    def test_an_outright_wearing_a_fixture_token_is_still_refused(self):
        """`ADVANCE` is in the vocabulary because a dated cup tie uses it. The
        DATE half is what separates the tie from the tournament outright, and
        `26USOSEMI` is not a date: `\\d{2}[A-Z]{3}\\d{2}` needs two digits after
        the month and "SE" is not."""
        assert _is_dated_fixture_ticker("KXATPADVANCE-26USOSEMI") is False
        assert _is_dated_fixture_ticker("KXWTA-26USO") is False
        assert _is_dated_fixture_ticker("KXHONEYDEUCE-01JAN27") is False

    def test_the_day_backtracking_trap_is_still_refused(self):
        """`KXATP1RANK-26DEC31` — the outright with no matchup tail whose day
        `extract_game_date_from_ticker` backtracks to Dec 3. Requiring a full
        two-digit day AND a following letter is what closes it, and the
        vocabulary widening must not have reopened it: `1RANK` is not a
        market-type token, but `[A-Z0-9]*` now admits the digit in the league
        half, so this is a live risk rather than a formality."""
        assert _is_dated_fixture_ticker("KXATP1RANK-26DEC31") is False
        assert _is_dated_fixture_ticker("KXATPMATCH-26SEP6") is False

    @pytest.mark.parametrize("ticker", [None, ""])
    def test_no_ticker_is_refused(self, ticker):
        assert _is_dated_fixture_ticker(ticker) is False


# ---------------------------------------------------------------------------
# the venue's own numbers, replayed through the production functions
# ---------------------------------------------------------------------------

class TestTheVenueSpecimensGetTheirRealStart:
    """Read at Kalshi 2026-09-06 (notice 26) — occurrence and close both."""

    #: (ticker, occurrence, close). Every one is a real open market.
    SPECIMENS = [
        ("KXLIGUE1GAME-26SEP20OLMPSG",
         datetime(2026, 9, 20, 21, 45, tzinfo=UTC),
         datetime(2026, 9, 23, 0, 45, tzinfo=UTC)),
        ("KXLIGAMXGAME-26SEP19AMECDG",
         datetime(2026, 9, 20, 6, 0, tzinfo=UTC),
         datetime(2026, 9, 22, 9, 0, tzinfo=UTC)),
        ("KXNFLRACE-26SEP14DENKC-35",
         datetime(2026, 9, 15, 3, 15, tzinfo=UTC),
         datetime(2026, 9, 17, 0, 15, tzinfo=UTC)),
    ]

    @pytest.mark.parametrize("ticker,occ,close", SPECIMENS)
    def test_the_market_stores_the_kick_off_not_the_settlement_close(
        self, ticker, occ, close
    ):
        assert _kalshi_commence_time(
            [_M(close, occ)],
            is_game=bool(_is_kalshi_game_ticker(ticker)),
            is_dated_fixture=_is_dated_fixture_ticker(ticker),
        ) == occ

    @pytest.mark.parametrize("ticker,occ,close", SPECIMENS)
    def test_without_the_gate_it_is_the_close_which_is_the_wrong_day(
        self, ticker, occ, close
    ):
        """The two-armed half. `KXNFLRACE-26SEP14DENKC-35` closes 2026-09-17
        for a game on the 14th — a user reading that page is told to watch on
        the wrong day, which is the bug, reproduced."""
        assert _kalshi_commence_time(
            [_M(close, occ)], is_game=False, is_dated_fixture=False
        ) == close
        assert close.date() != occ.date()

    @pytest.mark.parametrize("ticker,occ,close", SPECIMENS)
    def test_the_event_page_then_gets_that_hour_off_its_own_market(
        self, ticker, occ, close
    ):
        """The second half. `_refine_stand_in_event_starts` reads the market
        the poll has just re-timed, so the field the page renders —
        `events.commence_time` — ends on the venue's hour rather than the
        midnight the ticker date left there.

        The stand-in is the TICKER's day at midnight, derived here from the
        ticker rather than from the occurrence: two of these three fixtures
        occur the day AFTER the day their ticker names (Liga MX 06:00Z, the NFL
        Monday-night 03:15Z), so anchoring on the occurrence would quietly turn
        the +30h and +27.25h cases into +6h and +3.25h and stop testing the
        distance at all.
        """
        from app.utils.prediction_market_matching import (
            extract_game_date_from_ticker,
        )

        stand_in = extract_game_date_from_ticker(ticker)
        assert stand_in is not None and stand_in.time() == datetime.min.time()

        moved = _stand_in_refinement_target(
            external_id=ticker,
            event_commence=stand_in,
            event_commence_source="kalshi_ticker",
            market_commence=occ,
        )
        assert moved == occ
        # ...and the move really is the long one the docstring claims.
        assert timedelta(hours=9) <= occ - stand_in <= timedelta(hours=30)

    def test_the_measured_offsets_all_fit_the_shipped_window(self):
        """2,348 open markets across the 80 behaviour-changing series, read at
        the venue: +9.00h min, +30.00h max, none negative. A measured maximum
        is not a bound (that is why `_STAND_IN_REFINEMENT_MAX` is argued from
        the linkage guard, not from a sample) — but it IS what says the shipped
        bound is big enough for this population without being re-litigated."""
        assert timedelta(hours=30) <= _STAND_IN_REFINEMENT_MAX
        assert timedelta(hours=9) > timedelta(0)

    #: The same 2,348 venue rows, measured on `close_time` instead: the
    #: SMALLEST settlement close sits **+60.00h** past its own ticker midnight
    #: (max +4,098h). Nothing near the +0.5h..+36h band the event-side repair
    #: writes in.
    MEASURED_MIN_CLOSE_OFFSET = timedelta(hours=60)

    def test_a_market_still_on_its_close_can_never_be_copied_onto_an_event(self):
        """The deploy-ordering hazard, measured for the widened population.

        Between a deploy and the poll that re-times a series, a market still
        holds Kalshi's settlement close. If that close could land inside the
        refinement window the repair would copy a settlement date onto an event
        — strictly worse than the midnight it replaced, and the exact failure
        `_STAND_IN_REFINEMENT_MAX` exists to prevent.

        It cannot: 0 of the 2,348 venue rows have a close inside the band, and
        the closest is +60h against a 36h bound. So the repair is safe to run
        against a market the poll has not reached yet — which it does, on every
        poll, for every series the run did not get to.
        """
        assert self.MEASURED_MIN_CLOSE_OFFSET > _STAND_IN_REFINEMENT_MAX

        ticker, occ, close = self.SPECIMENS[0]
        stand_in = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
        assert close - stand_in > _STAND_IN_REFINEMENT_MAX
        assert _stand_in_refinement_target(
            external_id=ticker,
            event_commence=stand_in,
            event_commence_source="kalshi_ticker",
            market_commence=close,          # not yet re-timed
        ) is None

    def test_an_occurrence_after_its_own_close_is_still_refused(self):
        """The bound that does the safety work is `occ <= close`, not the
        sport and not the vocabulary. Zero of the 2,348 venue rows violate it —
        so this arm is the one that proves the check is still WIRED, since no
        real row exercises it."""
        occ = datetime(2027, 1, 1, 15, 0, tzinfo=UTC)
        close = datetime(2027, 1, 1, 4, 59, tzinfo=UTC)
        assert _kalshi_commence_time(
            [_M(close, occ)], is_game=False, is_dated_fixture=True
        ) == close


# ---------------------------------------------------------------------------
# wiring — the poll has to ask
# ---------------------------------------------------------------------------

def test_both_poll_call_sites_pass_the_widened_gate():
    """#3488's own guard, re-armed for the wider predicate: the tests above all
    drive the helpers directly, so the one thing that makes this reach
    production — the poll consulting it on BOTH branches of the
    single-market/multi-market split — is what nothing else asserts."""
    import ast
    import inspect

    import app.tasks.kalshi as kalshi_task

    tree = ast.parse(inspect.getsource(kalshi_task._poll_kalshi_markets))
    gates = [
        kw
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_kalshi_commence_time"
        for kw in node.keywords
        if kw.arg == "is_dated_fixture"
    ]
    assert len(gates) == 2, "both call sites must pass the gate"
    for kw in gates:
        assert isinstance(kw.value, ast.Call)
        assert kw.value.func.id == "_is_dated_fixture_ticker"
