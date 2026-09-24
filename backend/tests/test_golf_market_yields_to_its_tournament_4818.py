"""A golf winner market yields its slot to the tournament card that blends it (#4818).

Served on production ``/api/feed?limit=40&event_pct=0.15``, 2026-09-24 18:2xZ:

    slot 8   tournament  FedEx Open de France   Matthew Fitzpatrick 19%
    slot 18  futures     61814765 "DP World Tour: Open de France Winner"
                                                Matthew Fitzpatrick 17%

The tournament card's ``market_ids`` carried 61814765: the second card was one of
the first card's own inputs, at one source's number. The fifteen markets and names
below are that tournament's, read from ``futures_markets`` the same minute.

The harness drives the REAL ``_score_golf_tournaments`` over a stubbed golf base
(as ``test_golf_card_leader_needs_the_field_8334.py`` does) and the REAL
``apply_discover_display_chain``.
"""

import asyncio
from datetime import datetime, timedelta, timezone

#: Gotcha #44 — offset from the clock, never a literal date.
_FEED_NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)

#: FedEx Open de France on production, 2026-09-24 — (id, name) in base order.
_OPEN_DE_FRANCE_MARKETS = [
    (61814770, "DP World Tour: Open de France Top 5"),
    (61814764, "DP World Tour: Open de France First Round Leader"),
    (61814765, "DP World Tour: Open de France Winner"),
    (61814766, "DP World Tour: Open de France Albatross?"),
    (61814762, "DP World Tour: Open de France Third Round Leader"),
    (61814769, "DP World Tour: Open de France Top 10"),
    (61814763, "DP World Tour: Open de France Second Round Leader"),
    (61814767, "DP World Tour: Open de France Hole in One?"),
    (61461681, "FedEx Open de France Winner"),
    (61814768, "DP World Tour: Open de France Top 20"),
    (61720782, "FedEx Open de France - Winner"),
    (61720785, "FedEx Open de France - Top 20 Finish"),
    (61720784, "FedEx Open de France - Top 10 Finish"),
    (61720783, "FedEx Open de France - Top 5 Finish"),
    (61720786, "FedEx Open de France - Make the Cut"),
]
_WINNER_FIELDS = {61814765, 61461681, 61720782}


def _golfers(n: int = 144, leader: float = 0.19) -> list[dict]:
    rest = (1.0 - leader) / (n - 1)
    probs = [leader] + [rest] * (n - 1)
    return [
        {
            "id": i + 1,
            "name": "Matthew Fitzpatrick" if i == 0 else f"Golfer {i + 1}",
            "probability": p,
            "movement_24h": None,
            "movement_is_dated": False,
            "rank": i + 1,
        }
        for i, p in enumerate(probs)
    ]


def _tournament(markets=_OPEN_DE_FRANCE_MARKETS, names=None) -> dict:
    golfers = _golfers()
    return {
        "key": "fedex_open_de_france",
        "name": "FedEx Open de France",
        "slug": "fedex-open-de-france",
        "tour": "dp_world",
        "tour_label": "DP World Tour",
        "is_major": False,
        "is_tour_event": True,
        "commence_time": (_FEED_NOW - timedelta(hours=3)).isoformat(),
        "resolution_date": (_FEED_NOW + timedelta(days=3)).isoformat(),
        "start_date": (_FEED_NOW - timedelta(hours=3)).isoformat(),
        "end_date": (_FEED_NOW + timedelta(days=3)).isoformat(),
        "market_ids": [mid for mid, _ in markets],
        "market_names": names if names is not None else [n for _, n in markets],
        "market_sources": ["polymarket", "kalshi", "datagolf"],
        "golfers": golfers[:15],
        "_all_golfers": golfers,
    }


def _tournament_items(monkeypatch, tournament: dict) -> list[dict]:
    import app.utils.golf_base as golf_base
    from app.routes import feed as feed_module

    async def _fake_base(db, now, stages=None):
        return ([tournament], "fresh")

    monkeypatch.setattr(golf_base, "get_golf_base", _fake_base)
    return asyncio.run(feed_module._score_golf_tournaments(None, _FEED_NOW, None, None))


def _futures(market_id: int, name: str, score: float = 42) -> dict:
    return {
        "type": "futures",
        "score": score,
        "reason": f"{name} reason",
        "headline": f"{name} headline",
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": "golf",
            "market_type": "field",
            "top_outcomes": [
                {"id": market_id * 10, "name": "Matthew Fitzpatrick", "probability": 0.17},
            ],
        },
    }


def _served_ids(items: list[dict]) -> set[int]:
    from app.routes.feed import PersonalizationContext, apply_discover_display_chain

    out, _meta = apply_discover_display_chain(
        items,
        limit=40,
        ctx=PersonalizationContext(),
        event_pct=0.15,
        now=_FEED_NOW,
    )
    return {it["data"]["id"] for it in out if it.get("type") == "futures"}


def _pool(monkeypatch, tournament=None, markets=_OPEN_DE_FRANCE_MARKETS) -> list[dict]:
    tournament_items = (
        _tournament_items(monkeypatch, tournament) if tournament is not None else []
    )
    return tournament_items + [_futures(mid, name) for mid, name in markets]


def _kept_ids(items: list[dict]) -> set[int]:
    """The drop alone — the chain's first step, before any cap can confound it."""
    from app.routes.feed import _drop_futures_blended_into_tournaments

    return {
        it["data"]["id"]
        for it in _drop_futures_blended_into_tournaments(items)
        if it.get("type") == "futures"
    }


#: The served specimen alone, so no family cap can decide its fate.
_SPECIMEN = [(61814765, "DP World Tour: Open de France Winner")]


class TestTheProductionSpecimen:
    def test_the_tournament_card_is_built(self, monkeypatch):
        items = _tournament_items(monkeypatch, _tournament())
        assert len(items) == 1
        assert items[0]["type"] == "tournament"

    def test_its_blend_is_exactly_the_three_winner_fields(self, monkeypatch):
        (item,) = _tournament_items(monkeypatch, _tournament())
        assert item["_blended_market_ids"] == frozenset(_WINNER_FIELDS)

    def test_the_drop_removes_the_three_winner_fields(self, monkeypatch):
        kept = _kept_ids(_pool(monkeypatch, _tournament()))
        assert kept.isdisjoint(_WINNER_FIELDS)

    def test_61814765_is_not_served_beside_its_tournament(self, monkeypatch):
        assert 61814765 not in _served_ids(_pool(monkeypatch, _tournament(), _SPECIMEN))

    def test_control_61814765_is_served_when_no_tournament_card_is(self, monkeypatch):
        # Without this arm the test above passes for any reason the chain drops it.
        assert 61814765 in _served_ids(_pool(monkeypatch, None, _SPECIMEN))

    def test_the_tournament_card_itself_is_still_served(self, monkeypatch):
        from app.routes.feed import PersonalizationContext, apply_discover_display_chain

        out, _ = apply_discover_display_chain(
            _pool(monkeypatch, _tournament(), _SPECIMEN),
            limit=40,
            ctx=PersonalizationContext(),
            event_pct=0.15,
            now=_FEED_NOW,
        )
        assert [it["data"]["key"] for it in out if it["type"] == "tournament"] == [
            "fedex_open_de_france"
        ]


class TestOtherQuestionsKeepTheirCards:
    """Control: only the winner fields go. Top-N, cut, round-leader and the yes/no
    props are different questions, and the tournament card does not answer them."""

    def test_every_non_winner_market_is_kept(self, monkeypatch):
        kept = _kept_ids(_pool(monkeypatch, _tournament()))
        non_winner = {mid for mid, _ in _OPEN_DE_FRANCE_MARKETS} - _WINNER_FIELDS
        assert len(non_winner) == 12
        assert kept == non_winner

    def test_the_albatross_yes_no_market_is_not_counted_as_blended(self, monkeypatch):
        # Passes golf's `_NON_WINNER_MARKET_RE`; only the "winner" word keeps it out.
        from app.routes.golf import _NON_WINNER_MARKET_RE

        assert not _NON_WINNER_MARKET_RE.search("DP World Tour: Open de France Albatross?")
        (item,) = _tournament_items(monkeypatch, _tournament())
        assert 61814766 not in item["_blended_market_ids"]

    def test_nationality_of_winner_is_not_counted_as_blended(self):
        # Says "winner", refused by the golf route's regex: the other half of the rule.
        from app.routes.feed import _tournament_blended_market_ids

        t = {"market_ids": [1, 2], "market_names": ["Open Winner", "Open Nationality of Winner"]}
        assert _tournament_blended_market_ids(t) == frozenset({1})


class TestNoTournamentNoDrop:
    def test_without_a_tournament_card_nothing_is_dropped(self, monkeypatch):
        kept = _kept_ids(_pool(monkeypatch, None))
        assert kept == {mid for mid, _ in _OPEN_DE_FRANCE_MARKETS}

    def test_a_base_whose_names_do_not_pair_blends_nothing(self, monkeypatch):
        (item,) = _tournament_items(
            monkeypatch, _tournament(names=["DP World Tour: Open de France Winner"])
        )
        assert item["_blended_market_ids"] == frozenset()
        assert _WINNER_FIELDS <= _kept_ids([item] + _pool(monkeypatch, None))
