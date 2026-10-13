"""#10776 (classification slice) — a Kalshi head-to-head match is not its sport's title race.

WHAT THE READER SAW (Alex, 2026-10-12 ~19:45Z). Searching "Bayerlova" returned
no event and one futures card, market 65418078 ``Bayerlova vs Kupres``
(``KXITFWMATCH-26OCT12BAYKUP``). Its served detail
(artifacts/release-1.0.4-pickup-20261011/bayerlova-65418078/detail.json) read
``market_type: duel`` beside ``canonical_market_key: tennis::championship:2026``
— the same key as "2026 Men's US Open Winner". Same shape for Mattioli–Bosio
(``KXITFWMATCH-26OCT08MATBOS``, the issue's first specimen).

WHY. ``detect_market_type`` finds no competition word in "A vs B" and returns
its ``"championship"`` default, so every Kalshi match keyed as its sport's
season championship. The key is not inert:

* My Stuff reads the type segment as a progression stage
  (``frontend/lib/myStuffProgression.ts``: ``championship`` → "Champion");
* the feed's canonical dedupe folds same-key cards whose outcomes share a name,
  and Polymarket's set-handicap contract for the SAME match
  ("Set Handicap: Michaela Bayerlova (-1.5) vs Mia Kupres (+1.5)", 65540936)
  falls to the same default key — so a match-winner and a set handicap read as
  one question and one of them is not drawn;
* the hub fold and the fair-fight pairing both use the key as their bucket.

THE FIX IS GATED ON THE TICKER, NOT THE NAME. Kalshi's MATCH/DOUBLES series is
the venue's own statement that the event is one head-to-head contest (the same
shape ``_TENNIS_MATCH_SERIES_RE`` already trusts for the commence-time repair).
Each match is its own question, so its type carries the match — the #9113
precedent for player destinations. Under-merging is the safe direction: a
missing cross-venue pairing costs a badge, a false one prints a lie.

WHAT THIS DOES NOT DO (preserved, per the issue's October 8 diagnosis): no
sports row, no event admission, no start inferred from ``expected_expiration``
/ ``occurrence_datetime``, no live state, no score. ``category`` is untouched —
the matcher's ``is_game_level_market`` reads it.
"""

from __future__ import annotations

import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _dedupe_futures_by_canonical
from app.utils.canonical_market_key import canonical_key_identifies_one_question
from app.utils.futures_categorization import (
    compute_canonical_market_key,
    detect_league,
    detect_market_type,
    detect_season,
)


def _utc(*a) -> datetime:
    return datetime(*a, tzinfo=timezone.utc)


# KXITFWMATCH-26OCT12BAYKUP as saved (kalshi.json / detail.json, 19:45:47Z):
# contract close Oct 26 15:00Z (postponement allowance — NOT the match date);
# expected_expiration_time == occurrence_datetime == Oct 12 21:00Z (NOT a start).
BAY_TICKER = "KXITFWMATCH-26OCT12BAYKUP"
BAY_CLOSE = _utc(2026, 10, 26, 15, 0)
BAY_OCCURRENCE = _utc(2026, 10, 12, 21, 0)
BAY_KEY = "tennis::match_kxitfwmatch_26oct12baykup:2026"
STORED_DEFECT_KEY = "tennis::championship:2026"


# ── the helper: which tickers carry their match ─────────────────────────────


@pytest.mark.parametrize(
    "ticker,expected",
    [
        (BAY_TICKER, "match_kxitfwmatch_26oct12baykup"),
        ("KXITFWMATCH-26OCT08MATBOS", "match_kxitfwmatch_26oct08matbos"),
        ("KXITFMATCH-26OCT12ABCDEF", "match_kxitfmatch_26oct12abcdef"),
        ("KXATPMATCH-26SEP07ZVEDAR", "match_kxatpmatch_26sep07zvedar"),
        ("KXWTAMATCH-26OCT12SWAZHE", "match_kxwtamatch_26oct12swazhe"),
        ("KXATPDOUBLES-26SEP05ABCDEF", "match_kxatpdoubles_26sep05abcdef"),
    ],
)
def test_a_dated_head_to_head_ticker_is_typed_by_its_match(ticker, expected):
    from app.tasks.kalshi import _kalshi_match_market_type

    assert _kalshi_match_market_type(ticker) == expected


@pytest.mark.parametrize(
    "ticker",
    [
        # Season futures and outrights keep the name-derived type.
        "KXWTA-26USO",
        "KXATPADVANCE-26USOSEMI",
        "KXATP1RANK-26DEC31",
        "KXMLB-26",
        # Dated fixtures that are not a head-to-head MATCH series are out of
        # this slice (a league moneyline, a prop on a fixture).
        "KXNFLGAME-26SEP07KCPHI",
        "KXNFLRACE-26SEP14DENKC-35",
        # Not a ticker shape at all.
        "",
        None,
        "KXHONEYDEUCE-26",
    ],
)
def test_anything_else_keeps_its_name_derived_type(ticker):
    from app.tasks.kalshi import _kalshi_match_market_type

    assert _kalshi_match_market_type(ticker) is None


def test_the_stored_defect_is_the_name_rule_default():
    """The strawman: the name rules alone produce exactly the served key."""
    name = "Bayerlova vs Kupres"
    league = detect_league(name, sport_category="tennis")
    key = compute_canonical_market_key(
        "tennis", league, detect_market_type(name),
        detect_season(name, league, BAY_CLOSE),
    )
    assert key == STORED_DEFECT_KEY


def test_the_match_key_names_one_question_and_no_progression_stage():
    assert canonical_key_identifies_one_question(BAY_KEY)
    # myStuffProgression.extractMarketType reads parts[2].
    assert BAY_KEY.split(":")[2] not in {
        "make_playoffs", "division_winner", "conference_winner", "championship",
    }


# ── the reader: a match-winner and a set handicap are two questions ─────────


def _card(fid, name, source, key, outcomes):
    return {
        "type": "futures",
        "data": {
            "id": fid,
            "name": name,
            "source": source,
            "canonical_market_key": key,
            "top_outcomes": [
                {"name": n, "probability": p} for n, p in outcomes
            ],
        },
    }


_SET_HANDICAP_NAME = "Set Handicap: Michaela Bayerlova (-1.5) vs Mia Kupres (+1.5)"


def _set_handicap_key() -> str:
    league = detect_league(_SET_HANDICAP_NAME, sport_category="tennis")
    return compute_canonical_market_key(
        "tennis", league, detect_market_type(_SET_HANDICAP_NAME),
        detect_season(_SET_HANDICAP_NAME, league, _utc(2026, 10, 19, 15, 0)),
    )


def _feed(match_key):
    return [
        _card(65418078, "Bayerlova vs Kupres", "kalshi", match_key,
              [("Mia Kupres", 0.705), ("Michaela Bayerlova", 0.295)]),
        _card(65540936, _SET_HANDICAP_NAME, "polymarket", _set_handicap_key(),
              [("Mia Kupres", 0.905), ("Michaela Bayerlova", 0.095)]),
    ]


def test_the_stored_keys_fold_the_set_handicap_into_the_match():
    """Strawman: with the stored key the two contracts read as one question."""
    kept = {c["data"]["id"] for c in _dedupe_futures_by_canonical(_feed(STORED_DEFECT_KEY))}
    assert len(kept) == 1, kept


def test_the_match_key_keeps_both_contracts():
    assert _set_handicap_key() != BAY_KEY
    kept = {c["data"]["id"] for c in _dedupe_futures_by_canonical(_feed(BAY_KEY))}
    assert kept == {65418078, 65540936}


# ── the writer: the real poll stores the match key ──────────────────────────


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


class _Savepoint:
    is_active = True

    async def commit(self):
        self.is_active = False

    async def rollback(self):
        self.is_active = False

    def expunge_all(self):
        pass


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

    async def begin_nested(self):
        return _Savepoint()

    async def flush(self):
        pass

    async def close(self):
        pass

    def add(self, *a, **kw):
        pass


def _bayerlova_event():
    from app.services.kalshi_api import KalshiEvent, KalshiMarket

    def leg(code, player):
        return KalshiMarket(
            ticker=f"{BAY_TICKER}-{code}",
            event_ticker=BAY_TICKER,
            title="Will Mia Kupres win the Bayerlova vs Kupres : Round Of 16 match?",
            yes_sub_title=player,
            status="active",
            yes_bid=70,
            yes_ask=71,
            last_price=70,
            close_time=BAY_CLOSE,
            expiration_time=BAY_CLOSE,
            expected_expiration_time=BAY_OCCURRENCE,
            occurrence_datetime=BAY_OCCURRENCE,
        )

    return KalshiEvent(
        event_ticker=BAY_TICKER,
        series_ticker="KXITFWMATCH",
        title="Bayerlova vs Kupres",
        category="Sports",
        mutually_exclusive=True,
        markets=[leg("KUP", "Mia Kupres"), leg("BAY", "Michaela Bayerlova")],
    )


def _us_open_event():
    """A real tennis season future in the SAME poll — must keep its key."""
    from app.services.kalshi_api import KalshiEvent, KalshiMarket

    close = _utc(2026, 9, 13, 23, 0)

    def leg(code, player):
        return KalshiMarket(
            ticker=f"KXWTA-26USO-{code}",
            event_ticker="KXWTA-26USO",
            title="2026 Women's US Open Winner",
            yes_sub_title=player,
            status="active",
            yes_bid=20,
            yes_ask=22,
            last_price=21,
            close_time=close,
            expiration_time=close,
        )

    return KalshiEvent(
        event_ticker="KXWTA-26USO",
        series_ticker="KXWTA",
        title="2026 Women's US Open Winner",
        category="Sports",
        mutually_exclusive=True,
        markets=[leg("SAB", "Aryna Sabalenka"), leg("SWI", "Iga Swiatek")],
    )


def _written(stmts) -> list[dict]:
    rows = []
    for stmt in stmts:
        table = getattr(getattr(stmt, "table", None), "name", None)
        if table != "futures_markets":
            continue
        params = stmt.compile().params
        ext = next(
            (v for k, v in params.items() if k.startswith("external_id")), None
        )
        keys = {
            v for k, v in params.items()
            if "canonical_market_key" in k and isinstance(v, str)
        }
        cats = {
            v for k, v in params.items()
            if k.startswith("category") and not k.startswith("category_tags")
            and isinstance(v, str)
        }
        if ext:
            rows.append({"external_id": ext, "keys": keys, "categories": cats})
    return rows


async def _poll(events) -> list[dict]:
    from app.tasks import kalshi as kalshi_task
    from app.tasks import redis_state

    sink: list = []

    @asynccontextmanager
    async def _session_cm(**_budget):
        yield _Session(sink)

    service = MagicMock()
    service.get_all_events = AsyncMock(return_value=events)
    service.close = AsyncMock()

    with ExitStack() as es:
        es.enter_context(patch.object(redis_state, "get_redis_client", lambda: MagicMock()))
        es.enter_context(patch.object(kalshi_task, "get_task_session", _session_cm))
        es.enter_context(
            patch("app.services.kalshi_api.KalshiAPIService", return_value=service)
        )
        es.enter_context(patch.dict(os.environ, {"KALSHI_API_KEY": "test-key"}))
        await kalshi_task._poll_kalshi_markets()
    return _written(sink)


@pytest.mark.asyncio
async def test_the_poll_keys_the_itf_match_as_its_own_question():
    rows = await _poll([_bayerlova_event(), _us_open_event()])
    by_ext = {r["external_id"]: r for r in rows}
    assert BAY_TICKER in by_ext, (
        f"the poll wrote no row for {BAY_TICKER} — the harness broke, not the ship: {rows}"
    )
    assert by_ext[BAY_TICKER]["keys"] == {BAY_KEY}, by_ext[BAY_TICKER]
    # The real season future in the same pass keeps its name-derived key —
    # the catch-all the match just left. Its own coarseness is not this slice.
    assert "KXWTA-26USO" in by_ext, rows
    assert by_ext["KXWTA-26USO"]["keys"] == {STORED_DEFECT_KEY}, by_ext["KXWTA-26USO"]


@pytest.mark.asyncio
async def test_the_poll_leaves_the_category_column_alone():
    """``category`` means "sport" at this door and the matcher's game-level
    gate reads it; this slice moves only the key."""
    rows = await _poll([_bayerlova_event()])
    (row,) = [r for r in rows if r["external_id"] == BAY_TICKER]
    assert row["categories"] == {"championship"}, row
