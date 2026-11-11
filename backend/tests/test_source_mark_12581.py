"""#12581: source evidence follows the number's actual decision path."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path
import asyncio
import json

import pytest

from app.utils.aggregation import compute_aggregate_probability_tiered
from app.utils.hero_probability import resolve_hero
from app.utils.source_mark import (
    cap_source_mark,
    headline_source_marks,
    quote_source_mark,
)

NOW = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)


def event(sources=None, **overrides):
    fields = dict(
        status="scheduled",
        win_probability_sources=sources or {},
        espn_win_prob_home=None,
        opening_home_probability=None,
        opening_away_probability=None,
        home_score=None,
        away_score=None,
        completed_at=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def quote(value, age_minutes=0):
    return {
        "value": value,
        "updated_at": (NOW - timedelta(minutes=age_minutes)).isoformat(),
    }


class TestActualHeadlineInputs:
    @pytest.fixture(autouse=True)
    def fixed_quote_clock(self, monkeypatch):
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

        monkeypatch.setattr("app.utils.aggregation.datetime", Clock)

    def test_divergence_lists_only_the_source_that_priced_the_headline(self):
        fixture = event({"betting": quote(0.9), "kalshi": quote(0.1)})
        sources = []
        hero = resolve_hero(fixture, source_inputs=sources)
        assert hero.home_probability == 0.9
        assert sources == [("betting", 0.9)]

    def test_healthy_median_keeps_all_admitted_inputs(self):
        fixture = event(
            {
                "betting": quote(0.6),
                "kalshi": quote(0.62),
                "polymarket": quote(0.64),
                "betting_book_count": 5,
            }
        )
        sources = []
        plain = resolve_hero(fixture)
        traced = resolve_hero(fixture, source_inputs=sources)
        assert traced == plain
        assert traced.home_probability == 0.62
        assert dict(sources) == {"betting": 0.6, "kalshi": 0.62, "polymarket": 0.64}

    def test_zero_weight_live_source_is_not_a_contributor(self):
        fixture = event(
            {
                "betting": quote(0.6),
                "kalshi": quote(0.62),
                "polymarket": quote(0.64),
                "espn": quote(0.5, 45),
            },
            status="live",
        )
        sources = []
        plain = compute_aggregate_probability_tiered(fixture)
        traced = compute_aggregate_probability_tiered(fixture, source_inputs=sources)
        assert traced == plain
        assert dict(sources) == {"betting": 0.6, "kalshi": 0.62, "polymarket": 0.64}

    def test_undated_live_source_does_not_escape_eligibility(self):
        fixture = event(
            {
                "betting": 0.9,
                "kalshi": quote(0.6),
                "polymarket": quote(0.62),
            },
            status="live",
        )
        sources = []
        hero = resolve_hero(fixture, source_inputs=sources)
        assert hero.home_probability == pytest.approx(0.61)
        assert dict(sources) == {"kalshi": 0.6, "polymarket": 0.62}

    def test_final_score_does_not_claim_old_trading_inputs(self):
        fixture = event(
            {"kalshi": quote(0.6)},
            status="completed",
            home_score=10,
            away_score=20,
            completed_at=NOW,
        )
        sources = []
        hero = resolve_hero(fixture, source_inputs=sources)
        assert hero.source == "settled"
        assert hero.home_probability == 0
        assert sources == []

    def test_opening_fallback_does_not_invent_a_current_contributor(self):
        sources = []
        hero = resolve_hero(event(opening_home_probability=0.63), source_inputs=sources)
        assert hero.source == "opening"
        assert hero.home_probability == 0.63
        assert sources == []

    def test_espn_fallback_names_espn_without_inventing_a_clock(self):
        sources = []
        hero = resolve_hero(event(espn_win_prob_home=0.58), source_inputs=sources)
        assert hero.home_probability == 0.58
        assert sources == [("espn", 0.58)]

    def test_no_probability_has_no_contributors(self):
        sources = []
        assert resolve_hero(event(), source_inputs=sources) is None
        assert sources == []


class TestSourceMarks:
    def test_two_sources_keep_their_own_prices_and_clocks_in_server_order(self):
        mark = quote_source_mark(
            [
                {
                    "key": "polymarket",
                    "probability": 0.6,
                    "observed_at": "2026-11-11T08:01:00-08:00",
                },
                {
                    "key": "kalshi",
                    "probability": 0.62,
                    "observed_at": "2026-11-11T16:00:00Z",
                },
            ]
        )
        assert mark == {
            "state": "blend",
            "sources": [
                {
                    "key": "kalshi",
                    "name": "Kalshi",
                    "probability": 0.62,
                    "observed_at": "2026-11-11T16:00:00Z",
                },
                {
                    "key": "polymarket",
                    "name": "Polymarket",
                    "probability": 0.6,
                    "observed_at": "2026-11-11T16:01:00Z",
                },
            ],
        }

    def test_two_rows_from_one_venue_are_one_source_with_oldest_clock(self):
        mark = quote_source_mark(
            [
                {
                    "key": "kalshi",
                    "probability": 0.5,
                    "observed_at": "2026-11-11T16:00:00Z",
                },
                {
                    "key": "kalshi",
                    "probability": 0.6,
                    "observed_at": "2026-11-11T15:00:00Z",
                },
            ]
        )
        assert len(mark["sources"]) == 1
        assert mark["sources"][0]["probability"] == 0.55
        assert mark["sources"][0]["observed_at"] == "2026-11-11T15:00:00Z"

    def test_unknown_clock_does_not_borrow_another_legs_clock(self):
        mark = quote_source_mark(
            [
                {
                    "key": "kalshi",
                    "probability": 0.5,
                    "observed_at": "2026-11-11T16:00:00Z",
                },
                {"key": "kalshi", "probability": 0.6, "observed_at": None},
            ]
        )
        assert mark["sources"][0]["observed_at"] is None
        assert mark["sources"][0]["reason"] == "observation_unknown"

    @pytest.mark.parametrize("bad", [None, True, float("nan"), float("inf"), -0.1, 1.1])
    def test_missing_input_cannot_silently_become_a_one_source_mark(self, bad):
        mark = quote_source_mark(
            [
                {"key": "kalshi", "probability": 0.5},
                {"key": "polymarket", "probability": bad},
            ]
        )
        assert mark == {
            "state": "none",
            "sources": [],
            "reason": "source_evidence_incomplete",
        }

    def test_capped_rung_keeps_its_number_and_own_quote_not_the_donors(self):
        mark = quote_source_mark(
            [
                {
                    "key": "kalshi",
                    "probability": 0.8,
                    "observed_at": "2026-11-11T16:00:00Z",
                }
            ]
        )
        row = {
            "over_probability": 0.6,
            "observed_at": "2026-11-11T14:00:00Z",
            "source_mark": mark,
        }
        cap_source_mark(row)
        assert row["over_probability"] == 0.6
        assert row["source_mark"] == {
            "state": "none",
            "sources": [],
            "reason": "monotonic_conflict",
        }
        assert row["source_evidence"] == mark["sources"]
        assert row["source_evidence"][0]["probability"] == 0.8
        assert row["source_evidence"][0]["observed_at"] == "2026-11-11T16:00:00Z"

    def test_headline_uses_selected_inputs_and_never_poll_or_publication_time(self):
        fixture = event(
            {"betting": quote(0.9), "kalshi": quote(0.1), "betting_book_count": 5}
        )
        fixture.win_probability_sources["betting"].update(
            observed_basis={"123": NOW.timestamp()},
            observed_value=0.9,
        )
        inputs = []
        hero = resolve_hero(fixture, source_inputs=inputs)
        home, away = headline_source_marks(fixture, hero, inputs)
        assert [s["key"] for s in home["sources"]] == ["betting"]
        assert home["sources"][0]["probability"] == 0.9
        assert away["sources"][0]["probability"] == 0.1
        assert home["sources"][0]["count"] == 5
        assert home["sources"][0]["observed_at"] is None
        assert away["sources"][0]["observed_at"] is None

    def test_final_headline_has_official_result_without_trading_sources(self):
        fixture = event(
            {"kalshi": quote(0.6)},
            status="completed",
            home_score=10,
            away_score=20,
            completed_at=NOW,
            score_source="espn",
        )
        hero = resolve_hero(fixture)
        home, away = headline_source_marks(fixture, hero, [])
        assert home == {
            "state": "settled",
            "sources": [],
            "settled": {
                "source": "espn",
                "result": "Lost",
                "at": "2026-11-11T15:00:00Z",
            },
        }
        assert away["settled"]["result"] == "Won"

    def test_withheld_away_side_does_not_gain_a_complement_in_its_mark(self):
        fixture = event({"kalshi": quote(0.6)})
        inputs = []
        hero = resolve_hero(fixture, source_inputs=inputs)
        home, away = headline_source_marks(fixture, hero, inputs, away_available=False)
        assert home["state"] == "blend"
        assert away == {"state": "none", "sources": [], "reason": "away_unavailable"}

    @pytest.mark.parametrize("value", [0, 1])
    def test_extreme_live_quote_is_still_a_quote(self, value):
        mark = quote_source_mark([{"key": "kalshi", "probability": value}])
        assert mark["state"] == "blend"
        assert mark["sources"][0]["probability"] == value


def nfl_page(*, kalshi_width=0.08, polymarket_width=0.02, poly_under_only=False):
    """Actual LaPorta label/contract shapes; tight-book choice is controlled."""
    import asyncio
    from app.routes.events import _build_game_markets
    from tests.test_event_props_matrix_10236 import _db, _event, _market, _outcome

    now = datetime.now(timezone.utc)
    commence = now + timedelta(days=4)
    fixture = _event(status="scheduled", commence=commence)
    fixture.sport.key = "americanfootball_nfl"
    fixture.home_team_name, fixture.away_team_name = (
        "Detroit Lions",
        "New England Patriots",
    )
    fixture.home_score = fixture.away_score = None
    fixture.period = None
    markets = [
        _market(
            id=69976788,
            name="New England vs Detroit: Receiving Yards",
            source="kalshi",
            commence=commence,
        ),
        _market(
            id=69976796,
            name="New England vs Detroit: Receiving Yards",
            source="kalshi",
            commence=commence,
        ),
        _market(
            id=33,
            name="Sam LaPorta: Receiving Yards O/U 14.5",
            source="polymarket",
            commence=commence,
        ),
        _market(
            id=34,
            name="Isaac TeSlaa: Receiving Yards O/U 9.5",
            source="polymarket",
            commence=commence,
        ),
    ]
    markets[0].external_id = "KXNFLRECYDS-26NOV15NEDET"
    markets[1].external_id = "KXNFLRECYDSPROT-26NOV15NEDET"
    for market in markets:
        market.llm_sport_category = "americanfootball"
    outcomes = [
        _outcome(id=262829404, market_id=69976788, name="Sam LaPorta: 15+", prob=0.86),
        _outcome(id=262830012, market_id=69976796, name="Sam LaPorta: 15+", prob=0.845),
        _outcome(id=331, market_id=33, name="Over", prob=0.82),
        _outcome(id=332, market_id=33, name="Under", prob=0.18),
        _outcome(id=341, market_id=34, name="Over", prob=0.63),
        _outcome(id=342, market_id=34, name="Under", prob=0.37),
    ]
    for leg in outcomes:
        width = (
            kalshi_width if leg.market_id in (69976788, 69976796) else polymarket_width
        )
        leg.current_yes_bid = (
            leg.current_probability - width / 2 if width is not None else None
        )
        leg.current_yes_ask = (
            leg.current_probability + width / 2 if width is not None else None
        )
    if poly_under_only:
        outcomes = [o for o in outcomes if o.id != 331]
    response, _, _ = asyncio.run(
        _build_game_markets(
            fixture.id,
            _db(
                fixture,
                markets,
                outcomes,
                {o.id: now - timedelta(minutes=2) for o in outcomes},
            ),
        )
    )
    return response


def nfl_polymarket_finished_page(
    *,
    finished,
    over_won=True,
    under_only=False,
    grade_source="api_settlement",
    void=False,
    kalshi_control=False,
    kalshi_won=None,
    kalshi_finished=None,
):
    """Synthetic venue-resolved NFL prop through the real assembly path."""
    from app.routes.events import _build_game_markets
    from tests.test_event_props_matrix_10236 import _db, _event, _market, _outcome

    now = datetime.now(timezone.utc)
    commence = now - timedelta(hours=6)
    fixture = _event(status="completed" if finished else "live", commence=commence)
    fixture.sport.key = "americanfootball_nfl"
    fixture.home_team_name, fixture.away_team_name = "Houston Texans", "Buffalo Bills"
    fixture.home_score, fixture.away_score = 21, 24
    fixture.completed_at = now - timedelta(hours=2) if finished else None
    fixture.period = None if finished else "Q3"
    market = _market(
        id=71,
        name="Josh Allen: Passing Yards O/U 224.5",
        source="polymarket",
        commence=commence,
    )
    market.llm_sport_category = "americanfootball"
    market.status = "resolved" if finished else "open"
    over = 0.5 if void else (0.97 if over_won else 0.03) if finished else 0.62
    outcomes = [
        _outcome(id=711, market_id=71, name="Over", prob=over),
        _outcome(id=712, market_id=71, name="Under", prob=1 - over),
    ]
    for leg in outcomes:
        leg.current_yes_bid = leg.current_yes_ask = None
        leg.opening_probability = 0.6 if leg.id == 711 else 0.4
        if finished:
            leg.is_winner = (
                False if void else over_won if leg.id == 711 else not over_won
            )
            leg.resolution_source = grade_source
    if under_only:
        outcomes = outcomes[1:]
    markets = [market]
    if kalshi_control:
        kalshi_won = not over_won if kalshi_won is None else kalshi_won
        kalshi_finished = finished if kalshi_finished is None else kalshi_finished
        kalshi = _market(
            id=72,
            name="Buffalo vs Houston: Passing Yards",
            source="kalshi",
            commence=commence,
        )
        kalshi.external_id = "KXNFLPASSYDS-26NOV12BUFHOU"
        kalshi.llm_sport_category = "americanfootball"
        kalshi.status = "resolved" if kalshi_finished else "open"
        leg = _outcome(
            id=721,
            market_id=72,
            name="Josh Allen: 225+",
            prob=(0.97 if kalshi_won else 0.03) if kalshi_finished else 0.64,
        )
        if kalshi_finished:
            leg.is_winner, leg.resolution_source = kalshi_won, "api_settlement"
        leg.current_yes_bid = leg.current_yes_ask = None
        outcomes.append(leg)
        markets.append(kalshi)
    page, _, _ = asyncio.run(
        _build_game_markets(
            fixture.id,
            _db(
                fixture,
                markets,
                outcomes,
                {o.id: now - timedelta(minutes=2) for o in outcomes},
            ),
        )
    )
    return page


def finished_polymarket_reader_fixture():
    """Only clock-independent fields, consumed by the real web grouping test."""
    fields = (
        "market_name",
        "outcome_name",
        "threshold",
        "over_probability",
        "opening_over_probability",
        "_inverted",
        "source",
        "source_mark",
        "hit",
        "actual",
        "is_winner",
        "resolution_source",
        "contributor_outcome_ids",
        "represented_outcome_ids",
    )
    return [
        {
            "over_won": over_won,
            "under_only": under_only,
            "kalshi_won": kalshi_won,
            "player_props": [
                {key: row[key] for key in fields}
                for row in nfl_polymarket_finished_page(
                    finished=True,
                    over_won=over_won,
                    under_only=under_only,
                    kalshi_control=kalshi_won is not None,
                    kalshi_won=kalshi_won,
                )["player_props"]
            ],
        }
        for over_won in (False, True)
        for under_only in (False, True)
        for kalshi_won in (None, False, True)
    ]


class TestServedPropSelection:
    def test_finished_polymarket_fixture_is_the_payload_the_web_test_reads(self):
        path = (
            Path(__file__).parents[2]
            / "frontend/__tests__/fixtures/nflPolymarketGrade12581.json"
        )
        assert json.loads(path.read_text()) == finished_polymarket_reader_fixture()

    @pytest.mark.parametrize(
        "kwargs", [{"void": True}, {"grade_source": "clean_resolution"}]
    )
    def test_under_only_unproved_grade_does_not_invent_an_over_winner(self, kwargs):
        page = nfl_polymarket_finished_page(finished=True, under_only=True, **kwargs)
        (row,) = page["player_props"]
        assert row["outcome_name"] == "Josh Allen: 225+"
        assert row["hit"] is None and row["is_winner"] is None
        assert row["source_mark"]["state"] != "settled"
        assert page["props_script"][0]["graded_result"] is None
        assert page["props_script"][0]["settled"] is False

    @pytest.mark.parametrize(
        "kalshi_won,over_won",
        [(False, False), (True, True), (False, True), (True, False)],
    )
    @pytest.mark.parametrize("under_only", [False, True])
    def test_graded_nfl_pair_serves_one_own_verdict_and_records_both(
        self, kalshi_won, over_won, under_only
    ):
        before = nfl_polymarket_finished_page(finished=False, kalshi_control=True)
        page = nfl_polymarket_finished_page(
            finished=True,
            kalshi_control=True,
            kalshi_won=kalshi_won,
            over_won=over_won,
            under_only=under_only,
        )
        (row,) = page["player_props"]
        (live,) = before["player_props"]
        assert (row["market_name"], row["outcome_name"]) == (
            live["market_name"],
            live["outcome_name"],
        )
        assert row["_market_id"] == 72
        assert row["hit"] is kalshi_won
        assert row["over_probability"] == (0.97 if kalshi_won else 0.03)
        assert row["contributor_outcome_ids"] == [721]
        assert row["represented_outcome_ids"] == (
            [712, 721] if under_only else [711, 712, 721]
        )
        assert row["source_mark"]["state"] == "settled"
        assert row["source_mark"]["settled"]["result"] == (
            "Won" if kalshi_won else "Lost"
        )
        (hold,) = page["prop_source_holds"]
        assert hold["selection"] == "settled_source_preference"
        assert hold["selected_source"] == "kalshi"
        assert hold["selected_outcome_ids"] == [721]
        assert hold["candidate_outcome_ids"] == row["represented_outcome_ids"]
        assert hold["candidate_market_ids"] == [71, 72]
        verdicts = {v["source"]: v for v in hold["candidate_verdicts"]}
        assert verdicts["kalshi"]["hit"] is kalshi_won
        assert verdicts["polymarket"]["hit"] is over_won
        assert verdicts["polymarket"]["represented_outcome_ids"] == (
            [712] if under_only else [711, 712]
        )
        for source, won in (("kalshi", kalshi_won), ("polymarket", over_won)):
            assert verdicts[source]["settled"]["result"] == ("Won" if won else "Lost")
        assert len(page["props_script"]) == 1
        assert page["props_script"][0]["graded_result"] == (
            "hit" if kalshi_won else "miss"
        )

    def test_a_cross_venue_pair_with_only_one_grade_still_has_one_rung(self):
        from app.routes.events import _prop_player_and_stat, _settled_over_verdict
        from app.utils.game_prop_sources import shape_nfl_prop_rows

        # At the shaping boundary: one venue has graded while the other is
        # still trading. Keep the graded venue's exact verdict, not a mean.
        rows, holds = shape_nfl_prop_rows(
            [
                {
                    "market_name": "Buffalo vs Houston: Passing Yards",
                    "outcome_name": "Josh Allen: 225+",
                    "source": "kalshi",
                    "_market_id": 72,
                    "contributor_outcome_ids": [721],
                    "over_probability": 0.97,
                    "hit": True,
                    "resolution_source": "api_settlement",
                },
                {
                    "market_name": "Josh Allen: Passing Yards O/U 224.5",
                    "outcome_name": "Over",
                    "source": "polymarket",
                    "_market_id": 71,
                    "contributor_outcome_ids": [711],
                    "over_probability": 0.62,
                },
            ],
            markets={},
            legs={},
            player_and_stat=_prop_player_and_stat,
            home_team="Houston Texans",
            away_team="Buffalo Bills",
            sport_key="americanfootball_nfl",
            orient_under_verdict=lambda row: _settled_over_verdict(row, True, True),
        )
        (row,) = rows
        assert row["hit"] is True and row["over_probability"] == 0.97
        assert row["represented_outcome_ids"] == [711, 721]
        (hold,) = holds
        assert hold["selection"] == "settled_source_preference"
        verdicts = {v["source"]: v for v in hold["candidate_verdicts"]}
        assert verdicts["kalshi"]["hit"] is True
        assert verdicts["polymarket"]["hit"] is None
        assert verdicts["polymarket"]["settled"] is None

    @pytest.mark.parametrize("over_won", [False, True])
    @pytest.mark.parametrize("under_only", [False, True])
    def test_finished_polymarket_prop_keeps_player_names_and_over_verdict(
        self, over_won, under_only
    ):
        before = nfl_polymarket_finished_page(finished=False, under_only=under_only)
        after = nfl_polymarket_finished_page(
            finished=True,
            over_won=over_won,
            under_only=under_only,
        )
        assert len(before["player_props"]) == len(after["player_props"]) == 1
        live, final = before["player_props"][0], after["player_props"][0]
        assert (
            (final["market_name"], final["outcome_name"])
            == (
                live["market_name"],
                live["outcome_name"],
            )
            == ("Buffalo Bills vs Houston Texans: Passing Yards", "Josh Allen: 225+")
        )
        assert final["represented_outcome_ids"] == ([712] if under_only else [711, 712])
        assert final["contributor_outcome_ids"] == ([712] if under_only else [711])
        assert final["hit"] is over_won
        assert final["actual"] is None
        assert final["resolution_source"] == "api_settlement"
        assert final["over_probability"] == (0.97 if over_won else 0.03)
        assert final["opening_over_probability"] == 0.6
        assert final["_inverted"] is False
        assert final["source_mark"]["state"] == "settled"
        assert final["source_mark"]["settled"]["result"] == (
            "Won" if over_won else "Lost"
        )
        assert after["props_script"][0]["label"] == "Josh Allen: 225+"
        assert after["props_script"][0]["graded_result"] == (
            "hit" if over_won else "miss"
        )
        assert after["prop_source_holds"] == []

    @pytest.mark.parametrize("protected", [False, True])
    def test_mixed_live_and_settled_ladder_keeps_names_and_existing_grades(
        self, protected
    ):
        from copy import deepcopy
        from app.routes.events import _prop_player_and_stat, _settled_over_verdict
        from app.utils.game_prop_sources import (
            annotate_prop_fields,
            shape_nfl_prop_rows,
        )

        suffix = " (Protected)" if protected else ""
        market = SimpleNamespace(
            id=501,
            source="kalshi",
            external_id=("KXNFLRSHYDSPROT" if protected else "KXNFLRSHYDS")
            + "-26NOV12BUFHOU",
        )
        original = [
            {
                "market_name": "Buffalo vs Houston: Rushing Yards" + suffix,
                "outcome_name": f"James Cook: {count}+",
                "threshold": count,
                "over_probability": probability,
                "source": "kalshi",
                "_market_id": 501,
                "contributor_outcome_ids": [count],
            }
            for count, probability in [(25, 0.9), (50, 0.7), (75, 0.5), (100, 0.3)]
        ]
        arguments = dict(
            markets={501: market},
            player_and_stat=_prop_player_and_stat,
            home_team="Houston Texans",
            away_team="Buffalo Bills",
        )

        def shape(rows):
            rows = deepcopy(rows)
            annotate_prop_fields(rows, **arguments)
            result, holds = shape_nfl_prop_rows(
                rows,
                legs={},
                sport_key="americanfootball_nfl",
                orient_under_verdict=lambda row: _settled_over_verdict(row, True, True),
                **arguments,
            )
            assert holds == []
            return {r["contributor_outcome_ids"][0]: r for r in result}

        before = shape(original)
        mixed = deepcopy(original)
        mixed[0].update(hit=True, actual=63, over_probability=1.0)
        mixed[1].update(
            is_winner=True, resolution_source="api_settlement", over_probability=1.0
        )
        after = shape(mixed)
        assert set(after) == {25, 50, 75, 100}
        # The installed iPhone groups by player + FULL market name, not stat.
        assert {r["market_name"] for r in after.values()} == {
            "Buffalo Bills vs Houston Texans: Rushing Yards" + suffix
        }
        for outcome_id in before:
            assert (
                after[outcome_id]["market_name"],
                after[outcome_id]["outcome_name"],
            ) == (before[outcome_id]["market_name"], before[outcome_id]["outcome_name"])
        # Naming cannot re-adjudicate, select away or change a settled rung.
        for raw in mixed:
            row = after[raw["contributor_outcome_ids"][0]]
            for key in (
                "hit",
                "actual",
                "is_winner",
                "resolution_source",
                "over_probability",
            ):
                assert row.get(key) == raw.get(key), (key, raw)

    def test_protected_contract_never_gets_averaged_with_standard(self):
        page = nfl_page(kalshi_width=0.01)
        laporta = [
            r for r in page["player_props"] if r["player"]["key"] == "sam laporta"
        ]
        assert len(laporta) == 2
        rows = {r["stat"]["key"]: r for r in laporta}
        assert rows["receiving_yards"]["over_probability"] == 0.86
        protected = rows["receiving_yards_protected"]
        assert protected["over_probability"] == 0.845
        assert protected["market_name"].endswith("Receiving Yards (Protected)")
        assert protected["source"] == "kalshi"
        assert protected["contributor_outcome_ids"] == [262830012]

    def test_held_pair_uses_tighter_book_once_with_its_own_quote(self):
        page = nfl_page()
        rows = page["player_props"]
        chosen = next(
            r
            for r in rows
            if r["player"]["key"] == "sam laporta"
            and r["stat"]["key"] == "receiving_yards"
        )
        assert chosen["over_probability"] == 0.82
        assert chosen["source"] == "bainluck"
        assert chosen["outcome_name"] == "Sam LaPorta: 15+"
        assert chosen["line"] == {"kind": "count_at_least", "value": 15, "label": "15+"}
        assert chosen["contributor_outcome_ids"] == [331]
        assert chosen["represented_outcome_ids"] == [331, 332, 262829404]
        assert [
            (s["key"], s["probability"]) for s in chosen["source_mark"]["sources"]
        ] == [("polymarket", 0.82)]
        assert len(page["prop_source_holds"]) == 1
        hold = page["prop_source_holds"][0]
        assert hold["reason"] == "participation_rule_differs"
        assert hold["selection"] == "tighter_book"
        assert hold["selected_source"] == "polymarket"
        # The Polymarket-only line also reaches a legacy colon-based reader.
        only = [r for r in rows if r["player"]["key"] == "isaac teslaa"]
        assert len(only) == 1
        assert only[0]["outcome_name"] == "Isaac TeSlaa: 10+"
        assert only[0]["over_probability"] == 0.63
        assert only[0]["represented_outcome_ids"] == [341, 342]

    def test_unknown_book_does_not_get_called_tighter(self):
        page = nfl_page(kalshi_width=None, polymarket_width=None)
        assert page["prop_source_holds"][0]["selection"] == "book_width_unknown"
        assert page["prop_source_holds"][0]["selected_source"] == "kalshi"

    def test_equal_books_use_stable_tie_without_claiming_one_is_tighter(self):
        page = nfl_page(kalshi_width=0.02, polymarket_width=0.02)
        assert page["prop_source_holds"][0]["selection"] == "book_width_tie"
        assert page["prop_source_holds"][0]["selected_source"] == "kalshi"

    def test_one_known_book_does_not_claim_an_unknown_book_is_wider(self):
        page = nfl_page(kalshi_width=None)
        assert page["prop_source_holds"][0]["selection"] == "only_known_book"
        assert page["prop_source_holds"][0]["selected_source"] == "polymarket"

    def test_under_only_book_is_reoriented_once_on_server(self):
        page = nfl_page(poly_under_only=True)
        row = next(
            r for r in page["player_props"] if r["contributor_outcome_ids"] == [332]
        )
        assert row["over_probability"] == 0.82
        assert row["_inverted"] is False
        assert row["source_mark"]["sources"][0]["probability"] == 0.82
        script = next(
            r for r in page["props_script"] if r["label"] == "Sam LaPorta: 15+"
        )
        assert script["current"] == 0.82


class TestAllGameMarketFamilies:
    def test_every_served_price_has_its_actual_quote_and_observation(self):
        from tests.test_a_game_market_row_carries_its_own_price_age_4970 import (
            _payload,
            PRICED_SECTIONS,
        )

        page = _payload()
        for section in PRICED_SECTIONS:
            assert page[section], section
            rows = (
                [leg for m in page[section] for leg in m["outcomes"]]
                if section == "matchups"
                else page[section]
            )
            for row in rows:
                mark = row["source_mark"]
                assert mark["state"] == "blend", section
                source = mark["sources"][0]
                assert source["key"] == "kalshi"
                assert source["probability"] == row.get(
                    "over_probability", row.get("probability")
                )
                assert datetime.fromisoformat(
                    source["observed_at"].replace("Z", "+00:00")
                ) == datetime.fromisoformat(row["observed_at"])

    def test_unknown_stat_stays_present_without_guessed_typed_fields(self):
        from app.routes.events import _prop_player_and_stat
        from app.utils.game_prop_sources import annotate_prop_fields

        row = {
            "market_name": "Sean Manaea: Outs Recorded O/U 16.5",
            "outcome_name": "Over",
            "over_probability": 0.6,
        }
        annotate_prop_fields(
            [row],
            markets={},
            player_and_stat=_prop_player_and_stat,
            home_team="Mets",
            away_team="Giants",
        )
        assert row["over_probability"] == 0.6
        assert row["typing_refusal"] == "untyped_stat"
        assert row["player"] is row["stat"] is row["line"] is row["side"] is None

    def test_database_error_is_not_reported_as_an_empty_prop_page(self):
        from unittest.mock import AsyncMock
        from app.routes.events import _build_game_markets

        db = AsyncMock()
        db.execute.side_effect = RuntimeError("quote read failed")
        with pytest.raises(RuntimeError, match="quote read failed"):
            asyncio.run(_build_game_markets(14639206, db))


class TestCapturedPatriotsLions:
    def test_all_336_legs_remain_represented_and_all_24_holds_select_one_book(self):
        from sqlalchemy import DateTime
        from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport
        from app.routes.events import _build_game_markets
        from tests.test_event_props_matrix_10236 import _db

        fixture = json.loads(
            (
                Path(__file__).parent / "fixtures/source_mark_12581/patriots_lions.json"
            ).read_text()
        )
        delta = datetime.now(timezone.utc) - datetime.fromisoformat(
            fixture["captured_at"]
        )

        def model(cls, data):
            values = {}
            for column in cls.__table__.columns:
                if column.name not in data:
                    continue
                value = data[column.name]
                if value is not None and isinstance(column.type, DateTime):
                    value = datetime.fromisoformat(value) + delta
                values[column.name] = value
            return cls(**values)

        event = model(Event, fixture["event"])
        event.sport = Sport(id=event.sport_id, key=fixture["event"]["sport_key"])
        event.sport_id = None  # the captured cohort is already selected
        markets = [model(FuturesMarket, m) for m in fixture["markets"]]
        legs = [model(FuturesOutcome, o) for o in fixture["outcomes"]]
        legs.sort(key=lambda o: -o.current_probability)
        seen = {
            o["id"]: datetime.fromisoformat(o["observed_at"]) + delta
            for o in fixture["observations"]
            if o["observed_at"]
        }
        page, _, _ = asyncio.run(
            _build_game_markets(event.id, _db(event, markets, legs, seen))
        )
        props = page["player_props"]
        assert len(props) == 270
        represented = {
            oid
            for r in props
            for oid in r.get("represented_outcome_ids", r["contributor_outcome_ids"])
        }
        assert len(represented) == 336
        assert represented == {o.id for o in legs}
        assert all(
            r["player"] and r["stat"] and r["line"] and r["side"] == "over"
            for r in props
        )
        assert all(
            r["stat"]["label"] == r["stat"]["label"].title()
            and r["market_name"].endswith(": " + r["stat"]["label"])
            for r in props
        )
        assert len(page["prop_source_holds"]) == 24
        assert {h["selected_source"] for h in page["prop_source_holds"]} == {"kalshi"}
        assert all(len(r["source_mark"]["sources"]) == 1 for r in props)
        only = [r for r in props if r["source"] == "bainluck"]
        assert len(only) == 18
        assert all(
            ":" in r["outcome_name"]
            and r["source_mark"]["sources"][0]["key"] == "polymarket"
            for r in only
        )
        # The old iOS header sorts legacy keys and its allowlist omits bainluck.
        assert sorted({r["source"] for r in props})[0] == "bainluck"
        rules = json.loads(
            (
                Path(__file__).parent / "fixtures/source_mark_12581/held_rules.json"
            ).read_text()
        )
        assert rules["rule_equivalent"] == 0 and len(rules["pairs"]) == 24
