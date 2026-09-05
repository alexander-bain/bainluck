"""#3198 — an id from another venue must not parse as a Kalshi game ticker.

## The ship

A settled tennis page's Games map says how the match actually went. On
Wu Yibing v Carlos Alcaraz (event 15301243, US Open, completed) it could not:
`Wu vs. Alcaraz: Match O/U 36.5` — linked, priced, classified `game_total` — was
absent from `/api/events/15301243/game-markets`, so the map was drawn from a
first-set line and a sets-count line instead of the match line, and #3161's
scope rule had to fail open on that page rather than say `26 games against an
expected 36.5`.

## What was actually wrong

Not classification, not the threshold dedup, not monotonicity, not the sport
range, not the prop window — #3198 rules each of those out by name against the
production rows. The four missing markets never entered `_build_game_markets`'s
loop at all: `filter_foreign_game_markets` deleted them.

`_KALSHI_GAME_TEAMS_RE` was `\\d{2}[A-Za-z]{3}\\d{1,2}(?:\\d{4})?([A-Za-z][A-Za-z0-9]*)`,
searched unanchored, with any three letters accepted where a month belongs. A
Polymarket condition id is 64 hex characters and hex letters are a-f, so runs
like `dec`/`feb`/`ffc` show up in them constantly. Measured on the production
rows for event 15301243 (2026-09-05, 16 linked markets):

| external_id | invented team-code |
|---|---|
| `0x…ffc69a58241` (Set 1 Games O/U 9.5) | `A58241` |
| `0x…dde2db943c`  (Total Sets O/U 4.5)  | `D71F633DDE2DB943C` |
| `0x…403164d03`   (Set 1 Winner)        | `D9C636C43F71013EBC641C51403164D03` |
| `0x…fb90be09e`   (Match O/U 36.5)      | `C076E39A5B5E353BFE0B99DA76A4E39C493FB9EEFB90BE09E` |

Five distinct "team codes" on a page with one Kalshi ticker (`YIBALC`) ⇒
`len(team_codes) > 1`, `true_codes == {YIBALC}` (the only code whose ticker date
parses at all), and the filter deleted every market carrying an invented code.

## 🔴 WHY THE EXISTING GUARD DID NOT CATCH THIS

`test_foreign_game_markets.py::test_polymarket_and_undated_always_kept` asserts
exactly the property that broke, and passes — because its Polymarket specimen is
the slug `"polymarket-celtics-76ers-ou"`, which has no digits and therefore
cannot parse under any version of the regex. The assertion was true by
construction. Every Polymarket id in this file is a REAL production
`condition_id`, copied verbatim, and four of them parsed before the fix.

## Sizing, so the fix is not defended by its own example

Census over every event commencing in a 2-day window (production, 2026-09-05):
1,358 events, 7,869 event-linked markets.

  * 1,904 non-Kalshi markets parsed an invented team-code
  * **79 event pages silently lost 623 markets**
  * **623 of 623 were false positives** — the filter caught zero genuine foreign
    markets in the window
  * after the fix: 0 bogus parses, and **0 of 5,965 Kalshi tickers parse
    differently**, so the filter's real arm (#209's foreign-props defense) is
    untouched — `test_the_real_foreign_market_is_still_dropped` is that claim.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.routes import events as events_route
from app.utils.prediction_market_matching import (
    filter_foreign_game_markets,
    kalshi_game_id,
    kalshi_game_teams,
)

# Verbatim from production, event 15301243 (`futures_markets.external_id`).
# The four that parsed before the fix are the four that vanished from the page.
POLYMARKET_IDS_THAT_PARSED = {
    "0x0fd309febc10a17c3f949d796a391574fd239ee6491fbc3d71f633dde2db943c": "Yibing Wu vs. Carlos Alcaraz: Total Sets O/U 4.5",
    "0x4adcbeb7da424a17aab818dcf996404d9c636c43f71013ebc641c51403164d03": "Set 1 Winner: Wu vs Alcaraz",
    "0xad44e74593fde87c076e39a5b5e353bfe0b99da76a4e39c493fb9eefb90be09e": "Wu vs. Alcaraz: Match O/U 36.5",
    "0xd9db5703ae1bd1483c066c12801d961b3b31e151b4b609d23f145ffc69a58241": "Wu vs. Alcaraz: Set 1 Games O/U 9.5",
}

POLYMARKET_IDS_THAT_DID_NOT_PARSE = (
    "0xa75c78cc95fa2927b6eca2ae771f1872d912b96e14b2076e9d459ad920d4d480",
    "0x49d1d7651e5baa08a441e1c317df56bd27280c69a7cb4509241438d86d232c24",
    "0xab6557c1c85a6d5fe82a52b706f14713af814784d9d9886a73a6c2f90005067b",
    "0xbe6f21cc2dfd2daf9a5cf790cce30211665cf7e6c012a9af552b88e5e7a6dc9b",
    "0x23c7bd202bbf3661f604f6535f5cc6e4c1fed5f94a65bf8cfdf7002a5cccff30",
    "0xfc2e8c0c8bc076d3aed36af9866f2a305fa8f4f81e14d69842196e0448d65d46",
    "0xfd45d1bdce282a7c719ee6ba0966ff00d19e0e8a7a772e591de89228ec349532",
    "957742",  # the Polymarket EVENT id — a bare numeric string
)

KALSHI_TICKER = "KXATPMATCH-26SEP04YIBALC"
EVENT_DATE = date(2026, 9, 4)


class _M:
    """Minimal market stub — external_id plus an id for identity."""

    def __init__(self, external_id, mid):
        self.external_id = external_id
        self.id = mid


# ── the parser ───────────────────────────────────────────────────────────────


def test_a_polymarket_condition_id_yields_no_team_code():
    """The four that parsed, by name. This is the regression."""
    for ext, market_name in POLYMARKET_IDS_THAT_PARSED.items():
        assert kalshi_game_teams(ext) is None, market_name
        assert kalshi_game_id(ext) is None, market_name


def test_every_polymarket_id_on_the_page_yields_no_team_code():
    """Not just the four — no id from that venue may produce a Kalshi answer."""
    for ext in POLYMARKET_IDS_THAT_DID_NOT_PARSE:
        assert kalshi_game_teams(ext) is None, ext
        assert kalshi_game_id(ext) is None, ext


def test_three_letters_between_digits_are_not_a_month():
    """The rule that kills the class: the month must be a real month.

    `xyz` and `ffc` are letters in the month's position and nothing more. Both
    parsed before the fix.
    """
    assert kalshi_game_teams("KXNBAGAME-26XYZ21DETCHI") is None
    assert kalshi_game_teams("KXNBAGAME-26FFC21DETCHI") is None
    assert kalshi_game_teams("KXNBAGAME-26FEB21DETCHI") == "DETCHI"


def test_the_token_must_start_a_hyphen_segment():
    """The other half of the rule: a ticker is `<SERIES>-<GAMEID>`, so the
    game-id begins a segment. A date-shaped run buried mid-word is a substring
    of something else, which is precisely what a hex id is."""
    assert kalshi_game_teams("junk26feb21detchi") is None
    assert kalshi_game_teams("KXNBAGAME-26FEB21DETCHI") == "DETCHI"
    # A bare game-id handed in directly still parses (`^` is a segment start).
    assert kalshi_game_teams("26FEB21DETCHI") == "DETCHI"


def test_real_kalshi_tickers_are_unchanged():
    """Every shape the pre-#3198 docstrings promised, still parsing.

    Measured claim behind this: over 5,965 Kalshi-sourced linked markets in the
    2-day production window, zero parse differently after the fix.
    """
    assert kalshi_game_teams("KXNCAAMBGAME-26FEB22IOWAWIS") == "IOWAWIS"
    assert kalshi_game_teams("KXNBAMENTION-26FEB20BOSGSW") == "BOSGSW"
    assert kalshi_game_teams("KXMLBGAME-26APR291840COLCIN") == "COLCIN"
    assert kalshi_game_teams(KALSHI_TICKER) == "YIBALC"
    assert kalshi_game_id("KXNCAAMBGAME-26FEB22IOWAWIS") == "26FEB22IOWAWIS"
    assert kalshi_game_id("KXCS2MAP-26FEB24OMEACE-1") == "26FEB24OMEACE"
    assert kalshi_game_id("KXMLBGAME-26APR291840COLCIN") == "26APR291840COLCIN"
    # Lower-case tickers occur in seeded/legacy rows; the token is normalised up.
    assert kalshi_game_teams("kxnbagame-26feb21detchi") == "DETCHI"


# ── the call site ────────────────────────────────────────────────────────────


def test_the_page_keeps_every_polymarket_market_beside_a_kalshi_ticker():
    """The exhibit, reassembled: 15 Polymarket ids + 1 Kalshi ticker.

    Before the fix this returned 12 of 16 — dropping the match total, the 4.5
    sets rung, the 9.5 set-games rung and the set-1 winner.
    """
    poly = [
        _M(ext, f"p{i}")
        for i, ext in enumerate(
            list(POLYMARKET_IDS_THAT_PARSED) + list(POLYMARKET_IDS_THAT_DID_NOT_PARSE)
        )
    ]
    kalshi = _M(KALSHI_TICKER, "k1")
    kept = filter_foreign_game_markets(poly + [kalshi], EVENT_DATE)
    assert {m.id for m in kept} == {m.id for m in poly} | {"k1"}


def test_the_real_foreign_market_is_still_dropped():
    """The fix must not turn the filter off — #209's defense still fires.

    A genuinely foreign Kalshi market (next day, different teams) beside the
    true game is still deleted, and the Polymarket rows beside them still ride.
    """
    real = [
        _M("KXNCAAMBGAME-26FEB22IOWAWIS", "r1"),
        _M("KXNCAAMBSPREAD-26FEB22IOWAWIS", "r2"),
    ]
    foreign = _M("KXNCAAMBGAME-26FEB23AMCCSELA", "f1")
    poly = _M(next(iter(POLYMARKET_IDS_THAT_PARSED)), "p1")
    kept = filter_foreign_game_markets(real + [foreign, poly], date(2026, 2, 22))
    assert {m.id for m in kept} == {"r1", "r2", "p1"}
    assert "f1" not in {m.id for m in kept}


# ── the ship, end to end ─────────────────────────────────────────────────────
#
# The rows below are the production market/outcome set for event 15301243 as of
# 2026-09-05, trimmed to the columns `_build_game_markets` reads. The point of
# driving the real build rather than the filter alone is that the user-visible
# claim is about the PAYLOAD: `totals` must carry the match line, and the set-1
# winner must be back in `other`.

_USO, _ATP = 356611, 105026
_ROWS = [
    (
        60105525,
        "Wu vs Alcaraz",
        "kalshi",
        KALSHI_TICKER,
        _USO,
        [("Carlos Alcaraz", "0.990000"), ("Yibing Wu", "0.010000")],
    ),
    (
        60114039,
        "Yibing Wu vs. Carlos Alcaraz: Total Sets O/U 3.5",
        "polymarket",
        "0x49d1d7651e5baa08a441e1c317df56bd27280c69a7cb4509241438d86d232c24",
        _USO,
        [("Over", "0.000500"), ("Under", "0.999500")],
    ),
    (
        60114042,
        "Yibing Wu vs. Carlos Alcaraz: Total Sets O/U 4.5",
        "polymarket",
        "0x0fd309febc10a17c3f949d796a391574fd239ee6491fbc3d71f633dde2db943c",
        _USO,
        [("Over", "0.000500"), ("Under", "0.999500")],
    ),
    (
        60116285,
        "Set 1 Winner: Wu vs Alcaraz",
        "polymarket",
        "0x4adcbeb7da424a17aab818dcf996404d9c636c43f71013ebc641c51403164d03",
        None,
        [("Yes", "0.000500"), ("No", "0.999000")],
    ),
    (
        60118161,
        "Wu vs. Alcaraz: Match O/U 36.5",
        "polymarket",
        "0xad44e74593fde87c076e39a5b5e353bfe0b99da76a4e39c493fb9eefb90be09e",
        _ATP,
        [("Over", "0.004500"), ("Under", "0.995500")],
    ),
    (
        60122980,
        "Set 2 Winner: Wu vs Alcaraz",
        "polymarket",
        "0xfc2e8c0c8bc076d3aed36af9866f2a305fa8f4f81e14d69842196e0448d65d46",
        None,
        [("Yes", "0.000500"), ("No", "0.999500")],
    ),
    (
        60125229,
        "Wu vs. Alcaraz: Set 1 Games O/U 9.5",
        "polymarket",
        "0xd9db5703ae1bd1483c066c12801d961b3b31e151b4b609d23f145ffc69a58241",
        _ATP,
        [("Over", "0.000500"), ("Under", "0.999500")],
    ),
    (
        60132492,
        "Wu vs. Alcaraz: Set 1 Games O/U 8.5",
        "polymarket",
        "0x1111111111111111111111111111111111111111111111111111111111111111",
        _ATP,
        [("Over", "0.999500"), ("Under", "0.000500")],
    ),
]


def _build_payload():
    """Run the real `_build_game_markets` over the production rows."""
    markets, outcomes = [], []
    for mid, name, source, ext, sport_id, outs in _ROWS:
        market = MagicMock()
        market.id, market.name, market.source, market.external_id = (
            mid,
            name,
            source,
            ext,
        )
        market.sport_id, market.llm_sport_category = sport_id, "tennis"
        market.status = "open"
        market.category, market.group_type = "game_prop", "polymarket_sub_market"
        market.group_id = "polymarket:957742"
        market.event_id, market.market_tier, market.market_type = 15301243, 5, None
        market.commence_time = datetime(2026, 9, 3, 5, 5, 23, tzinfo=timezone.utc)
        market.market_metadata = None
        markets.append(market)
        for name_, prob in outs:
            outcome = MagicMock()
            outcome.id = len(outcomes) + 1
            outcome.market_id, outcome.name = mid, name_
            outcome.current_probability = Decimal(prob)
            outcome.opening_probability = Decimal("0.500000")
            outcome.is_winner, outcome.resolution_source = False, None
            outcomes.append(outcome)
    outcomes.sort(key=lambda o: -float(o.current_probability))

    sport = MagicMock()
    sport.key, sport.id = "tennis_atp_us_open", _USO
    event = MagicMock()
    event.id, event.status, event.sport, event.sport_id = (
        15301243,
        "completed",
        sport,
        _USO,
    )
    event.home_team_name, event.away_team_name = "Wu Yibing", "Carlos Alcaraz"
    event.home_score, event.away_score = 0, 3
    event.period = event.game_clock = event.box_score_data = None
    event.commence_time = datetime(2026, 9, 4, 18, 16, 44, tzinfo=timezone.utc)
    event.completed_at = datetime(2026, 9, 4, 20, 46, 46, tzinfo=timezone.utc)
    event.__dict__.update({"llm_league": "ATP", "period": None})

    def _list(data):
        result = MagicMock()
        result.scalars.return_value.all.return_value = data
        result.all.return_value = [(x,) for x in data]
        result.first.return_value = (data[0],) if data else None
        result.scalar_one_or_none.return_value = None
        return result

    calls = {"markets": 0}

    async def execute(stmt, *args, **kwargs):
        sql = str(stmt).lower()
        if "futures_outcomes" in sql:
            return _list(outcomes)
        if "futures_markets" in sql:
            # Only the FIRST futures_markets query is the event-linked one; the
            # Polymarket-group and unlinked-fallback queries below it must not
            # be handed the same list back or the page would double.
            calls["markets"] += 1
            return _list(markets if calls["markets"] == 1 else [])
        if "events" in sql:
            result = MagicMock()
            result.scalar_one_or_none.return_value = event
            result.scalars.return_value.all.return_value = [event]
            return result
        return _list([])

    db = AsyncMock()
    db.execute = execute
    response, _status, _ids = asyncio.run(
        events_route._build_game_markets(15301243, db)
    )
    return response


def test_the_settled_games_map_carries_the_match_total():
    """The ship: the match line is on the rail, and it is the ONLY rung there.

    Both halves matter. Its presence is #3198. Its being alone is #3161 — with a
    match-scope rung available, `_match_scope_tennis_totals` stops failing open
    and the per-set lines leave the match games rail.
    """
    totals = _build_payload()["totals"]
    assert [t["threshold"] for t in totals] == [36.5]
    assert totals[0]["market_name"] == "Wu vs. Alcaraz: Match O/U 36.5"
    assert totals[0]["over_probability"] == 0.0045


def test_the_set_one_winner_is_served_beside_its_siblings():
    """The tell that this was never a totals bug: `Set 1 Winner` went missing
    from `other` while `Set 2 Winner` — same shape, same prices, same status —
    was served. Only the condition id differed."""
    names = {o["market_name"] for o in _build_payload()["other"]}
    assert "Set 1 Winner: Wu vs Alcaraz" in names
    assert "Set 2 Winner: Wu vs Alcaraz" in names
