"""#7188 — a matchup fragment is registered against the side it NAMES.

`_register_market_team_identities` used to pair `matchup.team_a` with
`event.home_team_id` and `matchup.team_b` with `event.away_team_id`.
`MatchupInfo.team_a` is documented as "first team in market name" — a position
in a string, not a side of the fixture — so that pairing was a coin flip, and
on Kalshi's abbreviated city names it lost every time we measured it:

  * `("kalshi", "baseball_mlb", "New York M") -> 6610 New York Yankees`,
    written 2026-09-12 01:10 during the 09-11/12/13 Subway Series, in which
    the METS were the visitors.
  * `("kalshi", "icehockey_nhl", "New York I") -> 53 New Jersey Devils` and
    `("kalshi", "icehockey_nhl", "New York R") -> 53 New Jersey Devils`,
    written 2026-09-19 04:52:49 and :50 — one second apart, from the two
    games New Jersey HOSTS on 09-20 and 09-21.

The mapping table is a durable cache consulted before any fuzzy matching, so
each wrong row answered every later lookup for that name at score 100. That is
how seven of the Mets' legs — NL East Division Winner, National League
Champion, Pro Baseball Worst Record among them — came to be listed on the
Yankees' team page.

These tests drive `_register_market_team_identities` ITSELF rather than
`resolve_team_side` alone: the whole defect lived in how the caller PAIRED the
resolver's inputs, and a test that only calls the helper cannot see a caller.
"""

import pytest

from app.tasks import prediction_market_matching as pmm


class _Sport:
    def __init__(self, key):
        self.key = key


class _Event:
    def __init__(self, home_id, home_name, away_id, away_name, sport_key):
        self.home_team_id = home_id
        self.home_team_name = home_name
        self.away_team_id = away_id
        self.away_team_name = away_name
        self.sport = _Sport(sport_key)


class _Market:
    def __init__(self, source="kalshi"):
        self.source = source


class _Matchup:
    """The two fragments a market name yields, in the order they appear in it."""

    def __init__(self, team_a, team_b):
        self.team_a = team_a
        self.team_b = team_b


class _EventSession:
    """Answers the one `select(Event)` the function makes."""

    def __init__(self, event):
        self._event = event

    async def execute(self, *_args, **_kwargs):
        event = self._event

        class _Result:
            def scalar_one_or_none(self):
                return event

        return _Result()


async def _register(monkeypatch, event, matchup, source="kalshi"):
    """Drive the real function; return [(team_id, source_name), ...] it wrote."""
    from app.services.team_identity import team_identity_service

    written = []

    async def _capture(_session, team_id, src, sport_key, **kwargs):
        written.append((team_id, kwargs.get("source_name")))

    monkeypatch.setattr(
        team_identity_service, "register_team_identity", _capture,
    )
    await pmm._register_market_team_identities(
        _EventSession(event), 1, matchup, _Market(source),
    )
    return written


# The three fixtures that actually produced the poisoned rows in production,
# with the real ids, and the real orientation (the named club is the VISITOR).
SUBWAY_SERIES = _Event(6610, "New York Yankees", 10737, "New York Mets", "baseball_mlb")
DEVILS_ISLANDERS = _Event(53, "New Jersey Devils", 54, "New York Islanders", "icehockey_nhl")
DEVILS_RANGERS = _Event(53, "New Jersey Devils", 57, "New York Rangers", "icehockey_nhl")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event,fragment,expected_team_id,expected_club",
    [
        (SUBWAY_SERIES, "New York M", 10737, "Mets"),
        (DEVILS_ISLANDERS, "New York I", 54, "Islanders"),
        (DEVILS_RANGERS, "New York R", 57, "Rangers"),
    ],
)
async def test_the_abbreviation_binds_to_the_club_it_names_not_the_home_side(
    monkeypatch, event, fragment, expected_team_id, expected_club
):
    """The exact production rows, with the fragment FIRST in the market name.

    First-in-the-name is what made the old code pair it with the home side.
    Each of these clubs was the visitor, so the old code wrote the opponent.
    """
    written = await _register(monkeypatch, event, _Matchup(fragment, event.home_team_name))

    assert (expected_team_id, fragment) in written, (
        f"'{fragment}' was not registered onto the {expected_club} "
        f"(team {expected_team_id}) — it went to {written!r}. This is the "
        f"#7188 defect: the fragment is first in the market name, so the "
        f"positional pairing hands it the HOME team, which is the opponent."
    )
    assert (event.home_team_id, fragment) not in written, (
        f"'{fragment}' was registered onto the home side "
        f"({event.home_team_name}) — the club it does not name."
    )


@pytest.mark.asyncio
async def test_the_orientation_is_read_not_assumed_when_the_home_side_is_first(
    monkeypatch,
):
    """The control for the test above: same fixture, fragments SWAPPED.

    Without this, a mutant that simply always registered `team_a` onto the AWAY
    side would pass every case above — they all happen to name the visitor
    first. This asserts the function reads the name rather than trading one
    fixed position for another.
    """
    written = await _register(
        monkeypatch, SUBWAY_SERIES, _Matchup("New York Y", "New York M"),
    )

    assert (6610, "New York Y") in written, (
        "'New York Y' must bind to the Yankees when it is FIRST in the name — "
        "the side is read from the name, not from the position"
    )
    assert (10737, "New York M") in written


@pytest.mark.asyncio
async def test_a_fragment_naming_both_clubs_is_dropped_rather_than_guessed(
    monkeypatch,
):
    """"New York" on a Yankees/Mets matchup is the alias that caused #7188.

    A bare city that both clubs answer to is precisely the input that must NOT
    become a cached fact. Dropping it costs a fast path; writing it down picks
    one club's page to be wrong on, permanently.
    """
    written = await _register(
        monkeypatch, SUBWAY_SERIES, _Matchup("New York", "New York Mets"),
    )

    assert all(name != "New York" for _, name in written), (
        f"the ambiguous bare city 'New York' was cached anyway: {written!r}"
    )


@pytest.mark.asyncio
async def test_a_fragment_naming_neither_club_is_dropped(monkeypatch):
    """"Chicago WS" is an abbreviation, not a prefix, so it names neither side.

    The old code wrote it onto whichever side its position picked. There is no
    correct answer available here, and a durable cache is the wrong place to
    record a guess.
    """
    white_sox_at_pirates = _Event(
        10736, "Pittsburgh Pirates", 10734, "Chicago White Sox", "baseball_mlb",
    )
    written = await _register(
        monkeypatch, white_sox_at_pirates, _Matchup("Chicago WS", "Pittsburgh P"),
    )

    assert all(name != "Chicago WS" for _, name in written), (
        f"'Chicago WS' names neither side and must not be cached: {written!r}"
    )


@pytest.mark.asyncio
async def test_both_fragments_claiming_one_side_registers_neither(monkeypatch):
    """A fixture disagreeing with itself is dropped whole.

    Two fragments that both resolve to the away side cannot both be right, and
    the loop would otherwise cache whichever it reached last. This is the state
    the positional pairing was structurally unable to notice.
    """
    written = await _register(
        monkeypatch, SUBWAY_SERIES, _Matchup("New York Mets", "New York Met"),
    )

    assert written == [], (
        f"two fragments both naming the Mets should register nothing, got {written!r}"
    )


@pytest.mark.asyncio
async def test_no_matchup_still_registers_each_event_name_on_its_own_side(
    monkeypatch,
):
    """The fallback path keeps working — it is the case that was always right.

    When no matchup parses, the only names available are the event's own, and
    each must still reach its own side. Routing them through the same resolver
    must not cost us these registrations.
    """
    written = await _register(monkeypatch, SUBWAY_SERIES, None)

    assert (6610, "New York Yankees") in written
    assert (10737, "New York Mets") in written


@pytest.mark.asyncio
async def test_a_missing_team_id_on_the_named_side_registers_nothing_for_it(
    monkeypatch,
):
    """An unlinked side is skipped, never backfilled onto the other club."""
    half_linked = _Event(None, "New York Yankees", 10737, "New York Mets", "baseball_mlb")
    written = await _register(monkeypatch, half_linked, _Matchup("New York Y", "New York M"))

    assert written == [(10737, "New York M")], (
        f"only the Mets side is linked, so only it can be registered: {written!r}"
    )
