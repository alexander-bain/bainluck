"""#3673 — the tournament's end date is the group's, not one venue's contract.

WHAT A READER SAW. `bainluck.com/event/tennis/us-open-men-s-singles-winner`, at
390px, on Sunday 2026-09-06 with US Open matches live on court:

    TENNIS   [ UPCOMING ]   [ MAJOR ]
    US Open Men's Singles Winner
    Sep 27  ·  2056 markets tracked

The men's final was Sep 13. `/hub/tennis` printed "Ends Sun, Sep 13" for the
same tournament in the same session, one click away.

THE MEASUREMENT BEHIND THE FIXTURE (production `futures_markets`, same day):

    34277822  kalshi      US Open Men's Singles Winner        2026-09-28 02:00Z  tier 1
    114159    polymarket  2026 Men's US Open Winner (Tennis)  2026-09-13 00:00Z  tier 1

Kalshi's value is the contract's expiration backstop, not the tournament's end —
the same field-semantics problem as #2592 one level up, at the winner field.

ONE ROOT CAUSE, TWO VISIBLE LIES, and that is the part worth keeping. The date
is read by `tennis_status` as well as by the header, and `proximity_live` calls
a tournament live within **21 days** of the date it is handed. On the Saturday
of the second week the backstop is 22 days out, so the page took the single
fall-through path that function has and announced an in-progress Grand Slam as
UPCOMING. Fixing the date fixes the phase; there was never a second bug.

These tests drive the REAL adapter helpers and the REAL hub lister — not copies
of their logic. The claim under test is that the two surfaces agree, so both of
them have to be the real ones (the cycle-64 lesson: a test that re-implements
the code under test certifies two things that can be wrong together).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.utils.event_tennis import (
    list_tennis_tournament_concepts,
    pick_richest_winner_field,
    select_winner_field,
    tennis_status,
    tournament_end_date,
    winner_field_candidates,
)

SLUG = "us-open-men-s-singles-winner"

#: Saturday of the second week — the moment the page was shot.
NOW = datetime(2026, 9, 6, 20, 35, tzinfo=timezone.utc)
#: The day of the men's final, as Polymarket states it.
FINAL = datetime(2026, 9, 13, 0, 0, tzinfo=timezone.utc)
#: Kalshi's contract expiration, fifteen days after the trophy.
BACKSTOP = datetime(2026, 9, 28, 2, 0, tzinfo=timezone.utc)


def _market(name, mid, n_outcomes, resolution_date, status="open", volume=0.0):
    return SimpleNamespace(
        name=name,
        id=mid,
        volume_24h=volume,
        status=status,
        resolution_date=resolution_date,
        outcomes=[SimpleNamespace(name=f"Player {i}") for i in range(n_outcomes)],
    )


def _count(m):
    return len(m.outcomes or [])


def _us_open_group(kalshi_date=BACKSTOP, poly_date=FINAL, status="open"):
    """The two production rows: the RICHER draw carries the WORSE date.

    That ordering is the whole trap. Kalshi's is the fullest field, so it wins
    the identity tie-break (L2-65 alias convergence, working as designed) — and
    reading the date off the winner therefore reads the backstop, every time,
    on exactly the tournament that matters most.
    """
    return [
        _market("US Open Men's Singles Winner", 34277822, 41, kalshi_date, status),
        _market(
            "2026 Men's US Open Winner (Tennis)", 114159, 24, poly_date, status
        ),
    ]


class TestTheDateIsTheGroups:
    def test_the_earliest_date_any_source_states_wins(self):
        assert tournament_end_date(_us_open_group()) == FINAL

    def test_order_does_not_matter(self):
        assert tournament_end_date(list(reversed(_us_open_group()))) == FINAL

    def test_a_group_with_no_date_at_all_invents_none(self):
        group = _us_open_group(kalshi_date=None, poly_date=None)
        assert tournament_end_date(group) is None

    def test_one_source_knowing_is_enough(self):
        """The old rule's good half: a winner with no date reads its sibling's."""
        group = _us_open_group(kalshi_date=None)
        assert tournament_end_date(group) == FINAL

    def test_a_lone_source_is_still_read(self):
        assert tournament_end_date([_us_open_group()[0]]) == BACKSTOP


class TestIdentityIsUntouched:
    """The date moved; which market IS the tournament did not."""

    def test_the_richest_draw_still_wins_the_tie_break(self):
        group = _us_open_group()
        assert select_winner_field(group, SLUG, _count).id == 34277822

    def test_the_split_helpers_compose_back_into_the_original(self):
        group = _us_open_group()
        candidates = winner_field_candidates(group, SLUG, _count)
        assert len(candidates) == 2
        assert (
            pick_richest_winner_field(candidates, SLUG, _count).id
            == select_winner_field(group, SLUG, _count).id
        )

    def test_a_slug_that_names_nothing_still_resolves_to_nothing(self):
        assert winner_field_candidates(_us_open_group(), "wimbledon", _count) == []
        assert select_winner_field(_us_open_group(), "wimbledon", _count) is None


class TestThePhaseFollowsTheDate:
    """The mechanism, stated as the two calls the adapter makes.

    `build_event` passes the group's date where it used to pass the winner's, so
    these two assertions ARE the before and after of the rendered chip.
    """

    def test_the_backstop_is_what_said_UPCOMING_mid_tournament(self):
        assert tennis_status("open", BACKSTOP, NOW, proximity_live=True) == "upcoming"

    def test_the_tournaments_own_date_says_LIVE(self):
        assert tennis_status("open", FINAL, NOW, proximity_live=True) == "live"

    def test_and_the_group_hands_it_the_second_one(self):
        end_at = tournament_end_date(_us_open_group())
        assert tennis_status("open", end_at, NOW, proximity_live=True) == "live"

    # Both directions (gotcha #43): the repair must not make everything live.
    def test_a_genuinely_forthcoming_tournament_still_says_upcoming(self):
        far = NOW + timedelta(days=40)
        group = _us_open_group(kalshi_date=far + timedelta(days=15), poly_date=far)
        end_at = tournament_end_date(group)
        assert end_at == far
        assert tennis_status("open", end_at, NOW, proximity_live=True) == "upcoming"

    def test_a_genuinely_finished_tournament_still_says_settled(self):
        done = NOW - timedelta(days=3)
        group = _us_open_group(kalshi_date=NOW - timedelta(days=1), poly_date=done)
        assert tennis_status("open", tournament_end_date(group), NOW, proximity_live=True) == "settled"

    def test_an_assigned_settled_status_still_wins_outright(self):
        """A resolved market is settled whatever the dates say."""
        group = _us_open_group(status="resolved")
        assert (
            tennis_status("resolved", tournament_end_date(group), NOW, proximity_live=True)
            == "settled"
        )


class _Result:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDB:
    def __init__(self, items):
        self._items = items

    async def execute(self, *a, **k):
        return _Result(self._items)


class TestTheRailAndThePageCannotDisagree:
    """The filed bug was a DISAGREEMENT, so the guard is an equality.

    `/hub/tennis` and the concept page now read one function over their own
    group. Pinning only the page's date would leave the two free to drift apart
    again the next time either grouping is touched, which is exactly how this
    arrived: both call sites had a date rule, and they were different rules.
    """

    async def _rail_card(self):
        db = _FakeDB(_us_open_group())
        concepts = await list_tennis_tournament_concepts(db, limit=50)
        assert concepts, "the rail is empty — the assertions below would be vacuous"
        return concepts[0]

    async def test_the_rail_prints_the_day_of_the_final(self):
        card = await self._rail_card()
        assert card["end_date"] == FINAL.isoformat()

    async def test_the_rail_and_the_adapter_read_the_same_value(self):
        card = await self._rail_card()
        page = tournament_end_date(
            winner_field_candidates(_us_open_group(), SLUG, _count)
        )
        assert card["end_date"] == page.isoformat()

    async def test_the_rail_never_prints_the_backstop(self):
        card = await self._rail_card()
        assert card["end_date"] != BACKSTOP.isoformat()
