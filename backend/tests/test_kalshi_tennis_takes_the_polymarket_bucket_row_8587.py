"""#8587 — a Kalshi tennis market links to the Polymarket row for its match
instead of minting a surname-only second row beside it.

Production, 2026-09-24 06:52Z: `KXATPMATCH-26SEP25MEDROY` ("Medvedev vs Royer")
retrieved event 15318217 ("Daniil Medvedev / Valentin Royer", `tennis_other`,
minted from Polymarket 29 minutes earlier), matched BOTH sides, and refused it
with verdict `wrong_sport` — the forward path's strict sport gate read the
Polymarket catch-all bucket as a different sport from the ticker's
`tennis_atp`. The market then minted 15318222 ("Medvedev / Royer"), and the
reader got the match twice. 98 of the 125 Kalshi-later tennis twins of the
preceding 14 days carry that verdict on their mint receipt.

The decision is asserted through `_score_candidates` — the function the
matcher calls — not only on the predicate, and every relaxation is paired with
the refusal it must NOT loosen: ATP on WTA, and a team sport's bucket.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks.prediction_market_matching import (
    _FORWARD_PATH_UNCLASSIFIED_BUCKET_FAMILIES,
    _is_cross_sport_link,
    _score_candidates,
)
from app.utils.prediction_market_matching import (
    extract_game_date_from_ticker,
    extract_matchup,
)

TICKER = "KXATPMATCH-26SEP25MEDROY"
NAME = "Medvedev vs Royer"
#: When the Kalshi market was matched on production.
NOW = datetime(2026, 9, 24, 6, 52, 48, tzinfo=timezone.utc)
#: Where 15318217 stood at that moment (its mint-time venue start).
POLYMARKET_START = datetime(2026, 9, 26, 2, 0, tzinfo=timezone.utc)


def _event(eid, home, away, sport_key, commence, status="scheduled"):
    return SimpleNamespace(
        id=eid,
        sport=SimpleNamespace(key=sport_key),
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        status=status,
        external_id=None,  # both rows are id-less mints, as on production
        sport_id=37956,
    )


def _market(ticker=TICKER, name=NAME):
    return SimpleNamespace(
        external_id=ticker, name=name, source="kalshi",
        llm_sport_category="tennis", commence_time=None,
    )


def _score(candidates, ticker=TICKER, name=NAME):
    game_date = extract_game_date_from_ticker(ticker)
    assert game_date is not None, "the specimen ticker must carry its date"
    return _score_candidates(
        candidates, extract_matchup(name, ticker), _market(ticker, name),
        NOW, game_date,
    )


class TestTheSpecimenLinks:
    def test_medvedev_royer_links_to_the_polymarket_row(self):
        row = _event(
            15318217, "Daniil Medvedev", "Valentin Royer", "tennis_other",
            POLYMARKET_START,
        )
        result = _score([row])
        assert result is not None, (
            "the Kalshi market refused its own match's row and would mint a "
            "second one (#8587)"
        )
        assert result["event_id"] == 15318217

    def test_a_wta_ticker_links_to_its_bucket_row_too(self):
        """Production 2026-09-24 18:50Z: `KXWTAMATCH-26SEP25SAKGIB` refused
        15318309 the same way and minted 15318359 ("Sakkari / Gibson")."""
        ticker = "KXWTAMATCH-26SEP25SAKGIB"
        row = _event(
            15318309, "Maria Sakkari", "Talia Gibson", "tennis_other",
            datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc),
        )
        result = _score([row], ticker=ticker, name="Sakkari vs Gibson")
        assert result is not None and result["event_id"] == 15318309


class TestWhatStaysRefused:
    def test_an_atp_ticker_still_refuses_a_wta_row(self):
        """The bucket is accepted; a DIFFERENT precise tennis key is not."""
        row = _event(
            1, "Daniil Medvedev", "Valentin Royer", "tennis_wta",
            POLYMARKET_START,
        )
        assert _score([row]) is None

    def test_an_atp_ticker_still_refuses_another_sports_bucket(self):
        row = _event(
            2, "Daniil Medvedev", "Valentin Royer", "basketball_other",
            POLYMARKET_START,
        )
        assert _score([row]) is None

    def test_a_team_sport_keeps_the_strict_forward_reject(self):
        """#3478's golden-set reason is untouched: NCAAF on the football bucket."""
        assert _is_cross_sport_link(
            "americanfootball_ncaaf", "americanfootball_other",
            allow_unclassified_bucket=False,
        ) is True
        assert _is_cross_sport_link(
            "soccer_epl", "soccer_other", allow_unclassified_bucket=False,
        ) is True

    def test_only_tennis_is_carved_out(self):
        """A new family here is a new relaxation of the forward path — it owes
        its own measured case, so the set is pinned."""
        assert _FORWARD_PATH_UNCLASSIFIED_BUCKET_FAMILIES == frozenset({"tennis"})


class TestThePredicate:
    @pytest.mark.parametrize("market_sport", ["tennis_atp", "tennis_wta"])
    def test_tennis_bucket_is_not_cross_sport_on_either_path(self, market_sport):
        for allow in (False, True):
            assert _is_cross_sport_link(
                market_sport, "tennis_other", allow_unclassified_bucket=allow,
            ) is False

    def test_tennis_precise_keys_still_disagree(self):
        for allow in (False, True):
            assert _is_cross_sport_link(
                "tennis_atp", "tennis_wta", allow_unclassified_bucket=allow,
            ) is True
