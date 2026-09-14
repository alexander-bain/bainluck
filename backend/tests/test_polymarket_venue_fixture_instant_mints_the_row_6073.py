"""#6073 — a minted fixture is dated from the venue's START, not its LISTING.

A reader on `/events/15312412` at 04:55Z on 2026-09-14 saw a hero badged **LIVE**
with two crests and `No price`, for an ITF tennis match Polymarket says starts at
13:00Z. Nothing had been played. The row then walked on into `suspended`, which
the event page renders as "No result reported" — a match that has not begun,
reported as one that finished without a result.

THE FIELD, AND WHY THE ROW PROVES IT WITHOUT INFERENCE. Gamma serves both stamps
on the same event payload and they mean different things:

    startTime = "2026-09-14T13:00:00Z"   <- the fixture instant
    startDate = "2026-09-14T01:59:21Z"   <- the LISTING stamp

`futures_markets.commence_time` for that market held `01:59:21Z`, to the second —
`startDate`. `_create_event_from_prediction_market` dated the event it minted
from that column, so the event's kickoff was the moment Polymarket published the
market, and the row sailed past it into `live`. Four specimens below, measured by
lane1b/233 against Gamma's own API (notice 26), at +11.0h, +12.8h, +12.8h and
+17.8h. No two offsets agree, which is what rules out a timezone constant and
names the field.

THE HELPER ALREADY EXISTED. `venue_game_start` has read
`market_metadata['venue_game_start']` since #4965, and its docstring says in as
many words why `commence_time` cannot answer this question. Two guards call it.
The minting path — one of the "many other readers" that stamp's own comment
anticipates — did not. This is the conversion of that call site, and nothing
more: no new signal, no new ingest, no absorption rule touched.

WHAT THIS DOES NOT DO, STATED SO NOBODY READS IT AS MORE. The four specimens
carry `venue_game_start` NULL today — the ingest half (`services/polymarket_api.py`
/ `tasks/polymarket.py`, lane1b's, filed on the same issue) builds the Polymarket
event wrapper without `title`/`startTime`, so the venue's instant never reaches
the row. This half pays out wherever the stamp IS present — 5,027 of 24,835 open
Polymarket markets on the same production read — and pays out on all of them once
the ingest half lands. It also mints FORWARD only: an event already standing with
a listing-stamp kickoff is not rewritten by this change.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.event_registry import _SOURCE_PRIORITY
from app.tasks.prediction_market_matching import (
    auto_create_commence_time,
    auto_create_status,
)
from app.utils.event_completion import (
    DERIVED_COMMENCE_SOURCES,
    POLYMARKET_VENUE_COMMENCE_SOURCE,
    TICKER_DERIVED_COMMENCE_SOURCE,
    commence_time_is_a_reported_start,
)

UTC = timezone.utc

#: The four production rows, verbatim from the issue's venue-read table:
#: (event id, our `commence_time` = Gamma `startDate`, Gamma `startTime`).
SPECIMENS = [
    (15312412, datetime(2026, 9, 14, 1, 59, 21, tzinfo=UTC),
     datetime(2026, 9, 14, 13, 0, tzinfo=UTC)),
    (15312430, datetime(2026, 9, 13, 20, 14, 27, tzinfo=UTC),
     datetime(2026, 9, 14, 9, 0, tzinfo=UTC)),
    (15312429, datetime(2026, 9, 13, 20, 14, 29, tzinfo=UTC),
     datetime(2026, 9, 14, 9, 0, tzinfo=UTC)),
    (15312434, datetime(2026, 9, 13, 22, 14, 16, tzinfo=UTC),
     datetime(2026, 9, 14, 16, 0, tzinfo=UTC)),
]

#: The instant lane1b took the screenshot of the LIVE-badged hero.
SHOT_AT = datetime(2026, 9, 14, 4, 55, tzinfo=UTC)


def _market(*, source="polymarket", listing_stamp, venue_stamp=None,
            external_id="0xspecimen", extra_metadata=None):
    """A market shaped like the row this path reads, and nothing more.

    `venue_stamp=None` writes NO key, which is the state of all four production
    specimens and of every row ingested before #4965's stamp existed.
    """
    metadata = dict(extra_metadata or {})
    if venue_stamp is not None:
        metadata["venue_game_start"] = venue_stamp
    return type("M", (), {
        "source": source,
        "external_id": external_id,
        "commence_time": listing_stamp,
        "market_metadata": metadata,
    })()


# ---------------------------------------------------------------------------
# 1. THE DEFECT.  The venue's instant wins over the listing stamp.
# ---------------------------------------------------------------------------


class TestTheVenueInstantIsPreferredOverTheListingStamp:
    @pytest.mark.parametrize("event_id,listing,fixture", SPECIMENS)
    def test_each_production_specimen_is_dated_from_the_start(
        self, event_id, listing, fixture
    ):
        market = _market(
            listing_stamp=listing, venue_stamp=fixture.isoformat().replace(
                "+00:00", "Z"
            ),
        )
        chosen, source = auto_create_commence_time(market, listing)

        assert chosen == fixture, (
            f"event {event_id} would be minted at the listing stamp, "
            f"{(fixture - listing).total_seconds() / 3600:.1f}h early"
        )
        assert source == POLYMARKET_VENUE_COMMENCE_SOURCE

    def test_the_fallback_is_ignored_even_when_the_caller_clamped_it_to_now(self):
        """The call site replaces an out-of-range `commence_time` with `now`
        before calling this ("the market is probably live"). #4242 measured what
        that costs. The venue's instant must beat that substitution too, not just
        the raw column — otherwise the arm only works on rows that were already
        nearly right.
        """
        fixture = datetime(2026, 9, 14, 13, 0, tzinfo=UTC)
        market = _market(
            listing_stamp=datetime(2023, 1, 1, tzinfo=UTC),
            venue_stamp="2026-09-14T13:00:00Z",
        )
        chosen, source = auto_create_commence_time(market, SHOT_AT)  # the clamp

        assert chosen == fixture
        assert source == POLYMARKET_VENUE_COMMENCE_SOURCE

    @pytest.mark.parametrize("raw,expected", [
        ("2026-09-14T13:00:00Z", datetime(2026, 9, 14, 13, 0, tzinfo=UTC)),
        ("2026-09-14T13:00:00+00:00", datetime(2026, 9, 14, 13, 0, tzinfo=UTC)),
        (datetime(2026, 9, 14, 13, 0, tzinfo=UTC),
         datetime(2026, 9, 14, 13, 0, tzinfo=UTC)),
        # Naive: the stamp is UTC by construction, so it is read as UTC rather
        # than refused — a refusal here would silently restore the defect.
        (datetime(2026, 9, 14, 13, 0), datetime(2026, 9, 14, 13, 0, tzinfo=UTC)),
    ])
    def test_every_shape_the_stamp_is_written_in_is_read(self, raw, expected):
        market = _market(
            listing_stamp=datetime(2026, 9, 14, 1, 59, 21, tzinfo=UTC),
            venue_stamp=raw,
        )
        chosen, _ = auto_create_commence_time(market, market.commence_time)
        assert chosen == expected

    def test_a_fixture_beyond_the_callers_thirty_day_clamp_is_not_flattened(self):
        """The ±30d clamp at the call site replaces a far value with `now`. A
        venue publishing a fixture 60 days out is publishing a real fixture 60
        days out, and flattening it to `now` is #4242's fabrication, not a cure
        for one. Deliberate, and asserted so it is not "tidied" into the clamp.
        """
        fixture = SHOT_AT + timedelta(days=60)
        market = _market(
            listing_stamp=SHOT_AT,
            venue_stamp=fixture.isoformat().replace("+00:00", "Z"),
        )
        chosen, source = auto_create_commence_time(market, SHOT_AT)

        assert chosen == fixture
        assert source == POLYMARKET_VENUE_COMMENCE_SOURCE


# ---------------------------------------------------------------------------
# 2. WHAT THE READER SAW.  The status door, driven with both values.
# ---------------------------------------------------------------------------


class TestTheHeroStopsSayingLIVEBeforeTheMatchExists:
    @pytest.mark.parametrize("event_id,listing,fixture", SPECIMENS)
    def test_the_listing_stamp_is_what_births_the_row_live(
        self, event_id, listing, fixture
    ):
        """BOTH DIRECTIONS, and this is the one that must stay red under a
        mutant: with the old value the door really does open onto `live` at the
        clock the screenshot was taken. A guard that only asserts the fixed side
        passes just as happily when the fix is deleted.
        """
        assert listing <= SHOT_AT < fixture, "specimen no longer straddles the shot"
        assert auto_create_status(listing, None, SHOT_AT) == "live"

    @pytest.mark.parametrize("event_id,listing,fixture", SPECIMENS)
    def test_the_venue_instant_leaves_the_row_scheduled(
        self, event_id, listing, fixture
    ):
        market = _market(
            listing_stamp=listing,
            venue_stamp=fixture.isoformat().replace("+00:00", "Z"),
        )
        chosen, source = auto_create_commence_time(market, listing)

        assert auto_create_status(chosen, source, SHOT_AT) == "scheduled", (
            f"event {event_id} still born live before its own start"
        )

    def test_and_it_is_still_live_once_the_venues_own_start_has_passed(self):
        """The other direction of the other direction. The fix is "read the right
        field", never "never say live": a match the venue started an hour ago is
        live, and a guard that cannot tell those apart has replaced one wrong
        badge with another.
        """
        fixture = SHOT_AT - timedelta(hours=1)
        market = _market(
            listing_stamp=SHOT_AT - timedelta(hours=12),
            venue_stamp=fixture.isoformat().replace("+00:00", "Z"),
        )
        chosen, source = auto_create_commence_time(market, market.commence_time)

        assert auto_create_status(chosen, source, SHOT_AT) == "live"


# ---------------------------------------------------------------------------
# 3. NO WIDENING.  Every population this arm must not touch.
# ---------------------------------------------------------------------------


class TestNothingElseMoves:
    @pytest.mark.parametrize("venue_stamp", [None, "", "   ", "not-a-date", 12345])
    def test_no_usable_stamp_is_exactly_todays_behaviour(self, venue_stamp):
        """A row ingested before the stamp existed, one the venue gives no start
        for, and an unparseable value are indistinguishable here, and all three
        must fall through rather than refuse. `venue_game_start` fails open for
        this reason; the arm inherits it.
        """
        listing = datetime(2026, 9, 14, 1, 59, 21, tzinfo=UTC)
        market = _market(listing_stamp=listing, venue_stamp=venue_stamp)

        assert auto_create_commence_time(market, listing) == (listing, None)

    def test_a_market_with_no_metadata_dict_at_all_falls_through(self):
        listing = datetime(2026, 9, 14, 1, 59, 21, tzinfo=UTC)
        market = type("M", (), {
            "source": "polymarket",
            "external_id": "0xspecimen",
            "commence_time": listing,
            "market_metadata": None,
        })()

        assert auto_create_commence_time(market, listing) == (listing, None)

    def test_kalshi_never_takes_this_arm_even_carrying_the_key(self):
        """Gated on the source, not on the key. `tasks.polymarket` is the only
        writer of that stamp, so a Kalshi row holding one is a data question, and
        Kalshi states its referent in the ticker — which the arm below must keep
        answering for it.
        """
        listing = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
        market = _market(
            source="kalshi",
            external_id="KXLOLGAME-26AUG210500GAMTSW",
            listing_stamp=listing,
            venue_stamp="2026-09-14T13:00:00Z",
        )
        chosen, source = auto_create_commence_time(market, listing)

        assert source == TICKER_DERIVED_COMMENCE_SOURCE
        assert chosen == datetime(2026, 8, 21, 5, 0, tzinfo=UTC)

    def test_the_ticker_arm_is_untouched(self):
        """#2020's specimen, re-run whole: ticker date 26AUG21 against a close
        time two days later. The new arm sits ABOVE this one in the function, so
        this is the assertion that it did not shadow it.
        """
        listing = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
        market = _market(
            source="kalshi",
            external_id="KXLOLGAME-26AUG210500GAMTSW",
            listing_stamp=listing,
        )
        chosen, source = auto_create_commence_time(market, listing)

        assert (chosen, source) == (
            datetime(2026, 8, 21, 5, 0, tzinfo=UTC), TICKER_DERIVED_COMMENCE_SOURCE,
        )

    def test_other_polymarket_metadata_keys_are_not_read_as_a_start(self):
        """The specimens' metadata holds `polymarket_event_id`, `matchup_title`,
        `clob_token_ids`, `content_understanding_v1` and `shape` — and neither
        `event_title` nor `venue_game_start`. None of those is a start time.
        """
        listing = datetime(2026, 9, 14, 1, 59, 21, tzinfo=UTC)
        market = _market(listing_stamp=listing, extra_metadata={
            "polymarket_event_id": "31456",
            "matchup_title": "Junior vs. Bruno",
            "clob_token_ids": ["0xa", "0xb"],
            "content_understanding_v1": {"sport": "tennis"},
            "shape": "game",
        })

        assert auto_create_commence_time(market, listing) == (listing, None)


# ---------------------------------------------------------------------------
# 4. THE PROVENANCE.  Honest about which field answered, and correctable.
# ---------------------------------------------------------------------------


class TestTheStampSaysWhichFieldAnsweredWithoutFreezingTheRow:
    def test_it_is_a_reported_start_because_the_venue_reported_it(self):
        """NOT in `DERIVED_COMMENCE_SOURCES`. That set means "nothing published
        one"; here the venue published exactly this, as a real time-of-day rather
        than a date resolved to midnight. Adding it there would refuse the clock
        on rows whose start we now know precisely — the defect inverted.
        """
        assert POLYMARKET_VENUE_COMMENCE_SOURCE not in DERIVED_COMMENCE_SOURCES
        assert commence_time_is_a_reported_start(
            POLYMARKET_VENUE_COMMENCE_SOURCE
        ) is True
        assert DERIVED_COMMENCE_SOURCES == frozenset({TICKER_DERIVED_COMMENCE_SOURCE})

    def test_it_carries_the_same_authority_as_polymarket_itself(self):
        """Same provider, same row: the string records WHICH field answered, not
        a promotion. Ranking it above `polymarket` would be a different change
        with a different blast radius.
        """
        assert (
            _SOURCE_PRIORITY[POLYMARKET_VENUE_COMMENCE_SOURCE]
            == _SOURCE_PRIORITY["polymarket"]
        )

    @pytest.mark.parametrize(
        "real", ["odds_api", "statpal", "espn", "mlb_schedule_repair"]
    )
    def test_every_real_schedule_still_outranks_it(self, real):
        """The row stays correctable. A venue's own fixture time is a good start,
        not a better one than the schedule's, and #2018's ladder is what lets
        ESPN/StatPal fix it.
        """
        assert (
            _SOURCE_PRIORITY[real]
            > _SOURCE_PRIORITY[POLYMARKET_VENUE_COMMENCE_SOURCE]
        )

    def test_it_is_IN_the_ladder_so_the_provider_can_revise_its_own_reading(self):
        """q066b's `same_record_revision` requires membership: it authorises a
        write only when `incoming_source == current_source` AND that source is in
        the ladder. An unlisted string ranks 0 just the same and reads as a
        no-op — while silently costing these rows the one path by which
        Polymarket corrects a start it published wrong.
        """
        from app.services.event_registry import commence_time_write_authorized

        authorized, reason = commence_time_write_authorized(
            POLYMARKET_VENUE_COMMENCE_SOURCE,
            POLYMARKET_VENUE_COMMENCE_SOURCE,
            same_record_revision=True,
        )
        assert authorized is True, reason

    def test_the_writer_stamps_the_literal_the_readers_import(self):
        """One string, three readers — asserted through the writer's real return
        value rather than by comparing two constants (q076's form).
        """
        fixture = datetime(2026, 9, 14, 13, 0, tzinfo=UTC)
        market = _market(
            listing_stamp=datetime(2026, 9, 14, 1, 59, 21, tzinfo=UTC),
            venue_stamp="2026-09-14T13:00:00Z",
        )
        _, source = auto_create_commence_time(market, market.commence_time)

        assert source == "polymarket_venue"
        assert source in _SOURCE_PRIORITY
        assert commence_time_is_a_reported_start(source) is True
        assert auto_create_status(fixture, source, SHOT_AT) == "scheduled"
