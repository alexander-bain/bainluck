"""#6769 — a settled whole-game stat leg is served as a graded result, or is
accounted for by a NAMED exclusion. It is never deleted in silence, and it is
never served as somebody else's points total.

## What #6769 turned out to be on the current base

The issue measured 479 of 987 resolved markets "unserved" by NAME intersection,
before #6751 merged, and guessed that the `team_total` / `game_total` / `other`
half "never enters step 9 at all". Traced by market/outcome IDENTITY on base
`8264130bc`, that guess is wrong for most of the cohort and right for a precise
residue:

* **Most of it rode #6751.** A Kalshi stat market is named
  `"Buffalo vs Houston: Passing Yards"` and its legs are `"Josh Allen: 225+"`.
  The `team_total` and `other` branches of `_build_game_markets` already hand a
  leg matching `_PLAYER_OUTCOME_RE` to `player_props`, so those legs DO reach
  step 9 — and #6751's third branch readmits them once graded. The public
  `/game-markets` response for the primary specimen went from 6 `player_props`
  rows (banked BEFORE-6751 payload) to 399 (refreshed 2026-09-17 23:14Z, build
  `v4704`), Passing Yards, Rushing Yards, Passing Attempts and Receptions among
  them.

* **The residue is the leg `_PLAYER_OUTCOME_RE` does not recognise.** That regex
  demands two capitalised name tokens made of letters, so it refuses
  `"C.J. Stroud: 10+"` (an initial carries a full stop), `"T.J. Hockenson:
  15+"`, and every single-token team subject — `"Detroit: 250+"`,
  `"Houston: 300+"`. In a `team_total`-classified market such a leg falls
  through to `totals_thresholds` wearing `market_type: team_total`, i.e. as a
  rung of one side's POINTS total. Two things then happen to it, both measured
  on the refreshed public payload for `14780141` (Bills @ Texans):

    - threshold inside football's team band (5–65): it is SERVED in
      `team_totals[]` as `team_name: "Houston Texans", team_side: "home"` —
      C.J. Stroud's six Rushing Yards rungs printed as the Texans' points
      ladder. Across the 14 banked payloads every colon-subject row in
      `team_totals[]` (18 of 18) is this misfiling; none is a real points total.
    - threshold outside it: step 7a's sport-range guard deletes it. Stroud's
      Passing Yards rungs are absent while Josh Allen's nine are served from the
      SAME market; `Team Total Yards` is absent whole from Atlanta–Pittsburgh
      (both subjects one token) and half-served on New Orleans–Detroit (only
      "New Orleans: N+").

* **`game_total`: "Total Touchdowns".** `"total"` in the name and no period
  marker classifies it as the game's combined POINTS total. Its thresholds are
  single digits, football's band is 15–120, so 7a deletes every rung, graded or
  not. Absent from all four refreshed payloads.

* **`other`: "Passing Attempts", "Receptions".** An unrecognised subject here
  falls to `other[]` and IS served, graded (`"C.J. Stroud: 27+"`, `is_winner:
  true`, `api_settlement` on the refreshed payload). That is an existing
  equivalent destination, not a loss, and this change leaves it alone.

## The rule these tests pin

1. In a `team_total` market, a leg shaped `"<subject>: N+"` names its own
   subject and is that subject's stat ladder — never a rung of a side's points
   total. It takes the rail its siblings already take (`player_props`), in every
   event state, so a leg does not change buckets when the whistle blows.
2. A `game_total` / `team_total` rung that 7a's range guard is going to delete
   is served in `other[]` instead when — and only when — it sits on a market
   LINKED to this event and `_settled_grade_fields` publishes an authoritative
   verdict for it. Ungraded, unlinked, unresolved or wrong-fixture rungs are
   dropped exactly as they are today: the contamination guard is not loosened.

## Provenance of the inputs

Every market below is a SYNTHETIC fixture built with the repo's seeded route
harness. Names, tickers and leg spellings marked "as served" are copied from the
public `/game-markets` payloads named above; prices and grades are
reconstructed, NOT captured database rows. The outcome spelling of "Total
Touchdowns" was not observable anywhere (the market is served nowhere), so both
Kalshi ladder spellings are exercised.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

EVENT_ID = 14780141  # Bills @ Texans — the refreshed public specimen.
GRADED = {"resolution_source": "api_settlement"}

# ── team_total: lone stat word, per-subject legs (names/legs as served) ────────
RUSH_NAME = "Buffalo vs Houston: Rushing Yards"
RUSH_TICKER = "KXNFLRSHYDS-26SEP13BUFHOU"
PASS_NAME = "Buffalo vs Houston: Passing Yards"
PASS_TICKER = "KXNFLPASSYDS-26SEP13BUFHOU"
RECOGNISED_LEG = "Josh Allen: 40+"          # two plain tokens — served today
INITIALLED_IN_BAND_WON = "C.J. Stroud: 10+"   # threshold inside 5–65
INITIALLED_IN_BAND_LOST = "C.J. Stroud: 20+"
INITIALLED_OUT_OF_BAND_WON = "C.J. Stroud: 225+"   # threshold outside 5–65
INITIALLED_OUT_OF_BAND_LOST = "C.J. Stroud: 275+"
UNGRADED_EXTREME_LEG = "C.J. Stroud: 350+"    # the #921 cohort — must stay out

# ── team_total by "team" + "total": single-token team subjects ────────────────
TTY_NAME = "Buffalo vs Houston: Team Total Yards"
TTY_TICKER = "KXNFLTEAMYDS-26SEP13BUFHOU"  # synthetic ticker
TEAM_SUBJECT_WON = "Houston: 300+"
TEAM_SUBJECT_LOST = "Buffalo: 400+"

# ── game_total whose unit is not the score ────────────────────────────────────
TD_NAME = "Buffalo vs Houston: Total Touchdowns"
TD_TICKER = "KXNFLTOTALTD-26SEP13BUFHOU"  # synthetic ticker
TD_SPELLINGS = {
    "over": ("Over 4.5 touchdowns scored", "Over 7.5 touchdowns scored"),
    "plus": ("5+", "8+"),
    # live/363: THE SPELLING THE VENUE ACTUALLY USES, which the candidate could
    # not observe because the market is served nowhere — so both rows above were
    # guesses and neither is it. Read off the stored rows for the specimen's own
    # market (60482141, `Buffalo vs Houston: Total Touchdowns`, `resolved`, 6/6
    # graded) and confirmed to be the ONLY ladder spelling Kalshi ships for this
    # family: the distinct outcome names across every `%Total Touchdowns%`
    # market that is not a team market are `3+ … 9+ touchdowns`, `Over`, `Under`
    # and nothing else. It matters because the threshold has to survive a
    # trailing NOUN — `"5+"` and `"Over 4.5 touchdowns scored"` both parse by a
    # different path than `"3+ touchdowns"` does.
    "venue": ("3+ touchdowns", "9+ touchdowns"),
}

# ── other: served today in `other[]`, an equivalent destination ───────────────
ATT_NAME = "Buffalo vs Houston: Passing Attempts"
ATT_TICKER = "KXNFLPASSATT-26SEP13BUFHOU"
ATT_LEG = "C.J. Stroud: 27+"

# ── healthy controls: REAL points totals, which must not move ────────────────
TEAM_TOTAL_NAME = "Buffalo vs Houston: Team Total"
TEAM_TOTAL_TICKER = "KXNFLTEAMTOTAL-26SEP13BUFHOU"
TEAM_TOTAL_LEG = "Houston over 20.5 points scored"
GAME_TOTAL_NAME = "Buffalo vs Houston: Total Points"
GAME_TOTAL_TICKER = "KXNFLTOTAL-26SEP13BUFHOU"
GAME_TOTAL_LEG = "Over 40.5 points scored"

# ── excluded controls: the contamination the range guard exists for ──────────
FOREIGN_UNGRADED_NAME = "Buffalo vs Houston: Total Goals"   # hockey-sized line
FOREIGN_UNGRADED_LEG = "Over 5.5 goals scored"
UNRESOLVED_NAME = "Buffalo vs Houston: Total Sacks"
UNRESOLVED_LEG = "Over 4.5 sacks recorded"
UNLINKED_NAME = "Buffalo vs Houston: Total Field Goals"
UNLINKED_LEG = "Over 3.5 field goals made"


def _market(id_, name, ticker, *, status, linked=True):
    m = _make_futures_market(id=id_, name=name, source="kalshi",
                             sport_category="football")
    m.external_id = ticker
    m.event_id = EVENT_ID if linked else None
    m.market_tier = 5
    m.category = "game_prop"
    # `_settled_grade_fields` requires `resolved` before it publishes a verdict.
    m.status = status
    m.settled_at = None
    return m


def _bills_at_texans(status: str, td_spelling: str = "over"):
    finished = status == "completed"
    event = _make_event(
        id=EVENT_ID,
        home_team="Houston Texans",
        away_team="Buffalo Bills",
        status=status,
        sport_key="americanfootball_nfl",
        home_score=27,
        away_score=24,
    )
    event.llm_league = "NFL"
    event.period = None if finished else "Q3"
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=6)
    event.completed_at = (
        datetime.now(timezone.utc) - timedelta(hours=3) if finished else None
    )
    event.box_score_data = {
        "players": {},
        "home_period_scores": [7, 6, 7, 7],
        "away_period_scores": [3, 7, 7, 7],
    }

    mstatus = "resolved" if finished else "open"
    td_won, td_lost = TD_SPELLINGS[td_spelling]
    markets = [
        _market(701, RUSH_NAME, RUSH_TICKER, status=mstatus),
        _market(702, PASS_NAME, PASS_TICKER, status=mstatus),
        _market(703, TTY_NAME, TTY_TICKER, status=mstatus),
        _market(704, TD_NAME, TD_TICKER, status=mstatus),
        _market(705, ATT_NAME, ATT_TICKER, status=mstatus),
        _market(706, TEAM_TOTAL_NAME, TEAM_TOTAL_TICKER, status=mstatus),
        _market(707, GAME_TOTAL_NAME, GAME_TOTAL_TICKER, status=mstatus),
        _market(708, FOREIGN_UNGRADED_NAME, "KXNFLTOTALGOALS-26SEP13BUFHOU",
                status=mstatus),
        # Carries a resolution_source but the market never reached `resolved`:
        # `_settled_grade_fields` withholds, so there is no verdict to serve.
        _market(709, UNRESOLVED_NAME, "KXNFLTOTALSACKS-26SEP13BUFHOU",
                status="open"),
        # Graded and resolved, but only name-matched to this game (no stored
        # link) — the "overly broad fallback" half of the guard's purpose.
        _market(710, UNLINKED_NAME, "KXNFLTOTALFG-26SEP13BUFHOU",
                status=mstatus, linked=False),
    ]

    def leg(id_, market_id, name, won):
        if not finished:
            # A live ladder: a real mid-band price and no grade anywhere.
            return _make_outcome(id=id_, market_id=market_id, name=name,
                                 probability=0.55)
        return _make_outcome(id=id_, market_id=market_id, name=name,
                             probability=1.0 if won else 0.0,
                             is_winner=won, **GRADED)

    outcomes = [
        leg(7011, 701, RECOGNISED_LEG, True),
        leg(7012, 701, INITIALLED_IN_BAND_WON, True),
        leg(7013, 701, INITIALLED_IN_BAND_LOST, False),
        leg(7021, 702, INITIALLED_OUT_OF_BAND_WON, True),
        leg(7022, 702, INITIALLED_OUT_OF_BAND_LOST, False),
        _make_outcome(id=7023, market_id=702, name=UNGRADED_EXTREME_LEG,
                      probability=0.01, is_winner=None, resolution_source=None),
        leg(7031, 703, TEAM_SUBJECT_WON, True),
        leg(7032, 703, TEAM_SUBJECT_LOST, False),
        leg(7041, 704, td_won, True),
        leg(7042, 704, td_lost, False),
        leg(7051, 705, ATT_LEG, True),
        leg(7061, 706, TEAM_TOTAL_LEG, True),
        leg(7071, 707, GAME_TOTAL_LEG, True),
        _make_outcome(id=7081, market_id=708, name=FOREIGN_UNGRADED_LEG,
                      probability=0.62, is_winner=None, resolution_source=None),
        _make_outcome(id=7091, market_id=709, name=UNRESOLVED_LEG,
                      probability=1.0, is_winner=True, **GRADED),
        _make_outcome(id=7101, market_id=710, name=UNLINKED_LEG,
                      probability=1.0, is_winner=True, **GRADED),
    ]
    return event, markets, outcomes


async def _get_game_markets(status: str, td_spelling: str = "over") -> dict:
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _bills_at_texans(status, td_spelling)
    session = _make_event_detail_session(event=event, futures=futures,
                                         outcomes=outcomes)

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get(f"/api/events/{EVENT_ID}/game-markets")
    finally:
        app.dependency_overrides.clear()
        _game_markets_cache.clear()
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture
async def finished():
    return await _get_game_markets("completed")


@pytest.fixture
async def live():
    return await _get_game_markets("live")


_BUCKETS = ("totals", "team_totals", "player_props", "spreads",
            "period_markets", "other")


def _where(payload: dict, market_name: str, outcome_name: str) -> dict:
    """{bucket: row} for every bucket serving this exact market+leg identity."""
    found = {}
    for bucket in _BUCKETS:
        for row in payload.get(bucket) or []:
            if (row.get("market_name") == market_name
                    and row.get("outcome_name") == outcome_name):
                found[bucket] = row
    return found


# ═══ the fixture is wired: a reader of an empty page proves nothing ═══════════


async def test_the_controls_that_are_healthy_today_are_served(finished):
    assert set(_where(finished, RUSH_NAME, RECOGNISED_LEG)) == {"player_props"}
    assert set(_where(finished, TEAM_TOTAL_NAME, TEAM_TOTAL_LEG)) == {"team_totals"}
    assert set(_where(finished, GAME_TOTAL_NAME, GAME_TOTAL_LEG)) == {"totals"}


# ═══ team_total: a "<subject>: N+" leg is its subject's ladder ════════════════


@pytest.mark.parametrize("leg,won", [
    (INITIALLED_IN_BAND_WON, True),
    (INITIALLED_IN_BAND_LOST, False),
])
async def test_an_initialled_players_leg_is_not_served_as_a_teams_points_total(
    finished, leg, won
):
    """THE MISFILING. On base this row is in `team_totals[]` tagged
    `team_name: "Houston Texans"` — a quarterback's rushing ladder printed as
    the Texans' points ladder."""
    served = _where(finished, RUSH_NAME, leg)
    assert "team_totals" not in served, served.get("team_totals")
    assert set(served) == {"player_props"}
    row = served["player_props"]
    assert row["_market_id"] == 701
    assert row["threshold"] == float(leg.split(": ")[1].rstrip("+"))
    assert row["is_winner"] is won
    assert row["resolution_source"] == "api_settlement"
    assert row["over_probability"] == (1.0 if won else 0.0)
    assert "team_side" not in row and "team_name" not in row


@pytest.mark.parametrize("leg,won", [
    (INITIALLED_OUT_OF_BAND_WON, True),
    (INITIALLED_OUT_OF_BAND_LOST, False),
])
async def test_an_initialled_players_out_of_band_leg_is_not_deleted(
    finished, leg, won
):
    """THE SILENT LOSS. Same market as nine served Josh Allen rungs; on base the
    range guard deletes these because 225 is not a football team's points."""
    served = _where(finished, PASS_NAME, leg)
    assert set(served) == {"player_props"}
    row = served["player_props"]
    assert row["_market_id"] == 702
    assert row["is_winner"] is won
    assert row["resolution_source"] == "api_settlement"


@pytest.mark.parametrize("leg,won", [
    (TEAM_SUBJECT_WON, True),
    (TEAM_SUBJECT_LOST, False),
])
async def test_a_one_word_team_subject_is_served_beside_its_two_word_sibling(
    finished, leg, won
):
    """`"New Orleans: 250+"` is served today and `"Detroit: 250+"` is not — the
    only difference is how many words the city has."""
    served = _where(finished, TTY_NAME, leg)
    assert set(served) == {"player_props"}
    row = served["player_props"]
    assert row["_market_id"] == 703
    assert row["is_winner"] is won
    # A team is not on a roster: the enrichment must not pin it to a side it
    # guessed, which is the orientation half of the misfiling above.
    assert row.get("player_team") is None


async def test_an_ungraded_extreme_leg_is_still_dropped(finished):
    """#921, unchanged: routing a leg to the prop rail does not exempt it from
    step 9. No grade in hand and a dead price is still not a card."""
    assert _where(finished, PASS_NAME, UNGRADED_EXTREME_LEG) == {}


# ═══ game_total: a graded rung the range guard removes is served in other[] ═══


@pytest.mark.parametrize("spelling", sorted(TD_SPELLINGS))
async def test_settled_total_touchdowns_reaches_the_page_graded(spelling):
    payload = await _get_game_markets("completed", spelling)
    td_won, td_lost = TD_SPELLINGS[spelling]

    won = _where(payload, TD_NAME, td_won)
    lost = _where(payload, TD_NAME, td_lost)
    assert set(won) == {"other"} and set(lost) == {"other"}

    # The existing `other[]` graded-row contract, key for key — what the web
    # `OtherMarketRow` and the native `GameMarketOther` already decode.
    assert won["other"]["is_winner"] is True
    assert lost["other"]["is_winner"] is False
    for row in (won["other"], lost["other"]):
        assert row["resolution_source"] == "api_settlement"
        assert row["source"] == "kalshi"
        assert row["_market_id"] == 704
        assert {"market_name", "outcome_name", "probability", "observed_at"} <= set(row)

    # …and it is still NOT a points total: nothing of it prices the game.
    assert all(t["market_name"] != TD_NAME for t in payload["totals"])


async def test_real_points_totals_keep_their_bucket_and_their_side(finished):
    team = _where(finished, TEAM_TOTAL_NAME, TEAM_TOTAL_LEG)["team_totals"]
    assert team["market_type"] == "team_total"
    assert team["team_side"] == "home" and team["team_name"] == "Houston Texans"
    assert team["is_winner"] is True

    game = _where(finished, GAME_TOTAL_NAME, GAME_TOTAL_LEG)["totals"]
    assert game["market_type"] == "game_total" and game["threshold"] == 40.5
    # Nothing but real points totals is left in either points bucket.
    assert {t["market_name"] for t in finished["team_totals"]} == {TEAM_TOTAL_NAME}
    assert {t["market_name"] for t in finished["totals"]} == {GAME_TOTAL_NAME}


# ═══ retained exclusions: the contamination guard is not loosened ═════════════


@pytest.mark.parametrize("market_name,leg,why", [
    (FOREIGN_UNGRADED_NAME, FOREIGN_UNGRADED_LEG, "no grade at all"),
    (UNRESOLVED_NAME, UNRESOLVED_LEG, "market not resolved — verdict withheld"),
    (UNLINKED_NAME, UNLINKED_LEG, "name-matched only, no stored link"),
])
async def test_an_out_of_band_rung_without_a_trustworthy_grade_stays_out(
    finished, market_name, leg, why
):
    assert _where(finished, market_name, leg) == {}, why


async def test_the_other_class_keeps_its_existing_destination(finished):
    """Passing Attempts / Receptions with an unrecognised subject are served in
    `other[]` on base, graded. An equivalent destination is not a loss; this
    change does not move it."""
    served = _where(finished, ATT_NAME, ATT_LEG)
    assert set(served) == {"other"}
    assert served["other"]["is_winner"] is True
    assert served["other"]["resolution_source"] == "api_settlement"


# ═══ live: the routing is a fact about the leg, not about the whistle ═════════


async def test_a_live_initialled_leg_is_a_prop_with_its_live_price(live):
    for market_name, leg in ((RUSH_NAME, INITIALLED_IN_BAND_WON),
                             (PASS_NAME, INITIALLED_OUT_OF_BAND_WON),
                             (TTY_NAME, TEAM_SUBJECT_WON)):
        served = _where(live, market_name, leg)
        assert set(served) == {"player_props"}, (market_name, leg, served)
        row = served["player_props"]
        assert row["over_probability"] == 0.55
        # A live payload carries none of the settled-grade keys (#190 contract).
        assert "is_winner" not in row and "hit" not in row


async def test_a_live_out_of_band_total_is_dropped_exactly_as_before(live):
    """No verdict, so nothing to serve: the `other[]` route is settled-only and
    a live "Total Touchdowns" rung is as absent as it is on base."""
    td_won, td_lost = TD_SPELLINGS["over"]
    assert _where(live, TD_NAME, td_won) == {}
    assert _where(live, TD_NAME, td_lost) == {}
    assert set(_where(live, GAME_TOTAL_NAME, GAME_TOTAL_LEG)) == {"totals"}
    assert set(_where(live, TEAM_TOTAL_NAME, TEAM_TOTAL_LEG)) == {"team_totals"}


# ═══ live/363: THE DISCRIMINATOR, ON SPELLINGS READ OFF PRODUCTION ═══════════
#
# The fixtures above are NFL, because the #6751 cohort is. Codex's Brief-21
# checkpoint asks for the semantic control on the wider population — "regex
# shape alone is not universal proof" — so this pins the rule against the
# strings a reader is actually being served, on a cohort the candidate never
# saw.
#
# MEASURED 2026-09-18 02:4xZ, live/363, two independent passes:
#
#  (a) SERVED payloads. `/api/events/{id}/game-markets` for ten events across
#      NFL, MLB, NCAAF, WNBA, CFL, boxing, esports and two soccer leagues: 168
#      rows in `team_totals[]`, of which 11 match this shape and ALL ELEVEN are
#      misfilings — six C.J. Stroud Rushing Yards rungs on 14780141, and on MLB
#      15308413 (A's at Blue Jays, completed) `Andrés Giménez: N+` and
#      `Max Muncy (ATH): N+` from `Toronto vs A's: Hits` and `: Home Runs`,
#      every one of them tagged `team_name: "Toronto Blue Jays"` — including an
#      Athletics batter printed as a Blue Jays run ladder. ZERO of the 157
#      genuine rows match: their whole vocabulary is `Over`, `Under` and
#      `"<City> over N points scored"`.
#
#  (b) STORED rows. Every market on a linked event whose legs carry this shape,
#      grouped by the stat its name ends in: 40 distinct stats across MLB, NFL,
#      NCAAF and two soccer leagues — Hits, Total Bases, Receiving Yards, Team
#      Corners, Team Sacks, Team Total Yards … — and not one of them is a side's
#      POINTS/GOALS/RUNS total.
#
# The two failures of `_PLAYER_OUTCOME_RE` this adds to the initial-and-
# single-token cases already covered above are an ACCENT (`é` is not in
# `[A-Za-z]`) and a PARENTHETICAL disambiguator. Neither is an NFL phenomenon,
# and both are on production today.
#
# The negative arm is the load-bearing half: if a future widening ever lets a
# genuine points-total spelling through, the leg leaves the totals map and the
# projection loses a rung. `Exact Margin: Lions by 25+` is the near-miss that
# makes the point — a real Polymarket leg (market 58586145) with a colon, a
# number and a plus sign that is NOT this shape, because the digits do not
# follow the colon.


@pytest.mark.parametrize("leg", [
    "Andrés Giménez: 1+",      # MLB, served in team_totals[] as a Blue Jay
    "Andrés Giménez: 4+",
    "Max Muncy (ATH): 2+",     # an Athletic, served as a Blue Jay
    "C.J. Stroud: 10+",        # the NFL specimen, for completeness
    "T.J. Hockenson: 15+",
    "Detroit: 250+",
    "Brazil: 6+",              # soccer Team Corners, one-token country
    "Panama: 8+",
    "North Carolina: 2+",      # NCAAF Team Total Touchdowns
    "Josh Allen: 40+",         # already recognised — must stay recognised
])
def test_a_production_stat_ladder_leg_names_its_own_subject(leg):
    from app.routes.events import _leg_names_its_own_subject

    assert _leg_names_its_own_subject(leg) is True, leg


@pytest.mark.parametrize("leg", [
    "Over",                                  # 157/168 served rows are these
    "Under",
    "Buffalo over 7.5 points scored",
    "Detroit over 10.5 1H points scored",
    "Over 45.5",
    "Over 40.5 points scored",
    "Exact Margin: Lions by 25+",            # the near-miss, market 58586145
    "Exact Margin: Bills by 21+",
    "Houston scores first TD",
    "No team scores a TD",
    "",
])
def test_a_real_points_total_leg_does_not(leg):
    from app.routes.events import _leg_names_its_own_subject

    assert _leg_names_its_own_subject(leg) is False, leg
