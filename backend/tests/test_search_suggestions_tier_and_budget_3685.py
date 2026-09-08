"""#3685 — the "Right now" row stops being four minor-league baseball games.

WHAT A USER SAW (production, 2026-09-06 20:50Z, https://bainluck.com/search), all
eight chips from section 1:

    Chicago Fire        Live — tight game vs Vancouver Whitecaps FC   (MLS)
    Platense            Live — tight game vs Deportivo Riestra        (Argentine Primera)
    Tacoma Rainiers     Live — tight game vs Albuquerque Isotopes     (AAA baseball)
    AFC Whyteleafe      Live — tight game vs Crowborough Athletic FC  (English 9th tier)
    León                Live — tight game vs Pumas                    (Liga MX)
    Durham Bulls        Live — tight game vs Memphis Redbirds         (AAA baseball)
    Round Rock Express  Live — tight game vs Oklahoma City Comets     (AAA baseball)
    El Paso Chihuahuas  Live — tight game vs Las Vegas Aviators       (AAA baseball)

— on a Saturday with the US Open and a full college-football slate, while section
5 (`Presidential Election Winner 2028`, `US Open Men's Singles Winner`, `College
Football National Championship`, ordered by real `volume_24h`) could not reach the
row at all.

TWO defects, and they are not alternatives:

  1. no tier gate on section 1, so minor-league rows were candidates; and
  2. no per-section budget, so the first section to run owned the window.

Both are guarded here, and the tier gate is guarded in the direction that would
have shipped a WORSE row than the one it fixes: the obvious spelling of "tier 1-2
only" excludes every Grand Slam match.
"""

import ast
import inspect
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import events as events_routes
from app.routes.events import _MAX_SUGGESTIONS, _SUGGESTION_SECTION_BUDGETS
from app.utils.highlights import LEAGUE_TIERS, get_league_tier, tier_12_sport_keys

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 1. The tier gate, and the trap inside it
# ---------------------------------------------------------------------------


class TestTheTierKeySet:
    def test_every_key_it_returns_really_is_tier_one_or_two(self):
        """Round-trip through the function a SQL predicate cannot call."""
        for key in tier_12_sport_keys():
            assert get_league_tier(key) <= 2, (
                f"{key!r} is in the tier-1/2 predicate but scores "
                f"{get_league_tier(key)}"
            )

    def test_it_carries_the_spellings_events_are_actually_keyed_on(self):
        """🔴 THE DEFECT THIS HELPER EXISTS FOR, AND THE ONE THAT WOULD HAVE
        SHIPPED WITHOUT IT.

        `LEAGUE_TIERS` spells the slams `tennis_us_open`; every US Open match in
        `events` is keyed `tennis_atp_us_open` / `tennis_wta_us_open`, and only
        `get_league_tier`'s tour-agnostic fallback bridges the two (#2552). So the
        obvious `{k for k, t in LEAGUE_TIERS.items() if t <= 2}` — which is what
        section 2 used and what section 1 was about to copy — is a "tier 1-2 only"
        filter that drops every Grand Slam match on the day of the final.
        """
        keys = tier_12_sport_keys()
        naive = {k for k, t in LEAGUE_TIERS.items() if t <= 2}

        for slam_key in ("tennis_atp_us_open", "tennis_wta_us_open"):
            assert get_league_tier(slam_key) <= 2, "fixture drift, not a bug here"
            assert slam_key in keys, (
                f"{slam_key!r} is a tier-2 Grand Slam match and is missing from "
                "the predicate — a live US Open match could not reach the row"
            )
            assert slam_key not in naive, (
                "this assertion is the WHOLE point of the helper; if the naive "
                "comprehension now carries the tour spellings, delete the helper "
                "rather than leaving two ways to spell the same set"
            )

    def test_a_minor_league_never_slips_in(self):
        for key in (
            "baseball_milb",          # AAA — four of the eight chips
            "soccer_mexico_ligamx",   # tier 3
            "soccer_england_league2", # tier 4
            "tennis_atp_dubai",       # a regular tour stop, not a slam
            "tennis_wta_dubai",
        ):
            assert key not in tier_12_sport_keys(), f"{key!r} is not tier 1-2"

    def test_the_expansion_is_derived_and_not_a_second_hand_written_list(self):
        """A hand-listed expansion goes stale the next time a slam is added."""
        src = inspect.getsource(tier_12_sport_keys)
        assert "LEAGUE_TIERS" in src and "_TENNIS_TOUR_SEGMENTS" in src, (
            "the expansion must be derived from the tier table and the tour "
            "segments, so a new slam needs one line and not two"
        )


class TestSectionsOneAndFourAskTheDatabaseForTierOneAndTwo:
    """The gate has to be IN THE STATEMENT, not applied to the rows afterwards.

    Section 1 reads `.limit(50)` in no particular order: filtering after the read
    would hand the row whatever fifty minor-league games the planner found first
    and then show three of them.
    """

    async def test_the_live_and_upset_statements_both_filter_on_sport_key(self):
        db = _RecordingDB([_Rows([]) for _ in range(5)])
        await events_routes._build_search_suggestions(db)

        compiled = [str(stmt) for stmt in db.executed]
        assert len(compiled) == 5, "fixture drift: expected one statement a section"

        live_sql, upset_sql = compiled[0], compiled[3]
        for label, sql in (("section 1 (live)", live_sql), ("section 4 (upsets)", upset_sql)):
            assert "sports" in sql and "sports.key IN" in sql, (
                f"{label} does not gate on sport key — the row is open to "
                f"minor leagues again:\n{sql}"
            )
        assert "status" in live_sql.lower()
        assert "home_score" in upset_sql.lower(), "fixture drift: not section 4"


# ---------------------------------------------------------------------------
# 2. The budget, end to end through the route
# ---------------------------------------------------------------------------


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _RecordingDB:
    def __init__(self, results):
        self._results = list(results)
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        if not self._results:
            raise AssertionError(
                "the build issued more statements than the fixture queued — a "
                "section would have been swallowed as dead"
            )
        return self._results.pop(0)


def _live(pairs):
    """Games in progress: `status='live'` AND a start time already behind them.

    Both halves matter since #3728 — section 1 reads the row's own
    `commence_time` through `served_event_status`, so a fixture that omits it is
    a fixture of a row the section is now right to refuse.
    """
    started = datetime.now(timezone.utc) - timedelta(minutes=40)
    return [
        SimpleNamespace(
            id=i + 1,
            status="live",
            commence_time=started,
            home_team_name=home,
            away_team_name=away,
            win_probability_sources={"betting": 0.5},
            opening_home_probability=None,
            espn_win_prob_home=None,
        )
        for i, (home, away) in enumerate(pairs)
    ]


def _soon(pairs, sport_key="basketball_wnba"):
    """Section 2's rows — (Event, sport_key) TUPLES, not bare events.

    #3718 made section 2 a two-column select (`select(Event, Sport.key)`) so the
    countdown's verb can be chosen from the sport without a lazy load, so its
    result rows are pairs. The fixture teams here are WNBA, hence the default.
    """
    at = datetime.now(timezone.utc) + timedelta(minutes=30)
    return [
        (
            SimpleNamespace(
                id=50 + i, home_team_name=home, away_team_name=away, commence_time=at
            ),
            sport_key,
        )
        for i, (home, away) in enumerate(pairs)
    ]


def _champ(names):
    return [
        SimpleNamespace(id=100 + i, name=name, status="open", market_tier=1)
        for i, name in enumerate(names)
    ]


#: The eight live pairs production served, and the five markets section 5 wanted
#: to serve underneath them — both read at the same minute.
_PRODUCTION_LIVE_PAIRS = [
    ("Chicago Fire", "Vancouver Whitecaps FC"),
    ("Platense", "Deportivo Riestra"),
    ("Albuquerque Isotopes", "Tacoma Rainiers"),
    ("AFC Whyteleafe", "Crowborough Athletic FC"),
    ("Pumas", "León"),
    ("Memphis Redbirds", "Durham Bulls"),
    ("Round Rock Express", "Oklahoma City Comets"),
    ("El Paso Chihuahuas", "Las Vegas Aviators"),
]

_PRODUCTION_CHAMP_MARKETS = [
    "Presidential Election Winner 2028",
    "US Open Men's Singles Winner",
    "College Football National Championship",
    "2027 Pro Football Champion",
    "US Open Women's Singles Winner",
    "2027 NBA Champion",
    "2027 Stanley Cup Champion",
    "2026 World Series Winner",
]


@pytest.fixture
def no_redis(monkeypatch):
    import app.tasks.redis_state as redis_state

    monkeypatch.setattr(redis_state, "get_redis_client", lambda: None)


class TestTheRowTheUserGets:
    async def test_the_popular_markets_reach_the_row(self, no_redis):
        """🔴 THE SHIP, IN ONE ASSERTION.

        Same eight live games, same five (here eight) championship markets, one
        run of the real build: section 1 keeps its three and the rest of the row
        is what people are actually trading. Before #3685 this fixture returned
        eight live chips and none of the markets.
        """
        db = _RecordingDB(
            [
                _Rows(_live(_PRODUCTION_LIVE_PAIRS)),
                _Rows([]),
                _Rows([]),
                _Rows([]),
                _Rows(_champ(_PRODUCTION_CHAMP_MARKETS)),
            ]
        )

        resp = await events_routes._build_search_suggestions(db)
        chips = resp["suggestions"]

        assert len(chips) == _MAX_SUGGESTIONS, "the row must still be full"
        live_chips = [c for c in chips if c["type"] == "event"]
        champ_chips = [c for c in chips if c["type"] == "futures"]

        assert len(live_chips) == _SUGGESTION_SECTION_BUDGETS[1], (
            f"section 1 kept {len(live_chips)} of the eight slots: "
            f"{[c['query'] for c in live_chips]}"
        )
        assert [c["query"] for c in champ_chips] == _PRODUCTION_CHAMP_MARKETS[
            : _MAX_SUGGESTIONS - _SUGGESTION_SECTION_BUDGETS[1]
        ], "section 5 must backfill the row in volume order"
        assert "US Open Men's Singles Winner" in [c["query"] for c in champ_chips], (
            "the thing a person opening Search on US Open Saturday is looking "
            "for is not on the row"
        )

    async def test_the_declared_us_open_ship_survives_all_four_sections_at_budget(
        self, no_redis
    ):
        """🔴 CERT-2138's BLOCK, PINNED — the state the first presentation missed.

        The ship is named "the first row shows the US Open", and the first
        version of this change did not deliver it in the state that matters:
        every timely section saturated. 3 + 2 + 1 + 1 is the whole budget table,
        which left the backfill exactly ONE slot — enough for `Presidential
        Election Winner 2028` and not for `US Open Men's Singles Winner`, which
        is rank 2 of the measured order. The row was "no longer minor-league" and
        still not the declared ship.

        Two arms, because the repair answers the block in two different ways.

        **A — the grader's own shape.** Offer all four sections their full
        budget. `_SUGGESTION_BACKFILL_RESERVE` makes that state UNREACHABLE
        rather than survivable: sections 1 and 2 spend the whole timely
        allowance, so sections 3 and 4 are not even queried, and the reserved
        three slots go to the top of the volume order. The trade is visible in
        the assertion — two timely chips for the two markets a person opening
        Search on US Open Saturday is actually looking for.

        **B — all four sections actually contributing.** A quieter evening where
        sections 1 and 2 do not spend the allowance on their own, so the mover
        and the upset both reach the row. The marquee must still be there; a
        reserve that only works when the later timely sections are starved would
        be answering the block by accident.
        """
        # ---- arm A: every timely section offered its budget -----------------
        db = _RecordingDB(
            [
                _Rows(_live(_PRODUCTION_LIVE_PAIRS)),      # offers 8, may keep 3
                _Rows(_soon([("Aces", "Liberty"), ("Sky", "Storm")])),
                _Rows(_champ(_PRODUCTION_CHAMP_MARKETS)),
                # NOTHING for sections 3 and 4: if they are queried at all this
                # fixture raises, which is the assertion.
            ]
        )

        resp = await events_routes._build_search_suggestions(db)
        queries = [c["query"] for c in resp["suggestions"]]
        reserve = events_routes._SUGGESTION_BACKFILL_RESERVE

        assert "US Open Men's Singles Winner" in queries, (
            "CERT-2138's exact finding is back: the timely sections are at their "
            f"allowance and the marquee chip fell off the row — {queries}"
        )
        assert queries[: _MAX_SUGGESTIONS - reserve] == [
            "Chicago Fire",
            "Platense",
            "Tacoma Rainiers",
            "Aces",
            "Sky",
        ], f"the timely allowance is not spent in section order: {queries}"
        assert queries[_MAX_SUGGESTIONS - reserve :] == (
            _PRODUCTION_CHAMP_MARKETS[:reserve]
        ), f"the reserved slots are not the top of the volume order: {queries}"
        assert len(queries) == _MAX_SUGGESTIONS

        # ---- arm B: all four timely sections actually contribute ------------
        mover = SimpleNamespace(
            name="Denver",
            market_id=900,
            probability_change_24h=0.06,
            market=SimpleNamespace(name="NBA Championship Winner", event=None),
        )
        upset = SimpleNamespace(
            id=70,
            home_team_name="Fever",
            away_team_name="Sparks",
            home_score=88,
            away_score=80,
            opening_home_probability=0.30,
            commence_time=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db = _RecordingDB(
            [
                _Rows(_live(_PRODUCTION_LIVE_PAIRS[:1])),
                _Rows(_soon([("Aces", "Liberty")])),
                _Rows([mover]),
                _Rows([upset]),
                _Rows(_champ(_PRODUCTION_CHAMP_MARKETS)),
            ]
        )

        resp = await events_routes._build_search_suggestions(db)
        queries = [c["query"] for c in resp["suggestions"]]

        assert queries[:4] == ["Chicago Fire", "Aces", "Denver", "Fever"], (
            f"all four timely sections must reach the row here: {queries}"
        )
        assert "US Open Men's Singles Winner" in queries, (
            f"the marquee chip is missing when the later sections do run: {queries}"
        )
        assert len(queries) == _MAX_SUGGESTIONS

    async def test_the_reserve_makes_the_expensive_section_skippable_again(
        self, no_redis
    ):
        """The cost half of the same repair, and it is a WIN not a concession.

        Sections 1 and 2 at full budget spend the whole timely allowance, so
        sections 3 and 4 are skipped outright — the 588 ms pooled movers
        statement is never issued on a busy evening. LAT-P124's ship, restored by
        the change that was supposed to spend it.
        """
        # Built through `_soon` rather than inline, so the section-2 row SHAPE is
        # defined in exactly one place. The inline copy this replaced is why the
        # #3718 two-column select turned up here as a silent dead section.
        soon = _soon([("Aces", "Liberty"), ("Sky", "Storm")])
        db = _RecordingDB(
            [
                _Rows(_live(_PRODUCTION_LIVE_PAIRS)),
                _Rows(soon),
                _Rows(_champ(_PRODUCTION_CHAMP_MARKETS)),
            ]
        )

        resp = await events_routes._build_search_suggestions(db)

        assert len(db.executed) == 3, (
            "sections 3 and 4 must not be queried once the timely allowance is "
            "spent — the movers sort is back on every build"
        )
        assert len(resp["suggestions"]) == _MAX_SUGGESTIONS

    async def test_the_row_never_overruns_the_window(self, no_redis):
        """🔴 THE BOUND IS THE PREDICATE'S JOB NOW, AND THIS IS THE TEST THAT
        MAKES THAT TRUE.

        `_build_search_suggestions` used to end in `suggestions[:_MAX_SUGGESTIONS]`
        — a second authority on the window that silently absorbed any failure of
        the first. The mutation battery proved it: M6 turns `_window_full`'s
        `>=` into `>` and SURVIVED, because the ninth chip it admitted was
        truncated by the slice and nothing could see the predicate had stopped
        working.

        Every section here offers more than it may keep, so a predicate that is
        off by one overruns the row instead of being quietly trimmed.
        """
        db = _RecordingDB(
            [
                _Rows(_live(_PRODUCTION_LIVE_PAIRS)),
                _Rows(_soon([("Aces", "Liberty"), ("Sky", "Storm"), ("Sun", "Wings")])),
                _Rows(_champ(_PRODUCTION_CHAMP_MARKETS)),
            ]
        )

        resp = await events_routes._build_search_suggestions(db)

        assert len(resp["suggestions"]) == _MAX_SUGGESTIONS, (
            f"the build returned {len(resp['suggestions'])} chips for an "
            f"eight-slot row: {[c['query'] for c in resp['suggestions']]}"
        )

    async def test_a_quiet_night_still_fills_the_row(self, no_redis):
        """Nothing live, nothing soon, nothing moving — and still eight chips.

        The uncapped backfill is why the tier gate can be strict: an honest row
        of the most-traded markets beats a full row of AAA baseball, and beats a
        row of two.
        """
        db = _RecordingDB(
            [_Rows([]), _Rows([]), _Rows([]), _Rows([]), _Rows(_champ(_PRODUCTION_CHAMP_MARKETS))]
        )

        resp = await events_routes._build_search_suggestions(db)

        assert len(resp["suggestions"]) == _MAX_SUGGESTIONS
        assert all(c["type"] == "futures" for c in resp["suggestions"])

    async def test_a_section_that_has_nothing_hands_its_slots_forward(self, no_redis):
        """Slack flows forward: an empty section does not reserve its budget."""
        db = _RecordingDB(
            [
                _Rows([]),
                _Rows([]),
                _Rows([]),
                _Rows([]),
                _Rows(_champ(_PRODUCTION_CHAMP_MARKETS[:3])),
            ]
        )

        resp = await events_routes._build_search_suggestions(db)

        assert [c["query"] for c in resp["suggestions"]] == _PRODUCTION_CHAMP_MARKETS[:3]

    async def test_a_deduped_row_does_not_spend_a_budget_slot(self, no_redis):
        """Two live games whose shorter team name collides are ONE chip, and the
        section must still be allowed its full budget of distinct ones.

        `_add` dedups on the query string; counting the budget on the candidate
        rather than on the add would silently shrink the section.
        """
        pairs = [
            ("Pumas", "Club America"),
            ("Pumas", "Tigres UANL"),   # same shorter name — deduped away
            ("Aces", "Liberty"),
            ("Sky", "Storm"),
            ("Fever", "Dream"),
        ]
        db = _RecordingDB(
            [_Rows(_live(pairs)), _Rows([]), _Rows([]), _Rows([]), _Rows([])]
        )

        resp = await events_routes._build_search_suggestions(db)
        queries = [c["query"] for c in resp["suggestions"]]

        assert queries == ["Pumas", "Aces", "Sky"], (
            f"the duplicate must cost the section nothing: {queries}"
        )
        assert len(queries) == _SUGGESTION_SECTION_BUDGETS[1]


class TestTheBudgetTableIsReadable:
    def test_the_route_reads_the_table_and_not_a_literal(self):
        """No section may carry its own private number."""
        src = inspect.getsource(events_routes._build_search_suggestions)
        tree = ast.parse(src.lstrip())
        bare = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Compare)
            and any(
                isinstance(c, ast.Constant)
                and isinstance(c.value, int)
                and c.value in set(_SUGGESTION_SECTION_BUDGETS.values())
                and c.value > 1
                for c in n.comparators
            )
        ]
        assert bare == [], (
            "a budget-sized literal is being compared inside the build; read "
            "_SUGGESTION_SECTION_BUDGETS so the table stays the only authority"
        )

    async def test_the_response_is_json_serialisable_with_the_new_shape(self):
        """The budget added an internal counter; nothing internal may leak."""
        db = _RecordingDB(
            [
                _Rows(_live(_PRODUCTION_LIVE_PAIRS[:2])),
                _Rows([]),
                _Rows([]),
                _Rows([]),
                _Rows(_champ(_PRODUCTION_CHAMP_MARKETS[:2])),
            ]
        )
        resp = await events_routes._build_search_suggestions(db)
        json.dumps(resp)
        for chip in resp["suggestions"]:
            assert "section" not in chip, (
                "the section number is bookkeeping and must not reach the wire"
            )
