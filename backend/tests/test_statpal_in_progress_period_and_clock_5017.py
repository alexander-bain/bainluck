"""#5017 — StatPal's in-progress labels reach `event.period`, with the clock beside them.

WHAT BROKE
==========
`_normalize_status` mapped the ABBREVIATIONS (`q2`, `ht`, `2nd`) while StatPal's
live boards serve FULL WORDS (`'2nd Quarter'`, `'Halftime'`, `'Top 8th'`). Every
long form fell through the passthrough, so `status != "live"`, so
`_parse_single_fixture` set `raw_status=None`, so the livescores writer — which
writes `event.period` only from `raw_status` — never advanced the period. After
#4954 flips football to StatPal, the score would advance and the quarter freeze.

WHY THE OLD TEST DID NOT CATCH IT
=================================
`TestNormalizeStatus::test_live_variants` asserts `_normalize_status("Q1") ==
"live"` — it enumerates the MAP'S OWN TOKENS, so it can only ever confirm that
the map contains what the map contains. It can never see the string the venue
actually sends. The predicate here is the inverse and is the one that catches
the whole class at once:

    _normalize_status(raw) in CLOSED_VOCAB

over inputs RECORDED FROM THE WIRE (standing notice 26 applied to a unit test).

WHY PATTERNS AND NOT A LONGER TUPLE
===================================
The families are open. Six strings were observed only because a game happened to
be in those states while someone was looking; `'1st Quarter'`, `'Overtime'` and
`'Middle 8th'` are the same grammar and were never observed. Enumerating the
observed six would repeat the original mistake one size larger, so the fix
matches the GRAMMAR and this file tests unobserved members of each family.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.services.statpal_api import _normalize_status


# sqlite cannot render the postgres column types on `events`; the rail only
# needs somewhere to put them. Same shim as #3094's harness.
@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"

#: Our whole status vocabulary. Anything else is a fall-through by definition.
CLOSED_VOCAB = {
    "scheduled",
    "live",
    "finished",
    "postponed",
    "cancelled",
    "suspended",
}

#: Raw `status` strings RECORDED FROM StatPal's live boards, with provenance.
#: Every one of these was read off the wire, not copied out of our own map.
#:
#:   NFL, `livescores`, 2026-09-11 01:33Z–02:42Z, SF@LAR (contestid 280446),
#:   across authority/117 (`'2nd Quarter'`, `'Halftime'`) and authority/120
#:   (`'3rd Quarter'`, `'4th Quarter'`).
#:   MLB, `livescores`, 2026-09-11 01:5xZ, authority/118.
OBSERVED_IN_PROGRESS = [
    ("nfl", "2nd Quarter"),
    ("nfl", "3rd Quarter"),
    ("nfl", "4th Quarter"),
    ("nfl", "Halftime"),
    ("mlb", "Top 8th"),
    ("mlb", "Bottom 8th"),
]

#: Same grammar, NEVER observed — these are what make this a family test rather
#: than a lookup test. A fix that enumerated the six above leaves every one of
#: these broken, and a real game will serve them.
UNOBSERVED_SAME_FAMILY = [
    ("nfl", "1st Quarter"),
    ("nfl", "Overtime"),
    ("mlb", "Middle 3rd"),
    ("mlb", "End 9th"),
    ("nhl", "2nd Period"),
]

#: Terminal / pre-game strings observed on the same boards. These already worked
#: and must KEEP working — the fix must not widen "live" over them.
OBSERVED_NON_LIVE = [
    ("Final", "finished"),
    ("Finished", "finished"),
    ("Not Started", "scheduled"),
]


# ---------------------------------------------------------------------------
# 1. The vocabulary, by the closed-vocab predicate, over wire inputs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sport,raw", OBSERVED_IN_PROGRESS)
def test_observed_in_progress_labels_do_not_fall_through(sport, raw):
    """The exact strings the venue served must land inside our vocabulary."""
    assert _normalize_status(raw) in CLOSED_VOCAB, (
        f"{sport} served {raw!r} and it fell through to the passthrough"
    )


@pytest.mark.parametrize("sport,raw", OBSERVED_IN_PROGRESS)
def test_observed_in_progress_labels_are_live_specifically(sport, raw):
    """Not merely 'in the vocabulary' — an in-progress game is `live`.

    `raw_status` (and therefore `event.period`) is populated ONLY when the
    normalized status is exactly `live`, so landing on any other member of the
    vocabulary would still leave the period frozen.
    """
    assert _normalize_status(raw) == "live"


@pytest.mark.parametrize("sport,raw", UNOBSERVED_SAME_FAMILY)
def test_unobserved_members_of_the_same_family_also_map(sport, raw):
    """The open-set half: never seen on the wire, same grammar, must still map."""
    assert _normalize_status(raw) == "live"


@pytest.mark.parametrize("raw,expected", OBSERVED_NON_LIVE)
def test_terminal_and_pregame_labels_are_unchanged(raw, expected):
    """The fix must not swallow the states that already worked."""
    assert _normalize_status(raw) == expected


def test_the_pattern_does_not_make_everything_live():
    """Negative control.

    Without this, a fix that returned `"live"` unconditionally would pass every
    assertion above. These are deliberately near-misses of the two patterns.
    """
    for raw in (
        "quarter",          # noun with no ordinal
        "8th",              # bare ordinal is the ABBREVIATION family, not ours
        "top",              # qualifier with no ordinal
        "1st Down",         # ordinal + a noun that is not a period
        "Rain Delay",
        "Postponed",
    ):
        assert _normalize_status(raw) != "live" or raw == "8th", (
            f"{raw!r} should not have been widened to live by the new patterns"
        )
    # `'8th'` is pre-existing behaviour from the abbreviation tuple; pin it so a
    # future edit cannot quietly drop it while this file looks green.
    assert _normalize_status("8th") == "live"


# ---------------------------------------------------------------------------
# 2. The parse: the ticking clock stops being discarded
# ---------------------------------------------------------------------------


def _parse(item: dict):
    from app.services.statpal_api import StatPalAPIService

    return StatPalAPIService()._parse_single_fixture(item)


def _live_item(**over):
    item = {
        "id": "280446",
        "contestid": "280446",
        "status": "3rd Quarter",
        "timer": "7:16",
        "home": {"name": "Los Angeles Rams", "id": "6616", "totalscore": "7"},
        "away": {"name": "San Francisco 49ers", "id": "3206", "totalscore": "17"},
    }
    item.update(over)
    return item


def test_live_fixture_carries_the_game_clock():
    """`timer` reaches the dataclass. It never did before — hence the freeze."""
    fx = _parse(_live_item())
    assert fx is not None
    assert fx.game_clock == "7:16"
    assert fx.raw_status == "3rd Quarter"


def test_empty_timer_becomes_none_not_empty_string():
    """Football sends `''` where the clock does not apply.

    Storing `''` would be counted as a populated clock by the coverage query in
    `admin_providers.py` (`Event.game_clock.isnot(None)`), so the monitor would
    report full clock coverage for rows that display nothing.
    """
    fx = _parse(_live_item(timer=""))
    assert fx is not None
    assert fx.game_clock is None


def test_absent_timer_becomes_none():
    """Baseball omits the key entirely rather than sending an empty string."""
    item = _live_item()
    del item["timer"]
    fx = _parse(item)
    assert fx is not None
    assert fx.game_clock is None


def test_non_live_fixture_carries_no_clock():
    """A `Final` row must not keep a clock, whatever the board sends."""
    fx = _parse(_live_item(status="Final", timer="7:16"))
    assert fx is not None
    assert fx.status == "finished"
    assert fx.game_clock is None


# ---------------------------------------------------------------------------
# 3. The write, driven through the real task
# ---------------------------------------------------------------------------


class _Fixture:
    """A StatPal live-board row shaped as the writer consumes it."""

    def __init__(
        self,
        start_time,
        home,
        away,
        *,
        raw_status,
        game_clock,
        clock_field_served=True,
    ):
        self.start_time = start_time
        self.home_team = home
        self.away_team = away
        self.status = "live"
        self.fixture_id = "280446"
        self.odds_id = None
        self.home_score = 7
        self.away_score = 17
        self.raw_status = raw_status
        self.game_clock = game_clock
        # Defaults True because every fixture in this file is a FOOTBALL row
        # unless it says otherwise, and football's board carries `timer`. The
        # baseball tests below pass False, which is what their board measures.
        self.clock_field_served = clock_field_served


async def _run_livescores(
    monkeypatch, *, fixtures, events, sport_key="americanfootball_nfl"
):
    """Drive the real `_sync_statpal_livescores` and return the event rows."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    import app.services.statpal_api as statpal_api
    import app.tasks.base as task_base
    from app.models.models import Base, Event, ScoreSnapshot, Sport
    from app.tasks.statpal_sync import _sync_statpal_livescores

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Event.__table__, Sport.__table__, ScoreSnapshot.__table__]
    )
    sync_session = Session(engine, expire_on_commit=False)

    # sqlite reloads datetimes naive; the premature-live guard (#1945) compares
    # against an aware `now` and would raise, eating every assertion. Rail
    # fidelity gap, not a production shape — same treatment as #3094's harness.
    @sa_event.listens_for(sync_session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    sport = Sport(key=sport_key, name=sport_key)
    sync_session.add(sport)
    sync_session.flush()
    event_ids = []
    for spec in events:
        # 3-tuple `(home, away, clock)` is the shape every earlier test uses; a
        # 4th element presets `period` as well. The terminal tests need both
        # columns populated up front, because what they assert is that NEITHER
        # moves — and a column that starts empty cannot show that (#5079).
        home, away, preset_clock = spec[0], spec[1], spec[2]
        preset_period = spec[3] if len(spec) > 3 else None
        row = Event(
            sport_id=sport.id,
            home_team_name=home,
            away_team_name=away,
            commence_time=now - timedelta(hours=1),
            status="live",
            game_clock=preset_clock,
            period=preset_period,
        )
        sync_session.add(row)
        sync_session.flush()
        event_ids.append(row.id)
    sync_session.commit()

    class _AsyncShim:
        def __init__(self, session):
            self._s = session

        async def execute(self, statement):
            return self._s.execute(statement)

        def add(self, obj):
            self._s.add(obj)

        async def commit(self):
            self._s.commit()

        async def flush(self):
            self._s.flush()

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(sync_session)

        async def __aexit__(self_inner, *exc):
            sync_session.commit()
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(
        "app.tasks.statpal_sync.get_task_session", lambda: _Ctx(), raising=False
    )
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)

    class _Service:
        async def get_live_scores(self, sport):
            return list(fixtures)

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)

    await _sync_statpal_livescores()
    return [
        sync_session.execute(select(Event).where(Event.id == i)).scalar_one()
        for i in event_ids
    ]


@pytest.mark.asyncio
async def test_period_matches_espns_compound_format(monkeypatch):
    """The ship: the period reads exactly as ESPN writes it.

    ESPN sets `event.period = ee.status_detail` — `'14:53 - 3rd Quarter'`. A
    flipped sport must be indistinguishable, so the front end (`trustedLiveClock`,
    which suppresses the duplicate clock only when the period spells it out)
    needs no change.
    """
    now = datetime.now(timezone.utc)
    fx = _Fixture(
        now - timedelta(hours=1),
        "Los Angeles Rams",
        "San Francisco 49ers",
        raw_status="3rd Quarter",
        game_clock="7:16",
    )
    rows = await _run_livescores(
        monkeypatch,
        fixtures=[fx],
        events=[("Los Angeles Rams", "San Francisco 49ers", None)],
    )
    assert rows[0].period == "7:16 - 3rd Quarter"
    assert rows[0].game_clock == "7:16"


@pytest.mark.asyncio
async def test_the_clock_is_not_left_frozen_at_espns_last_value(monkeypatch):
    """The regression that makes a period-only fix WORSE than the bug.

    The row starts with the clock ESPN wrote before the flip. If the fix
    advanced the period but not the clock, the card would paint
    `3rd Quarter 14:53` — frozen for the rest of the game. A frozen label reads
    as stale; a frozen CLOCK reads as current.
    """
    now = datetime.now(timezone.utc)
    fx = _Fixture(
        now - timedelta(hours=1),
        "Los Angeles Rams",
        "San Francisco 49ers",
        raw_status="3rd Quarter",
        game_clock="7:16",
    )
    rows = await _run_livescores(
        monkeypatch,
        fixtures=[fx],
        events=[("Los Angeles Rams", "San Francisco 49ers", "14:53")],
    )
    assert rows[0].game_clock == "7:16", "the clock stayed at ESPN's last value"
    assert "14:53" not in (rows[0].period or "")


@pytest.mark.asyncio
async def test_halftime_clears_prior_live_clock(monkeypatch):
    """CERT-2569's required regression: when the venue clears the clock, so do we.

    The first version of this fix guarded the `game_clock` write on the incoming
    clock being truthy. At halftime StatPal sends no timer, so the guard meant
    the row KEPT the previous quarter's clock: `period='Halftime'` beside
    `game_clock='0:00'`, and `trustedLiveClock` preserves both — a
    running-looking clock the venue had already cleared.

    That is the very failure this ship exists to fix, re-entering through the
    front door. `test_halftime_writes_a_bare_label_and_no_separator` could not
    catch it because it starts from a row with NO clock, so the assignment it
    needs to observe is a no-op there. This one starts from a populated clock.
    """
    now = datetime.now(timezone.utc)
    fx = _Fixture(
        now - timedelta(hours=1),
        "Los Angeles Rams",
        "San Francisco 49ers",
        raw_status="Halftime",
        game_clock=None,
    )
    rows = await _run_livescores(
        monkeypatch,
        fixtures=[fx],
        events=[("Los Angeles Rams", "San Francisco 49ers", "0:00")],
    )
    assert rows[0].game_clock is None, (
        "halftime kept the prior clock — a cleared clock must reach the DB as NULL"
    )
    assert rows[0].period == "Halftime"


@pytest.mark.asyncio
async def test_a_quarter_transition_clears_a_stale_clock_too(monkeypatch):
    """The same rule at a non-halftime boundary, so the fix is not halftime-shaped.

    #5079: this drove `raw_status="Final"` — a TERMINAL label, which is neither
    a quarter transition (the name's claim) nor a shape the parser can produce
    (`_parse_single_fixture` sets `raw_status = … if status == "live" else None`,
    so a real `Final` row arrives with `raw_status=None` and never enters this
    branch at all). The fixture is now built by the real parser from the
    between-quarters shape the board actually serves: an in-progress label with
    the timer emptied. The terminal case is a different question and has its
    own section below.
    """
    now = datetime.now(timezone.utc)
    parsed = _parse(_live_item(status="4th Quarter", timer=""))
    assert parsed is not None and parsed.raw_status == "4th Quarter", (
        "the parser must still produce this shape, or the test below is fiction"
    )
    fx = _Fixture(
        now - timedelta(hours=1),
        "Los Angeles Rams",
        "San Francisco 49ers",
        raw_status=parsed.raw_status,
        game_clock=parsed.game_clock,
        clock_field_served=parsed.clock_field_served,
    )
    rows = await _run_livescores(
        monkeypatch,
        fixtures=[fx],
        events=[("Los Angeles Rams", "San Francisco 49ers", "12:05")],
    )
    assert rows[0].game_clock is None
    assert rows[0].period == "4th Quarter"


@pytest.mark.parametrize("zero", ["0:00", "00:00", "0.00", "0"])
def test_a_zero_clock_is_not_a_clock(zero):
    """live/141: `''` renders as nothing, `'0:00'` renders as a stopped clock.

    Both mean "no clock", so both must reach the DB as NULL.
    """
    fx = _parse(_live_item(timer=zero))
    assert fx is not None
    assert fx.game_clock is None


@pytest.mark.asyncio
async def test_halftime_writes_a_bare_label_and_no_separator(monkeypatch):
    """Halftime is genuinely live and genuinely has no clock.

    So guarding the composition on liveness alone is not enough: it would write
    `' - Halftime'` with a leading separator. The guard is on the clock being
    non-empty.
    """
    now = datetime.now(timezone.utc)
    fx = _Fixture(
        now - timedelta(hours=1),
        "Los Angeles Rams",
        "San Francisco 49ers",
        raw_status="Halftime",
        game_clock=None,
    )
    rows = await _run_livescores(
        monkeypatch,
        fixtures=[fx],
        events=[("Los Angeles Rams", "San Francisco 49ers", None)],
    )
    assert rows[0].period == "Halftime"
    assert not (rows[0].period or "").startswith(" - ")


# ---------------------------------------------------------------------------
# 4. The sport this ship widened by accident (authority/121, repairs CERT-2574)
# ---------------------------------------------------------------------------
#
# #5017's whole mechanism is `_normalize_status` learning the full-word
# in-progress families. Football was the motivating sport, but the families are
# shared: MLB's board serves `'Top 8th'` / `'Bottom 8th'`, which fell through to
# the passthrough BEFORE this ship and so never reached the writer's
# period/clock branch at all. After it, they do.
#
# That matters because the branch ends in an unguarded `event.game_clock =
# fixture_clock` (CERT-2569's repair, correct for football). Measured at the
# venue, 04:26Z: the football game object carries `timer` and empties it, while
# the BASEBALL game object has no `timer` key at all — it carries `outs` where
# football carries `timer`. So baseball's `fixture_clock` is always None, and
# `mlb_sync` deliberately writes the inning into `Event.game_clock` for the live
# badge. Ungarded, this beat blanks that inning every 60s.
#
# `_sync_statpal_livescores` is not gated on `AUTHORITY_BY_SPORT`, so this would
# have shipped on deploy, on the next MLB slate — not at the football flip.


def test_the_baseball_board_makes_no_clock_claim():
    """The parse half: no `timer` key means no claim, not an empty clock.

    `game_clock` alone cannot carry this — `_clean_game_clock` maps absent, `''`
    and `'0:00'` to the same `None` on purpose. `clock_field_served` is the
    field that survives that collapse.
    """
    baseball_item = {
        "id": "1",
        "status": "Top 8th",
        "home": {"name": "Boston Red Sox", "totalscore": "4"},
        "away": {"name": "New York Yankees", "totalscore": "2"},
        "outs": "1",
    }
    fx = _parse(baseball_item)
    assert fx is not None
    assert fx.status == "live"
    assert fx.raw_status == "Top 8th"
    assert fx.game_clock is None
    assert fx.clock_field_served is False


def test_the_football_board_does_make_one():
    """The contrast, on the same parser: `timer` present is a claim."""
    fx = _parse(_live_item(timer=""))
    assert fx is not None
    assert fx.game_clock is None
    assert fx.clock_field_served is True, (
        "an EMPTY timer is still the venue keeping a clock and clearing it — "
        "that is what CERT-2569 required us to follow"
    )


@pytest.mark.asyncio
async def test_a_live_baseball_row_keeps_the_inning_in_game_clock(monkeypatch):
    """The regression this repair exists to stop.

    The row starts with the inning form `mlb_sync` INTENDS for the live badge.
    StatPal serves the half-inning as its status and NO clock field. The period
    should advance; `game_clock` must be left exactly as it was, because the
    venue said nothing about it.

    NOT vacuous: the row starts with a non-empty `game_clock`, so an assignment
    of `None` is observable here. (A clearing test that starts from an already
    empty column cannot fail — the trap that let CERT-2569's defect through.)

    ON THE SEED (#5334, authority/143): `"Top 8"` is a value production has
    never held. `mlb_sync`'s `event.game_clock` write is guarded on
    `mlb_game.inning is not None`, and that field is never populated — 0 of
    11,488 `source='mlb'` snapshots in 14 days carry `inning`, against 11,488
    carrying `mlb_game_pk` from the same line-group. What MLB rows actually
    carry is ESPN's `'0:00'`, on 193 of 193 rows that have a clock at all. The
    proposition under test is the same either way — the pre-existing value
    survives, whatever wrote it — so this case stays as the general form, and
    the case below drives the value production really holds.
    """
    now = datetime.now(timezone.utc)
    fx = _Fixture(
        now - timedelta(hours=1),
        "Boston Red Sox",
        "New York Yankees",
        raw_status="Top 8th",
        game_clock=None,
        clock_field_served=False,
    )
    rows = await _run_livescores(
        monkeypatch,
        fixtures=[fx],
        events=[("Boston Red Sox", "New York Yankees", "Top 8")],
        sport_key="baseball_mlb",
    )
    assert rows[0].period == "Top 8th"
    assert rows[0].game_clock == "Top 8", (
        "StatPal blanked a clock it never claimed — the baseball board has no "
        "`timer` key, so its silence is structural and must not be read as a "
        "cleared clock"
    )


@pytest.mark.asyncio
async def test_a_live_baseball_row_keeps_the_clock_production_actually_holds(
    monkeypatch,
):
    """The same guard, driven on the value MLB rows really carry (#5334).

    The case above seeds `"Top 8"`, the inning form `mlb_sync` intends. That
    write has never fired, so the column it protects has never held that value.
    Production holds ESPN's `'0:00'` instead — baseball has no clock and ESPN
    serves the field anyway — on 193 of 193 MLB rows that carry a clock.

    This matters beyond tidiness. The guard's recorded rationale in
    `statpal_sync.py` justifies itself by an inning in `Event.game_clock` that
    is not there, so a reader who checks the premise finds it false. The guard
    is still RIGHT: StatPal must not write a clock for a sport whose board keeps
    none, whatever `mlb_sync` does or stops doing. Pinning the real value here
    means removing the gate reds a test seeded from production rather than one
    seeded from a premise that has already gone stale.

    NOT vacuous, and for a sharper reason than the case above: `'0:00'` is
    exactly the string `_zero_clock_is_not_a_clock` normalises AWAY on the
    parser side, so a writer that round-tripped the venue's silence through
    that normalisation would land `None` here and this would fail.
    """
    now = datetime.now(timezone.utc)
    fx = _Fixture(
        now - timedelta(hours=1),
        "Chicago Cubs",
        "Pittsburgh Pirates",
        raw_status="Bottom 6th",
        game_clock=None,
        clock_field_served=False,
    )
    rows = await _run_livescores(
        monkeypatch,
        fixtures=[fx],
        events=[("Chicago Cubs", "Pittsburgh Pirates", "0:00")],
        sport_key="baseball_mlb",
    )
    assert rows[0].period == "Bottom 6th"
    assert rows[0].game_clock == "0:00", (
        "StatPal overwrote the clock ESPN wrote for a baseball row — the "
        "baseball board serves no `timer` key, so it has made no claim about "
        "this column and must leave it alone (CERT-2574)"
    )


@pytest.mark.asyncio
async def test_football_halftime_still_clears_the_clock(monkeypatch):
    """The guard must not undo CERT-2569 for the sport it was written for.

    Same starting state as the baseball case — a populated `game_clock` — so the
    two tests differ ONLY in whether the venue keeps a clock. Football's does,
    so halftime clears it.
    """
    now = datetime.now(timezone.utc)
    fx = _Fixture(
        now - timedelta(hours=1),
        "Los Angeles Rams",
        "San Francisco 49ers",
        raw_status="Halftime",
        game_clock=None,
        clock_field_served=True,
    )
    rows = await _run_livescores(
        monkeypatch,
        fixtures=[fx],
        events=[("Los Angeles Rams", "San Francisco 49ers", "0:47")],
    )
    assert rows[0].period == "Halftime"
    assert rows[0].game_clock is None, (
        "halftime must still clear a stale football clock (CERT-2569)"
    )


@pytest.mark.asyncio
async def test_a_fixture_that_makes_no_clock_claim_at_all_leaves_it_alone(monkeypatch):
    """Pins the `getattr` DEFAULT, which no other test reaches.

    The baseball test above passes `clock_field_served=False` explicitly, so it
    cannot tell a default of `False` from a default of `True` — a mutant that
    flips the default survives it. This drives a fixture with no such attribute
    at all, which is what every other duck-typed construction path in the tree
    hands this writer. No claim about the clock means no write.
    """
    now = datetime.now(timezone.utc)

    class _ClocklessFixture:
        def __init__(self):
            self.start_time = now - timedelta(hours=1)
            self.home_team = "Boston Red Sox"
            self.away_team = "New York Yankees"
            self.status = "live"
            self.fixture_id = "1"
            self.odds_id = None
            self.home_score = 4
            self.away_score = 2
            self.raw_status = "Top 8th"
            self.game_clock = None
            # deliberately no `clock_field_served`

    assert not hasattr(_ClocklessFixture(), "clock_field_served")
    rows = await _run_livescores(
        monkeypatch,
        fixtures=[_ClocklessFixture()],
        events=[("Boston Red Sox", "New York Yankees", "Top 8")],
        sport_key="baseball_mlb",
    )
    assert rows[0].period == "Top 8th"
    assert rows[0].game_clock == "Top 8", (
        "a fixture that never mentions the clock must not clear it — the "
        "`getattr` default carries this and nothing else asserts it"
    )


def test_the_tennis_parser_makes_no_clock_claim_either():
    """Pins the DATACLASS default, which the tennis path relies on.

    Tennis reaches `_sync_statpal_livescores` (only soccer is in
    `LIVESCORES_INGESTION_DARK_SPORTS`) and its board serves no clock. Its
    parser never passes `clock_field_served`, so the dataclass default is the
    only thing standing between a live tennis row and the same blanking the
    baseball tests describe. Asserted through the real parser rather than by
    constructing the dataclass, so it stays true if the parser starts setting it.
    """
    from app.services.statpal_api import StatPalAPIService

    item = {
        "id": "9",
        "status": "3rd Set",
        "date": "11.09.2026",
        "time": "19:00",
        "player": [
            {"name": "Gauff", "id": "1", "totalscore": "1"},
            {"name": "Rybakina", "id": "2", "totalscore": "0"},
        ],
    }
    fx = StatPalAPIService()._parse_tennis_match(item, {"id": "5", "name": "US Open"})
    assert fx is not None
    assert fx.clock_field_served is False


# ---------------------------------------------------------------------------
# 5. The TERMINAL row, driven from the parser's own output (#5079)
# ---------------------------------------------------------------------------
#
# Every writer test above hand-builds `_Fixture`. That is fine for in-progress
# labels, which the parser really does produce — but it let a terminal test
# assert a rule for `raw_status="Final"`, a shape `_parse_single_fixture`
# cannot emit. So the terminal path's real behaviour was never proven.
#
# These drive the RECORDED live board (`statpal_nfl_livescores_20260903.json`,
# four genuine `status='Final'` rows) through the real parser and hand the
# result to the real writer. The finding they pin is deliberately not
# "the clock is cleared" — it is what actually happens, which is nothing.


def _recorded_terminal_fixtures():
    """The four `Final` rows from the recorded NFL live board, really parsed."""
    import json
    from pathlib import Path

    from app.services.statpal_api import StatPalAPIService

    payload = json.loads(
        (
            Path(__file__).parent / "fixtures" / "statpal_nfl_livescores_20260903.json"
        ).read_text()
    )
    return StatPalAPIService()._parse_fixtures(payload, "nfl")


def test_the_recorded_terminal_board_parses_to_no_status_and_no_clock():
    """The premise, measured rather than assumed.

    A real `Final` row reaches the writer with `raw_status=None` — which is the
    whole reason the writer's period/clock block is skipped on it.

    It also carries `clock_field_served=False`, and that is a SECOND terminal
    shape worth naming: #5079 predicted `timer=''` (which is what the board
    serves at the instant a game goes final, measured 03:27Z on 9/11). This
    settled board omits the `timer` key altogether. The two disagree about
    `clock_field_served` and agree about everything the writer reads.
    """
    fixtures = _recorded_terminal_fixtures()
    assert len(fixtures) == 4, "the recorded board should hold four finished games"
    for fx in fixtures:
        assert fx.status == "finished"
        assert fx.raw_status is None, (
            "a terminal row must not carry a raw_status — the writer's whole "
            "period/clock branch is gated on it"
        )
        assert fx.game_clock is None
        assert fx.clock_field_served is False


def test_the_two_terminal_shapes_agree_on_what_the_writer_reads():
    """`timer=''` and no `timer` key at all must reach the writer identically.

    Only the second is in the recorded board, so without this the first — the
    shape a game actually passes through as it goes final — is untested.
    """
    at_the_whistle = _parse(_live_item(status="Final", timer=""))
    settled = _parse(_live_item(status="Final"))
    del_key = _live_item(status="Final")
    del del_key["timer"]
    settled_no_key = _parse(del_key)

    for fx in (at_the_whistle, settled, settled_no_key):
        assert fx is not None
        assert fx.status == "finished"
        assert fx.raw_status is None
        assert fx.game_clock is None


@pytest.mark.asyncio
async def test_a_terminal_row_leaves_the_period_and_clock_exactly_as_it_found_them(
    monkeypatch,
):
    """THE FINDING, pinned rather than asserted to be correct.

    Our row is still `status='live'` (the livescores writer only ever selects
    those) and carries the period and clock ESPN last wrote mid-game. StatPal's
    board has already gone `Final`. The writer advances the SCORE and leaves the
    period and the clock untouched — so for as long as our row stays live, the
    card pairs a final score with a running-looking third-quarter clock.

    That window is closed by a different writer, not this one: measured on
    production over the last 7 days (authority/121), completed rows carry
    ESPN's terminal write — `period='Final'`, `game_clock='0:00'` for
    NFL/NCAAF/MLB, `period='FT'` for soccer. So this is p3 and pinned as
    behaviour, not filed as a defect.

    Its DURATION is unmeasured, and deliberately not described as short here.
    The window is "our row still says live after the venue said Final", and
    rows do linger: measured 06:20Z on 9/11, live rows sat 4.2h (MiLB) and 6.1h
    (ATP) past their own commence_time. Neither sport reaches this writer, so
    that is a bound on nothing — which is the point. Whoever needs the duration
    for NFL/MLB must measure it during a slate, not infer it from here.

    NOT VACUOUS: both columns start populated and DIFFERENT from what a
    clearing writer would leave, so an assignment of either `None` or the
    fixture's own values is observable here. (The trap that let CERT-2569's
    defect through was a clearing test whose column started empty.)
    """
    now = datetime.now(timezone.utc)
    terminal = next(
        f
        for f in _recorded_terminal_fixtures()
        if f.home_team == "Buffalo Bills"
    )
    terminal.start_time = now - timedelta(hours=1)

    rows = await _run_livescores(
        monkeypatch,
        fixtures=[terminal],
        events=[
            (
                "Buffalo Bills",
                "Pittsburgh Steelers",
                "7:16",           # game_clock ESPN last wrote
                "7:16 - 3rd Quarter",  # period ESPN last wrote
            )
        ],
    )
    assert rows[0].period == "7:16 - 3rd Quarter", (
        "the terminal row must not rewrite the period — it carries no "
        "raw_status, so the writer's period branch never runs"
    )
    assert rows[0].game_clock == "7:16", (
        "and it must not clear the clock either: same skipped branch. If this "
        "ever fails, the writer grew a terminal path and #5079's question "
        "needs re-asking"
    )
    # The half that DOES move, which is what makes the pairing observable.
    assert rows[0].home_score == 28
    assert rows[0].away_score == 27
