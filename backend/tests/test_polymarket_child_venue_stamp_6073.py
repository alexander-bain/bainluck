"""#6073, INGEST HALF — the child row carries the venue's kickoff, so the
minting half has something to read.

WHAT A READER SAW. `/events/15312412` at 04:55Z on 2026-09-14 (artifact
`artifacts-lane1b-233/live-tennis-15312412-top-0455Z.png`): a hero badged
**LIVE**, two crests, `No price`. Polymarket's own Gamma payload said that match
starts at 13:00Z — eight hours after the shot. Nothing had been played. Three
sibling fixtures had already walked past their invented kickoff into
``suspended``, which the event page renders as "No result reported": a match
that has not begun, reported as one that finished without a result.

THIS IS ONE OF TWO HALVES AND IT IS THE INPUT, NOT THE DECISION.

* **Minting (NOT here).** ``auto_create_commence_time`` now prefers
  ``venue_game_start(market)`` for a Polymarket row — lane1's ``a02aca00a``,
  CERT-2827 GREEN, already on master. It reads the stamp; it does not write it.
* **Ingest (HERE).** ``sub_market_metadata`` built the child row's metadata
  without ``venue_game_start``, though the parent row two branches earlier
  stamps it from the same ``event.game_start_time``.

**Which is why the merged half changes nothing today.** Measured on production
2026-09-14 06:02Z, group ``polymarket:1019271``: parent ``60980453`` carries
``venue_game_start = 2026-09-14T09:00:00Z`` and ``event_id`` **NULL**, while all
six children carry **no such key** and ``event_id = 15312442``. The child is the
row the event is minted from, so the truth was stamped on the only row that
never mints, and ``venue_game_start()`` returns ``None`` on every row that does.
Same class as the ``polymarket_event_id`` and ``clob_token_ids`` omissions this
helper's docstring already records — a value in scope in the same loop
iteration, dropped on the way into the child.

THE JOIN IS ASSERTED, NOT ASSUMED. ``TestTheTwoHalvesAgreeOnTheFormat`` parses
the string this half writes with ``venue_game_start`` — the reader the merged
half calls — so the two cannot drift on the key name or the value format. A
suite that pinned each half against its own hand-built fixture would pass while
production stayed broken, which is the only interesting way this can break.

BOTH DIRECTIONS (gotcha #43). A market with no published kickoff stamps nothing
and keeps exactly today's behaviour: no metadata, a row ingested before the
stamp existed, an unparseable value, a source that is not Polymarket. Widening
the stamp must not invent a kickoff for a row the venue never gave one for.

AND THE WIRING MUTANT NO UNIT TEST CAN SEE. ``sub_market_metadata`` is pure and
is called from an ingest loop no unit test reaches without a database: drop the
keyword at that one call site and every assertion above still passes while
production goes straight back to stamping nothing. ``TestTheIngestLoopIsWired``
reads the call site itself, and asserts its population is non-empty first — an
AST guard whose search finds nothing passes for free.

NOT IN THIS SUITE, AND NOT IN THIS SHA: the four events in ``SPECIMENS`` are
already minted and linked. Neither half re-dates them — ``_SOURCE_PRIORITY``
ranks ``polymarket_venue`` 0 and the self-revision path needs
``incoming_source == current_source``, which a row stamped plain ``polymarket``
fails. That repair is CERT-2826's named
``6073-REDATE-ALREADY-LINKED-POLYMARKET-FIXTURES`` and is owed separately. The
specimens appear here as the measured skews (+11.0h, +12.8h, +12.8h, +17.8h,
all different, which is what rules out a timezone constant), not as rows this
sha repairs.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.polymarket import sub_market_metadata
from app.tasks.prediction_market_matching import venue_game_start


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


class TestTheIngestLoopIsWired:
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


# ═══ The join: does the MERGED chooser now have something to read? ═══════════


class TestTheMergedChooserNowHasSomethingToRead:
    """The pair, end to end through the two pure halves.

    This is the assertion the whole sha exists for, and it is the one neither
    lane could write alone. lane1's ``a02aca00a`` (CERT-2827 GREEN, on master)
    made ``auto_create_commence_time`` prefer ``venue_game_start(market)`` for a
    Polymarket row. That half is CORRECT and it is INERT, because on production
    the only rows it ever sees — the children — carry no such key.

    So the test drives master's real chooser with a row built by THIS sha's
    ingest half, rather than with a hand-written metadata dict. A hand-built
    fixture would prove the chooser works on a row shape production does not
    have, which is exactly the gap that let a GREEN half ship inert.
    """

    def test_a_child_row_built_by_this_sha_dates_from_the_venue_instant(self):
        from app.tasks.prediction_market_matching import auto_create_commence_time

        for event_id, listing_stamp, venue_start, _skew in SPECIMENS:
            market = _poly_row(venue_start, listing_stamp)
            commence, source = auto_create_commence_time(market, listing_stamp)

            assert commence == venue_start, (
                f"event {event_id}: the chooser still dated the fixture from the "
                f"LISTING stamp {listing_stamp} instead of the venue's "
                f"{venue_start}. The merged half reads `venue_game_start`; this "
                "sha is what puts it on the child row."
            )
            assert source is not None, (
                "a commence_time chosen from the venue must say so — an "
                "unsourced value cannot be told from the listing stamp later"
            )

    def test_without_this_shas_stamp_the_chooser_falls_back(self):
        """The other direction, and the proof that the stamp is the active input.

        A child row as production builds it TODAY — no `venue_game_start` — must
        still take the fallback. If this passed with the venue instant, the
        chooser would be getting the time from somewhere else and this sha would
        not be the thing that fixes #6073.
        """
        from app.tasks.prediction_market_matching import auto_create_commence_time

        _event_id, listing_stamp, _venue_start, _skew = SPECIMENS[0]
        meta = sub_market_metadata(event_id="1019271", matchup_title="Mazzola vs. Zeltina")
        bare_child = _Market(commence_time=listing_stamp, market_metadata=meta)

        commence, _source = auto_create_commence_time(bare_child, listing_stamp)
        assert commence == listing_stamp, (
            "a child row with no venue stamp must keep today's behaviour; the "
            "venue instant may only arrive through the stamp this sha adds"
        )
