"""#3284 / CAL-P1016 — the sweep reads the games that have already been played.

The beat's FIRST unattended production run (2026-09-05 04:20Z) selected 500 rows,
wrote 125, and corrected **four** dead prices. Its ordering — `updated_at ASC` —
was chosen on the argument that the 2h open-market poll bumps that stamp only
while the venue still lists a market. Measured the same day, the stamp is
dominated by the poller's coverage instead: 237 of 8,879 open KX rows touched in
3 hours, 1,428 in 26. Two rows sampled from the stale band were genuinely active
at the venue and two had finalised days before; the stamp does not separate them.

The ticker's own `YYMONDD` segment does. Twelve rows sampled from that band and
checked against Kalshi's public API: 8 finalised with a `close_time` months
earlier than the date we store, 3 purged, 1 a season market whose ticker date is
its opener.

That last one is the whole reason these guards insist the band is an ORDER:

    a filter would wrongly exclude `KXMYSLGAME-26SEP04BRUJOH`;
    a sort merely mis-orders it, and it is still reached.

So the load-bearing guard here is not "the played game comes first" — it is
:meth:`TestTheBandIsAnOrderAndNotAFilter.test_the_band_changes_only_the_order`,
which proves the predicate is byte-identical to the one every CERT-766 /
CAL-P992 guard already validates. Everything else this file asserts is about
rank.

Clocks are literals (gotcha #44): the band is derived from a fixed `NOW`, never
from the wall clock, so these guards cannot flip with the calendar.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks import kalshi_resolution_sweep as sweep  # noqa: E402
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS  # noqa: E402

#: The instant the cohort was measured on production. A literal, never `now()`.
NOW = datetime(2026, 9, 5, 4, 20, tzinfo=timezone.utc)
PURGE_FLOOR = NOW - timedelta(days=PROVABLY_PURGED_AGE_DAYS)

CREATE_TABLE = """
    CREATE TABLE futures_markets (
        id INTEGER PRIMARY KEY,
        external_id TEXT,
        source TEXT,
        status TEXT,
        market_tier INTEGER,
        commence_time TEXT,
        resolution_date TEXT,
        expiration_time TEXT,
        updated_at TEXT
    )
"""

INSERT = """
    INSERT INTO futures_markets
        (id, external_id, source, status, market_tier, commence_time,
         resolution_date, expiration_time, updated_at)
    VALUES (:id, :external_id, 'kalshi', 'open', :market_tier, :commence_time,
            :resolution_date, NULL, :updated_at)
"""


def _seed(rows):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))
        for r in rows:
            conn.execute(text(INSERT), r)
    return engine


def _row(id_, external_id, *, updated_at, tier=5, commence=None):
    """One provisional row. `expiration_time` is NULL, so it is always eligible."""
    return {
        "id": id_,
        "external_id": external_id,
        "market_tier": tier,
        "commence_time": (commence or (NOW - timedelta(days=1))).isoformat(),
        "resolution_date": (NOW + timedelta(days=30)).isoformat(),
        "updated_at": updated_at.isoformat(),
    }


def _select(engine, *, limit=100, offset=0, now=NOW):
    tokens = sweep.past_event_band_tokens(now)
    sql = sweep.banded_select_sql(len(tokens))
    with engine.begin() as conn:
        rows = conn.execute(
            text(sql),
            {
                "purge_floor": PURGE_FLOOR.isoformat(),
                "limit": limit,
                "offset": offset,
                **sweep.band_bind_params(tokens),
            },
        ).all()
    return [r[1] for r in rows]


# --- the band's own arithmetic ----------------------------------------------


class TestTheBandNamesTheDaysTheVenueCanStillAnswerFor:
    def test_it_starts_yesterday_and_never_includes_today(self):
        """A game being played right now would only buy a backstop re-read.

        Strictly-before is also what the production measurement counted (604
        rows), so the band the guard describes is the band that was sized.
        """
        tokens = sweep.past_event_band_tokens(NOW)

        assert tokens[0] == "%-26SEP04%"
        assert "%-26SEP05%" not in tokens

    def test_it_stops_at_the_retention_bound_it_reads(self):
        """`PAST_EVENT_BAND_DAYS` is the measured constant, not a second number.

        A band wider than the venue's answer horizon promotes rows that cannot
        be written, which is the jam #2723 already names.
        """
        tokens = sweep.past_event_band_tokens(NOW)

        assert sweep.PAST_EVENT_BAND_DAYS == PROVABLY_PURGED_AGE_DAYS
        assert len(tokens) == PROVABLY_PURGED_AGE_DAYS
        oldest = (NOW.date() - timedelta(days=PROVABLY_PURGED_AGE_DAYS))
        assert tokens[-1] == f"%-{oldest.year % 100:02d}JUN{oldest.day:02d}%"

    def test_it_crosses_a_month_and_a_year_boundary(self):
        """January 2nd must reach back into the previous December and year.

        An off-by-one in the year rolls the whole band onto tickers that do not
        exist, and the sweep would silently rank nothing — a band that matches
        no row is indistinguishable from no band at all.

        17:00Z is midday in Eastern, so this instant is January 2nd on BOTH
        calendars and the guard measures the year roll alone. Midnight UTC would
        have measured the year roll and the timezone at once, and a failure
        could not say which.
        """
        tokens = sweep.past_event_band_tokens(
            datetime(2027, 1, 2, 17, 0, tzinfo=timezone.utc), days=3
        )

        assert tokens == ["%-27JAN01%", "%-26DEC31%", "%-26DEC30%"]

    def test_the_python_and_sql_readings_agree_on_a_real_ticker(self):
        """`row_is_in_band` reports the batch; the SQL ranks it. One answer.

        These are two spellings of one membership test, and the run's own
        `candidates_in_band` is only auditable if they cannot disagree.
        """
        tokens = sweep.past_event_band_tokens(NOW)
        engine = _seed(
            [
                _row(1, "KXNCAAF1H-26SEP04UTEPOKLA", updated_at=NOW),
                _row(2, "KXMIDTERMVOTETURN-AKSEN", updated_at=NOW - timedelta(days=60)),
            ]
        )

        # SQL ranks the played game first despite the far older stamp on the other.
        assert _select(engine)[0] == "KXNCAAF1H-26SEP04UTEPOKLA"
        assert sweep.row_is_in_band("KXNCAAF1H-26SEP04UTEPOKLA", tokens) is True
        assert sweep.row_is_in_band("KXMIDTERMVOTETURN-AKSEN", tokens) is False


# --- the load-bearing property ----------------------------------------------


class TestTheBandIsAnOrderAndNotAFilter:
    def test_the_band_changes_only_the_order(self):
        """THE guard. Everything before the ORDER BY is byte-identical.

        `banded_select_sql` is surgery on `SELECT_SQL`, so this cannot be
        satisfied by a copy that happens to look the same today. If anyone ever
        adds a band term to the predicate — the tempting, wrong version of this
        change — this reds immediately and by name.
        """
        banded = sweep.banded_select_sql(12)

        assert banded.partition("ORDER BY")[0] == sweep.SELECT_SQL.partition("ORDER BY")[0]
        assert "WHERE" in banded.partition("ORDER BY")[0]

    def test_the_season_market_whose_ticker_lies_is_still_selected(self):
        """`KXMYSLGAME-26SEP04BRUJOH` — the venue says active until 2027-02-21.

        1 of the 12 sampled rows. Under a FILTER on the band it would be
        promoted into a batch it cannot satisfy AND the rows behind it would be
        starved; under a SORT it is simply read early, told the backstop, and
        rotated. Either way it must still appear.
        """
        engine = _seed(
            [
                _row(1, "KXMYSLGAME-26SEP04BRUJOH", updated_at=NOW),
                _row(2, "KXMIDTERMVOTETURN-AKSEN", updated_at=NOW),
            ]
        )

        assert set(_select(engine)) == {
            "KXMYSLGAME-26SEP04BRUJOH",
            "KXMIDTERMVOTETURN-AKSEN",
        }

    def test_no_row_is_lost_when_the_band_matches_nothing(self):
        """A population with no dated tickers must select exactly as before.

        The band is additive or it is a regression; an empty band has to be a
        no-op, not an empty result.
        """
        engine = _seed(
            [
                _row(1, "KXMIDTERMVOTETURN-AKSEN", updated_at=NOW - timedelta(days=2)),
                _row(2, "KXNCAAMBMVAL-27", updated_at=NOW - timedelta(days=1)),
            ]
        )
        tokens = sweep.past_event_band_tokens(NOW)

        with engine.begin() as conn:
            plain = [
                r[1]
                for r in conn.execute(
                    text(sweep.SELECT_SQL),
                    {"purge_floor": PURGE_FLOOR.isoformat(), "limit": 100, "offset": 0},
                ).all()
            ]

        assert _select(engine) == plain
        assert all(not sweep.row_is_in_band(t, tokens) for t in plain)

    def test_an_empty_band_leaves_the_inherited_ordering_untouched(self):
        """`days=0` must produce a legal, neutral sort key, not a broken CASE.

        The zero case is reachable: it is what a future caller passing a
        narrowed band gets, and a `CASE` with no arms is a syntax error rather
        than a quiet no-op.

        It must also not be the OBVIOUS neutral key. The first version of this
        returned the literal ``0``, and the execution below is what caught it:
        a bare integer in an ORDER BY is an ordinal column reference in both
        SQLite and Postgres, so `ORDER BY 0` raises "term out of range". The
        constant is asserted here so a future simplification back to ``0``
        cannot pass on the string test alone.
        """
        assert sweep.band_rank_sql(0) == "NULL"

        engine = _seed([_row(1, "KXNCAAF1H-26SEP04UTEPOKLA", updated_at=NOW)])
        with engine.begin() as conn:
            rows = conn.execute(
                text(sweep.banded_select_sql(0)),
                {"purge_floor": PURGE_FLOOR.isoformat(), "limit": 10, "offset": 0},
            ).all()

        assert [r[1] for r in rows] == ["KXNCAAF1H-26SEP04UTEPOKLA"]


# --- the rank, on the shape the population actually has ---------------------


class TestThePlayedGameIsReachedFirst:
    def test_a_played_game_outranks_a_whole_batch_of_fresher_rows(self):
        """The production shape: the band is a few hundred rows in ~7,000.

        Seeded so the played game has the NEWEST stamp of all — under the
        inherited `updated_at ASC` it sorts dead last and a 10-row batch never
        reaches it. That is the fortnight of dead price, reproduced.
        """
        rows = [
            _row(i, f"KXMIDTERMMOV-CO{i:02d}D", updated_at=NOW - timedelta(days=60 + i))
            for i in range(1, 30)
        ]
        rows.append(_row(9001, "KXSVKCUPGAME-26SEP02DVLDDS", updated_at=NOW))
        engine = _seed(rows)

        with engine.begin() as conn:
            inherited = [
                r[1]
                for r in conn.execute(
                    text(sweep.SELECT_SQL),
                    {"purge_floor": PURGE_FLOOR.isoformat(), "limit": 10, "offset": 0},
                ).all()
            ]
        assert "KXSVKCUPGAME-26SEP02DVLDDS" not in inherited  # the defect

        assert _select(engine, limit=10)[0] == "KXSVKCUPGAME-26SEP02DVLDDS"

    def test_the_most_recent_game_leads_the_band(self):
        """Graded, not binary — and this is the guard that says why.

        Under a binary rank the inherited `updated_at ASC` tie-break decides
        within the band, which sorts the oldest stamps first; measured at the
        venue, that head was 7 purged rows of 14. Recency has to be the band's
        own ordering, because the venue's ability to answer decays with the age
        of the game and nothing else in the row tracks that.
        """
        engine = _seed(
            [
                _row(1, "KXOLD-26AUG20AAA", updated_at=NOW - timedelta(days=90)),
                _row(2, "KXNEW-26SEP04BBB", updated_at=NOW),
                _row(3, "KXMID-26SEP01CCC", updated_at=NOW - timedelta(days=45)),
            ]
        )

        assert _select(engine) == [
            "KXNEW-26SEP04BBB",
            "KXMID-26SEP01CCC",
            "KXOLD-26AUG20AAA",
        ]

    def test_within_one_day_the_inherited_ordering_still_decides(self):
        """The band is a PREFIX, not a replacement — rotation must survive.

        `updated_at ASC` is what makes a written row rotate to the back of its
        own day; if the band replaced the inherited keys outright, the cursor's
        "a clean batch holds its offset" contract would break and the head would
        jam. Same ticker date on all three, so only the tie-break can order them.
        """
        engine = _seed(
            [
                _row(1, "KXECULPGAME-26SEP03UNISDA", updated_at=NOW),
                _row(2, "KXCOPPAITALIAGAME-26SEP03CAGVER", updated_at=NOW - timedelta(days=4)),
                _row(3, "KXALLSVENSKANGAME-26SEP03MJADJU", updated_at=NOW - timedelta(days=2)),
            ]
        )

        assert _select(engine) == [
            "KXCOPPAITALIAGAME-26SEP03CAGVER",
            "KXALLSVENSKANGAME-26SEP03MJADJU",
            "KXECULPGAME-26SEP03UNISDA",
        ]

    def test_every_band_row_outranks_every_row_outside_it(self):
        """The `ELSE` arm must exceed the largest rank, not tie with it.

        `ELSE n_tokens` is one past the last index. An `ELSE` that reused the
        final index would interleave the oldest band day with the entire undated
        population, and the oldest band day is the least answerable — the exact
        rows the grading exists to push back.
        """
        oldest = NOW.date() - timedelta(days=PROVABLY_PURGED_AGE_DAYS)
        engine = _seed(
            [
                _row(1, "KXMIDTERMVOTETURN-AKSEN", updated_at=NOW - timedelta(days=90)),
                _row(2, f"KXEDGE-{oldest.year % 100:02d}JUN{oldest.day:02d}ZZZ", updated_at=NOW),
            ]
        )

        assert _select(engine)[0].startswith("KXEDGE-")

    def test_a_game_older_than_the_venue_can_answer_is_not_promoted(self):
        """Beyond the retention bound the venue returns no markets (#2723).

        Three of the twelve sampled rows were exactly this. Promoting them would
        spend the batch on rows that can never be written — the jam the band
        exists to step around, rebuilt inside the band itself.
        """
        stale = NOW.date() - timedelta(days=PROVABLY_PURGED_AGE_DAYS + 30)
        old_ticker = f"KXEARNINGSMENTIONABNB-{stale.year % 100:02d}MAY{stale.day:02d}"
        engine = _seed(
            [
                _row(1, old_ticker, updated_at=NOW - timedelta(days=90)),
                _row(2, "KXATPCHALLENGERMATCH-26SEP04SIMLEO", updated_at=NOW),
            ]
        )

        assert _select(engine)[0] == "KXATPCHALLENGERMATCH-26SEP04SIMLEO"

    def test_the_band_survives_the_offset_the_cursor_carries(self):
        """The cursor pages within the new order, so page two is still band-first.

        A band that only worked at offset 0 would be a band the beat sees once
        per cycle, which is the fortnight again.
        """
        rows = [
            _row(i, f"KXCOPPAITALIAGAME-26SEP03X{i:03d}", updated_at=NOW - timedelta(hours=i))
            for i in range(1, 6)
        ]
        rows += [
            _row(100 + i, f"KXMIDTERMMOV-CO{i:02d}D", updated_at=NOW - timedelta(days=90))
            for i in range(1, 4)
        ]
        engine = _seed(rows)
        tokens = sweep.past_event_band_tokens(NOW)

        page_two = _select(engine, limit=3, offset=3)

        # Two band rows remain at offset 3; the undated tail begins after them.
        assert sum(1 for t in page_two if sweep.row_is_in_band(t, tokens)) == 2


# --- what the run reports ----------------------------------------------------


class TestTheRunSaysHowMuchOfItsBatchTheBandSupplied:
    @pytest.mark.asyncio
    async def test_the_summary_carries_the_band_numbers(self):
        """`band_days` and `candidates_in_band`, beside `newly_past`.

        Without them the next reader has to re-derive the cohort against
        production to know whether the reorder paid out, which is how a shipped
        ordering goes a fortnight without anyone noticing it stopped matching.
        """
        report = await _run_against(
            ["KXNCAAF1H-26SEP04UTEPOKLA", "KXMIDTERMVOTETURN-AKSEN"]
        )

        assert report["stats"]["band_days"] == PROVABLY_PURGED_AGE_DAYS
        assert report["stats"]["candidates_in_band"] == 1
        assert report["stats"]["candidates"] == 2

    @pytest.mark.asyncio
    async def test_the_band_binds_reach_the_driver_with_the_select(self):
        """The rank is useless if the tokens never leave the process.

        A `LIKE :band_0` with no `band_0` bound is a runtime error in Postgres
        and an unranked batch in anything that tolerates it, so assert on the
        parameters the statement actually carried.
        """
        report = await _run_against(["KXNCAAF1H-26SEP04UTEPOKLA"])
        select_sql, params = report["_statements"][0]

        assert "CASE WHEN external_id LIKE :band_0" in select_sql
        assert params["band_0"] == "%-26SEP04%"
        assert len([k for k in params if k.startswith("band_")]) == PROVABLY_PURGED_AGE_DAYS

    @pytest.mark.asyncio
    async def test_a_batch_with_no_band_rows_reports_zero_not_absent(self):
        """A missing key and a measured zero are not the same fact (gotcha #53).

        The band draining to zero is the correct steady state, and it has to be
        legible as one rather than as a field that stopped being written.
        """
        report = await _run_against(["KXMIDTERMVOTETURN-AKSEN"])

        assert report["stats"]["candidates_in_band"] == 0
        assert report["stats"]["band_days"] == PROVABLY_PURGED_AGE_DAYS


# --- the band's calendar is the venue's, not UTC's (CERT-1939 follow-up) ------
#
# The beat fires at 04:20Z. That instant reads as two different days depending
# on the season:
#
#     EDT (summer)   04:20Z = 00:20 ET the SAME day   -> the two agree
#     EST (winter)   04:20Z = 23:20 ET the day BEFORE -> UTC is one day ahead
#
# So a UTC reading of "strictly before today" admits the Eastern day that is
# still being played, and it admits it at RANK 0. Measured on production
# 2026-09-05, that day is the largest cohort in the band — 785 eligible rows on
# `26SEP05` against 212 on the finished `26SEP04` — so it would fill the whole
# 500-row batch with unfinished games and the batch would never reach a played
# day. That is the starvation CAL-P992 measured, re-created by the ordering
# built to end it, arriving on 2026-11-01 with no commit to blame.
#
# WINTER_NOW is the same beat, on the other side of the DST change.

WINTER_NOW = datetime(2026, 11, 15, 4, 20, tzinfo=timezone.utc)  # = 23:20 EST 11-14


class TestTheBandReadsTheVenuesDayAndNotUTCs:
    def test_the_winter_beat_does_not_promote_the_day_still_being_played(self):
        """23:20 ET on the 14th must not call the 14th a played day."""
        tokens = sweep.past_event_band_tokens(WINTER_NOW)

        assert tokens[0] == "%-26NOV13%"
        assert "%-26NOV14%" not in tokens

    def test_the_summer_beat_is_exactly_what_was_measured(self):
        """The fix must be a NO-OP on the clock the 604-row cohort was sized on.

        Both readings agree under EDT. If this moves, the production proof in
        CAL-P1016's report no longer describes the code.
        """
        assert sweep.past_event_band_tokens(NOW)[0] == "%-26SEP04%"

    @pytest.mark.parametrize(
        "beat,expected_first",
        [
            (datetime(2026, 9, 5, 4, 20, tzinfo=timezone.utc), "%-26SEP04%"),
            (datetime(2026, 10, 31, 4, 20, tzinfo=timezone.utc), "%-26OCT30%"),
            (datetime(2026, 11, 1, 4, 20, tzinfo=timezone.utc), "%-26OCT31%"),
            (datetime(2026, 11, 2, 4, 20, tzinfo=timezone.utc), "%-26OCT31%"),
            (datetime(2026, 11, 15, 4, 20, tzinfo=timezone.utc), "%-26NOV13%"),
        ],
    )
    def test_the_newest_token_is_always_eastern_yesterday(self, beat, expected_first):
        """Five consecutive 04:20Z beats across the 2026-11-01 DST change.

        The load-bearing pair is 11-01 and 11-02: the UTC date advances by a day
        but the Eastern day does not, because the clock fell back an hour in
        between, so the band correctly repeats. A conversion that subtracted a
        FIXED four hours would read 11-02 as Eastern November 2nd and promote
        the whole of November 1st's evening — every game of it still in play at
        23:20 ET. Only a real timezone gets both rows right.
        """
        assert sweep.past_event_band_tokens(beat)[0] == expected_first

    def test_a_naive_clock_is_read_as_utc_and_not_as_local(self):
        """A naive datetime must not silently take the runner's own timezone.

        The developer machines in this program run on EDT while production runs
        on UTC, so a naive instant interpreted locally would give the guards one
        band and the beat another.
        """
        naive = WINTER_NOW.replace(tzinfo=None)

        assert sweep.past_event_band_tokens(naive) == sweep.past_event_band_tokens(
            WINTER_NOW
        )

    @pytest.mark.parametrize("unreadable", [None, "last tuesday", 1763180400])
    def test_it_refuses_a_clock_it_cannot_read_and_says_so(self, unreadable):
        """An unreadable clock must not degrade into an empty band.

        `band_rank_sql(0)` is `NULL`, i.e. the inherited ordering — so a caller
        that passed the wrong thing would not fail, it would quietly un-ship the
        band and nothing in the run's summary would look wrong. Raise instead.

        The MESSAGE is asserted, not just the type. Letting the bad value fall
        through to `today - timedelta(...)` also raises `TypeError`, so a guard
        on the type alone passes either way — and the beat's operator would get
        "unsupported operand type(s) for -" from inside a loop instead of a
        sentence naming the clock. A mutant that removed the explicit raise
        survived this file until this assertion was added.
        """
        with pytest.raises(TypeError, match="needs a datetime to read the venue's day"):
            sweep.past_event_band_tokens(unreadable)

    def test_an_iso_string_is_read_rather_than_refused(self):
        """Pinning what the shared helper actually tolerates, so nobody re-adds it.

        `eastern_game_date` parses ISO strings, and reusing it means this does
        too. That is harmless — it is the same instant — but it means the
        refusal above is about UNREADABLE input, not about type purity, and a
        future reader must not "tighten" it into rejecting the string form.
        """
        assert sweep.past_event_band_tokens(
            WINTER_NOW.isoformat()
        ) == sweep.past_event_band_tokens(WINTER_NOW)


class TestTheWinterBatchStillLeadsWithAPlayedGame:
    def test_the_in_progress_eastern_day_never_outranks_the_finished_one(self):
        """The ship, end to end, through the real SQL at the winter instant."""
        engine = _seed(
            [
                # In progress at 23:20 ET on the 14th, and the freshest stamp,
                # so under the inherited ordering alone it would sort LAST —
                # only a band that wrongly contains it can promote it.
                _row(1, "KXNFLGAME-26NOV14BUFMIA", updated_at=WINTER_NOW),
                _row(2, "KXNFLGAME-26NOV13NYJNE", updated_at=WINTER_NOW),
            ]
        )

        order = _select(engine, now=WINTER_NOW)

        assert order[0] == "KXNFLGAME-26NOV13NYJNE"

    @pytest.mark.asyncio
    async def test_the_run_does_not_count_the_unfinished_day_as_band_supply(self):
        """`candidates_in_band` is the number the post-deploy check reads.

        If the in-progress day counted, a batch of unfinished games would report
        as a fully-banded run and the yield collapse would look like a venue
        problem rather than an ordering one.
        """
        report = await _run_against(
            ["KXNFLGAME-26NOV14BUFMIA", "KXNFLGAME-26NOV13NYJNE"], now=WINTER_NOW
        )

        assert report["stats"]["candidates_in_band"] == 1

    @pytest.mark.asyncio
    async def test_the_retention_floor_stays_on_the_utc_clock(self):
        """Only the CALENDAR moved. The floor is an age, not a date.

        Pushing the Eastern reading into `purge_floor` too would shift the whole
        eligibility window by up to five hours against a constant that was
        measured in absolute time (`PROVABLY_PURGED_AGE_DAYS`).
        """
        report = await _run_against(["KXNFLGAME-26NOV13NYJNE"], now=WINTER_NOW)
        _, params = report["_statements"][0]

        assert params["purge_floor"] == WINTER_NOW - timedelta(
            days=PROVABLY_PURGED_AGE_DAYS
        )


class TestTheCursorDoesNotSurviveTheReorder:
    def test_the_cursor_key_is_versioned(self):
        """An offset is a position in an order; the order changed.

        Resuming `375` under the new ordering would skip an arbitrary slice of
        the population on the first run after deploy, and nothing in the summary
        would say so.
        """
        assert sweep.SWEEP_CURSOR_KEY.endswith(":v2")
        assert sweep.SWEEP_CURSOR_KEY != "bainluck:kalshi_resolution_sweep:offset"


# --- driving the real composed path against the seeded table ----------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Answers the two reads by shape and records what reached the driver.

    A fake rather than an in-memory engine, matching
    `test_kalshi_resolution_backfill_script_989.py`: the point here is that the
    band's binds travel with the statement and that the REPORT is computed from
    the rows, and a fake makes both observable. The ordering itself is proved
    against real SQL by the SQLite guards above.
    """

    def __init__(self, recorder, rows, totals):
        self._recorder = recorder
        self._rows = rows
        self._totals = totals

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self._recorder.append((sql, params))
        if "count(*)" in sql:
            return _FakeResult([self._totals])
        return _FakeResult(self._rows)

    async def commit(self):
        return None


async def _run_against(tickers, *, limit=100, now=NOW):
    """`run_backfill` over the given tickers with a venue that answers nothing.

    The venue is deliberately barren: this file measures SELECTION and the
    REPORT, and a venue that returned dates would let a write hide a mis-ranked
    batch behind a plausible-looking total.
    """
    recorder: list = []
    rows = [(i + 1, t, None, None, 5) for i, t in enumerate(tickers)]
    totals = (len(tickers), 0, len(tickers), 0)

    class _Venue:
        async def get_event(self, ticker, with_nested_markets=True):
            return {"markets": []}

        async def close(self):
            return None

    report = await sweep.run_backfill(
        session_maker=lambda: _FakeSession(recorder, rows, totals),
        client_factory=_Venue,
        limit=limit,
        offset=0,
        apply=False,
        now=now,
    )
    report["_statements"] = recorder
    return report
