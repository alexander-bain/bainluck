"""T2-1 (#5058): the projection the dropdown reads, and the ways it must fail.

Two halves, one contract:

* the WRITER turns an already-published championship grid plus the league's own
  wins ladders into a few kilobytes of decided answers;
* the READER puts those answers on the team rows a person is actually shown,
  and puts nothing anywhere when it cannot.

THE READER'S FAILURE MODES ARE THE POINT. This runs on `/typeahead`, the first
surface a person touches and the one measured against a 500 ms p50. Every way
this can go wrong — Redis down, key expired, a payload from a schema this code
predates, a team the projection never covered — has to arrive as "the row a
reader saw before T2-1 existed", never as an exception, an empty second line, or
a `NaN%`.

THE DUPLICATE-ROW CASE IS NOT HYPOTHETICAL. Measured on production 2026-09-11:
the NFL championship grid resolves the Chargers to team `17736` and the Steelers
to `17757` — both rows in `americanfootball_nfl_preseason` — while the search
pool offers `556` and `540` in `americanfootball_nfl` (#5120). An id-only
lookup leaves two of thirty-two NFL clubs permanently blank for a reason no
reader could ever see, so the name index is a tested requirement and not a
nicety.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.config.league_configs import get_league_config
from app.services.season_answers_reader import attach_season_answers
from app.tasks.season_answers_projection import (
    SEASON_ANSWERS_SCHEMA,
    build_projection,
    season_answers_key,
)

NFL = get_league_config("nfl")
STAMP = datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc)


def _cell(p, state="live"):
    return {
        "merged_probability": p,
        "state": state,
        "sources": [
            {"source": "kalshi", "probability": p, "market_name": "Pro Football Playoff Qualifiers"},
        ],
    }


def _grid(teams):
    return {"league": "nfl", "season": "2026-27", "teams": teams}


def _ladder(external_id, name, rungs, market_id=1, source="kalshi"):
    return {
        "market_id": market_id,
        "external_id": external_id,
        "name": name,
        "source": source,
        "rungs": [
            {
                "threshold": t,
                "probability": p,
                "outcome_id": market_id * 1000 + t,
                "price_changed_at": None,
            }
            for t, p in rungs
        ],
    }


NE_RUNGS = [(8, 0.730), (9, 0.665), (10, 0.465), (11, 0.305)]
NE_LADDER = _ladder(
    "KXNFLWINS-27NE", "Pro Football: New England Total Wins", NE_RUNGS, market_id=12230814
)


class FakeRedis:
    """A Redis stand-in that records the reads, so "did not call" is assertable."""

    def __init__(self, entries: dict[str, str] | None = None, raises: bool = False):
        self.entries = entries or {}
        self.raises = raises
        self.reads: list[str] = []

    def get(self, key):
        self.reads.append(key)
        if self.raises:
            raise ConnectionError("redis is down")
        return self.entries.get(key)


class TestTheProjection:
    def test_a_team_gets_both_answers_in_reading_order(self):
        grid = _grid([
            {"team_id": 11, "name": "New England Patriots", "cells": {"make_playoffs": _cell(0.4905)}},
        ])
        payload = build_projection(NFL, grid, [NE_LADDER], generated_at=STAMP)

        assert payload["schema"] == SEASON_ANSWERS_SCHEMA
        assert payload["season"] == "2026-27"
        [entry] = payload["teams"]
        assert entry["team_id"] == 11
        assert entry["name_key"] == "new england patriots"
        assert [a["key"] for a in entry["answers"]] == ["season_wins", "make_playoffs"]
        wins, playoffs = entry["answers"]
        assert wins["label"] == "10+ regular-season wins"
        assert wins["probability"] == 0.465
        assert wins["market_id"] == 12230814
        # The playoff number is the grid's own blend, carried verbatim.
        assert playoffs["probability"] == 0.4905
        assert playoffs["label"] == "Make Playoffs"

    def test_a_team_with_no_wins_ladder_still_answers_the_playoff_question(self):
        grid = _grid([
            {"team_id": 538, "name": "Buffalo Bills", "cells": {"make_playoffs": _cell(0.7375)}},
        ])
        [entry] = build_projection(NFL, grid, [], generated_at=STAMP)["teams"]
        assert [a["key"] for a in entry["answers"]] == ["make_playoffs"]

    def test_a_team_with_nothing_to_say_is_left_out_entirely(self):
        """Not an entry with an empty answer list — no entry at all.

        The reader treats an empty list and a missing team the same way, and one
        of the two shapes has to be the one that exists.
        """
        grid = _grid([
            {"team_id": 999, "name": "Somewhere United", "cells": {"make_playoffs": _cell(None)}},
        ])
        assert build_projection(NFL, grid, [], generated_at=STAMP)["teams"] == []

    def test_two_open_ladders_for_one_club_answer_nothing(self):
        """Two seasons open at once, or two clubs folded into one — either way
        the card would be printing a number whose question nobody can name."""
        grid = _grid([
            {"team_id": 11, "name": "New England Patriots", "cells": {"make_playoffs": _cell(0.4905)}},
        ])
        last_season = _ladder(
            "KXNFLWINS-26NE", "Pro Football: New England Total Wins",
            [(9, 0.52)], market_id=777,
        )
        [entry] = build_projection(NFL, grid, [NE_LADDER, last_season], generated_at=STAMP)["teams"]
        assert [a["key"] for a in entry["answers"]] == ["make_playoffs"]

    def test_a_ladder_naming_a_club_this_league_does_not_have_is_ignored(self):
        grid = _grid([
            {"team_id": 11, "name": "New England Patriots", "cells": {"make_playoffs": _cell(0.4905)}},
        ])
        stray = _ladder(
            "KXNCAAFWINS-27GMU", "College Football: George Mason Total Wins",
            [(6, 0.5)], market_id=888,
        )
        [entry] = build_projection(NFL, grid, [stray], generated_at=STAMP)["teams"]
        assert [a["key"] for a in entry["answers"]] == ["make_playoffs"]

    def test_an_ambiguous_subject_answers_nothing_even_with_a_perfect_ladder(self):
        """`Los Angeles` fits two clubs. Neither gets the number."""
        grid = _grid([
            {"team_id": 544, "name": "Los Angeles Rams", "cells": {"make_playoffs": _cell(0.785)}},
            {"team_id": 556, "name": "Los Angeles Chargers", "cells": {"make_playoffs": _cell(0.61)}},
        ])
        ambiguous = _ladder(
            "KXNFLWINS-27LA", "Pro Football: Los Angeles Total Wins",
            [(9, 0.5)], market_id=999,
        )
        payload = build_projection(NFL, grid, [ambiguous], generated_at=STAMP)
        assert all(
            [a["key"] for a in e["answers"]] == ["make_playoffs"] for e in payload["teams"]
        )


class TestTheReader:
    def _entry(self, sport_key="americanfootball_nfl"):
        grid = _grid([
            {"team_id": 11, "name": "New England Patriots", "cells": {"make_playoffs": _cell(0.4905)}},
        ])
        payload = build_projection(NFL, grid, [NE_LADDER], generated_at=STAMP)
        return FakeRedis({season_answers_key(sport_key): json.dumps(payload)})

    def test_the_team_row_a_reader_sees_carries_both_facts(self):
        rc = self._entry()
        rows = [
            {"type": "team", "text": "New England Patriots", "team_id": 11,
             "sport_key": "americanfootball_nfl"},
            {"type": "futures", "text": "NFL Super Bowl Winner"},
        ]
        assert attach_season_answers(rc, rows) == 1
        assert [a["label"] for a in rows[0]["season_answers"]] == [
            "10+ regular-season wins", "Make Playoffs",
        ]
        # A futures row is not a team row and gains nothing.
        assert "season_answers" not in rows[1]

    def test_a_team_the_grid_keyed_to_its_preseason_row_still_answers(self):
        """#5120: the grid says Chargers = 17736, the dropdown says 556.

        The folded name is the same on both rows, and it is the only thing that
        is. Without this index two NFL clubs are blank on the front door.
        """
        grid = _grid([
            {"team_id": 17736, "name": "Los Angeles Chargers", "cells": {"make_playoffs": _cell(0.61)}},
        ])
        payload = build_projection(NFL, grid, [], generated_at=STAMP)
        rc = FakeRedis({season_answers_key("americanfootball_nfl"): json.dumps(payload)})
        rows = [{"type": "team", "text": "Los Angeles Chargers", "team_id": 556,
                 "sport_key": "americanfootball_nfl"}]
        assert attach_season_answers(rc, rows) == 1
        assert rows[0]["season_answers"][0]["probability"] == 0.61

    def test_no_team_row_means_no_redis_call_at_all(self):
        """The commonest keystroke shows no team, and must pay nothing for this."""
        rc = self._entry()
        rows = [{"type": "futures", "text": "NFL Super Bowl Winner"},
                {"type": "event", "text": "Seattle at New England"}]
        assert attach_season_answers(rc, rows) == 0
        assert rc.reads == []

    def test_three_team_rows_of_one_league_read_the_key_once(self):
        rc = self._entry()
        rows = [
            {"type": "team", "text": "New England Patriots", "team_id": 11,
             "sport_key": "americanfootball_nfl"},
            {"type": "team", "text": "George Mason Patriots", "team_id": 3509,
             "sport_key": "americanfootball_nfl"},
            {"type": "team", "text": "Dallas Baptist Patriots", "team_id": 894,
             "sport_key": "americanfootball_nfl"},
        ]
        attach_season_answers(rc, rows)
        assert rc.reads == [season_answers_key("americanfootball_nfl")]

    def test_a_team_the_projection_never_covered_gains_nothing(self):
        rc = self._entry()
        rows = [{"type": "team", "text": "George Mason Patriots", "team_id": 3509,
                 "sport_key": "basketball_ncaab"}]
        assert attach_season_answers(rc, rows) == 0
        assert "season_answers" not in rows[0]

    def test_redis_being_down_leaves_the_row_exactly_as_it_was(self):
        rc = FakeRedis(raises=True)
        rows = [{"type": "team", "text": "New England Patriots", "team_id": 11,
                 "sport_key": "americanfootball_nfl"}]
        assert attach_season_answers(rc, rows) == 0
        assert "season_answers" not in rows[0]

    def test_a_payload_from_a_schema_this_reader_predates_is_refused(self):
        """Refused, not guessed at. A projection whose answers moved is not one
        whose answers can be inferred from the shape that is still recognised."""
        grid = _grid([
            {"team_id": 11, "name": "New England Patriots", "cells": {"make_playoffs": _cell(0.4905)}},
        ])
        payload = build_projection(NFL, grid, [NE_LADDER], generated_at=STAMP)
        payload["schema"] = "season-answers/v99"
        rc = FakeRedis({season_answers_key("americanfootball_nfl"): json.dumps(payload)})
        rows = [{"type": "team", "text": "New England Patriots", "team_id": 11,
                 "sport_key": "americanfootball_nfl"}]
        assert attach_season_answers(rc, rows) == 0

    def test_a_corrupt_entry_leaves_the_row_exactly_as_it_was(self):
        rc = FakeRedis({season_answers_key("americanfootball_nfl"): "{not json"})
        rows = [{"type": "team", "text": "New England Patriots", "team_id": 11,
                 "sport_key": "americanfootball_nfl"}]
        assert attach_season_answers(rc, rows) == 0

    def test_a_team_row_with_no_sport_key_is_skipped_rather_than_guessed(self):
        rc = self._entry()
        rows = [{"type": "team", "text": "New England Patriots", "team_id": 11}]
        assert attach_season_answers(rc, rows) == 0
        assert rc.reads == []


class TestTheWinsSeriesConfig:
    def test_only_leagues_whose_subject_resolution_was_measured_carry_a_series(self):
        """An empty `wins_series` means "not checked", never "no such market".

        College football HAS a `KXNCAAFWINS` series with 73 open markets; it is
        deliberately not wired, because resolving a bare place name against
        several hundred programmes that share place names with each other and
        with the pros is a different measurement than the one that was taken.
        """
        assert get_league_config("nfl").wins_series == ["KXNFLWINS"]
        assert get_league_config("nba").wins_series == ["KXNBAWINS"]
        assert get_league_config("ncaa-football").wins_series == []
        assert get_league_config("mlb").wins_series == []

    @pytest.mark.parametrize("slug", ["nfl", "nba"])
    def test_every_wired_league_has_a_make_playoffs_column_to_lift_from(self, slug):
        config = get_league_config(slug)
        assert any(c.key == "make_playoffs" for c in config.columns)
        assert config.sport_keys
