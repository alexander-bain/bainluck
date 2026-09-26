"""#3047 — the World Series is one card on Discover, not two.

WHAT THE READER SAW (discover/d523, 2026-09-26 02:25Z, 390px): Discover's first
20 carried "MLB World Series Winner" (id 1, odds_api + polymarket, Dodgers 27%)
at position 4 and "Pro Baseball Champion" (id 275, Kalshi ``KXMLB-26``, Dodgers
30%) at position 18. One question, two numbers — the blend ruling read backwards.

WHY THE FEED COULD NOT FOLD THEM. The feed's reader-side adoption (#4799,
``_canonical_dedupe_keys``) folds a seasonless card into its UNIQUE seasoned
sibling with the same ``sport:league:category``. Row 275 was stored
``baseball::championship:2028`` and broke both halves at once:

* **season 2028 on a ``-26`` ticker.** The Kalshi poll handed ``detect_season``
  the event's ``expiration_time`` — the legal backstop CAL-P989 (#2660/#1818)
  moved into its own column because it can sit YEARS past the decision — rather
  than ``resolution_date`` (``max(close_time)``, 2026-11-01 for KXMLB-26). Every
  other writer (Polymarket, team_linking) already passes the resolution date;
  ``detect_season``'s own contract calls the argument "when the market resolves".
* **empty league.** Kalshi titles the event without the league's name ("Pro
  Baseball Champion"), so ``detect_league`` found nothing.

AND ONE THING THE REPAIR MUST NOT DO. Correcting the season lands the Kalshi
pennants (``KXMLBAL-26`` / ``KXMLBNL-26``, stored ``baseball:MLB:championship:
2028``) on ``:2026`` — the World Series' key — and the feed's canonical dedupe
folds any two same-key cards whose top outcomes share a name. AL teams sit in
both lists, so "American League Champion" could vanish into the World Series
card. A pennant is its own question, so it gets its own market type.

Counterfactual over production (2026-09-26 ~05:30Z, every open row the change
can touch, re-polled rows only): 388 keys move; 119 rows LEAVE a key another
venue shares (their season was wrong), 21 JOIN one — the Polymarket twins of
WNBA, NBA conference, Heisman, NFL award and rugby champions, whose season now
agrees. Recorded in the PR.
"""

from __future__ import annotations

import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _canonical_dedupe_keys, _dedupe_futures_by_canonical
from app.utils.futures_categorization import (
    compute_canonical_market_key,
    detect_league,
    detect_market_type,
    detect_season,
)


def _utc(*a) -> datetime:
    return datetime(*a, tzinfo=timezone.utc)


# KXMLB-26 as the venue serves it (prod row 275, read 2026-09-26): trading stops
# 2026-11-01, the legal backstop is 2028.
WS_CLOSE = _utc(2026, 11, 1, 3, 0)
WS_BACKSTOP = _utc(2028, 11, 1, 3, 0)


def _kalshi_key(name: str, resolution_date: datetime) -> str | None:
    """The key the Kalshi poll computes, composed the way the poll composes it."""
    league = detect_league(name, sport_category="baseball")
    season = detect_season(name, league, resolution_date)
    return compute_canonical_market_key(
        "baseball", league, detect_market_type(name), season
    )


# ── the key's inputs ─────────────────────────────────────────────────────────


def test_the_kalshi_world_series_keys_like_every_other_world_series():
    assert _kalshi_key("Pro Baseball Champion", WS_CLOSE) == (
        "baseball:MLB:championship:2026"
    )
    # The Polymarket World Series row (prod 114584) — the family it must meet.
    poly_league = detect_league("MLB World Series Champion 2026", sport_category="baseball")
    assert compute_canonical_market_key(
        "baseball",
        poly_league,
        detect_market_type("MLB World Series Champion 2026"),
        detect_season("MLB World Series Champion 2026", poly_league, None),
    ) == "baseball:MLB:championship:2026"


def test_the_backstop_year_is_the_2028_that_was_stored():
    """Strawman: fed the backstop, the same composition reproduces the defect
    row's season — so the test above passes because of the date, not by luck."""
    assert _kalshi_key("Pro Baseball Champion", WS_BACKSTOP).endswith(":2028")


def test_only_the_champion_phrase_names_the_league():
    """The new league pattern is the championship phrase, not every 'pro baseball'
    title — the 30 Kalshi win-total rows and the World Series matchup market
    (served at feed position 102 on 2026-09-26) keep the key they have."""
    assert detect_league("Pro Baseball Champion", sport_category="baseball") == "MLB"
    assert detect_league("Pro Baseball Championship Series Matchup", sport_category="baseball") is None
    assert detect_league("Toronto pro baseball wins this season?", sport_category="baseball") is None


@pytest.mark.parametrize(
    "name, expected",
    [
        ("American League Champion", "al_pennant"),
        ("National League Champion", "nl_pennant"),
        ("MLB: 2026 American League Champion", "al_pennant"),
        ("MLB: 2026 National League Champion", "nl_pennant"),
        ("AL Pennant Winner", "al_pennant"),
        # The league word must touch "champion": a division stays a division
        # row's type, and an award keeps its award.
        ("MLB: 2026 AL Central Champion", "championship"),
        ("AL East Division Winner", "division_winner"),
        ("AL MVP Winner?", "al_mvp"),
        ("AL Cy Young Winner?", "al_cy_young"),
        # The World Series itself is unchanged.
        ("MLB World Series Champion 2026", "championship"),
        ("Pro Baseball Champion", "championship"),
    ],
)
def test_a_pennant_is_its_own_question(name, expected):
    assert detect_market_type(name) == expected


# ── the reader's side: what Discover does with the corrected keys ────────────


def _card(fid, key, leader, *others, score=50.0):
    outcomes = [{"name": n, "probability": 0.1} for n in (leader, *others)]
    return {
        "type": "futures",
        "id": fid,
        "score": score,
        "_rank_score": score,
        "data": {
            "id": fid,
            "canonical_market_key": key,
            "top_outcomes": outcomes,
        },
    }


def _feed(ws_kalshi_key, al_kalshi_key):
    return [
        # id 1 — odds_api, no season in its title (#4799's specimen).
        _card(1, "baseball:MLB:championship:", "Los Angeles Dodgers",
              "Milwaukee Brewers", "Tampa Bay Rays", score=80.0),
        _card(275, ws_kalshi_key, "Los Angeles Dodgers",
              "Milwaukee Brewers", "Tampa Bay Rays", score=40.0),
        # Kalshi's AL pennant: its leader is an AL team that is ALSO in the
        # World Series card's top outcomes.
        _card(270, al_kalshi_key, "Tampa Bay Rays",
              "New York Yankees", "Seattle Mariners", score=35.0),
    ]


def test_discover_prints_the_world_series_once():
    feed = _feed(
        _kalshi_key("Pro Baseball Champion", WS_CLOSE),
        _kalshi_key("American League Champion", _utc(2026, 10, 25)),
    )
    kept = {c["id"] for c in _dedupe_futures_by_canonical(feed)}
    assert 275 not in kept and 1 in kept, (
        "Kalshi's World Series should fold into the better-ranked World Series card"
    )
    assert 270 in kept, "the AL pennant is a different question and must stay"


def test_the_stored_defect_keys_left_two_world_series_on_the_page():
    """Control: the keys production stores today reproduce the reader's symptom."""
    feed = _feed("baseball::championship:2028", "baseball:MLB:championship:2028")
    kept = {c["id"] for c in _dedupe_futures_by_canonical(feed)}
    assert {1, 275} <= kept


def test_without_the_pennant_type_the_al_card_would_be_eaten():
    """Why the pennant split rides this ship: season fixed, pennant still keyed
    `championship`, and the AL card is folded into the World Series."""
    feed = _feed(
        _kalshi_key("Pro Baseball Champion", WS_CLOSE),
        "baseball:MLB:championship:2026",
    )
    keys = _canonical_dedupe_keys(feed)
    assert keys[0] == "baseball:MLB:championship:2026"
    kept = {c["id"] for c in _dedupe_futures_by_canonical(feed)}
    assert 270 not in kept


# ── the writer: the real poll hands detect_season the resolution date ───────


class _Result:
    rowcount = 1

    def __getattr__(self, name):
        def _empty(*a, **kw):
            return self if name in ("mappings", "scalars") else (
                [] if name in ("fetchall", "all", "keys") else None
            )
        return _empty

    def __iter__(self):
        return iter([])


class _Session:
    def __init__(self, sink):
        self.sink = sink

    async def execute(self, stmt, *a, **kw):
        self.sink.append(stmt)
        return _Result()

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def flush(self):
        pass

    async def close(self):
        pass

    def add(self, *a, **kw):
        pass

    def expunge_all(self):
        pass


def _ws_event():
    from app.services.kalshi_api import KalshiEvent, KalshiMarket

    def leg(code, team):
        return KalshiMarket(
            ticker=f"KXMLB-26-{code}",
            event_ticker="KXMLB-26",
            title="Pro Baseball Champion",
            yes_sub_title=team,
            status="active",
            yes_bid=29,
            yes_ask=31,
            last_price=30,
            close_time=WS_CLOSE,
            expiration_time=WS_BACKSTOP,
        )

    return KalshiEvent(
        event_ticker="KXMLB-26",
        series_ticker="KXMLB",
        title="Pro Baseball Champion",
        category="Sports",
        mutually_exclusive=True,
        markets=[leg("LAD", "Los Angeles D"), leg("MIL", "Milwaukee")],
    )


def _written_keys(stmts) -> list[str]:
    keys = []
    for stmt in stmts:
        table = getattr(getattr(stmt, "table", None), "name", None)
        if table != "futures_markets":
            continue
        params = stmt.compile().params
        for name, value in params.items():
            if "canonical_market_key" in name and isinstance(value, str):
                keys.append(value)
    return keys


@pytest.mark.asyncio
async def test_the_poll_writes_the_world_series_with_its_2026_season(monkeypatch):
    from app.tasks import kalshi as kalshi_task
    from app.tasks import redis_state

    sink: list = []

    @asynccontextmanager
    async def _session_cm(**_budget):
        yield _Session(sink)

    service = MagicMock()
    service.get_all_events = AsyncMock(return_value=[_ws_event()])
    service.close = AsyncMock()

    monkeypatch.setattr(redis_state, "get_redis_client", lambda: MagicMock())
    monkeypatch.setattr(kalshi_task, "get_task_session", _session_cm)

    with ExitStack() as es:
        es.enter_context(
            patch("app.services.kalshi_api.KalshiAPIService", return_value=service)
        )
        es.enter_context(patch.dict(os.environ, {"KALSHI_API_KEY": "test-key"}))
        await kalshi_task._poll_kalshi_markets()

    keys = _written_keys(sink)
    assert keys, "the poll wrote no futures_markets row — the harness broke, not the ship"
    assert set(keys) == {"baseball:MLB:championship:2026"}, keys


def test_the_playoff_grid_still_fetches_every_pennant_type():
    """`/api/futures/playoff-grid` gathers its candidates by key TYPE through a
    local `_CANONICAL_TO_STAGE` map before it classifies stages by name. A pennant
    type the map does not list is a pennant the grid silently stops fetching."""
    import ast
    from pathlib import Path

    from app.utils.futures_categorization import _MARKET_TYPE_PATTERNS

    src = (Path(__file__).resolve().parents[1] / "app/routes/futures.py").read_text()
    stage_map = None
    for node in ast.walk(ast.parse(src)):
        if (
            isinstance(node, ast.Assign)
            and any(getattr(t, "id", None) == "_CANONICAL_TO_STAGE" for t in node.targets)
        ):
            stage_map = ast.literal_eval(node.value)
    assert stage_map, "_CANONICAL_TO_STAGE not found — the guard lost its subject"

    pennant_types = {t for _, t in _MARKET_TYPE_PATTERNS if t.endswith("pennant")}
    assert pennant_types == {"al_pennant", "nl_pennant"}
    for t in pennant_types:
        assert stage_map.get(t) == "pennant", t
