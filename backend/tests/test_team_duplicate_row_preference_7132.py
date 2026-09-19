"""Guard tests: two rows for one club must not resolve by arrival order (#7132).

THE READER-VISIBLE DEFECT. `/events/15314262` — Blue Jackets vs Penguins, five
days before puck drop — served

    Columbus   38-24-11, 92 pts
    Pittsburgh  0-0, 0 pts

a finished 83-game season beside a team that had played none, in a league whose
season had not started. Both numbers came from the same builder. The Penguins
have one team row; Columbus has two, and the one the name lookup happened to
resolve to carried a board frozen on 2026-08-29 that never rolled over.

THE MECHANISM. `_enriched_teams_stmt()` is UNORDERED, and where two rows of one
league claimed a name key `_dedupe_team_name_lookup` kept whichever arrived
first — so the answer was Postgres heap order. Measured over production's 1,630
enriched rows on 2026-09-19, 176 of 1,070 name keys resolved to a different row
in ascending than in descending id order.

WHY EVERY ASSERTION HERE RUNS IN BOTH ARRIVAL ORDERS. A one-order test of an
order-dependent function passes against the bug roughly half the time, and
which half depends on the fixture's id order — the trap these tests exist to
close. One order proves nothing about a tiebreak.

The fixtures are the production shapes, not one specimen: Columbus (canonical
long name holds the live board) and Toronto (the SHORT duplicate holds it) are
deliberately opposite, because a rule that prefers the row's own name over
another row's alias, or the lower id, is right for Columbus and wrong for
Toronto. On 2026-09-19 three of six NHL clubs with a duplicate row were each
shape.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.routes.events import _dedupe_team_name_lookup
from app.utils.standings_shape import record_text

NOW = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc)
YESTERDAY = NOW - timedelta(days=1)
THREE_WEEKS_AGO = NOW - timedelta(days=21)

#: The board a club's row carries once the new season has rolled it over. This
#: is what makes `record_text` withhold `current_record` (#5520 / #5377).
ROLLED_OVER = {"wins": 0, "losses": 0, "points": 0}
#: Last season's completed board, still sitting on the row nobody rewrote.
LAST_SEASON = {"wins": 40, "losses": 30, "points": 92}


@dataclass
class _FakeTeam:
    id: int
    name: str
    sport_id: int
    sport_key: str | None = None
    alternate_names: list = field(default_factory=list)
    current_record: str | None = None
    standings_data: dict | None = None
    standings_updated_at: datetime | None = None
    primary_color: str | None = "#002d62"
    logo_url_small: str | None = "https://cdn.example/cbj.png"


def _both_orders(rows, key):
    """The resolved row id for `key` with `rows` fed in each direction."""
    forward = _dedupe_team_name_lookup(list(rows)).get(key)
    backward = _dedupe_team_name_lookup(list(reversed(rows))).get(key)
    return (forward.id if forward else None, backward.id if backward else None)


def _columbus_pair():
    """Production's 2026-09-19 Columbus rows. The LONG canonical name (572)
    holds the rolled-over board; the short duplicate (6182) is the frozen one."""
    live = _FakeTeam(
        572, "Columbus Blue Jackets", sport_id=4, sport_key="icehockey_nhl",
        alternate_names=["Columbus", "Blue Jackets"],
        current_record="38-25-12", standings_data=dict(ROLLED_OVER),
        standings_updated_at=NOW,
    )
    frozen = _FakeTeam(
        6182, "Columbus", sport_id=4, sport_key="icehockey_nhl",
        alternate_names=["Columbus Blue Jackets", "Blue Jackets"],
        current_record="38-24-11", standings_data=dict(LAST_SEASON),
        standings_updated_at=THREE_WEEKS_AGO,
    )
    return live, frozen


def _toronto_pair():
    """The OPPOSITE shape, also on production: the SHORT duplicate (12715)
    holds the live board and the long canonical row (115) is the frozen one."""
    frozen = _FakeTeam(
        115, "Toronto Maple Leafs", sport_id=4, sport_key="icehockey_nhl",
        alternate_names=["Maple Leafs"],
        current_record="0-0-0", standings_data={"wins": 32, "losses": 36, "points": 78},
        standings_updated_at=THREE_WEEKS_AGO,
    )
    live = _FakeTeam(
        12715, "Toronto", sport_id=4, sport_key="icehockey_nhl",
        alternate_names=["Maple Leafs", "Toronto Maple Leafs"],
        current_record="32-35-14", standings_data=dict(ROLLED_OVER),
        standings_updated_at=NOW,
    )
    return live, frozen


def test_one_clubs_two_rows_resolve_to_the_same_row_in_both_arrival_orders():
    """The coin flip itself: 176 name keys answered two ways on one database."""
    live, frozen = _columbus_pair()
    forward, backward = _both_orders([live, frozen], "Columbus Blue Jackets")
    assert forward == backward, (
        "the same name key resolved to two different rows depending on which "
        "one Postgres handed us first — that is #7132"
    )


def test_the_hero_stops_printing_a_finished_season_before_a_game_is_played():
    """The ship, stated as the reader sees it, in both arrival orders.

    Asserted through `record_text` — the function the hero actually prints —
    rather than on the row id, so this fails if the resolution is fixed and the
    rendered string is still last season's.
    """
    live, frozen = _columbus_pair()
    for rows in ([live, frozen], [frozen, live]):
        team = _dedupe_team_name_lookup(rows)["Columbus Blue Jackets"]
        shown = record_text(team.current_record, team.standings_data)
        assert shown == "0-0", (
            f"hero would print {shown!r} for a club that has played no games; "
            "38-24-11 is last season, and it sat beside Pittsburgh's 0-0"
        )


def test_the_row_with_the_live_board_wins_even_when_it_is_the_SHORT_name():
    """Toronto's shape. Kills 'prefer the row's own name over another's alias'
    and 'prefer the lower id' — both pick 115, whose board is last season's."""
    live, frozen = _toronto_pair()
    forward, backward = _both_orders([live, frozen], "Toronto Maple Leafs")
    assert forward == backward == live.id, (
        "the live board is on the short-name duplicate here; a canonical-name "
        "or lowest-id rule picks the frozen row"
    )


def test_the_row_with_the_live_board_wins_when_it_is_the_LONG_name():
    """Columbus's shape — the same rule, the opposite row. Asserted alongside
    the Toronto case on purpose: together they admit no name- or id-shaped
    rule, only the board's write stamp."""
    live, frozen = _columbus_pair()
    forward, backward = _both_orders([live, frozen], "Columbus Blue Jackets")
    assert forward == backward == live.id


def test_an_unstamped_row_never_outranks_a_stamped_one():
    """`standings_updated_at` is NULL on most rows. A row nobody has written is
    not evidence of freshness, whichever direction it arrives from."""
    stamped = _FakeTeam(
        10, "Real Club", sport_id=4, sport_key="icehockey_nhl",
        standings_data=dict(ROLLED_OVER), standings_updated_at=YESTERDAY,
    )
    unstamped = _FakeTeam(
        9999, "Real Club", sport_id=4, sport_key="icehockey_nhl",
        standings_data=dict(LAST_SEASON), standings_updated_at=None,
    )
    assert _both_orders([stamped, unstamped], "Real Club") == (10, 10)


def test_an_unreadable_stamp_is_not_treated_as_fresh():
    """A stamp that will not answer `.timestamp()` is unreadable, not recent —
    it must not beat a row carrying a real one (gotcha #53)."""
    good = _FakeTeam(
        10, "Real Club", sport_id=4, sport_key="icehockey_nhl",
        standings_data=dict(ROLLED_OVER), standings_updated_at=YESTERDAY,
    )
    junk = _FakeTeam(
        9999, "Real Club", sport_id=4, sport_key="icehockey_nhl",
        standings_data=dict(LAST_SEASON), standings_updated_at="2026-09-19",
    )
    assert _both_orders([good, junk], "Real Club") == (10, 10)


def test_the_season_variant_rule_still_beats_a_fresher_variant_board():
    """#4945 must dominate the new term. A `baseball_mlb_preseason` row written
    more recently than its parent still loses: preferring it is what left every
    MLB card with no standings."""
    parent = _FakeTeam(
        100, "Boston Red Sox", sport_id=53232, sport_key="baseball_mlb",
        current_record="92-60", standings_data={"wins": 92, "losses": 60},
        standings_updated_at=THREE_WEEKS_AGO,
    )
    variant = _FakeTeam(
        101, "Boston Red Sox", sport_id=33178, sport_key="baseball_mlb_preseason",
        standings_data=None, standings_updated_at=NOW,
    )
    assert _both_orders([parent, variant], "Boston Red Sox") == (100, 100)


def test_a_cross_league_mascot_collision_is_still_dropped():
    """The new preference runs only inside one league. Queue #238's guard —
    never a wrong crest — is untouched, in both arrival orders."""
    nfl = _FakeTeam(
        1, "Carolina Panthers", sport_id=1, sport_key="americanfootball_nfl",
        alternate_names=["Panthers"], logo_url_small="https://cdn.example/car.png",
        standings_updated_at=NOW,
    )
    nhl = _FakeTeam(
        2, "Florida Panthers", sport_id=4, sport_key="icehockey_nhl",
        alternate_names=["Panthers"], logo_url_small="https://cdn.example/fla.png",
        standings_updated_at=THREE_WEEKS_AGO,
    )
    assert _both_orders([nfl, nhl], "Panthers") == (None, None)
    assert _both_orders([nfl, nhl], "Carolina Panthers") == (1, 1)
    assert _both_orders([nfl, nhl], "Florida Panthers") == (2, 2)


def test_a_club_with_one_row_is_untouched():
    """93.6% of the 420 sides measured in the -3d/+14d window had no duplicate.
    The Penguins' half of the specimen page must resolve exactly as before."""
    pens = _FakeTeam(
        60, "Pittsburgh Penguins", sport_id=4, sport_key="icehockey_nhl",
        alternate_names=["Penguins"], current_record="41-25-16",
        standings_data=dict(ROLLED_OVER), standings_updated_at=NOW,
    )
    lookup = _dedupe_team_name_lookup([pens])
    assert lookup["Pittsburgh Penguins"].id == 60
    assert record_text(pens.current_record, pens.standings_data) == "0-0"
