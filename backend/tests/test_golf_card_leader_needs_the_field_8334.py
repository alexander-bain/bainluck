"""A golf card may call someone the leader only if it holds the field they lead (#8334).

Served on production ``/api/feed``, 2026-09-24 02:38Z, one tournament twice:

    pos 69 tournament  LPGA Tour: Ina Yoon leads at 3.2%
    pos 80 futures     Walmart NW Arkansas Championship ... Miyu Yamashita leads at 14%

The tournament card was built from Polymarket's winner market ``61811389``, which
holds four golfers — 3.15 + 2.45 + 1.85 + 1.85 = 9.3% of the win probability. The
144-golfer Kalshi field beside it priced Yamashita at 13.5%. "Leads" was true only
of the four rows we happened to hold.

Every full field in the same golf base carried 0.93-1.03 of the probability
(FedEx Open de France 1.033 over 144, Compliance Solutions 1.004 over 113,
Presidents Cup 0.96, Ryder Cup 0.935), so a 0.5 floor sits a long way from both.

The harness drives the REAL ``_score_golf_tournaments`` over a stubbed golf base,
the same way ``test_golf_movement_is_points_not_percent_d1.py`` does.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

#: Gotcha #44 — offset from the clock, never a literal date.
_FEED_NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)

#: Polymarket 61811389 on production, 2026-09-24 02:40Z — the whole held field.
_NW_ARKANSAS_HELD = [
    ("Ina Yoon", 0.0315),
    ("Jenny Shin", 0.0245),
    ("Isabell Gabsa", 0.0185),
    ("Jeong-Eun Lee", 0.0185),
]


def _golfer(rank: int, name: str, probability: float) -> dict:
    return {
        "id": rank,
        "name": name,
        "probability": probability,
        "movement_24h": None,
        "movement_is_dated": False,
        "rank": rank,
    }


def _tournament(field: list[tuple[str, float]] | None, top: int = 15) -> dict:
    """One golf-base entry, shaped as `get_golf_base` publishes it.

    ``golfers`` is the top slice and ``_all_golfers`` the whole field, as
    ``routes/golf.py`` builds them. ``field=None`` models a base that carries
    no ``_all_golfers`` key.
    """
    golfers = [_golfer(i + 1, n, p) for i, (n, p) in enumerate(field or [])]
    entry = {
        "key": "nw_arkansas_championship_womens",
        "name": "NW Arkansas Championship",
        "slug": "nw-arkansas-championship-womens",
        "tour": "lpga",
        "tour_label": "LPGA Tour",
        "is_major": False,
        "is_tour_event": True,
        "commence_time": (_FEED_NOW + timedelta(days=1)).isoformat(),
        "resolution_date": (_FEED_NOW + timedelta(days=4)).isoformat(),
        "start_date": (_FEED_NOW + timedelta(days=1)).isoformat(),
        "end_date": (_FEED_NOW + timedelta(days=4)).isoformat(),
        "market_names": ["LPGA: NW Arkansas Championship Winner"],
        "market_ids": [61811389],
        "market_sources": ["polymarket"],
        "golfers": golfers[:top],
    }
    if field is not None:
        entry["_all_golfers"] = golfers
    return entry


def _served(monkeypatch, tournament: dict) -> list[dict]:
    import app.utils.golf_base as golf_base
    from app.routes import feed as feed_module

    async def _fake_base(db, now, stages=None):
        return ([tournament], "fresh")

    monkeypatch.setattr(golf_base, "get_golf_base", _fake_base)
    return asyncio.run(feed_module._score_golf_tournaments(None, _FEED_NOW, None, None))


def _full_field(n: int, leader: float) -> list[tuple[str, float]]:
    """A leader plus ``n - 1`` golfers sharing the rest, summing to 1.0."""
    rest = (1.0 - leader) / (n - 1)
    return [("Leader", leader)] + [(f"Golfer {i}", rest) for i in range(2, n + 1)]


class TestTheProductionSpecimen:
    def test_four_of_the_field_yield_no_card(self, monkeypatch):
        assert _served(monkeypatch, _tournament(_NW_ARKANSAS_HELD)) == []

    def test_the_specimen_is_below_the_floor_by_measurement(self):
        from app.routes.feed import TOURNAMENT_LEADER_MIN_FIELD_MASS

        mass = sum(p for _, p in _NW_ARKANSAS_HELD)
        assert mass == pytest.approx(0.093)
        assert mass < TOURNAMENT_LEADER_MIN_FIELD_MASS


class TestAFullFieldKeepsItsCard:
    """Control: the gate removes partial fields and nothing else."""

    def test_a_144_golfer_field_is_served_with_its_leader(self, monkeypatch):
        items = _served(monkeypatch, _tournament(_full_field(144, 0.106)))
        assert len(items) == 1
        assert items[0]["reason"] == "LPGA Tour: Leader leads at 10.6%"

    def test_the_field_is_read_from_all_golfers_not_the_top_slice(self, monkeypatch):
        # Top 15 of a 113-golfer field with a flat tail carry well under half the
        # probability; the card must survive because the whole field is present.
        field = _full_field(113, 0.057)
        assert sum(p for _, p in field[:15]) < 0.5
        items = _served(monkeypatch, _tournament(field, top=15))
        assert len(items) == 1

    def test_a_two_team_cup_is_served(self, monkeypatch):
        items = _served(
            monkeypatch, _tournament([("Team USA", 0.835), ("Team World", 0.125)])
        )
        assert len(items) == 1
        assert items[0]["data"]["golfers"][0]["name"] == "Team USA"

    def test_a_base_without_the_whole_field_keeps_its_card(self, monkeypatch):
        t = _tournament(_NW_ARKANSAS_HELD)
        del t["_all_golfers"]
        assert len(_served(monkeypatch, t)) == 1


class TestTheFloor:
    @pytest.mark.parametrize("mass,served", [(0.49, 0), (0.5, 1), (0.93, 1)])
    def test_the_boundary(self, monkeypatch, mass, served):
        field = [("Leader", mass / 2), ("Second", mass / 2)]
        assert len(_served(monkeypatch, _tournament(field))) == served
