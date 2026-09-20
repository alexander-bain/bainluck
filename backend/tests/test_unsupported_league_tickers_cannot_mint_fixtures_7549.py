"""#7549 — a league we declare unsupported may not mint fixtures by NAME either.

#3446 / CERT-2055 closed the auto-create writer against the 73 Kalshi soccer
cup/continental PROP prefixes, and its own docstring names the mechanism: Kalshi
writes a leg as "Toluca vs Leon: Regulation Time Spread", the COLON defeats
`is_derivative_market_name` (which refuses only a DASH-introduced suffix, #2871),
the name parses as a clean matchup, no candidate event is found, and the leg
reaches `find_or_create_event` and MINTS a fixture. The claim is id-less, so it
can never absorb (ruling 048 / gotcha #32) — one tie becomes one fixture PER LEG.

The gap this file guards: Pass 1 is subtracted by `_CLASSIFICATION_ONLY_PREFIXES`,
which is that cup dict UNION the 29 `_UNSUPPORTED_LEAGUE_PREFIXES`. The Pass-2
guard read only the cup half. So the 29 were closed at Pass 1 and left OPEN at
Pass 2, and #3446's failure mode ran on them verbatim.

Measured on production 2026-09-20 (`db-query`, read-only), 7 days of rows carrying
`commence_time_source IN ('kalshi','kalshi_ticker')`: **1,206 rows, of which 11
fixtures held 141.** The worst was Feyenoord v FC Utrecht at **57 rows for one
match**. The eight Eredivisie legs below all carry the same game token
`26SEP20FEYFCU`, and every one of them held a `market`-kind anchor — never a
`game` one — so cascade Step 2 could not see the row its sibling had just made.

What a reader met (the ship): searching "feyenoord" claimed 63 games, rendered 8
across three pages, and page 2 led with a ● LIVE card for the match that had
finished 5–0 four hours earlier.

The specimens are written literally. Deriving them from the prefix maps would make
the test agree with production by construction and assert nothing.
"""

from datetime import datetime, timezone

import pytest

# A fixed anchor. No branch on the clock (gotcha #44): every arm offsets from this.
_NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)

#: The eight real Kalshi legs of Feyenoord v FC Utrecht, read off
#: `event_provider_anchors` on 2026-09-20 with the event row each one minted.
#: Every ticker shares the game token `26SEP20FEYFCU`; every anchor was
#: `id_kind='market'`, which is why none of them could find the others.
FEYENOORD_LEGS = [
    ("KXEREDIVISIETOTAL-26SEP20FEYFCU", 15315219),
    ("KXEREDIVISIESPREAD-26SEP20FEYFCU", 15315220),
    ("KXEREDIVISIEBTTS-26SEP20FEYFCU", 15315221),
    ("KXEREDIVISIE1HTOTAL-26SEP20FEYFCU", 15315222),
    ("KXEREDIVISIE1HSPREAD-26SEP20FEYFCU", 15315223),
    ("KXEREDIVISIE1HBTTS-26SEP20FEYFCU", 15315224),
    ("KXEREDIVISIEGAME-26SEP20FEYFCU", 15315236),
    ("KXEREDIVISIE1H-26SEP20FEYFCU", 15315237),
]

#: The market name shape that defeats every other gate. Kalshi's own wording.
FEYENOORD_NAME = "Feyenoord vs Utrecht: Regulation Time Spread"

#: Real game tickers from leagues we DO ingest. These must keep creating — the
#: repair is a refusal, and a refusal that over-fires is the failure mode with no
#: symptom until a real fixture goes missing.
REAL_GAME_TICKERS = [
    "KXSERIEAGAME-26SEP19ROMINT",
    "KXNFLGAME-26SEP21KCPHI",
    "KXEPLGAME-26SEP20ARSMCI",
    "KXMLBGAME-26SEP20NYYBOS",
]


class TestThePredicateReadsTheSetTheSubtractionReads:
    """The anti-drift property, stated over the UNION rather than one half."""

    def test_every_prefix_pass_1_subtracts_is_refused_at_pass_2(self):
        """This is the arm that fails on the pre-fix SHA, for 29 of 102."""
        from app.utils.sport_keys import (
            _CLASSIFICATION_ONLY_PREFIXES,
            is_classification_only_ticker,
        )

        missed = [
            p for p in _CLASSIFICATION_ONLY_PREFIXES
            if not is_classification_only_ticker(f"{p.upper()}-26SEP20AAABBB")
        ]
        assert not missed, (
            f"{len(missed)} prefixes are subtracted from Pass 1 but still "
            f"auto-create at Pass 2: {sorted(missed)[:8]}"
        )

    def test_the_unsupported_league_half_is_the_half_that_was_open(self):
        """Named separately so the regression stays legible after the union arm.

        `_UNSUPPORTED_LEAGUE_PREFIXES` is the set whose own comment says "we
        ingest NO events for these leagues". A prefix that cannot link is the
        last one that should be allowed to invent a fixture.
        """
        from app.utils.sport_keys import (
            _UNSUPPORTED_LEAGUE_PREFIXES,
            is_classification_only_ticker,
        )

        assert len(_UNSUPPORTED_LEAGUE_PREFIXES) == 29, (
            "the set moved — re-measure the population before editing this bound"
        )
        open_prefixes = [
            p for p in _UNSUPPORTED_LEAGUE_PREFIXES
            if not is_classification_only_ticker(f"{p.upper()}-26SEP20AAABBB")
        ]
        assert not open_prefixes, sorted(open_prefixes)

    def test_3446s_own_dict_is_not_regressed_by_widening(self):
        """The narrower predicate keeps its contract; #3446's tests still bind."""
        from app.utils.sport_keys import (
            _SOCCER_CUP_PROP_TICKER_TO_SPORT_KEY,
            is_classification_only_soccer_prop_ticker,
        )

        missed = [
            p for p in _SOCCER_CUP_PROP_TICKER_TO_SPORT_KEY
            if not is_classification_only_soccer_prop_ticker(
                f"{p.upper()}-26SEP20AAABBB"
            )
        ]
        assert not missed, f"narrow predicate regressed: {missed[:5]}"


class TestTheRefusalDoesNotOverFire:
    """A refusal is only safe while it still lets real fixtures through."""

    @pytest.mark.parametrize("ticker", REAL_GAME_TICKERS)
    def test_a_real_game_ticker_is_never_classification_only(self, ticker):
        from app.utils.sport_keys import (
            is_classification_only_ticker,
            is_kalshi_game_level_ticker,
        )

        assert not is_classification_only_ticker(ticker)
        # The pair that matters: refused-at-Pass-2 and game-level-at-Pass-1 must
        # stay opposites for a league we ingest, or a real fixture goes missing.
        assert is_kalshi_game_level_ticker(ticker)

    def test_a_strictly_longer_game_prefix_still_wins(self):
        """Longest prefix wins, asserted through the shared body.

        No real pair has this shape today (measured 2026-09-20: 0 of the 29 have
        a longer game prefix), so this drives the helper directly rather than
        pretending to find a specimen. It guards the rule, not a row: the day a
        women's or second-tier league is mapped as its own game prefix, its legs
        must create normally even though the parent prefix is classification-only.
        """
        from app.utils.sport_keys import _is_classification_only_against

        # `kxeredivisie` is classification-only; a hypothetical longer real game
        # prefix extending it must beat it on length.
        assert _is_classification_only_against(
            "KXEREDIVISIEGAME-26SEP20FEYFCU", {"kxeredivisie"}
        )
        assert not _is_classification_only_against(
            "KXNFLGAME-26SEP21KCPHI", {"kxnfl"}
        ), "a longer real game prefix (kxnflgame) must outrank a shorter candidate"

    def test_an_empty_or_unmapped_ticker_is_not_refused(self):
        from app.utils.sport_keys import is_classification_only_ticker

        assert not is_classification_only_ticker(None)
        assert not is_classification_only_ticker("")
        assert not is_classification_only_ticker("KXNOTATICKER-26SEP20AAABBB")


class TestTheFeyenoordLegsMintNothing:
    """The named sample, proved at the writer.

    ``session=None`` is the whole assertion. The refusal has to land BEFORE
    anything reaches ``find_or_create_event``; a refusal that happened after it
    would already have written the row. On the pre-fix SHA these raise instead of
    returning None, which is what makes the arm non-vacuous.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("ticker,minted_event_id", FEYENOORD_LEGS)
    async def test_each_leg_that_minted_a_row_now_mints_none(
        self, ticker, minted_event_id,
    ):
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )
        from app.utils.prediction_market_matching import extract_matchup

        matchup = extract_matchup(FEYENOORD_NAME)
        assert matchup is not None, (
            "the specimen name no longer parses as a matchup — if Kalshi changed "
            "its wording, pick a current one; do NOT weaken the arm"
        )

        result = await _create_event_from_prediction_market(
            None, matchup, _KalshiMarket(ticker, FEYENOORD_NAME), _NOW,
        )
        assert result is None, (
            f"{ticker} still mints a fixture; on production it minted "
            f"event {minted_event_id}"
        )

    @pytest.mark.asyncio
    async def test_every_unsupported_prefix_is_refused_at_the_writer(self):
        """The boundary is the SET, so the guard covers all of it at the writer.

        The predicate arms above test the rule; this tests that the writer asks
        it. A guard wired to the wrong predicate passes every unit arm.
        """
        from app.tasks.prediction_market_matching import (
            _create_event_from_prediction_market,
        )
        from app.utils.prediction_market_matching import extract_matchup
        from app.utils.sport_keys import _UNSUPPORTED_LEAGUE_PREFIXES

        matchup = extract_matchup(FEYENOORD_NAME)
        minted = []
        for prefix in sorted(_UNSUPPORTED_LEAGUE_PREFIXES):
            ticker = f"{prefix.upper()}-26SEP20FEYFCU"
            try:
                result = await _create_event_from_prediction_market(
                    None, matchup, _KalshiMarket(ticker, FEYENOORD_NAME), _NOW,
                )
            except Exception as exc:  # reached the registry with a None session
                minted.append((prefix, type(exc).__name__))
                continue
            if result is not None:
                minted.append((prefix, "created"))
        assert not minted, (
            f"{len(minted)} unsupported-league prefixes still reach the "
            f"registry: {minted[:5]}"
        )


class _KalshiMarket:
    """The fields `_create_event_from_prediction_market` reads, and no others."""

    def __init__(self, external_id, name):
        self.source = "kalshi"
        self.external_id = external_id
        self.name = name
        self.llm_sport_category = "soccer"
        self.commence_time = _NOW
