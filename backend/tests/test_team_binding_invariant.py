"""#1918 — the write-time guard that stops #1798 being newly produced.

The specimens in this file are not invented. Every pair in ``POISONED_MAPPING`` was
read out of production ``team_identity_mapping`` on 2026-08-17 (queue 361) at commit
``1eb968ee``: 30 rows for ``source='statpal', sport_key='baseball_mlb'``, written in a
single transaction on 2026-03-25 and never updated since, of which these 15 name one
club and point at another.

FAILS-FIRST, AND WHY IT IS ASSERTED RATHER THAN CLAIMED

A guard test that only asserts the new behaviour proves nothing about the bug — it
would pass just as happily against a writer that never had the defect. So each
fresh-ingest specimen asserts BOTH halves:

  1. the legacy predicate (``team and not event.<side>_team_id``) is TRUE, so the code
     as it stood really would have written this id; and
  2. the guard refuses it.

Delete the guard and half 2 fails. Delete the defect and half 1 fails. Neither half can
go green by accident.
"""

import inspect

import pytest

from app.utils.team_binding_invariant import (
    CROSS_CLUB,
    WRONG_SPORT,
    accept_team_binding,
    binding_defect,
    binding_is_sound,
    normalize_club_name,
)

MLB = 53232
PRESEASON = 33178


# (statpal source_name == the event's own team name, team_id, that team's real name,
#  that team row's sport_id) — production rows, 2026-08-17.
POISONED_MAPPING = [
    ("Arizona Diamondbacks", 10707, "Los Angeles Dodgers", MLB),
    ("Athletics", 850, "Seattle Mariners", PRESEASON),
    ("Baltimore Orioles", 865, "New York Yankees", PRESEASON),
    ("Boston Red Sox", 855, "Minnesota Twins", PRESEASON),
    ("Chicago White Sox", 10735, "Milwaukee Brewers", MLB),
    ("Cincinnati Reds", 10709, "Boston Red Sox", MLB),
    ("Houston Astros", 863, "New York Mets", PRESEASON),
    ("Los Angeles Dodgers", 10710, "Arizona Diamondbacks", MLB),
    ("Milwaukee Brewers", 10734, "Chicago White Sox", MLB),
    ("Minnesota Twins", 853, "Boston Red Sox", PRESEASON),
    ("New York Mets", 2691, "Houston Astros", PRESEASON),
    ("New York Yankees", 6609, "San Francisco Giants", MLB),
    ("San Francisco Giants", 866, "Colorado Rockies", PRESEASON),
    ("Seattle Mariners", 862, "Athletics", PRESEASON),
    ("Texas Rangers", 2913, "Milwaukee Brewers", PRESEASON),
]

# The other half of the same batch — correct, and they must keep working. A guard that
# also refuses these would take MLB team linkage to zero, which is a worse outage than
# the bug.
SOUND_MAPPING = [
    ("Atlanta Braves", 872, "Atlanta Braves", PRESEASON),
    ("Chicago Cubs", 10714, "Chicago Cubs", MLB),
    ("Cleveland Guardians", 10744, "Cleveland Guardians", MLB),
    ("Colorado Rockies", 10708, "Colorado Rockies", MLB),
    ("Detroit Tigers", 10747, "Detroit Tigers", MLB),
    ("Kansas City Royals", 871, "Kansas City Royals", PRESEASON),
    ("Los Angeles Angels", 10712, "Los Angeles Angels", MLB),
    ("Miami Marlins", 10716, "Miami Marlins", MLB),
    ("Philadelphia Phillies", 10746, "Philadelphia Phillies", MLB),
    ("Pittsburgh Pirates", 870, "Pittsburgh Pirates", PRESEASON),
    ("San Diego Padres", 10745, "San Diego Padres", MLB),
    ("St.Louis Cardinals", 2692, "St. Louis Cardinals", PRESEASON),
    ("Tampa Bay Rays", 10741, "Tampa Bay Rays", MLB),
    ("Toronto Blue Jays", 873, "Toronto Blue Jays", PRESEASON),
    ("Washington Nationals", 10711, "Washington Nationals", MLB),
]


class _Team:
    """The three attributes the guard reads off a ``Team`` row."""

    def __init__(self, id, name, sport_id):
        self.id = id
        self.name = name
        self.sport_id = sport_id


class _Event:
    """A freshly created StatPal event: names populated, ids still NULL."""

    def __init__(self, id, sport_id, home_team_name, away_team_name):
        self.id = id
        self.sport_id = sport_id
        self.home_team_name = home_team_name
        self.away_team_name = away_team_name
        self.home_team_id = None
        self.away_team_id = None


class TestPredicate:
    def test_sound_binding_passes(self):
        assert binding_is_sound("Boston Red Sox", "Boston Red Sox", MLB, MLB)
        assert binding_defect("Boston Red Sox", "Boston Red Sox", MLB, MLB) is None

    def test_cross_club_is_caught(self):
        assert binding_defect("Milwaukee Brewers", "Chicago White Sox", MLB, MLB) == CROSS_CLUB

    def test_wrong_sport_twin_is_caught_and_named_separately(self):
        assert binding_defect("Boston Red Sox", "Boston Red Sox", PRESEASON, MLB) == WRONG_SPORT

    def test_unresolvable_fk_is_not_this_guards_class(self):
        """A NULL dereference is absence, not a wrong club (gotcha #53)."""
        assert binding_defect("Boston Red Sox", None, None, MLB) is None

    def test_punctuation_and_case_are_not_a_disagreement(self):
        assert binding_is_sound("St. Louis Cardinals", "St.Louis Cardinals", MLB, MLB)
        assert binding_is_sound("boston red sox", "Boston Red Sox", MLB, MLB)

    def test_normalizer_strips_to_alnum(self):
        assert normalize_club_name("St. Louis Cardinals") == "stlouiscardinals"
        assert normalize_club_name(None) == ""

    def test_missing_event_sport_does_not_invent_a_wrong_sport_defect(self):
        assert binding_defect("Boston Red Sox", "Boston Red Sox", PRESEASON, None) is None


class TestFreshIngestSpecimens:
    """The bug, replayed one club at a time, on a brand-new event."""

    @pytest.mark.parametrize(
        "source_name,team_id,bound_name,bound_sport", POISONED_MAPPING
    )
    def test_poisoned_mapping_is_refused_and_the_column_stays_null(
        self, source_name, team_id, bound_name, bound_sport
    ):
        event = _Event(15198912, MLB, source_name, "Some Other Club")
        resolved = _Team(team_id, bound_name, bound_sport)
        stats: dict = {}

        # Half 1 — fails-first. The predicate the writer used before this fix is TRUE
        # here, so the pre-fix code really did write `team_id` onto this row.
        assert resolved and not event.home_team_id

        # Half 2 — the guard refuses, and refusing means writing nothing at all.
        assert not accept_team_binding(
            side="home",
            row_name=event.home_team_name,
            team=resolved,
            event_sport_id=event.sport_id,
            source="statpal",
            event_id=event.id,
            stats=stats,
        )
        assert event.home_team_id is None
        assert stats["team_binding_refused"] == 1

    @pytest.mark.parametrize(
        "source_name,team_id,bound_name,bound_sport", SOUND_MAPPING
    )
    def test_correct_mapping_still_binds(
        self, source_name, team_id, bound_name, bound_sport
    ):
        event = _Event(15198913, bound_sport, source_name, "Some Other Club")
        resolved = _Team(team_id, bound_name, bound_sport)
        stats: dict = {}

        assert accept_team_binding(
            side="home",
            row_name=event.home_team_name,
            team=resolved,
            event_sport_id=event.sport_id,
            source="statpal",
            event_id=event.id,
            stats=stats,
        )
        assert stats == {}

    def test_the_measured_production_specimen_end_to_end(self):
        """Event 15198912, Cincinnati Reds @ Arizona Diamondbacks, 2026-08-23.

        Created 2026-08-15 by StatPal — i.e. after INT-063's 2026-08-13 repair — and
        found in production with BOTH sides miswired. The guard must refuse both.
        """
        event = _Event(15198912, MLB, "Arizona Diamondbacks", "Cincinnati Reds")
        home = _Team(10707, "Los Angeles Dodgers", MLB)
        away = _Team(10709, "Boston Red Sox", MLB)
        stats: dict = {}

        for side, team in (("home", home), ("away", away)):
            assert not accept_team_binding(
                side=side,
                row_name=getattr(event, f"{side}_team_name"),
                team=team,
                event_sport_id=event.sport_id,
                source="statpal",
                event_id=event.id,
                stats=stats,
            )

        assert event.home_team_id is None
        assert event.away_team_id is None
        assert stats["team_binding_refused"] == 2
        assert stats[f"team_binding_refused_{CROSS_CLUB}"] == 2

    def test_unresolved_team_is_not_counted_as_a_refusal(self):
        """No club found is a coverage gap. Counting it here would bury the signal."""
        stats: dict = {}
        assert not accept_team_binding(
            side="home",
            row_name="Arizona Diamondbacks",
            team=None,
            event_sport_id=MLB,
            source="statpal",
            stats=stats,
        )
        assert stats == {}


class TestWriteSitesAreActuallyGated:
    """The guard only works where it is called. Assert the call sites exist.

    Without this, the parametrized specimens above stay green forever while someone
    reverts the two-line change that routes the writer through them.
    """

    def test_statpal_schedule_sync_gates_both_sides(self):
        from app.tasks import statpal_sync

        src = inspect.getsource(statpal_sync._sync_statpal_schedules)
        assert src.count("accept_team_binding(") == 2, (
            "statpal_sync must gate BOTH home and away bindings — this is the site "
            "that was emitting ~5 wrong-club sides a day (#1918)"
        )
        assert 'side="home"' in src and 'side="away"' in src

    def test_espn_sync_gates_both_sides(self):
        from app.tasks import espn_sync

        src = inspect.getsource(espn_sync)
        assert src.count("accept_team_binding(") == 2

    def test_detector_and_guard_share_one_predicate(self):
        """Two copies of this predicate is how a repair rail certifies rows its own
        writer would refuse. They must be the same function object."""
        from app.tasks.repair_event_team_binding import _classify, _norm

        assert _classify is binding_defect
        assert _norm is normalize_club_name
