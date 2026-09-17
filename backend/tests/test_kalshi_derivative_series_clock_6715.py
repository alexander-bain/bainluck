"""A soccer derivative series does not get to say when the fixture kicks off (#6715).

SHIP: the La Liga "No result reported" rail stops drawing the same fixture twice
— once as a real card and once, an hour later, as a crestless row with no price.
(Pillar: MATCHING. Under #2693, acceptance 2's stored half.)

WHAT THESE PIN, AND WHY THE OBVIOUS FIX IS THE WRONG ONE
────────────────────────────────────────────────────────
`15312871` (Levante v Bilbao) is stored at 23:30Z for a 19:30Z kick-off. #6715
measured the ghost/real delta as bimodal — 180 min x10, 240 min x2 — and recorded
the 240 as an unexplained second value. Acting on that reading would have meant
widening `KALSHI_EXPECTED_EXPIRATION_PAD` to 4h (explicitly forbidden: it would
make an exact recovery approximate for every soccer row on the site) or building
the per-competition table its note prescribes (which cannot work — La Liga
produces BOTH values).

The venue says it is neither. `occurrence_datetime` is published 60 minutes later
on the derivative series than on the GAME series for the same fixture, 183 of 183
comparisons across six leagues and three kinds. Both pads are exact; the
discriminator is the series KIND. So the row is not owed a wider tolerance, it is
owed the GAME series' clock — after which the 180-minute pad already on the books
recovers it to 19:30Z to the minute.

`test_the_specimen_recovers_to_its_true_kickoff` is the one that would have caught
this class: it runs the real mint value through the real recovery and asserts the
kick-off, so a future widening of either constant fails here rather than on a page.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.kalshi_occurrence_start import (
    KALSHI_DERIVATIVE_SERIES_EXCESS,
    KALSHI_EXPECTED_EXPIRATION_PAD,
    KALSHI_MEASURED_SOCCER_LEAGUE_PREFIXES,
    KALSHI_SOCCER_DERIVATIVE_KINDS,
    kalshi_derivative_series_excess,
    kalshi_game_scale_commence,
    kalshi_occurrence_scheduled_start,
)


class _Market:
    """A futures_markets row as the mint path reads it. No ORM, no session."""

    def __init__(self, external_id, commence_time, source="kalshi"):
        self.external_id = external_id
        self.commence_time = commence_time
        self.source = source


class _Event:
    """An events row as `kalshi_occurrence_scheduled_start` reads it."""

    def __init__(self, commence_time, source="kalshi", external_id=None):
        self.commence_time = commence_time
        self.commence_time_source = source
        self.external_id = external_id


# The specimen, verbatim from production and from the venue (2026-09-17).
SPECIMEN_KICKOFF = datetime(2026, 9, 16, 19, 30, tzinfo=timezone.utc)
SPECIMEN_GAME_OCCURRENCE = datetime(2026, 9, 16, 22, 30, tzinfo=timezone.utc)
SPECIMEN_DERIV_OCCURRENCE = datetime(2026, 9, 16, 23, 30, tzinfo=timezone.utc)


class TestTheSpecimen:
    def test_the_venue_numbers_this_rests_on_are_what_i_say_they_are(self):
        """The arithmetic, stated once, so a later edit cannot drift off it."""
        assert SPECIMEN_GAME_OCCURRENCE - SPECIMEN_KICKOFF == KALSHI_EXPECTED_EXPIRATION_PAD
        assert (
            SPECIMEN_DERIV_OCCURRENCE - SPECIMEN_GAME_OCCURRENCE
            == KALSHI_DERIVATIVE_SERIES_EXCESS
        )

    def test_the_derivative_market_is_minted_on_the_game_clock(self):
        deriv = _Market("KXLALIGATOTAL-26SEP16LEVATH", SPECIMEN_DERIV_OCCURRENCE)
        assert kalshi_game_scale_commence(deriv) == SPECIMEN_GAME_OCCURRENCE

    def test_the_game_market_is_not_touched(self):
        """The GAME series is already the scale; moving it would invent an hour."""
        game = _Market("KXLALIGAGAME-26SEP16LEVATH", SPECIMEN_GAME_OCCURRENCE)
        assert kalshi_game_scale_commence(game) == SPECIMEN_GAME_OCCURRENCE

    def test_all_four_of_the_specimens_markets_agree_after_normalisation(self):
        """The four rows on `15312871` disagreed by an hour; now they do not.

        This is the property the twin fold needs — one fixture, one instant —
        and it is asserted across the real ticker set rather than one of them.
        """
        tickers = [
            ("KXLALIGAGAME-26SEP16LEVATH", SPECIMEN_GAME_OCCURRENCE),
            ("KXLALIGATOTAL-26SEP16LEVATH", SPECIMEN_DERIV_OCCURRENCE),
            ("KXLALIGASPREAD-26SEP16LEVATH", SPECIMEN_DERIV_OCCURRENCE),
            ("KXLALIGABTTS-26SEP16LEVATH", SPECIMEN_DERIV_OCCURRENCE),
        ]
        minted = {kalshi_game_scale_commence(_Market(t, c)) for t, c in tickers}
        assert minted == {SPECIMEN_GAME_OCCURRENCE}

    def test_the_specimen_recovers_to_its_true_kickoff(self):
        """End to end: mint from the derivative, then recover. 19:30Z, exactly.

        Before this ship the same two calls produced 20:30Z — an hour out, which
        is precisely why `fold_twin_events` refused the pair and the reader saw
        two cards. Neither constant may be widened to make this pass.
        """
        deriv = _Market("KXLALIGATOTAL-26SEP16LEVATH", SPECIMEN_DERIV_OCCURRENCE)
        minted = kalshi_game_scale_commence(deriv)
        recovered = kalshi_occurrence_scheduled_start(
            _Event(minted), "soccer_spain_la_liga"
        )
        assert recovered == SPECIMEN_KICKOFF

    def test_without_the_normalisation_the_recovery_misses_by_exactly_an_hour(self):
        """The defect itself, pinned — so the test above cannot pass vacuously.

        If someone deletes the normalisation, the test above fails and this one
        still describes what the reader then gets.
        """
        recovered = kalshi_occurrence_scheduled_start(
            _Event(SPECIMEN_DERIV_OCCURRENCE), "soccer_spain_la_liga"
        )
        assert recovered == SPECIMEN_KICKOFF + timedelta(hours=1)


class TestTheGate:
    @pytest.mark.parametrize("league", sorted(KALSHI_MEASURED_SOCCER_LEAGUE_PREFIXES))
    @pytest.mark.parametrize("kind", KALSHI_SOCCER_DERIVATIVE_KINDS)
    def test_every_measured_series_carries_the_measured_excess(self, league, kind):
        ticker = f"{league}{kind}-26SEP16AAABBB"
        assert kalshi_derivative_series_excess(ticker) == KALSHI_DERIVATIVE_SERIES_EXCESS

    @pytest.mark.parametrize("league", sorted(KALSHI_MEASURED_SOCCER_LEAGUE_PREFIXES))
    def test_the_game_series_is_never_moved(self, league):
        assert kalshi_derivative_series_excess(f"{league}GAME-26SEP16AAABBB") == timedelta(0)

    @pytest.mark.parametrize(
        "ticker",
        [
            # The sports this constant is MEASURED to be wrong about. An NFL
            # spread's expected expiration tracks a game that can run long; a
            # fight card's tracks a card that does. Inheriting soccer's hour into
            # them is the exact mistake the pad's own docstring refuses.
            "KXNFLSPREAD-26SEP16KCBUF",
            "KXNBATOTAL-26SEP16BOSLAL",
            "KXUFCFIGHT-26SEP08LOUNAT",
            "KXMLBTOTAL-26SEP16NYYBOS",
            # Unmeasured soccer leagues: left alone, not asserted to be zero.
            "KXUCLTOTAL-26SEP16RMABAR",
            "KXBUNDESSPREAD-26SEP16BAYDOR",
        ],
    )
    def test_an_unmeasured_series_is_left_exactly_as_it_is(self, ticker):
        assert kalshi_derivative_series_excess(ticker) == timedelta(0)

    def test_membership_is_equality_not_a_prefix(self):
        """A longer series that merely OPENS with a measured name is a miss.

        A `startswith` here would reach any future `KXEPLTOTAL…` shape the venue
        invents, on a measurement taken of a different market.
        """
        assert kalshi_derivative_series_excess("KXEPLTOTALCORNERS-26SEP16ARSTOT") == timedelta(0)

    @pytest.mark.parametrize("ticker", [None, "", "KXLALIGATOTAL", 17, b"KXEPLTOTAL-2"])
    def test_a_ticker_it_cannot_read_moves_nothing(self, ticker):
        assert kalshi_derivative_series_excess(ticker) == timedelta(0)


class TestTheNormaliserLeavesEverythingElseAlone:
    def test_a_polymarket_row_is_untouched(self):
        """Gated on the SOURCE, not the ticker shape: Polymarket has no ticker,
        and #6073 gave that arm its own venue instant one guard over."""
        poly = _Market("0xabc", SPECIMEN_DERIV_OCCURRENCE, source="polymarket")
        assert kalshi_game_scale_commence(poly) == SPECIMEN_DERIV_OCCURRENCE

    def test_a_missing_commence_time_is_returned_unchanged(self):
        """`None` must survive: the caller's next line tests it and substitutes
        `now`. Returning a datetime here would invent a start for a market that
        has none."""
        assert kalshi_game_scale_commence(_Market("KXLALIGATOTAL-26SEP16LEVATH", None)) is None

    def test_a_non_datetime_commence_time_is_returned_unchanged(self):
        m = _Market("KXLALIGATOTAL-26SEP16LEVATH", "2026-09-16T23:30:00Z")
        assert kalshi_game_scale_commence(m) == "2026-09-16T23:30:00Z"

    def test_a_market_with_no_ticker_at_all_is_returned_unchanged(self):
        m = _Market(None, SPECIMEN_DERIV_OCCURRENCE)
        assert kalshi_game_scale_commence(m) == SPECIMEN_DERIV_OCCURRENCE

    def test_it_only_ever_moves_a_row_EARLIER(self):
        """The excess is subtracted. A normalisation that moved a kick-off later
        would push a live game into the future and re-open #5896's withdrawal."""
        for kind in KALSHI_SOCCER_DERIVATIVE_KINDS:
            m = _Market(f"KXEPL{kind}-26SEP16ARSTOT", SPECIMEN_DERIV_OCCURRENCE)
            assert kalshi_game_scale_commence(m) < SPECIMEN_DERIV_OCCURRENCE

    def test_it_is_idempotent_in_value_terms_only_when_reapplied_to_its_output(self):
        """🔴 IT IS NOT IDEMPOTENT, AND THAT IS RECORDED RATHER THAN HIDDEN.

        The function keys on the TICKER, which it does not change, so handing it
        its own output with the same ticker subtracts a second hour — the same
        shape as the ladder `KALSHI_RECOVERY_STAMP` exists to stop. It is safe
        here because it has exactly one caller and that caller applies it once to
        a value read straight off the row. Any second caller owes a stamp.
        """
        m = _Market("KXLALIGATOTAL-26SEP16LEVATH", SPECIMEN_DERIV_OCCURRENCE)
        once = kalshi_game_scale_commence(m)
        m.commence_time = once
        assert kalshi_game_scale_commence(m) == once - KALSHI_DERIVATIVE_SERIES_EXCESS


class TestTheCallSite:
    """A helper is not a call site (ruling 102, obligation 4).

    Everything above tests two pure functions and would still pass if nothing
    ever called them. These drive the real `_create_event_from_prediction_market`
    and read the `EventIdentity` the registry is actually handed — delete the
    normalisation at the call site and only these go red.
    """

    @staticmethod
    def _market(ticker, commence):
        m = _Market(ticker, commence)
        m.name = "Levante vs Bilbao: Total Goals"
        m.llm_sport_category = "soccer"
        m.id = 60636796
        return m

    class _Matchup:
        def __init__(self, team_a, team_b):
            self.team_a = team_a
            self.team_b = team_b

    async def _identity_for(self, monkeypatch, ticker, commence):
        import app.services.event_registry as registry
        import app.tasks.prediction_market_matching as pmm

        seen = {}

        async def _capture(session, identity):
            seen["identity"] = identity
            raise ValueError("stop here — the identity is what this test reads")

        monkeypatch.setattr(registry, "find_or_create_event", _capture)
        # Not under test, and both would need a live session: the league
        # resolvers that decide whether to refuse or relabel. Neither touches the
        # clock, which is the only field these tests read.
        async def _no_covered_league(*a, **kw):
            return None

        async def _no_placement(*a, **kw):
            return None

        monkeypatch.setattr(pmm, "covered_league_for_matchup", _no_covered_league)
        monkeypatch.setattr(pmm, "placeable_league_for_matchup", _no_placement)

        await pmm._create_event_from_prediction_market(
            None,
            self._Matchup("Levante", "Bilbao"),
            self._market(ticker, commence),
            datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
        )
        return seen.get("identity")

    @pytest.mark.asyncio
    async def test_the_minted_row_carries_the_game_clock(self, monkeypatch):
        """THE ONE THAT WOULD HAVE CAUGHT #6715.

        The row `15312871` was written at 23:30Z from exactly this market. It
        must now be written at 22:30Z, which the 180-minute pad recovers to the
        true 19:30Z kick-off.
        """
        identity = await self._identity_for(
            monkeypatch, "KXLALIGATOTAL-26SEP16LEVATH", SPECIMEN_DERIV_OCCURRENCE
        )
        assert identity is not None, "the call site never reached the registry"
        assert identity.commence_time == SPECIMEN_GAME_OCCURRENCE

    @pytest.mark.asyncio
    async def test_a_game_series_mint_is_unchanged(self, monkeypatch):
        """The control. If this moved too, the ship would be re-timing the
        population that was already correct."""
        identity = await self._identity_for(
            monkeypatch, "KXLALIGAGAME-26SEP16LEVATH", SPECIMEN_GAME_OCCURRENCE
        )
        assert identity is not None
        assert identity.commence_time == SPECIMEN_GAME_OCCURRENCE

    @pytest.mark.asyncio
    async def test_ruling_048_is_untouched(self, monkeypatch):
        """This ship re-times a claim; it does not anchor one. An id-less claim
        still CREATES rather than absorbing (gotcha #32)."""
        identity = await self._identity_for(
            monkeypatch, "KXLALIGATOTAL-26SEP16LEVATH", SPECIMEN_DERIV_OCCURRENCE
        )
        assert identity.claim.schedule_derived is False


class TestTheConstants:
    def test_the_pad_is_not_widened_by_this_ship(self):
        """The whole point: #6715's 240-minute rows are explained WITHOUT
        touching the pad. If this ever reads 4h, the exact recovery is gone."""
        assert KALSHI_EXPECTED_EXPIRATION_PAD == timedelta(hours=3)

    def test_the_excess_is_the_measured_hour(self):
        assert KALSHI_DERIVATIVE_SERIES_EXCESS == timedelta(minutes=60)

    def test_the_two_constants_reconstruct_the_derivative_pad(self):
        """240 minutes is not a constant anywhere in the code, and must not
        become one — it is the sum, which is why nothing needs to widen."""
        assert KALSHI_EXPECTED_EXPIRATION_PAD + KALSHI_DERIVATIVE_SERIES_EXCESS == timedelta(
            minutes=240
        )
