"""#7798 — a Championship Path card stops calling Leeds United "United".

THE SPECIMEN, read on production 2026-09-21 18:35Z:

    GET /api/events/15311082/team-progression   (Leeds United @ Arsenal, EPL)
      away_team: {"name": "Leeds United", "short_name": "United",
                  "team_id": null, "logo_url": null}

    GET /api/playoffs/epl                       (the SAME minute)
      {"name": "Leeds United", "short_name": "LEE", "team_id": 1,
       "logo_url": "https://a.espncdn.com/i/teamlogos/soccer/500/357.png"}

The grid had the right answer and the event payload minted its own wrong one.
On the iPhone the header read "LEE vs ARS" and the card three hundred points
below read "United" — which in an English-football context is a DIFFERENT CLUB.

Three arms, and each one is a different half of the repair:

  1. `compact_team_label` — the grid's own mint (`playoffs.py`), which took the
     last word unconditionally and had a precedence bug on top of it.
  2. `TeamLeagueContext` — the carrier, which dropped the label and the crest.
  3. `_build_team` in the `/team-progression` route — the consumer, which
     re-derived a label and hardcoded `team_id`/`logo_url` to null.

Fixing any one alone leaves the reader looking at the same card.
"""

import json
from types import SimpleNamespace

import pytest

from app.services.league_context import (
    LeagueContext,
    TeamLeagueContext,
    _compute_league_context,
    enrich_event_with_context,
)
from app.utils.team_short_name import (
    CLUB_TYPE_SUFFIXES,
    compact_team_label,
    is_non_distinctive_trailing_word,
)


def _shipped_line(name, abbreviation):
    """The line that was replaced, transcribed so the BEFORE is executable.

    Kept verbatim — including the precedence bug — because "4 rows change" is
    only a measurement if both sides of it can be run.
    """
    return (abbreviation or name.split()[-1]) if name else None


class TestCompactTeamLabel:
    """Arm 1 — the mint."""

    #: Every grid row the change moves, measured over the whole served
    #: population on 2026-09-21: 530 rows across all 14 configured leagues,
    #: 379 of them backed by a `teams` row. These four, and no others.
    PRODUCTION_SPECIMENS = [
        # (league, teams.name, teams.abbreviation, before, after)
        ("champions-league", "Manchester United", None, "United", "Manchester United"),
        ("epl", "Coventry City", None, "City", "Coventry City"),
        ("epl", "Hull City", None, "City", "Hull City"),
        ("mls", "Los Angeles FC", None, "FC", "Los Angeles FC"),
    ]

    @pytest.mark.parametrize(
        "league,name,abbreviation,before,after", PRODUCTION_SPECIMENS
    )
    def test_the_four_moving_rows_move_and_the_before_is_what_shipped(
        self, league, name, abbreviation, before, after
    ):
        # The BEFORE is asserted too. Without it this test passes just as well
        # against a rule that never changed anything.
        assert _shipped_line(name, abbreviation) == before
        assert compact_team_label(name, abbreviation) == after

    def test_coventry_and_hull_stop_sharing_one_label_on_one_grid(self):
        """The defect a reader could see without knowing either club.

        Two EPL rows both read "City" while Manchester City read "MNC".
        """
        coventry = compact_team_label("Coventry City", None)
        hull = compact_team_label("Hull City", None)
        assert _shipped_line("Coventry City", None) == _shipped_line("Hull City", None)
        assert coventry != hull

    #: Rows whose abbreviation is real and short. The naive reading of the
    #: web's `length <= 2` clause would flag all of these — it is a test on a
    #: trailing WORD of a name, never on the abbreviation field, and getting
    #: that backwards would rename a third of the NFL.
    ABBREVIATION_CONTROLS = [
        ("Leeds United", "LEE"),
        ("Arsenal", "ARS"),
        ("Manchester City", "MNC"),
        ("Tampa Bay Rays", "TB"),
        ("San Francisco 49ers", "SF"),
        ("Kansas City Chiefs", "KC"),
        ("New York Knicks", "NY"),
        ("VfB Stuttgart", "VFB"),
        ("PSV Eindhoven", "PSV"),
        ("D.C. United", "DC"),
    ]

    @pytest.mark.parametrize("name,abbreviation", ABBREVIATION_CONTROLS)
    def test_an_abbreviation_is_returned_untouched(self, name, abbreviation):
        assert compact_team_label(name, abbreviation) == abbreviation
        assert _shipped_line(name, abbreviation) == abbreviation  # unchanged

    #: The distinctive last word is still taken — this is the behaviour 375 of
    #: 379 production rows depend on, and the fix is worthless if it stops.
    MASCOT_CONTROLS = [
        ("Boston Celtics", "Celtics"),
        ("Kansas Jayhawks", "Jayhawks"),
        ("Texas Rangers", "Rangers"),
        ("Los Angeles Kings", "Kings"),
        ("Oklahoma St Cowgirls", "Cowgirls"),
    ]

    @pytest.mark.parametrize("name,expected", MASCOT_CONTROLS)
    def test_a_distinctive_last_word_is_still_taken(self, name, expected):
        assert compact_team_label(name, None) == expected
        assert _shipped_line(name, None) == expected  # unchanged

    def test_a_row_with_an_abbreviation_and_no_name_serves_the_abbreviation(self):
        """The precedence bug, which no production row exercises today.

        `a or b if c else None` binds as `(a or b) if c else None`, so the one
        case the `abbreviation or` was written to cover was the case it threw
        away.
        """
        assert _shipped_line(None, "LEE") is None
        assert compact_team_label(None, "LEE") == "LEE"

    def test_nothing_known_is_still_none(self):
        assert compact_team_label(None, None) is None
        assert compact_team_label("", None) is None

    def test_a_single_word_name_is_returned_whole(self):
        assert compact_team_label("Arsenal", None) == "Arsenal"

    def test_every_output_is_the_abbreviation_the_name_or_its_last_word(self):
        """The fail-safe property, asserted rather than described.

        The module's claim is that it can never emit a string the club is not
        called. A rule change that started composing or truncating would keep
        every case above green and break this one.
        """
        names = [n for _, n, _, _, _ in self.PRODUCTION_SPECIMENS]
        names += [n for n, _ in self.ABBREVIATION_CONTROLS]
        names += [n for n, _ in self.MASCOT_CONTROLS]
        names += ["Paris Saint Germain", "1. FC Koln", "Ludogorets III", "Crimson U21"]
        for name in names:
            for abbreviation in (None, "XYZ"):
                out = compact_team_label(name, abbreviation)
                assert out in {abbreviation, name, name.split()[-1]}


class TestNonDistinctiveTrailingWord:
    """The designator predicate, which the three clients must agree on."""

    @pytest.mark.parametrize(
        "token", ["United", "City", "Town", "State", "AFC", "FC", "SC", "II", "III", "U21", "23", ""]
    )
    def test_non_distinctive(self, token):
        assert is_non_distinctive_trailing_word(token) is True

    @pytest.mark.parametrize(
        "token", ["Celtics", "Jayhawks", "Rangers", "Kings", "Madrid", "Stuttgart"]
    )
    def test_distinctive(self, token):
        assert is_non_distinctive_trailing_word(token) is False

    def test_punctuation_is_stripped_before_the_length_test(self):
        assert is_non_distinctive_trailing_word("F.C.") is True

    def test_the_designator_set_is_lowercase_and_deduped(self):
        """A capitalised entry is a DEAD entry: the lookup lowercases first."""
        assert all(token == token.lower() for token in CLUB_TYPE_SUFFIXES)
        assert len(CLUB_TYPE_SUFFIXES) >= 36


class TestContextCarriesTheGridsDecision:
    """Arm 2 — the carrier."""

    @staticmethod
    async def _fake_grid(**kwargs):
        return {
            "teams": [
                {
                    "name": "Leeds United",
                    "team_id": 1,
                    "short_name": "LEE",
                    "logo_url": "https://a.espncdn.com/i/teamlogos/soccer/500/357.png",
                    "record": "2-3-0",
                    "stages": [{"key": "relegation", "probability": 0.075}],
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_short_name_and_logo_survive_the_context(self, monkeypatch):
        monkeypatch.setattr(
            "app.routes.playoffs.get_playoff_grid_cached", self._fake_grid
        )

        ctx = await _compute_league_context("epl", db=object())

        team = ctx.teams["leeds united"]
        assert team.short_name == "LEE"
        assert team.logo_url.endswith("/357.png")
        assert team.team_id == 1

    @pytest.mark.asyncio
    async def test_enriched_event_payload_carries_identity_not_just_probabilities(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "app.routes.playoffs.get_playoff_grid_cached", self._fake_grid
        )

        async def fake_execute(_stmt):
            return SimpleNamespace(scalar=lambda: "soccer_epl")

        event = SimpleNamespace(
            sport_id=7,
            home_team_name="Leeds United",
            away_team_name="Nobody FC",
        )
        enriched = await enrich_event_with_context(
            event, db=SimpleNamespace(execute=fake_execute)
        )

        assert enriched["home_team"]["short_name"] == "LEE"
        assert enriched["home_team"]["logo_url"].endswith("/357.png")
        assert enriched["home_team"]["team_id"] == 1

    def test_a_cache_entry_written_before_these_fields_existed_still_decodes(self):
        """The rollout arm.

        `LeagueContext.from_json` splats the cached dict into the dataclass, so
        a field with no default would turn every warm Redis entry into a
        TypeError at the moment of release.
        """
        legacy = json.dumps(
            {
                "league_slug": "epl",
                "league_name": "Premier League",
                "sport_group": "soccer",
                "columns": [],
                "last_computed": "",
                "teams": {
                    "leeds united": {
                        "team_name": "Leeds United",
                        "team_id": 1,
                        "league_slug": "epl",
                        "conference": None,
                        "record": "2-3-0",
                        "cells": {"relegation": 0.075},
                        "changes_24h": {},
                        "column_labels": {},
                        "sources_available": ["kalshi"],
                    }
                },
            }
        )

        ctx = LeagueContext.from_json(legacy)

        assert ctx.teams["leeds united"].short_name is None
        assert ctx.teams["leeds united"].logo_url is None
        assert ctx.teams["leeds united"].record == "2-3-0"

    def test_a_context_round_trips_through_json_with_the_new_fields(self):
        ctx = LeagueContext(
            league_slug="epl",
            teams={
                "leeds united": TeamLeagueContext(
                    team_name="Leeds United", short_name="LEE", logo_url="x.png"
                )
            },
        )
        restored = LeagueContext.from_json(ctx.to_json())
        assert restored.teams["leeds united"].short_name == "LEE"
        assert restored.teams["leeds united"].logo_url == "x.png"


class TestRouteServesTheCarriedLabel:
    """Arm 3 — the consumer, which is the line the reader actually hit."""

    @staticmethod
    def _route_source():
        import inspect

        from app.routes.events import get_team_progression

        return inspect.getsource(get_team_progression)

    def test_the_route_no_longer_mints_a_last_word_label(self):
        """The defect was one expression; its absence is the claim.

        Asserted on the route's own source rather than on a served payload
        because the arms that would let this line come back — a refactor, a
        merge, a copy into a sibling route — all reintroduce the EXPRESSION,
        and every payload-level test needs a database, a Redis and a warm grid
        to notice.
        """
        source = self._route_source()
        assert "team_name.split()[-1]" not in source
        assert 'team_ctx.get("short_name")' in source

    def test_the_route_no_longer_hardcodes_a_null_identity(self):
        source = self._route_source()
        assert '"team_id": None' not in source
        assert '"logo_url": None' not in source
        assert 'team_ctx.get("team_id")' in source
        assert 'team_ctx.get("logo_url")' in source

    def test_the_fallback_is_the_full_name_and_never_the_last_word(self):
        """The golf arm, and the reason this repair is not a client rule.

        132 of the 530 rows on the served grids are golf PLAYERS with no
        `teams` row, so they miss the lookup and take the fallback. The grid's
        own builder gives them their full name; a last-word fallback here would
        print "McIlroy" where the grid prints "Rory McIlroy", and would do it
        on the one surface where the reader is comparing the two.
        """
        source = self._route_source()
        assert 'team_ctx.get("short_name") or team_name or ""' in source
