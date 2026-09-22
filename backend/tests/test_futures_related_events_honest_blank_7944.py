"""#7944: a market the venue says is NOT a sport stops serving 21 football games.

WHAT A READER SAW, on production 2026-09-21 21:32 PDT, on `/futures/61461617` —
**2027 Steel Bridge National Champion**, a student engineering competition,
badged `OTHER` — under a heading that reads "Games This Week" and a caption that
reads "Each team's odds in this market":

    Liberty Flames        at  Coastal Carolina Chanticleers
    Clemson Tigers        at  California Golden Bears
    Texas A&M Aggies      at  LSU Tigers
    … eighteen more college football fixtures

None of them has anything to do with a bridge-building contest, and the caption
asserts that all of them do.

═══ WHY THE #2553 CLAUSE DID NOT CATCH IT ═══

`get_related_events` has constrained this strip by sport since #2553 (the MLB
World Series page serving MLS fixtures — `test_futures_related_events_sport_guard`,
whose rig this file reuses so the two guards can never diverge on the mechanics).
That clause fails open, deliberately:

    A market with no category, or a category the map does not carry, gets the
    old behaviour … an absent category is not evidence of a wrong sport.

Right when written. What changed is what can reach it. `llm_sport_category` now
also holds `"other"` — `NO_SPORT_CATEGORY`, #1888's door — which is not a
category the map happens to miss but the venue being asked for a sport and
answering that there isn't one (#7900's `HONEST_BLANK`, written when Kalshi tags
a series literally `Other`). `LLM_CATEGORY_TO_SPORT_PREFIX.get()` spells
"declined" and "unmapped" with the same `None`, so the strongest possible
evidence that no fixture belongs on this page arrived at the branch reserved for
the weakest.

So the rule is now two rules: **absent fails open, declined fails closed.**

═══ WHAT THE ARMS ARE ═══

  * **RED-FIRST**: with the new clause disabled (the constant pointed at a value
    no market carries), the football fixtures come back on the contest page. The
    "before" state is executed, not remembered.
  * **CONTROL, admitted**: a NULL-category market still gets its games in the
    same file. "Refuse X unless Y" is two clauses, and a guard that only proves
    the refusal would pass just as well against a route that emptied every
    strip — which is precisely the outcome #2553's fail-open paragraph exists to
    forbid.
  * **CONTROL, mapped**: a baseball market still serves its baseball game, so
    the early return cannot have been hoisted above the ordinary path.
  * **DRIFT**: the two spellings of the value (`sport_keys.NO_SPORT_CATEGORY`,
    which the route tests against, and `repair_kalshi_series_tag_category.HONEST_BLANK`,
    which the rail writes) are asserted equal, and the value is asserted ABSENT
    from `LLM_CATEGORY_TO_SPORT_PREFIX` — giving it a key there would send the
    contest back down the fail-open branch with every test here still green.

NOT THIS ISSUE: those 52 outcomes are universities carrying the `teams.id` of
NCAAF teams, which is the cross-domain `futures_outcomes.team_id` corruption
#2553's comment already names and #2693 owns. Nothing here touches a link, and
the clause is correct whatever the links say — which is the same reason #2553
was a WHERE clause and not a data patch.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Event, FuturesMarket, FuturesOutcome, Sport, Team
from app.routes.futures import get_related_events
from app.utils.sport_keys import LLM_CATEGORY_TO_SPORT_PREFIX, NO_SPORT_CATEGORY

# The #2553 rig: a fake session that answers the route's own compiled WHERE
# clause. Reused rather than re-implemented — a second copy would be a second
# thing to keep true, and its subtleties (whereclause only, never the full
# statement) were bought with CERT-2805's finding.
from tests.test_futures_related_events_sport_guard import (  # noqa: E402
    _FakeSession,
    _market as _mlb_market,
    _events as _mlb_events,
)


# ── The contest, and the football it was serving ─────────────────────────────

NCAAF = Sport(id=9101, key="americanfootball_ncaaf", name="NCAAF")

_SOON = datetime.now(timezone.utc) + timedelta(days=2)

# Two universities that really are in the market's outcome list, carrying the
# team ids of their football programmes — the corrupt link, in shape.
CLEMSON = Team(id=7701, sport_id=NCAAF.id, name="Clemson Tigers")
LSU = Team(id=7702, sport_id=NCAAF.id, name="LSU Tigers")

STEEL_BRIDGE_ID = 61461617


def _contest_market() -> FuturesMarket:
    """`KXSTEELBRIDGE-27`, as production carries it after #7900."""
    market = FuturesMarket(
        id=STEEL_BRIDGE_ID,
        source="kalshi",
        external_id="KXSTEELBRIDGE-27",
        name="2027 Steel Bridge National Champion",
        category="championship",
        # 🔴 THE LITERAL, NOT `NO_SPORT_CATEGORY`. The specimen is the string the
        # database holds for row 61461617, and a fixture built from the constant
        # is a fixture that agrees with the route however the constant drifts:
        # repointing it at `"no_sport"` left this arm green (measured) because
        # the market moved with it, and only the drift test below convicted.
        llm_sport_category="other",
        status="open",
    )
    market.outcomes = [
        FuturesOutcome(
            id=20,
            market_id=STEEL_BRIDGE_ID,
            name="Clemson",
            team_id=CLEMSON.id,
            current_probability=0.07,
            rank=1,
        ),
        FuturesOutcome(
            id=21,
            market_id=STEEL_BRIDGE_ID,
            name="LSU",
            team_id=LSU.id,
            current_probability=0.04,
            rank=2,
        ),
    ]
    return market


def _football_fixtures() -> list[Event]:
    """What the join returns for those team ids: college football games."""
    out = []
    for idx, (home, away) in enumerate(
        [(CLEMSON, LSU), (LSU, CLEMSON)], start=1
    ):
        event = Event(
            id=15500000 + idx,
            sport_id=NCAAF.id,
            home_team_id=home.id,
            away_team_id=away.id,
            home_team_name=home.name,
            away_team_name=away.name,
            status="scheduled",
            commence_time=_SOON + timedelta(hours=idx),
        )
        event.sport = NCAAF
        out.append(event)
    return out


@pytest.mark.asyncio
async def test_the_contest_page_serves_no_games():
    session = _FakeSession(_contest_market(), _football_fixtures())

    payload = await get_related_events(STEEL_BRIDGE_ID, db=session)

    assert payload["events"] == [], (
        "a market the venue declined to call a sport served fixtures again: "
        f"{[e['home_team'] + ' v ' + e['away_team'] for e in payload['events']]}"
    )
    # The empty strip is a STATED zero, not an absent field — the reader-facing
    # half of this route's payload contract.
    assert payload["total_count"] == 0
    assert payload["market_id"] == STEEL_BRIDGE_ID
    assert payload["market_name"] == "2027 Steel Bridge National Champion"


@pytest.mark.asyncio
async def test_without_the_clause_the_football_comes_back(monkeypatch):
    """RED-FIRST, executed. Disable the new branch; the defect returns.

    The constant is repointed rather than the market's category edited: this has
    to reproduce what production served for a row whose stored value really is
    `other`, and a market carrying some other string would be a different
    specimen answering a different question.
    """
    import app.routes.futures as futures_module

    monkeypatch.setattr(
        futures_module, "NO_SPORT_CATEGORY", "__a_value_no_market_carries__"
    )
    session = _FakeSession(_contest_market(), _football_fixtures())

    payload = await get_related_events(STEEL_BRIDGE_ID, db=session)

    assert len(payload["events"]) == 2, (
        "the red-first arm did not reproduce the defect, so the green arm above "
        "is not evidence of anything"
    )
    assert {e["sport"] for e in payload["events"]} == {"americanfootball_ncaaf"}


@pytest.mark.asyncio
async def test_a_market_with_no_category_still_gets_its_games():
    """CONTROL, admitted. Absent is not declined, and must still fail OPEN.

    Without this arm the file passes against a route that returns an empty strip
    for everything — the regression #2553's fail-open paragraph forbids, and the
    one a refusal-only guard cannot see.
    """
    market = _mlb_market()
    market.llm_sport_category = None
    session = _FakeSession(market, _mlb_events())

    payload = await get_related_events(1, db=session)

    assert len(payload["events"]) == 2


@pytest.mark.asyncio
async def test_a_mapped_market_still_serves_its_own_sport():
    """CONTROL. The early return did not swallow the ordinary path."""
    session = _FakeSession(_mlb_market(), _mlb_events())

    payload = await get_related_events(1, db=session)

    assert [e["sport"] for e in payload["events"]] == ["baseball_mlb"]
    assert payload["total_count"] == 1


def test_the_two_spellings_of_the_declined_value_agree():
    """The rail writes it; this route tests against it. One value, two modules.

    A drift here is silent in both directions: the rail would keep writing
    `other` while the route refused a string nothing carries (strip defect
    returns, every arm above still green), or the route would close on a value
    the rail never writes.
    """
    from app.tasks.repair_kalshi_series_tag_category import HONEST_BLANK

    assert HONEST_BLANK == NO_SPORT_CATEGORY


def test_the_declined_value_is_not_a_category_the_map_carries():
    """Giving `other` a prefix would re-open the fail-open branch silently.

    The route's test is `== NO_SPORT_CATEGORY`, which runs BEFORE the lookup, so
    a key added here would not change any assertion in this file — it would
    change the meaning of the constant's docstring instead, which is why the
    guard is on the map and not on the branch.
    """
    assert NO_SPORT_CATEGORY not in LLM_CATEGORY_TO_SPORT_PREFIX
    assert NO_SPORT_CATEGORY not in set(LLM_CATEGORY_TO_SPORT_PREFIX.values())
