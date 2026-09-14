"""#6073 — a fixture is dated by the venue's kickoff, not by the listing stamp.

WHAT A READER SAW. `/events/15312412` at 04:55Z on 2026-09-14 (artifact
`artifacts-lane1b-233/live-tennis-15312412-top-0455Z.png`): a hero badged
**LIVE**, two crests, `No price`. Polymarket's own Gamma payload said that match
starts at 13:00Z — eight hours after the shot. Nothing had been played. Three
sibling fixtures had already walked past their invented kickoff into
``suspended``, which the event page renders as "No result reported": a match
that has not begun, reported as one that finished without a result.

THE TWO HALVES, AND WHY EITHER ALONE IS NOT THE FIX.

* **Ingest.** ``sub_market_metadata`` built the child row's metadata without
  ``venue_game_start``, though the parent row two branches earlier stamps it
  from the same ``event.game_start_time``. Measured on production for group
  ``polymarket:1019271``: parent ``60980453`` carries
  ``venue_game_start = 2026-09-14T09:00:00Z`` and ``event_id`` NULL; its six
  children carry no such key and ``event_id = 15312430``. The child is the row
  the event is minted from, so the truth was stamped on the only row that never
  mints.
* **Minting.** ``_create_event_from_prediction_market`` dated the fixture from
  ``market.commence_time``, which for a Polymarket row is Gamma's ``startDate``
  — the moment the market was LISTED.

Both are asserted here, and so is the join between them: the string the ingest
half writes is parsed by the reader the minting half calls. A test that only
pinned each half against its own fixture would pass with the two halves
disagreeing about the format.

BOTH DIRECTIONS (gotcha #43 / notice 43). Every widening assertion has its
refusing twin: a market with no published kickoff keeps exactly today's
behaviour, and a fixture whose venue start is in the PAST still mints
live-eligible — so "never trust the market clock" does not pass either.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.polymarket import sub_market_metadata
from app.tasks.prediction_market_matching import (
    auto_create_status,
    auto_create_venue_commence_time,
    venue_game_start,
)


# ─── The four production specimens, #6073 ────────────────────────────────────
#
# `our_commence` is what `futures_markets.commence_time` held (Gamma
# `startDate`, the listing stamp); `venue_start` is Gamma's own `startTime` for
# the same event, read from the venue's API per standing notice 26. Each skew is
# different, which is what rules out a timezone constant.
SPECIMENS = [
    # (event_id, our_commence, venue_start, skew_hours)
    (
        15312412,
        datetime(2026, 9, 14, 1, 59, 21, tzinfo=timezone.utc),
        datetime(2026, 9, 14, 13, 0, 0, tzinfo=timezone.utc),
        11.0,
    ),
    (
        15312430,
        datetime(2026, 9, 13, 20, 14, 27, tzinfo=timezone.utc),
        datetime(2026, 9, 14, 9, 0, 0, tzinfo=timezone.utc),
        12.8,
    ),
    (
        15312429,
        datetime(2026, 9, 13, 20, 14, 29, tzinfo=timezone.utc),
        datetime(2026, 9, 14, 9, 0, 0, tzinfo=timezone.utc),
        12.8,
    ),
    (
        15312434,
        datetime(2026, 9, 13, 22, 14, 16, tzinfo=timezone.utc),
        datetime(2026, 9, 14, 16, 0, 0, tzinfo=timezone.utc),
        17.8,
    ),
]

#: The instant the LIVE badge was photographed on 15312412.
SHOT_AT = datetime(2026, 9, 14, 4, 55, 0, tzinfo=timezone.utc)


class _Market:
    """The read surface of a `FuturesMarket` row, as the pure helpers see it."""

    def __init__(self, *, source="polymarket", external_id="0xabc",
                 commence_time=None, market_metadata=None):
        self.source = source
        self.external_id = external_id
        self.commence_time = commence_time
        self.market_metadata = market_metadata
        self.name = "Alessandra Mazzola vs. Beatrise Zeltina"


def _poly_row(venue_start, commence_time):
    """A Polymarket sub-market row carrying the metadata the ingest half writes.

    Built by CALLING `sub_market_metadata`, never by hand-writing the dict: the
    point is that the minting half reads what the ingest half actually produces.
    A hand-built fixture here would keep passing if the two halves drifted on the
    key name or the value format, which is the only interesting way this can
    break.
    """
    meta = sub_market_metadata(
        event_id="1019271",
        matchup_title="Mazzola vs. Zeltina",
        venue_game_start=venue_start,
    )
    return _Market(commence_time=commence_time, market_metadata=meta)


# ═══ Half one: the ingest stamp ══════════════════════════════════════════════


class TestSubMarketCarriesTheVenueKickoff:

    def test_the_child_row_gets_the_instant_the_parent_already_had(self):
        """The value in scope in the same iteration reaches the child row."""
        meta = sub_market_metadata(
            event_id="1019271",
            matchup_title="Mazzola vs. Zeltina",
            venue_game_start=datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
        )
        assert meta["venue_game_start"] == "2026-09-14T09:00:00+00:00"

    def test_the_key_is_top_level(self):
        """jsonb `?` does not see nested keys; the census and the reader use it."""
        meta = sub_market_metadata(
            event_id="1019271",
            matchup_title="Mazzola vs. Zeltina",
            venue_game_start=datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
        )
        assert "venue_game_start" in meta.keys()

    def test_the_value_is_a_string_not_a_datetime(self):
        """`market_metadata` is JSONB; a datetime is not a JSON scalar, and the
        parent row stamps `.isoformat()`. Parent and child must compare equal."""
        meta = sub_market_metadata(
            event_id="1019271",
            matchup_title="Mazzola vs. Zeltina",
            venue_game_start=datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
        )
        assert isinstance(meta["venue_game_start"], str)
        # The exact expression `tasks.polymarket` uses for the PARENT row.
        parent_value = datetime(
            2026, 9, 14, 9, 0, tzinfo=timezone.utc
        ).isoformat()
        assert meta["venue_game_start"] == parent_value

    def test_a_string_is_passed_through_unchanged(self):
        """Re-stamping from an already-serialised value must not double-encode."""
        meta = sub_market_metadata(
            event_id="1019271",
            matchup_title=None,
            venue_game_start="2026-09-14T09:00:00+00:00",
        )
        assert meta["venue_game_start"] == "2026-09-14T09:00:00+00:00"

    @pytest.mark.parametrize("absent", [None, ""])
    def test_no_published_kickoff_stamps_nothing(self, absent):
        """THE OTHER DIRECTION. A fixture the venue gives no start time for keeps
        exactly today's behaviour — a placeholder would satisfy a census while
        pointing at nothing (gotcha #53), and would date a real fixture wrong."""
        meta = sub_market_metadata(
            event_id="1019271",
            matchup_title="Mazzola vs. Zeltina",
            venue_game_start=absent,
        )
        assert "venue_game_start" not in (meta or {})

    def test_nothing_to_say_still_returns_none(self):
        """`None`, not `{}`: the caller passes this straight into the insert and
        an empty object would overwrite populated metadata on re-ingest."""
        assert sub_market_metadata(
            event_id=None, matchup_title=None, venue_game_start=None,
        ) is None

    def test_the_other_keys_are_untouched(self):
        """The three keys already stamped here keep their exact contract."""
        meta = sub_market_metadata(
            event_id="1019271",
            matchup_title="Mazzola vs. Zeltina",
            clob_token_ids=["118334555378487561197673606725030533746055786851"],
            venue_game_start=datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
        )
        assert meta["polymarket_event_id"] == "1019271"
        assert meta["matchup_title"] == "Mazzola vs. Zeltina"
        assert meta["clob_token_ids"] == [
            "118334555378487561197673606725030533746055786851"
        ]


class TestTheTwoHalvesAgreeOnTheFormat:

    def test_the_reader_parses_what_the_writer_wrote(self):
        """The join. `venue_game_start()` is the minting half's only door into
        this key; the ingest half is its only writer. Asserting each against its
        own fixture would pass with the two disagreeing."""
        row = _poly_row(
            venue_start=datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc),
            commence_time=datetime(2026, 9, 13, 20, 14, 27, tzinfo=timezone.utc),
        )
        assert venue_game_start(row) == datetime(
            2026, 9, 14, 9, 0, tzinfo=timezone.utc
        )

    def test_a_naive_stamp_is_read_as_utc(self):
        """A datetime with no tzinfo must not come back naive — the caller
        compares it against a tz-aware `now` and would raise."""
        row = _poly_row(
            venue_start=datetime(2026, 9, 14, 9, 0),  # naive
            commence_time=datetime(2026, 9, 13, 20, 14, 27, tzinfo=timezone.utc),
        )
        assert venue_game_start(row).tzinfo is not None


# ═══ Half two: the minting choice ════════════════════════════════════════════


class TestAutoCreateDatesTheFixtureFromTheVenue:

    @pytest.mark.parametrize(
        "event_id,our_commence,venue_start,skew",
        SPECIMENS,
        ids=[str(s[0]) for s in SPECIMENS],
    )
    def test_every_specimen_mints_at_the_venues_instant(
        self, event_id, our_commence, venue_start, skew
    ):
        row = _poly_row(venue_start=venue_start, commence_time=our_commence)
        assert auto_create_venue_commence_time(row, our_commence) == venue_start

    @pytest.mark.parametrize(
        "event_id,our_commence,venue_start,skew",
        SPECIMENS,
        ids=[str(s[0]) for s in SPECIMENS],
    )
    def test_the_skews_are_not_one_constant(
        self, event_id, our_commence, venue_start, skew
    ):
        """Guards the diagnosis, not just the fix: if these were all the same
        offset the cause would be a timezone bug and this fix the wrong one."""
        measured = (venue_start - our_commence).total_seconds() / 3600
        assert round(measured, 1) == skew
        assert len({s[3] for s in SPECIMENS}) > 1

    def test_the_badge_the_reader_saw(self):
        """THE WHOLE SHIP, in the one function that decides the word on the hero.
        Same market, same clock; only the date the row is minted with changes."""
        our_commence = datetime(2026, 9, 14, 1, 59, 21, tzinfo=timezone.utc)
        venue_start = datetime(2026, 9, 14, 13, 0, 0, tzinfo=timezone.utc)
        row = _poly_row(venue_start=venue_start, commence_time=our_commence)

        # What master did: dated by the listing stamp, already past at 04:55Z.
        assert auto_create_status(our_commence, None, SHOT_AT) == "live"
        # What this ship does: dated by the venue, eight hours still to wait.
        minted = auto_create_venue_commence_time(row, our_commence)
        assert auto_create_status(minted, None, SHOT_AT) == "scheduled"


class TestTheRefusingDirection:
    """Every one of these must keep master's behaviour exactly."""

    def test_a_row_with_no_metadata_is_unchanged(self):
        row = _Market(
            commence_time=datetime(2026, 9, 13, 20, 14, tzinfo=timezone.utc),
            market_metadata=None,
        )
        fallback = datetime(2026, 9, 13, 20, 14, tzinfo=timezone.utc)
        assert auto_create_venue_commence_time(row, fallback) == fallback

    @pytest.mark.parametrize("meta", [{}, {"matchup_title": "A vs. B"}])
    def test_a_row_minted_before_the_stamp_is_unchanged(self, meta):
        """The historical class: metadata exists, this key does not. It must fail
        OPEN — a row not yet re-polled is indistinguishable from one the venue
        gives no fixture time for, and neither is grounds to re-date it."""
        row = _Market(
            commence_time=datetime(2026, 9, 13, 20, 14, tzinfo=timezone.utc),
            market_metadata=meta,
        )
        fallback = datetime(2026, 9, 13, 20, 14, tzinfo=timezone.utc)
        assert auto_create_venue_commence_time(row, fallback) == fallback

    @pytest.mark.parametrize("junk", ["", "   ", "not-a-date", "2026-13-45"])
    def test_an_unparseable_stamp_is_unchanged(self, junk):
        row = _Market(
            commence_time=datetime(2026, 9, 13, 20, 14, tzinfo=timezone.utc),
            market_metadata={"venue_game_start": junk},
        )
        fallback = datetime(2026, 9, 13, 20, 14, tzinfo=timezone.utc)
        assert auto_create_venue_commence_time(row, fallback) == fallback

    def test_a_kalshi_row_is_unchanged(self):
        """Only Polymarket ingest writes this key, and Kalshi has its own rescue
        (`auto_create_commence_time`, the ticker). This must not reach it."""
        row = _Market(
            source="kalshi",
            external_id="KXLOLGAME-26AUG210500GAMTSW",
            commence_time=datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc),
            market_metadata={"matchup_title": "GAM vs. TSW"},
        )
        fallback = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)
        assert auto_create_venue_commence_time(row, fallback) == fallback

    def test_a_match_already_under_way_still_mints_live(self):
        """THE TWIN OF THE SHIP. A fixture whose venue start is in the PAST is a
        real live match: it must still mint live-eligible, so "never trust the
        market clock" is not what passed here."""
        venue_start = datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc)
        row = _poly_row(
            venue_start=venue_start,
            commence_time=datetime(2026, 9, 13, 20, 14, tzinfo=timezone.utc),
        )
        minted = auto_create_venue_commence_time(
            row, datetime(2026, 9, 13, 20, 14, tzinfo=timezone.utc)
        )
        assert minted == venue_start
        assert auto_create_status(minted, None, SHOT_AT) == "live"

    def test_a_fixture_two_months_out_is_not_re_dated_to_the_clock(self):
        """WHY THIS SITS AFTER THE CALLER'S 30-DAY CLAMP. That clamp answers
        "this market's own time is garbage, so guess `now`" — and guessing `now`
        is the defect itself, since it mints the row already live. A fixture the
        venue publishes for two months out is not garbage."""
        now = SHOT_AT
        venue_start = now + timedelta(days=60)
        # The clamp has already fired: the caller handed us `now`.
        row = _poly_row(venue_start=venue_start, commence_time=None)
        minted = auto_create_venue_commence_time(row, now)
        assert minted == venue_start
        assert auto_create_status(minted, None, now) == "scheduled"


# ═══ The wiring, which every test above is blind to ══════════════════════════


class TestBothHalvesAreActuallyCalled:
    """Two mutants survive everything above, and they are the ones that matter.

    Both functions under test are pure and are called from code no unit test can
    reach without a database: the sub-market ingest loop and
    ``_create_event_from_prediction_market``. Delete the keyword argument at one call
    site, or the one line at the other, and every assertion above still passes
    while production goes straight back to the listing stamp. These read the
    call sites themselves.

    Each asserts its population is NON-EMPTY before asserting anything about it
    (an AST guard whose search finds nothing passes for free, which is the usual
    way this shape of test lies).
    """

    def _fn_ast(self, module, name):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                    node.name == name:
                return node
        raise AssertionError(f"{name} not found in {module.__name__}")

    def test_the_ingest_loop_passes_the_venue_kickoff(self):
        from app.tasks import polymarket as poly_mod

        tree = ast.parse(inspect.getsource(poly_mod))
        calls = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "sub_market_metadata"
        ]
        assert calls, "no call to sub_market_metadata — this guard reads nothing"

        for call in calls:
            kwargs = {k.arg: k for k in call.keywords if k.arg}
            assert "venue_game_start" in kwargs, (
                "the sub-market ingest dropped the venue kickoff again (#6073) — "
                "the child row is the one the event is minted from"
            )
            value = kwargs["venue_game_start"].value
            # `event.game_start_time`, not None and not a literal.
            assert isinstance(value, ast.Attribute), ast.dump(value)
            assert value.attr == "game_start_time"

    def test_the_auto_create_path_calls_the_venue_rescue_after_the_clamp(self):
        from app.tasks import prediction_market_matching as pmm

        fn = self._fn_ast(pmm, "_create_event_from_prediction_market")
        names = [
            n.func.id for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        ]
        assert "auto_create_venue_commence_time" in names, (
            "the auto-create no longer asks the venue when the fixture starts "
            "(#6073)"
        )

        # ORDER IS LOAD-BEARING, and it is the half of this a name check misses.
        # Before the 30-day clamp, a fixture the venue publishes two months out
        # is re-dated to `now` and the row is born live — the defect, restored.
        body = list(ast.walk(fn))
        def _line_of(pred):
            return min(
                (n.lineno for n in body if pred(n)), default=None,
            )
        # The clamp's threshold is written `86400 * 30`, so it is a BinOp of two
        # constants and NOT a single 2592000 an equality would find.
        def _is_thirty_day_threshold(n):
            if not isinstance(n, ast.BinOp) or not isinstance(n.op, ast.Mult):
                return False
            values = {
                c.value for c in (n.left, n.right)
                if isinstance(c, ast.Constant)
            }
            return values == {86400, 30}

        clamp = _line_of(_is_thirty_day_threshold)
        rescue = _line_of(
            lambda n: isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "auto_create_venue_commence_time"
        )
        assert clamp is not None, "the 30-day clamp is gone; re-read this guard"
        assert rescue is not None
        assert clamp < rescue, (
            "the venue rescue must run AFTER the sanity clamp, or a fixture the "
            "venue publishes far out is re-dated to the clock and born live"
        )
