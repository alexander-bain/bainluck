"""#9308 — a soccer goals map is made of goals, not corners.

#3995's other sport. Polymarket lists a CORNERS ladder beside the goals ladder on
nearly every soccer fixture, and `_NON_SCORING_TOTAL_RE` knew only baseball's
"bases". Each corners name says "o/u" or "total", and so it fell into the totals
branch as `half_total` when it named a half, and as `game_total` when it did not.

What readers saw on production (2026-09-28):

* Settled León–Juárez `/events/15316429`: the "1st half goals map" read "Four
  lines quoted" 0.5 / 3.5 / 4.5 / 5.5, and the last three were corner counts.
* Japan–Venezuela `/api/events/15312535/game-markets` (upcoming): the goals
  rail's 8.5 and 9.5 rungs were "O/U 8.5 Total Corners" / "O/U 9.5 Total
  Corners", priced 0.008. The real corners lines are 0.49 / 0.36; monotonicity
  had capped them under the goals ladder. The real 8.5-goals line (0.003)
  was the one displaced.

Measured over 60 days of linked totals markets: 26,405 name corners. On a
400-market random sample, the fix moves 389 (303 `game_total` + 86 `half_total`)
to `stat_total`. The other 11 ("Team to Take First Corner") are not totals and
do not move.

Every number below is production's stored price for 15312535, read 2026-09-28
06:5xZ from `futures_outcomes.current_probability`.
"""

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# The sqlite JSONB/ARRAY DDL shims register on import.
import tests.test_runs_map_is_made_of_runs_3995  # noqa: F401
from app.models import Event, Sport
from app.models.models import Base, FuturesMarket, FuturesOutcome
from app.routes.events import _NON_SCORING_TOTAL_RE, _classify_game_market

EVENT_ID = 15312535
SPORT_ID = 1
COMMENCE = datetime(2026, 9, 28, 10, 25, tzinfo=timezone.utc)

#: Kalshi `KXINTLFRIENDLYTOTAL-26SEP28JPNVEN`, "Over N goals scored".
KALSHI_GOALS = ((0.5, 0.955), (1.5, 0.795), (2.5, 0.575), (3.5, 0.335), (4.5, 0.165), (5.5, 0.075))
#: Polymarket's goals lines above the Kalshi ladder.
PM_GOALS = ((6.5, 0.0275), (7.5, 0.0105), (8.5, 0.003))
#: Polymarket's whole-game corners ladder. 7.5 and 8.5 sit exactly on goals rungs.
PM_CORNERS = ((7.5, 0.62), (8.5, 0.49), (9.5, 0.36), (10.5, 0.275), (11.5, 0.185), (12.5, 0.13), (13.5, 0.08))
#: A 1st-half pair of each quantity, in León–Juárez's shape.
PM_HALF_GOALS = ((0.5, 0.72), (1.5, 0.33))
PM_HALF_CORNERS = ((3.5, 0.55), (4.5, 0.38), (5.5, 0.22))


class TestTheClassifierKnowsWhatIsBeingCounted:
    @pytest.mark.parametrize(
        "name,external_id",
        [
            # The issue's specimens (markets 62937887, 62497983, 62497984).
            ("Club León FC vs. FC Juárez: 1st Half O/U 3.5 Total Corners", None),
            ("Club León FC vs. FC Juárez: 2nd Half O/U 5.5 Total Corners", None),
            ("Japan vs. Venezuela: O/U 8.5 Total Corners", None),
            ("Japan vs. Venezuela: O/U 13.5 Total Corners", None),
            # Per-club corners: the club name is not a player, so this reaches the rule.
            ("Club León FC vs. FC Juárez: Club León FC O/U 2.5 Corners", None),
            ("Club León FC vs. FC Juárez: Total Corners Odd or Even?", None),
            # Kalshi's form (43 markets in the window).
            ("Aston Villa vs Nottingham Forest: Total Corners", None),
        ],
    )
    def test_a_total_counted_in_corners_is_a_stat_total(self, name, external_id):
        got = _classify_game_market(name, external_id)
        assert got == "stat_total", f"{name!r} classified {got!r}"

    @pytest.mark.parametrize(
        "name,external_id,expected",
        [
            # 🔴 The goals that must not move. Same fixture, same venue, same shape.
            ("Japan vs. Venezuela: O/U 8.5", None, "game_total"),
            ("Japan vs Venezuela: Total Goals", "KXINTLFRIENDLYTOTAL-26SEP28JPNVEN", "game_total"),
            ("Club León FC vs. FC Juárez: 1st Half O/U 1.5", None, "half_total"),
            ("Club León FC vs. FC Juárez: FC Juárez 1st Half O/U 0.5", None, "half_total"),
            # #3995 still holds.
            ("New York M vs Miami: Total Bases", "KXMLBTB-26SEP081840NYMMIA", "stat_total"),
            ("New York M vs Miami: Total Runs", "KXMLBTOTAL-26SEP081840NYMMIA", "game_total"),
        ],
    )
    def test_the_goals_do_not_move(self, name, external_id, expected):
        assert _classify_game_market(name, external_id) == expected

    def test_a_corner_that_is_not_a_total_is_not_touched(self):
        """The rule lives inside the totals branch. "Team to Take First Corner"
        carries neither "total" nor "o/u", so this change cannot reach it."""
        got = _classify_game_market(
            "FC Sochaux-Montbéliard vs. En Avant Guingamp: Team to Take First Corner", None
        )
        assert got == "other"

    def test_the_word_boundary_cannot_reach_inside_a_club_name(self):
        """Negative control on the regex itself: a word containing "corner" is
        not the word."""
        assert _NON_SCORING_TOTAL_RE.search("total corners") is not None
        assert _NON_SCORING_TOTAL_RE.search("cornerstone united o/u 2.5") is None
        assert _NON_SCORING_TOTAL_RE.search("cornerback yards o/u 40.5") is None


# --------------------------------------------------------------------------
# The route: the rails the reader sees
# --------------------------------------------------------------------------


class _SyncAsAsync:
    def __init__(self, session):
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)


def _pm(name, prob, n):
    # Polymarket keys by condition_id and names the outcome "Over"/"Under", so
    # the NAME is the only signal the classifier has.
    return (name, f"0x{n:064x}", "polymarket", (("Over", prob), ("Under", round(1 - prob, 4))))


_KALSHI = (
    "Japan vs Venezuela: Total Goals",
    "KXINTLFRIENDLYTOTAL-26SEP28JPNVEN",
    "kalshi",
    tuple((f"Over {t} goals scored", p) for t, p in KALSHI_GOALS),
)
_GOALS = [_pm(f"Japan vs. Venezuela: O/U {t}", p, 100 + i) for i, (t, p) in enumerate(PM_GOALS)]
_CORNERS = [
    _pm(f"Japan vs. Venezuela: O/U {t} Total Corners", p, 200 + i) for i, (t, p) in enumerate(PM_CORNERS)
]
_HALF_GOALS = [
    _pm(f"Japan vs. Venezuela: 1st Half O/U {t}", p, 300 + i) for i, (t, p) in enumerate(PM_HALF_GOALS)
]
_HALF_CORNERS = [
    _pm(f"Japan vs. Venezuela: 1st Half O/U {t} Total Corners", p, 400 + i)
    for i, (t, p) in enumerate(PM_HALF_CORNERS)
]


def _served(markets):
    """`GET /api/events/{id}/game-markets`'s builder, actually executed."""
    from app.routes.events import _build_game_markets

    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=SPORT_ID, key="soccer_other", name="Soccer"))
        s.add(
            Event(
                id=EVENT_ID,
                sport_id=SPORT_ID,
                home_team_name="Japan",
                away_team_name="Venezuela",
                commence_time=COMMENCE,
                status="scheduled",
            )
        )
        outcome_id = 9000
        for market_id, (name, ext, source, outcomes) in enumerate(markets, start=700):
            s.add(
                FuturesMarket(
                    id=market_id,
                    event_id=EVENT_ID,
                    sport_id=SPORT_ID,
                    source=source,
                    external_id=ext,
                    name=name,
                    category="game",
                    llm_sport_category="soccer",
                    market_type="game_total",
                    status="open",
                )
            )
            for outcome_name, prob in outcomes:
                outcome_id += 1
                s.add(
                    FuturesOutcome(
                        id=outcome_id,
                        market_id=market_id,
                        external_id=f"{ext}-{outcome_name}",
                        name=outcome_name,
                        current_probability=prob,
                    )
                )
        s.commit()
        response, _status, _ids = asyncio.run(_build_game_markets(EVENT_ID, _SyncAsAsync(s)))
    return response


class TestTheServedGoalsRail:
    """Each arm seeds ONE contaminant beside the goals it could land on."""

    def test_the_corners_ladder_leaves_the_goals_rail(self):
        totals = _served([_KALSHI, *_GOALS, *_CORNERS])["totals"]

        corner_rows = [t["market_name"] for t in totals if "Corners" in t["market_name"]]
        assert corner_rows == [], f"corners on the goals rail: {corner_rows}"
        assert [t["threshold"] for t in totals] == [t for t, _ in KALSHI_GOALS + PM_GOALS]

    def test_the_fix_leaves_every_goals_price_alone(self):
        """A CONTROL, and it is green on the unfixed tree too. On this fixture
        the goals lines already won the shared 7.5/8.5 thresholds before the
        fix; production's 0.008 at those rungs came from more rows than this
        fixture seeds. The defect arm is the one above. This one only proves
        the move takes no goals price with it."""
        totals = _served([_KALSHI, *_GOALS, *_CORNERS])["totals"]
        served = {t["threshold"]: t["over_probability"] for t in totals}

        for threshold, real in KALSHI_GOALS + PM_GOALS:
            assert served[threshold] == pytest.approx(real, abs=1e-6), (
                f"goals rung {threshold} served {served[threshold]} not {real}"
            )

    def test_the_first_half_goals_card_holds_only_goals(self):
        """León–Juárez's "Four lines quoted": 0.5 / 3.5 / 4.5 / 5.5."""
        periods = _served([_KALSHI, *_HALF_GOALS, *_HALF_CORNERS])["period_markets"]
        half_totals = {
            (p["threshold"], p["market_name"])
            for p in periods
            if p.get("period") == "1H" and p.get("threshold") is not None
        }

        assert {t for t, _ in half_totals} == {t for t, _ in PM_HALF_GOALS}, (
            f"the 1st-half goals card carries {sorted(half_totals)}"
        )

    def test_the_corners_markets_are_still_SERVED(self):
        """Reclassifying moves a market; it never deletes one. `stat_total` is a
        LABEL (the page renders `other`), not an entry in the scope filter."""
        response = _served([_KALSHI, *_GOALS, *_CORNERS, *_HALF_CORNERS])

        other = {row["market_name"] for row in response.get("other") or []}
        for name, *_ in (*_CORNERS, *_HALF_CORNERS):
            assert name in other, f"{name!r} is no longer served anywhere"
