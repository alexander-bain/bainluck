"""The team page spells a club the same way its own footer does (#2142).

WHAT A READER SAW
=================

`/sport/baseball/mlb/team/new-york-yankees-mlb`, 390px, production 2026-09-20.
Four Season Futures rows read **`New York Y`** — American League Champion 23.5%,
Pro Baseball Champion 10%, AL East Division Winner 3.5%, Pro Baseball Best
Record 1% — sitting in the same list as the odds-api row spelling the club
`New York Yankees`, above a footer reading "New York Yankees · 30 markets
tracked". Frame: `artifacts-lane1b-428/BEFORE-yankees-390.png`.

Kalshi ships club names truncated. #6479 built the repair — read the nickname
off the rung's OWN id-anchored ticker (`futures_outcomes.external_id` is
`KXMLB-26-NYY`) — and it was wired into `routes/futures.py`, `routes/feed.py`
and `routes/events.py`. `_query_team_futures`, which serves the team page AND
"Your Teams' Futures", was never wired to it.

WHAT THESE TESTS PIN, AND WHY EACH ONE EXISTS
=============================================

1. The repair fires on the specimen, through the real function, not through a
   direct call to the helper (a helper test already exists — #6479's — and it
   would stay green with the call site missing, which is exactly the defect).
2. It abstains on a player carrying a generational suffix. This is the whole
   safety argument: `James Cook III` has the identical trailing-capitals shape
   and is 20 of the 238 live rows. Its ticker leg is a player code, so the
   helper declines. If that ever changes, a reader gets `James Cook Bills`.
3. It leaves an already-correct name alone — correct data is not rewritten.
4. THE MUTATION CONTROL ON WHERE THE REPAIR SITS. `_find_matched_team` reads
   the RAW name on purpose. A truncated row with no `team_id` does not match
   its club by name today and must not start to: moving the repair upstream of
   the matcher would change WHICH rows reach a team page, not just how they are
   spelled. That test goes red the moment the call is hoisted.

Population behind this (production, 2026-09-20, open Kalshi, team-bound rows of
this shape): 238 rows, of which the helper repairs 120 across 8 clubs
(`New York J` 43, `New York G` 35, `Los Angeles C` 12, `Los Angeles A` 6,
`New York Y` 6, `New York M` 6, `Chicago C` 5, `Los Angeles D` 5,
`Los Angeles L` 2) and abstains on 110.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _ns_team(**kw):
    """Team stand-in for `_query_team_futures` (attribute holder, no DB)."""
    kw.setdefault("roster_players", None)
    kw.setdefault("logo_url_small", None)
    kw.setdefault("logo_url", None)
    kw.setdefault("primary_color", None)
    kw.setdefault("espn_id", None)
    return SimpleNamespace(**kw)


def _result_all(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _outcome(name, external_id, team_id, probability=0.235):
    return SimpleNamespace(
        id=abs(hash((name, external_id))) % 100000,
        name=name,
        external_id=external_id,
        team_id=team_id,
        current_probability=probability,
        probability_change_24h=0.0,
        rank=1,
        is_winner=False,
    )


def _market(mid, name, category="baseball"):
    return SimpleNamespace(
        id=mid,
        name=name,
        market_tier=1,
        llm_sport_category=category,
        source="kalshi",
        resolution_date=None,
        canonical_market_key=None,
    )


async def _run(team, outcome_market_pairs, sport_key="baseball_mlb"):
    """Drive the real `_query_team_futures` over one team and some rows.

    A single team means the identity-collapse branch (and its
    identity-mapping-count query) does not run, so the call sequence is:
    load teams → q1 FK branch → q1 name-ILIKE branch → per-market stats.
    """
    from app.routes.user import _query_team_futures

    rows = [(o, m, sport_key) for o, m in outcome_market_pairs]
    stats = [(m.id, 30, 1.0) for _o, m in outcome_market_pairs]

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _result_all([(team, sport_key)]),
        _result_all(rows),
        _result_all([]),
        _result_all(stats),
    ])
    return await _query_team_futures([team.id], db, limit=20)


@pytest.mark.asyncio
async def test_the_truncated_club_is_spelled_out_on_the_team_page():
    """`New York Y` on the Yankees page reads `New York Yankees` (#2142)."""
    yankees = _ns_team(id=6610, name="New York Yankees", sport_id=4)
    data = await _run(
        yankees,
        [(
            _outcome("New York Y", "KXMLB-26-NYY", 6610),
            _market(274, "American League Champion"),
        )],
    )

    assert len(data["items"]) == 1
    assert data["items"][0]["outcome_name"] == "New York Yankees"
    # The row still belongs to the club it always belonged to.
    assert data["items"][0]["matched_team"]["id"] == 6610


@pytest.mark.asyncio
async def test_a_players_generational_suffix_is_not_a_truncated_club():
    """`James Cook III` keeps every letter the venue sent (#2142 / #6540).

    Twenty live rows carry this shape. The trailing capitals are identical to a
    truncation; the ticker leg `JCOOK4` is a player code, so the repair declines
    and the reader never sees `James Cook Bills`.
    """
    bills = _ns_team(id=999, name="Buffalo Bills", sport_id=2)
    data = await _run(
        bills,
        [(
            _outcome("James Cook III", "KXLEADERNFLRUSHTDS-27-JCOOK4", 999),
            _market(275, "Pro Football Rushing TD Leader", category="football"),
        )],
        sport_key="americanfootball_nfl",
    )

    assert len(data["items"]) == 1
    assert data["items"][0]["outcome_name"] == "James Cook III"


@pytest.mark.asyncio
async def test_a_name_that_is_already_right_is_not_rewritten():
    """Correct data ships untouched — the repair only reaches a truncation."""
    dodgers = _ns_team(id=101, name="Los Angeles Dodgers", sport_id=4)
    data = await _run(
        dodgers,
        [(
            _outcome("Los Angeles Dodgers", "KXMLB-26-LAD", 101),
            _market(276, "Pro Baseball Champion"),
        )],
    )

    assert data["items"][0]["outcome_name"] == "Los Angeles Dodgers"


@pytest.mark.asyncio
async def test_the_repair_does_not_decide_which_rows_reach_the_page():
    """MUTATION CONTROL — the matcher still reads the RAW venue name (#2142).

    `_strict_team_name_matches("New York Yankees", "New York Y")` is False, so a
    truncated row with no `team_id` reaches no team page today. Hoisting the
    repair above `_find_matched_team` would bind it by its repaired spelling and
    silently widen the page's contents. This asserts the row stays out.
    """
    from app.routes.user import _strict_team_name_matches

    assert _strict_team_name_matches("New York Yankees", "New York Y") is False

    yankees = _ns_team(id=6610, name="New York Yankees", sport_id=4)
    data = await _run(
        yankees,
        [(
            _outcome("New York Y", "KXMLB-26-NYY", None),  # no FK to lean on
            _market(277, "Pro Baseball Best Record"),
        )],
    )

    assert data["items"] == []
