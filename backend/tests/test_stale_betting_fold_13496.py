"""Regression guards for #13496: scheduled canonical rows must not serve a
>72h sportsbook (``betting``) reading when a fresher absorbed twin is present,
and ``betting_book_count`` must travel with the twin supplying ``betting``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Event, OddsSnapshot, Sport
from app.routes.events import _format_event_with_aggregated_odds
from app.utils.event_twin_fold import fold_twin_events
from app.utils.hero_probability import hero_sportsbook_count, resolve_hero
from app.utils.odds_math import aggregate_bookmaker_odds
from app.utils.proven_duplicates import (
    FoldedBlendView,
    latest_snapshot_for_each_bookmaker,
    merge_probability_sources,
    merge_probability_sources_with_owners,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
COMMENCE = NOW + timedelta(hours=30)

LEAGUE2 = Sport(id=91, key="soccer_england_league2", name="League Two")
BOXING = Sport(id=92, key="boxing_boxing", name="Boxing")


def _ts(delta: timedelta) -> str:
    return (NOW - delta).isoformat()


def _event(
    eid: int,
    *,
    home: str = "Crawley Town",
    away: str = "Barnet",
    sport: Sport = LEAGUE2,
    status: str = "scheduled",
    sources: dict | None = None,
    external_id: str | None = None,
    espn_id: str | None = None,
    tags: list[str] | None = None,
) -> Event:
    ev = Event(
        id=eid,
        sport_id=sport.id,
        home_team_name=home,
        away_team_name=away,
        home_team_id=eid * 10 + 1,
        away_team_id=eid * 10 + 2,
        commence_time=COMMENCE,
        status=status,
        external_id=external_id,
        espn_id=espn_id,
        win_probability_sources=sources if sources is not None else {},
        event_tags=tags if tags is not None else [],
    )
    ev.sport = sport
    return ev


class TestTwoRowCrawleyShape13496:
    """Two-row scheduled pair: stale canonical ``betting`` vs fresh twin ``betting``."""

    def _stale_bag(self) -> dict:
        return {
            "betting": {
                "value": 0.2248,
                "updated_at": _ts(timedelta(days=63)),
            },
            "betting_book_count": 4,
        }

    def _fresh_bag(self) -> dict:
        return {
            "betting": {
                "value": 0.2487,
                "away_value": 0.5041,
                "draw_value": 0.2472,
                "three_way_home_value": 0.2487,
                "updated_at": _ts(timedelta(minutes=30)),
            },
            "betting_book_count": 10,
        }

    def test_merge_probability_sources_supersedes_stale_betting_and_copies_book_count(self):
        canonical_bag = self._stale_bag()
        twin_bag = self._fresh_bag()

        merged, owners = merge_probability_sources_with_owners(
            15315470,
            canonical_bag,
            [(15352302, twin_bag)],
            event_status="scheduled",
            now=NOW,
        )

        assert owners["betting"] == 15352302
        assert merged["betting"]["value"] == pytest.approx(0.2487)
        assert merged["betting"]["updated_at"] == twin_bag["betting"]["updated_at"]
        assert merged["betting_book_count"] == 10

        view = FoldedBlendView(_event(15315470, sources=canonical_bag), merged)
        hero = resolve_hero(view)
        assert hero is not None and hero.source == "blend"
        assert hero.home_probability == pytest.approx(0.2487)
        assert hero_sportsbook_count(view) == 10
        # Caller's dict was not mutated in place.
        assert canonical_bag["betting"]["value"] == pytest.approx(0.2248)
        assert canonical_bag["betting_book_count"] == 4

    def test_fold_twin_events_and_list_card_format_use_fresh_betting_and_credit_10_books(self):
        canon = _event(
            15315470,
            sources=self._stale_bag(),
            external_id="a0bbfdf49b4c8a306da63f7801426e95",
        )
        canon.id = 15315470
        twin = _event(
            15352302,
            sources=self._fresh_bag(),
            external_id="17fe7f97afa7602f6ee038dbdc5b7c19",
        )
        twin.id = 15352302

        fold = fold_twin_events([canon, twin])
        assert fold.dropped_ids == [15352302]
        assert canon.id in fold.merged_sources
        merged = fold.merged_sources[canon.id]
        assert merged["betting"]["value"] == pytest.approx(0.2487)
        assert merged["betting_book_count"] == 10

        # Simulate list formatter with the 10 fresh sportsbook snapshots absorbed.
        fresh_snaps = [
            OddsSnapshot(
                id=i + 1,
                event_id=15352302,
                bookmaker=f"book_{i}",
                home_moneyline=302,
                away_moneyline=-102,
                home_win_probability=0.2487,
                away_win_probability=0.5041,
                captured_at=NOW - timedelta(hours=1),
            )
            for i in range(10)
        ]
        stale_snaps = [
            OddsSnapshot(
                id=100 + i,
                event_id=15315470,
                bookmaker=f"book_{i}",
                home_moneyline=345,
                away_moneyline=-115,
                home_win_probability=0.2248,
                away_win_probability=0.5350,
                captured_at=NOW - timedelta(days=63),
            )
            for i in range(4)
        ]
        latest = latest_snapshot_for_each_bookmaker(stale_snaps + fresh_snaps, 15315470)
        agg = aggregate_bookmaker_odds(latest)
        assert agg["bookmaker_count"] == 10

        card = _format_event_with_aggregated_odds(
            canon,
            {
                "aggregated": agg,
                "captured_at": NOW - timedelta(hours=1),
                "snapshots": latest,
            },
            folded_sources=merged,
        )
        assert card["hero_probability"] == pytest.approx(0.2487)
        assert card["current_odds"]["home_rendered_percent"] == 25
        assert card["current_odds"]["draw_rendered_percent"] == 25
        assert card["current_odds"]["away_rendered_percent"] == 50
        assert card["current_odds"]["bookmaker_count"] == 10
        assert card["source_mark"]["sources"][0]["key"] == "betting"
        assert card["source_mark"]["sources"][0]["count"] == 10

        # Verify raw canonical dict remained untouched by the read fold.
        assert canon.win_probability_sources["betting"]["value"] == pytest.approx(0.2248)


class TestGapFillBettingBookCount15315471:
    """Port Vale v Northampton shape: canonical lacks ``betting``, twin supplies it + count."""

    def test_gap_fill_betting_carries_twin_betting_book_count(self):
        canon_sources = {}
        twin_sources = {
            "betting": {
                "value": 0.4492,
                "away_value": 0.2631,
                "draw_value": 0.2877,
                "updated_at": _ts(timedelta(minutes=20)),
            },
            "betting_book_count": 10,
        }

        merged, owners = merge_probability_sources_with_owners(
            15315471,
            canon_sources,
            [(15352303, twin_sources)],
            event_status="scheduled",
            now=NOW,
        )
        assert owners["betting"] == 15352303
        assert merged["betting_book_count"] == 10
        view = FoldedBlendView(_event(15315471, sources=canon_sources), merged)
        assert hero_sportsbook_count(view) == 10

    def test_gap_fill_replaces_orphan_stale_book_count_and_works_in_twin_fold(self):
        canon = _event(
            15315471,
            sources={"betting": None, "betting_book_count": 2},
            external_id="6601d28f93317915788723bc082330fe",
        )
        twin = _event(
            15352303,
            sources={
                "betting": {"value": 0.4492, "updated_at": _ts(timedelta(minutes=20))},
                "betting_book_count": 10,
            },
            external_id="eaa911656924937cdfe0801f4dafe1e0",
        )

        fold = fold_twin_events([canon, twin])
        assert fold.dropped_ids == [15352303]
        merged = fold.merged_sources[15315471]
        assert merged["betting"]["value"] == pytest.approx(0.4492)
        assert merged["betting_book_count"] == 10


class TestStaleBettingBoundariesAndGuards:
    def test_72h_threshold_boundary(self):
        twin = (2, {"betting": {"value": 0.61, "updated_at": _ts(timedelta(minutes=5))}, "betting_book_count": 8})

        just_under = {
            "betting": {"value": 0.40, "updated_at": _ts(timedelta(hours=71, minutes=59))},
            "betting_book_count": 3,
        }
        kept = merge_probability_sources(just_under, [twin], event_status="scheduled", now=NOW)
        assert kept["betting"]["value"] == pytest.approx(0.40)
        assert kept["betting_book_count"] == 3

        just_over = {
            "betting": {"value": 0.40, "updated_at": _ts(timedelta(hours=72, minutes=1))},
            "betting_book_count": 3,
        }
        replaced = merge_probability_sources(just_over, [twin], event_status="scheduled", now=NOW)
        assert replaced["betting"]["value"] == pytest.approx(0.61)
        assert replaced["betting_book_count"] == 8

    @pytest.mark.parametrize("status", ["live", "completed", "closed", "suspended", None])
    def test_non_scheduled_status_never_overrides_existing_betting(self, status):
        canon = {
            "betting": {"value": 0.40, "updated_at": _ts(timedelta(days=10))},
            "betting_book_count": 3,
        }
        twin = (2, {"betting": {"value": 0.70, "updated_at": _ts(timedelta(minutes=5))}, "betting_book_count": 9})
        merged = merge_probability_sources(canon, [twin], event_status=status, now=NOW)
        assert merged["betting"]["value"] == pytest.approx(0.40)
        assert merged["betting_book_count"] == 3

    def test_untimestamped_or_naive_canonical_betting_not_overridden(self):
        twin = (2, {"betting": {"value": 0.70, "updated_at": _ts(timedelta(minutes=5))}, "betting_book_count": 9})

        bare = {"betting": 0.42, "betting_book_count": 5}
        assert merge_probability_sources(bare, [twin], event_status="scheduled", now=NOW) == bare

        naive = {"betting": {"value": 0.42, "updated_at": "2020-01-01T00:00:00"}}
        assert merge_probability_sources(naive, [twin], event_status="scheduled", now=NOW) == naive

    def test_older_twin_never_replaces_canonical(self):
        canon = {"betting": {"value": 0.40, "updated_at": _ts(timedelta(days=10))}, "betting_book_count": 4}
        older_twin = (2, {"betting": {"value": 0.75, "updated_at": _ts(timedelta(days=20))}, "betting_book_count": 11})
        merged = merge_probability_sources(canon, [older_twin], event_status="scheduled", now=NOW)
        assert merged["betting"]["value"] == pytest.approx(0.40)
        assert merged["betting_book_count"] == 4

    def test_picks_freshest_twin_deterministically_and_breaks_ties_by_lowest_id(self):
        canon = {"betting": {"value": 0.20, "updated_at": _ts(timedelta(days=30))}, "betting_book_count": 3}
        twins = [
            (30, {"betting": {"value": 0.55, "updated_at": _ts(timedelta(hours=2))}, "betting_book_count": 7}),
            (10, {"betting": {"value": 0.65, "updated_at": _ts(timedelta(minutes=15))}, "betting_book_count": 9}),
            (20, {"betting": {"value": 0.60, "updated_at": _ts(timedelta(minutes=15))}, "betting_book_count": 8}),
        ]
        m1, o1 = merge_probability_sources_with_owners(1, canon, twins, event_status="scheduled", now=NOW)
        m2, o2 = merge_probability_sources_with_owners(1, canon, list(reversed(twins)), event_status="scheduled", now=NOW)
        assert o1["betting"] == 10 and o2["betting"] == 10
        assert m1 == m2
        assert m1["betting"]["value"] == pytest.approx(0.65)
        assert m1["betting_book_count"] == 9

    def test_pops_stale_book_count_when_fresher_twin_omits_book_count(self):
        canon = {"betting": {"value": 0.2248, "updated_at": _ts(timedelta(days=63))}, "betting_book_count": 4}
        twin = (2, {"betting": {"value": 0.25, "updated_at": _ts(timedelta(minutes=10))}})
        merged = merge_probability_sources(canon, [twin], event_status="scheduled", now=NOW)
        assert merged["betting"]["value"] == pytest.approx(0.25)
        assert "betting_book_count" not in merged
        assert hero_sportsbook_count(FoldedBlendView(_event(1, sources=canon), merged)) is None

    def test_corner_flipped_claim_twin_complements_before_override(self):
        canon = _event(
            501,
            home="Boxer Alpha",
            away="Boxer Beta",
            sport=BOXING,
            espn_id="espn-box-501",
            sources={"betting": {"value": 0.30, "updated_at": _ts(timedelta(days=14))}, "betting_book_count": 3},
        )
        # Reversed id-less claim lists Beta @ Alpha with Beta at 0.35 -> Alpha is 0.65 once flipped.
        twin = _event(
            502,
            home="Boxer Beta",
            away="Boxer Alpha",
            sport=BOXING,
            external_id=None,
            sources={"betting": {"value": 0.35, "updated_at": _ts(timedelta(minutes=10))}, "betting_book_count": 8},
        )
        fold = fold_twin_events([canon, twin])
        assert fold.dropped_ids == [502]
        assert 502 in fold.flipped_loser_ids
        merged = fold.merged_sources[501]
        assert merged["betting"]["value"] == pytest.approx(0.65)
        assert merged["betting_book_count"] == 8

    def test_fold_twin_events_preserves_absorbed_betting_dict_without_value_key_5918(self):
        # Regression for test_league_route_name_pair_fold_has_loaded_sport_5918:
        # an absorbed twin carrying legacy/shape `{"home": 0.62, "away": 0.38}`
        # when the survivor has no `betting` key at all must still union onto the survivor.
        laliga = Sport(id=93, key="soccer_spain_la_liga", name="La Liga")
        survivor = _event(
            601,
            home="RC Celta de Vigo",
            away="Malaga CF",
            sport=laliga,
            espn_id="999001",
        )
        survivor.win_probability_sources = None
        absorbed = _event(
            602,
            home="Celta Vigo",
            away="Malaga",
            sport=laliga,
            sources={"betting": {"home": 0.62, "away": 0.38}},
        )
        fold = fold_twin_events([survivor, absorbed])
        assert fold.dropped_ids == [602]
        assert fold.merged_sources[601]["betting"] == {"home": 0.62, "away": 0.38}
