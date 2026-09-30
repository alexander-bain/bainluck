"""#9752 — /sports showed the LPGA LOTTE Championship twice, with two favourites.

Production, 2026-09-30 ~06:58Z. `/api/golf` served one tournament (Oct 1-4) as two:

    lotte_championship_presented_by_hoakalei  kalshi      25 golfers  Jeeno Thitikul 12.5%
    lotte_championship_womens                 polymarket  82 golfers  Miyu Yamashita 12.0%

Kalshi titles it "LOTTE Championship presented by Hoakalei Winner" and says LPGA
only in its ticker (`KXLPGATOUR-LOTCPBH26`); Polymarket titles it "LPGA: LOTTE
Championship Winner". The sponsor tail and the `_womens` suffix put the two venues
on two keys, and nothing folded them: PGA events fold through the DataGolf
schedule, and LPGA is deliberately not on it. Both cards already shared ONE slug,
`lotte-championship`.

The golfer names disagree too: Polymarket "Hyo-Joo Kim" / "A-Lim Kim" / "Atthaya
Thitikul", Kalshi "Hyo Joo Kim" / "A Lim Kim" / "Jeeno Thitikul" — one merged card
would otherwise list the same golfer twice.

The fixtures below are the production rows (ids, names, tickers, dates) with the
top of each winner field at its served price.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import golf as golf_route
from app.routes.golf import (
    _fold_sponsor_split_tournaments,
    _match_key,
    get_golf,
)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


_OID = iter(range(1, 10_000))


def _outcome(name, prob):
    return SimpleNamespace(
        id=next(_OID),
        name=name,
        current_probability=prob,
        current_yes_bid=round(prob - 0.005, 4),
        current_yes_ask=round(prob + 0.005, 4),
        opening_probability=None,
        probability_change_24h=None,
    )


def _market(mid, name, source, external_id, outcomes, *, commence, resolves):
    return SimpleNamespace(
        id=mid,
        name=name,
        source=source,
        external_id=external_id,
        outcomes=outcomes,
        commence_time=_dt(commence),
        resolution_date=_dt(resolves),
        status="open",
        llm_sport_category="golf",
        market_tier=1,
        market_metadata=None,
    )


def _kalshi_lotte():
    return _market(
        63115883,
        "LOTTE Championship presented by Hoakalei Winner",
        "kalshi",
        "KXLPGATOUR-LOTCPBH26",
        [
            _outcome("Jeeno Thitikul", 0.125),
            _outcome("Miyu Yamashita", 0.11),
            _outcome("A Lim Kim", 0.09),
            _outcome("Hyo Joo Kim", 0.077),
            _outcome("Nasa Hataoka", 0.037),
        ],
        commence="2026-10-18 04:00:00",
        resolves="2026-10-04 04:00:00",
    )


def _polymarket_lotte():
    return _market(
        63045538,
        "LPGA: LOTTE Championship Winner",
        "polymarket",
        "1098291",
        [
            _outcome("Miyu Yamashita", 0.12),
            _outcome("Atthaya Thitikul", 0.115),
            _outcome("Hyo-Joo Kim", 0.083),
            _outcome("A-Lim Kim", 0.042),
            _outcome("Akie Iwai", 0.037),
        ],
        commence="2026-09-28 15:03:39",
        resolves="2026-10-05 03:59:00",
    )


def _db(markets):
    markets_result = MagicMock()
    markets_result.scalars.return_value.unique.return_value.all.return_value = markets
    empty = MagicMock()
    empty.__iter__ = lambda self: iter(())
    session = AsyncMock()
    calls = {"n": 0}

    async def _execute(*_args, **_kwargs):
        calls["n"] += 1
        return markets_result if calls["n"] == 1 else empty

    session.execute.side_effect = _execute
    return session


@pytest.fixture(autouse=True)
def _no_schedule(monkeypatch):
    async def _empty():
        return []

    monkeypatch.setattr("app.routes.golf._get_golf_schedule", _empty)


def _lotte_cards(body):
    return [t for t in body["tournaments"] if "lotte" in t["key"]]


def _golfer(card, key):
    rows = [g for g in card["_all_golfers"] if _match_key(g["name"]) == key]
    assert len(rows) == 1, (key, [g["name"] for g in card["_all_golfers"]])
    return rows[0]


class TestTheBeforeReproduces:
    """Vacuity companion: with the fold removed, the specimen IS the defect."""

    async def test_without_the_fold_the_two_venues_are_two_cards(self, monkeypatch):
        monkeypatch.setattr(
            golf_route, "_fold_sponsor_split_tournaments", lambda tm: (tm, {})
        )
        body = await get_golf(_db([_kalshi_lotte(), _polymarket_lotte()]))
        cards = _lotte_cards(body)
        assert sorted(c["key"] for c in cards) == [
            "lotte_championship_presented_by_hoakalei",
            "lotte_championship_womens",
        ]
        favourites = {c["key"]: c["_all_golfers"][0]["name"] for c in cards}
        assert favourites["lotte_championship_presented_by_hoakalei"] == "Jeeno Thitikul"
        assert favourites["lotte_championship_womens"] == "Miyu Yamashita"


class TestTheShip:
    async def test_one_lotte_card_carrying_both_venues(self):
        body = await get_golf(_db([_kalshi_lotte(), _polymarket_lotte()]))
        cards = _lotte_cards(body)
        assert len(cards) == 1, [c["key"] for c in cards]
        card = cards[0]
        assert card["key"] == "lotte_championship_womens"
        assert card["name"] == "LOTTE Championship"
        assert card["is_womens"] is True
        assert card["tour"] == "lpga"
        assert sorted(card["market_ids"]) == [63045538, 63115883]
        assert sorted(set(card["market_sources"])) == ["kalshi", "polymarket"]

    async def test_each_golfer_is_one_row_blending_both_venues(self):
        body = await get_golf(_db([_kalshi_lotte(), _polymarket_lotte()]))
        card = _lotte_cards(body)[0]
        for key in ("jeeno thitikul", "hyojoo kim", "alim kim", "miyu yamashita"):
            assert set(_golfer(card, key)["sources"]) == {"kalshi", "polymarket"}, key
        # One number per question: Thitikul is the mean of 12.5% and 11.5%.
        assert _golfer(card, "jeeno thitikul")["probability"] == pytest.approx(0.12)
        # Single-venue golfers keep their row.
        assert set(_golfer(card, "nasa hataoka")["sources"]) == {"kalshi"}
        assert set(_golfer(card, "akie iwai")["sources"]) == {"polymarket"}
        names = [g["name"] for g in card["_all_golfers"]]
        assert len(names) == 6, names


class TestGolferNameFolding:
    @pytest.mark.parametrize(
        "polymarket,kalshi",
        [
            ("Hyo-Joo Kim", "Hyo Joo Kim"),
            ("A-Lim Kim", "A Lim Kim"),
            ("Jin-Hee Im", "Jin Hee Im"),
            ("In-Gee Chun", "In Gee Chun"),
            ("Atthaya Thitikul", "Jeeno Thitikul"),
            ("Kim, Si Woo", "Si Woo Kim"),
        ],
    )
    def test_one_golfer_one_key(self, polymarket, kalshi):
        assert _match_key(polymarket) == _match_key(kalshi)

    @pytest.mark.parametrize(
        "a,b",
        [
            ("Hyo Joo Kim", "A Lim Kim"),
            ("Grace Kim", "Auston Kim"),
            ("Jin Young Ko", "Lydia Ko"),
        ],
    )
    def test_different_golfers_stay_apart(self, a, b):
        assert _match_key(a) != _match_key(b)

    def test_two_token_names_are_untouched(self):
        assert _match_key("Scottie Scheffler") == "scottie scheffler"
        assert _match_key("J. Spaun") == "j spaun"


def _group(*markets):
    return list(markets)


def _named(name, source, external_id, resolves="2026-10-04 04:00:00"):
    return _market(
        1, name, source, external_id, [],
        commence="2026-09-28 00:00:00", resolves=resolves,
    )


class TestTheFoldRefuses:
    """What the fold keeps OUT, each beside the case it lets in."""

    def test_the_specimen_folds(self):
        folded, aliases = _fold_sponsor_split_tournaments({
            "lotte_championship_presented_by_hoakalei": _group(_kalshi_lotte()),
            "lotte_championship_womens": _group(_polymarket_lotte()),
        })
        assert list(folded) == ["lotte_championship_womens"]
        assert aliases == {"lotte_championship_presented_by_hoakalei": "lotte_championship_womens"}

    def test_a_mens_event_never_folds_into_a_womens_event_of_the_same_name(self):
        folded, aliases = _fold_sponsor_split_tournaments({
            "foo_championship_presented_by_bar": _group(
                _named("Foo Championship presented by Bar Winner", "kalshi", "KXPGATOUR-FOO26")
            ),
            "foo_championship_womens": _group(
                _named("LPGA: Foo Championship Winner", "polymarket", "1")
            ),
        })
        assert aliases == {}
        assert len(folded) == 2

    def test_an_undeclared_group_never_joins_a_womens_group(self):
        """Absence of a tour is not evidence of the LPGA."""
        folded, aliases = _fold_sponsor_split_tournaments({
            "foo_championship_presented_by_bar": _group(
                _named("Foo Championship presented by Bar Winner", "polymarket", "2")
            ),
            "foo_championship_womens": _group(
                _named("LPGA: Foo Championship Winner", "polymarket", "1")
            ),
        })
        assert aliases == {}

    def test_two_tours_on_one_core_never_fold(self):
        folded, aliases = _fold_sponsor_split_tournaments({
            "foo_masters_presented_by_bar": _group(
                _named("Foo Masters presented by Bar Winner", "kalshi", "KXDPWORLDTOUR-FOO26")
            ),
            "foo_masters": _group(
                _named("Korn Ferry Tour: Foo Masters Winner", "polymarket", "1")
            ),
        })
        assert aliases == {}

    def test_same_name_a_season_apart_never_folds(self):
        folded, aliases = _fold_sponsor_split_tournaments({
            "lotte_championship_presented_by_hoakalei": _group(_kalshi_lotte()),
            "lotte_championship_womens": _group(
                _named("LPGA: LOTTE Championship Winner", "polymarket", "1",
                       resolves="2027-10-04 04:00:00")
            ),
        })
        assert aliases == {}

    def test_a_generic_core_never_folds(self):
        folded, aliases = _fold_sponsor_split_tournaments({
            "championship_presented_by_bar": _group(
                _named("Championship presented by Bar Winner", "kalshi", "KXLPGATOUR-X")
            ),
            "championship_womens": _group(
                _named("LPGA: Championship Winner", "polymarket", "1")
            ),
        })
        assert aliases == {}

    def test_same_tour_sponsor_split_folds_without_a_womens_suffix(self):
        """Control for the gender rule: two men's spellings of one event DO fold."""
        folded, aliases = _fold_sponsor_split_tournaments({
            "foo_classic_presented_by_bar": _group(
                _named("Foo Classic presented by Bar Winner", "kalshi", "KXPGATOUR-FOO26")
            ),
            "foo_classic": _group(_named("Foo Classic Winner", "polymarket", "1")),
        })
        assert aliases == {"foo_classic_presented_by_bar": "foo_classic"}

    def test_the_survivor_does_not_depend_on_market_order(self):
        a = {
            "lotte_championship_womens": _group(_polymarket_lotte()),
            "lotte_championship_presented_by_hoakalei": _group(_kalshi_lotte()),
        }
        folded, _ = _fold_sponsor_split_tournaments(a)
        assert list(folded) == ["lotte_championship_womens"]
