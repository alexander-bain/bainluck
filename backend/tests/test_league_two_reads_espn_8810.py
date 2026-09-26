"""#8810 — a League Two match hears from ESPN, and never hears another game's news.

Production 2026-09-26: event 15315470, Crawley Town v Barnet
(`soccer_england_league2`, 11:30Z), was Postponed on ESPN (401881358,
STATUS_POSTPONED) while our page read "No result reported" with a frozen 22%.
`soccer_england_league2` (ESPN `eng.4`) was on no ESPN map, so no pass read the
league: no postponement, no live score, no full time.

Turning the board on has a second half, and it is the one that can hurt a
reader. `names_match` is a recall instrument and League Two's clubs share
suffixes — seven "Town", three "City", two "Rovers", two "United" — so it
says Crawley Town is Swindon Town. A game only pairs when BOTH sides match, but
League Two kicks off together: on 2026-09-01 Bristol Rovers v Colchester United
and Tranmere Rovers v Rotherham United both started 18:45Z, and each
name-matches the other. The candidate pick ties on distance and took whichever
ESPN listed first — for both rows. Six of our 107 League Two rows in the last
60 days sat in such a slot (read from production 2026-09-26).

The rosters below are the real ones: our 24 League Two names from production
and ESPN's 24 `eng.4/teams` entries, both read 2026-09-26.
"""

from datetime import datetime, timezone
from itertools import product
from types import SimpleNamespace

import pytest

from app.tasks.espn_sync import espn_team_matches, espn_team_matches_distinctly
from app.utils.espn_candidate_selection import (
    prefer_distinct_matches,
    select_authorized_espn_candidate,
)
from app.utils.espn_helpers import match_event_to_espn
from app.utils.sport_keys import (
    ESPN_SPORT_MAPPING,
    EXPECTED_GAME_STATE_INDICATORS,
    SPORT_LEAGUE_MAP,
)

L2 = "soccer_england_league2"

#: (our row's name, ESPN displayName, ESPN shortDisplayName) — the same club.
ROSTER = [
    ("Accrington Stanley", "Accrington Stanley", "Accrington"),
    ("Barnet", "Barnet", "Barnet"),
    ("Bristol Rovers", "Bristol Rovers", "Bristol Rovers"),
    ("Cheltenham Town", "Cheltenham Town", "Cheltenham"),
    ("Chesterfield FC", "Chesterfield", "Chesterfield"),
    ("Colchester United", "Colchester United", "Colchester"),
    ("Crawley Town", "Crawley Town", "Crawley"),
    ("Crewe Alexandra", "Crewe Alexandra", "Crewe"),
    ("Exeter City", "Exeter City", "Exeter"),
    ("Fleetwood Town", "Fleetwood Town", "Fleetwood Town"),
    ("Gillingham", "Gillingham", "Gillingham"),
    ("Grimsby Town", "Grimsby Town", "Grimsby"),
    ("Newport County", "Newport County", "Newport"),
    ("Northampton Town", "Northampton Town", "Northampton"),
    ("Oldham Athletic", "Oldham Athletic", "Oldham"),
    ("Port Vale", "Port Vale", "Port Vale"),
    ("Rochdale", "Rochdale", "Rochdale"),
    ("Rotherham United", "Rotherham United", "Rotherham"),
    ("Salford City", "Salford City", "Salford City"),
    ("Shrewsbury Town", "Shrewsbury Town", "Shrewsbury"),
    ("Swindon Town", "Swindon Town", "Swindon"),
    ("Tranmere Rovers", "Tranmere Rovers", "Tranmere"),
    ("Walsall", "Walsall", "Walsall"),
    ("York City", "York City", "York City"),
]


def _espn_team(display, short):
    # ESPN's `location` and `name` are the displayName for every eng.4 club.
    return SimpleNamespace(
        display_name=display, short_name=short, name=display, location=display,
    )


ESPN_TEAMS = {ours: _espn_team(d, s) for ours, d, s in ROSTER}
KICKOFF = datetime(2026, 9, 1, 18, 45, tzinfo=timezone.utc)


def _game(espn_id, home, away, when=KICKOFF):
    return SimpleNamespace(
        espn_id=espn_id, date=when,
        home_team=ESPN_TEAMS[home], away_team=ESPN_TEAMS[away],
    )


def _row(home, away, when=KICKOFF):
    return SimpleNamespace(
        id=1, espn_id=None, commence_time=when,
        home_team_name=home, away_team_name=away,
        home_team_normalized=None, away_team_normalized=None,
        home_team_alt_names=None, away_team_alt_names=None,
    )


BRISTOL = _game("401881001", "Bristol Rovers", "Colchester United")
TRANMERE = _game("401881002", "Tranmere Rovers", "Rotherham United")


class TestLeagueTwoIsOnTheEspnMaps:
    def test_league_path_live_path_and_halves(self):
        assert SPORT_LEAGUE_MAP[L2] == ("soccer", "eng.4")
        assert ESPN_SPORT_MAPPING[L2] == "soccer/eng.4"
        assert EXPECTED_GAME_STATE_INDICATORS[L2] == 2

    def test_eng4_is_no_other_keys_league(self):
        # `league_identity` folds keys that share a SPORT_LEAGUE_MAP value.
        assert [k for k, v in SPORT_LEAGUE_MAP.items() if v == ("soccer", "eng.4")] == [L2]


class TestTheRosterPairsOneToOne:
    def test_the_recall_matcher_does_not(self):
        # The premise: without the veto, a club matches others in its league.
        # If this ever goes 1:1 the narrowing below is moot, not wrong.
        assert espn_team_matches(["Crawley Town"], ESPN_TEAMS["Swindon Town"])
        assert espn_team_matches(["Bristol Rovers"], ESPN_TEAMS["Tranmere Rovers"])

    def test_every_pair_in_both_rosters(self):
        wrong = [
            (ours, other)
            for (ours, _, _), (other, _, _) in product(ROSTER, ROSTER)
            if espn_team_matches_distinctly([ours], ESPN_TEAMS[other]) != (ours == other)
        ]
        assert wrong == []


class TestTheSameSlotPicksItsOwnGame:
    @pytest.mark.parametrize("pool", [[TRANMERE, BRISTOL], [BRISTOL, TRANMERE]])
    def test_bristol_row_gets_bristol_game_in_either_order(self, pool):
        row = _row("Bristol Rovers", "Colchester United")
        matched, _ = match_event_to_espn(row, pool, {}, set(), espn_team_matches)
        assert matched is BRISTOL

    @pytest.mark.parametrize("pool", [[TRANMERE, BRISTOL], [BRISTOL, TRANMERE]])
    def test_tranmere_row_gets_tranmere_game_in_either_order(self, pool):
        row = _row("Tranmere Rovers", "Rotherham United")
        matched, _ = match_event_to_espn(row, pool, {}, set(), espn_team_matches)
        assert matched is TRANMERE

    def test_strawman_without_the_narrowing_takes_the_first_listed(self):
        # The defect, pinned: the same call with no `is_distinct_match`.
        row = _row("Bristol Rovers", "Colchester United")
        matched, _ = select_authorized_espn_candidate(
            [TRANMERE, BRISTOL], row.commence_time,
            is_name_match=lambda ee: (
                espn_team_matches(["Bristol Rovers"], ee.home_team)
                and espn_team_matches(["Colchester United"], ee.away_team)
            ),
        )
        assert matched is TRANMERE


class TestItNarrowsAndNeverRefuses:
    def test_a_lone_rival_hit_is_still_returned(self):
        # Preference, not a matcher: a pool whose only hit is the rival's game
        # behaves exactly as before the change.
        row = _row("Bristol Rovers", "Colchester United")
        matched, _ = match_event_to_espn(row, [TRANMERE], {}, set(), espn_team_matches)
        assert matched is TRANMERE

    def test_nothing_distinct_leaves_the_pool_alone(self):
        pool = [TRANMERE, BRISTOL]
        assert prefer_distinct_matches(pool, lambda ee: False) == pool

    def test_a_single_hit_is_not_consulted(self):
        def boom(_):
            raise AssertionError("a lone hit must not be judged")
        assert prefer_distinct_matches([BRISTOL], boom) == [BRISTOL]

    def test_two_distinct_same_teams_hits_both_survive(self):
        # A doubleheader's two halves are both distinct; distance decides.
        later = _game("401881003", "Bristol Rovers", "Colchester United",
                      when=KICKOFF.replace(hour=22))
        kept = prefer_distinct_matches(
            [later, TRANMERE, BRISTOL],
            lambda ee: espn_team_matches_distinctly(["Bristol Rovers"], ee.home_team),
        )
        assert kept == [later, BRISTOL]

    def test_a_fake_team_with_missing_fields_is_not_distinct(self):
        assert espn_team_matches_distinctly(["Barnet"], SimpleNamespace()) is False


class _Row:
    """A stand-in ORM row: any column not named here reads as NULL."""

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def __getattr__(self, _name):
        return None


class TestTheScheduledPassPicksItsOwnGame:
    """The 60s scheduled pass has its own loop — it took the FIRST same-day hit."""

    @staticmethod
    async def _run(monkeypatch, pool):
        from app.utils import espn_helpers

        class _Sport:
            id = 1
            key = L2

        event = _Row(
            id=15300001, espn_id=None, sport=_Sport(), sport_id=_Sport.id,
            home_team_name="Bristol Rovers", away_team_name="Colchester United",
            home_team_id=1, away_team_id=2, commence_time=KICKOFF,
            commence_time_source="odds_api", status="scheduled",
        )
        espn_pool = [
            _Row(espn_id=g.espn_id, date=g.date, home_team=g.home_team,
                 away_team=g.away_team, broadcasts=[])
            for g in pool
        ]

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):
                return self

            def all(self):
                return self._rows

        calls = {"n": 0}

        class _Session:
            async def execute(self, *_a, **_k):
                calls["n"] += 1
                return _Result([event] if calls["n"] == 1 else [])

        async def _noop(*_a, **_k):
            return None

        monkeypatch.setattr(espn_helpers, "upsert_team", _noop)
        monkeypatch.setattr(espn_helpers, "register_espn_team_identities", _noop)
        await espn_helpers.sync_scheduled_events(_Session(), L2, espn_pool, {})
        return event

    @pytest.mark.parametrize("pool", [[TRANMERE, BRISTOL], [BRISTOL, TRANMERE]])
    async def test_bristol_row_is_stamped_with_bristols_id(self, monkeypatch, pool):
        event = await self._run(monkeypatch, pool)
        assert event.espn_id == BRISTOL.espn_id

    async def test_a_lone_rival_game_is_still_taken(self, monkeypatch):
        # Unchanged behaviour, pinned so the narrowing can never become a veto.
        event = await self._run(monkeypatch, [TRANMERE])
        assert event.espn_id == TRANMERE.espn_id


def test_every_espn_id_rail_on_the_shared_primitive_passes_the_preference():
    """The two backfill rails select through the same primitive; a rail that
    forgets the kwarg silently keeps first-listed-wins."""
    import inspect

    from app.tasks import espn_sync
    from app.utils import espn_helpers

    for fn in (
        espn_sync._backfill_espn_ids,
        espn_helpers.backfill_missing_scores,
        espn_helpers.match_event_to_espn,
    ):
        assert "is_distinct_match=" in inspect.getsource(fn), fn.__name__
