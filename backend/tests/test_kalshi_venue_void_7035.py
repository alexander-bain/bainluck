"""#7035 — a postponed game stops being indistinguishable from an ungraded one.

WHAT A READER SEES, AND WHY IT NEVER CHANGES
--------------------------------------------

``/sport/soccer/laliga`` carries a card reading **"No result reported · Sep 16",
Levante v Bilbao**. The game was never played: it was postponed to Oct 21, and
the same page shows Athletic Bilbao playing Alavés three days later. The card is
not stale, it is FALSE, and nothing in the product can currently find that out.

Event ``15312871`` holds four Kalshi families, every one ``status='resolved'``
with every ``is_winner`` NULL. ``kalshi_resolution_sweep`` read
``market["status"]`` and never ``market["result"]``, so "the venue settled this"
and "the venue voided this" collapsed into one word.

🔴 WHY OUR OWN GRADING STATE CANNOT ANSWER IT — THE MEASUREMENT THAT PICKED THIS
DESIGN. The cheap reading is "every family resolved and no leg graded", which
needs no venue read. Measured on production 2026-09-22 over ``suspended`` past
events carrying Kalshi families, 14 days::

    all families resolved, >=1 leg graded   1,434
    all families resolved, 0 legs graded       77

77 looks like a clean population until it is split by age::

    age        graded   ungraded   ungraded %
    <24h          149         18        10.8
    1-3d          473         28         5.6
    3-7d          465         22         4.5
    >7d           347          9         2.5

**The ungraded fraction decays with age.** A stable void population cannot do
that — a void is never graded later, so it accumulates. A grading LAG does
exactly this, and it is worst on the freshest rows, which are the ones a reader
is looking at. So our own grading state confounds "the venue voided it" with "we
have not got to it yet". The venue's ``result`` has no lag.

THE VENUE'S OWN WORDS, READ 2026-09-22 (notice 26 — the venue, not our mirror)::

    KXLALIGAGAME-26SEP16LEVATH        3 legs, all finalized, all result='scalar'
    KXBUNDESLIGASCORE-26SEP12SCFBMG  30 legs, all finalized, result 'no'/'yes'

The postponed fixture's three legs settled $0.29 / $0.43 / $0.28 — summing to
1.00, because each paid its own last trading price. The ticker's own
``rules_secondary`` says when that happens: *"If the game is cancelled or
rescheduled to over 48 hours away, the market will resolve to a fair price."*
Those two payloads are the fixtures below, and neither was invented from the
code it tests (a hand-built fake made from the code cannot disagree with it).

WHAT THIS FILE HOLDS
--------------------

1. :func:`derive_venue_void` — the pure read, with the played payload as a
   standing CONTROL and every refusal stated as its own case.
2. The composed path: a voided event reaches a ``market_metadata`` write, and
   the graded control reaches NO such write at all.
3. The #1852 boundary, asserted against the statement text: the void write
   carries no grade, no status and no price. A void says the venue named NO
   outcome, which is the opposite of a winner.

CLOCK DISCIPLINE (gotcha #44). ``run_backfill`` takes ``now`` as a parameter and
every fixture pins it to a literal, so no assertion here can flip with the
calendar.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import kalshi_resolution_sweep as sweep
from app.tasks.kalshi_resolution_sweep import UPDATE_SQL, VOID_UPDATE_SQL
from app.utils.kalshi_resolution_window import (
    VENUE_UNGRADED_RESULTS,
    derive_venue_void,
)

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(days=30)
_FUTURE_ISO = FUTURE.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# The two real payloads, reduced to the fields this rail reads
# ---------------------------------------------------------------------------

#: ``KXLALIGAGAME-26SEP16LEVATH`` — the postponed fixture. Three legs, every one
#: finalized at a fair price and graded on nothing.
VOIDED_LEGS = [
    {
        "ticker": f"KXLALIGAGAME-26SEP16LEVATH-{side}",
        "status": "finalized",
        "result": "scalar",
        "close_time": _FUTURE_ISO,
        "expiration_time": _FUTURE_ISO,
    }
    for side in ("LEV", "ATH", "TIE")
]

#: ``KXBUNDESLIGASCORE-26SEP12SCFBMG`` — the played control, trimmed to six legs
#: with the winner where the real payload has it: NOT first. A rule that stopped
#: at the first leg would pass on a three-leg trim and fail here.
PLAYED_LEGS = [
    {
        "ticker": f"KXBUNDESLIGASCORE-26SEP12SCFBMG-L{i}",
        "status": "finalized",
        "result": "yes" if i == 4 else "no",
        "close_time": _FUTURE_ISO,
        "expiration_time": _FUTURE_ISO,
    }
    for i in range(6)
]


def _split(legs):
    return [m.get("status") for m in legs], [m.get("result") for m in legs]


class TestThePureRead:
    """``derive_venue_void`` — the venue's word, and every refusal."""

    def test_the_postponed_fixture_is_a_void(self):
        void = derive_venue_void(*_split(VOIDED_LEGS))
        assert void.voided is True
        assert void.reason == "voided_ungraded"
        assert (void.legs_total, void.legs_graded) == (3, 0)

    def test_the_played_control_is_not(self):
        """🔴 THE CONTROL. If this ever answers True the ship hides real games."""
        void = derive_venue_void(*_split(PLAYED_LEGS))
        assert void.voided is False
        assert void.reason == "graded"

    def test_a_no_is_a_grade_so_an_all_no_event_is_not_a_void(self):
        """Six legs, none of them won, and the event was still DECIDED.

        The real Bundesliga payload is 30 legs of which 29 read ``no`` — an
        exact-score market has one winner and a crowd of losers. A rule that
        read "graded" as "somebody won" would void every one of them.
        """
        statuses, results = _split(PLAYED_LEGS)
        void = derive_venue_void(statuses, ["no"] * len(results))
        assert void.voided is False
        assert void.legs_graded == len(results)

    def test_an_event_the_venue_has_not_finished_is_never_a_void(self):
        statuses, results = _split(VOIDED_LEGS)
        void = derive_venue_void(["active"] * 3, results)
        assert (void.voided, void.reason) == (False, "not_settled")

    def test_a_partially_settled_event_is_never_a_void(self):
        """One leg still trading. A void is not knowable until the venue is done."""
        void = derive_venue_void(
            ["finalized", "active", "finalized"], ["scalar", None, "scalar"]
        )
        assert (void.voided, void.reason) == (False, "not_settled")

    def test_a_missing_result_on_a_terminal_leg_refuses(self):
        """``None`` is "we did not read it", not "the venue declined to say"."""
        void = derive_venue_void(["finalized", "finalized"], ["scalar", None])
        assert (void.voided, void.reason) == (False, "result_absent")

    def test_a_dormant_leg_carries_no_result_and_does_not_vote(self):
        """#5024's dormant legs are dropped before the result test, not counted.

        An ``inactive`` leg never becomes terminal and never carries a result.
        Counting its absent result as ``result_absent`` would refuse every void
        on a venue that lists one; counting it as ungraded would let it vote FOR
        a void. It does neither.
        """
        void = derive_venue_void(
            ["finalized", "inactive", "finalized"], ["scalar", None, "scalar"]
        )
        assert (void.voided, void.reason) == (True, "voided_ungraded")

    def test_a_dormant_leg_does_not_rescue_a_graded_event(self):
        void = derive_venue_void(
            ["finalized", "inactive", "finalized"], ["yes", None, "no"]
        )
        assert (void.voided, void.reason) == (False, "graded")

    def test_an_event_of_nothing_but_dormant_legs_is_refused(self):
        void = derive_venue_void(["inactive", "inactive"], [None, None])
        assert (void.voided, void.reason) == (False, "not_settled")

    def test_no_legs_is_a_response_shape_not_a_void(self):
        """Gotcha #53: a 200 with no markets is not a fact about settlement."""
        assert derive_venue_void([], []).voided is False

    def test_mismatched_inputs_refuse_rather_than_zip_short(self):
        """``zip`` would silently drop the extra leg and answer on a subset."""
        void = derive_venue_void(["finalized", "finalized"], ["scalar"])
        assert (void.voided, void.reason) == (False, "mismatched_inputs")

    @pytest.mark.parametrize("word", sorted(VENUE_UNGRADED_RESULTS))
    def test_every_ungraded_word_reads_as_a_void(self, word):
        void = derive_venue_void(["finalized"] * 2, [word] * 2)
        assert void.voided is True

    def test_the_words_are_compared_case_and_space_insensitively(self):
        void = derive_venue_void(["FINALIZED", " finalized "], [" Scalar ", "SCALAR"])
        assert void.voided is True


# ---------------------------------------------------------------------------
# The composed path
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        """#7035's retirement phase reads its screen through `.scalars()`.

        Added when the consumer was composed into `run_resolved_voids`, and it
        answers with the SAME rows rather than an empty list on purpose: a
        double that hard-codes "no candidates" for the retirement screen would
        make every arm in `TestTheCaptureSpendsTheFactItWrote` pass whether the
        phase ran or not. The retirement's own behaviour is proved on a real
        Postgres in `tests/integration/test_venue_void_retirement_pg.py`; what
        these arms prove is that it is REACHED.
        """
        return _FakeScalars(self._rows)


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Records every statement and its parameters, in order."""

    def __init__(self, recorder, rows, totals):
        self._recorder = recorder
        self._rows = rows
        self._totals = totals
        self.committed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        sql = str(statement)
        self._recorder.append((sql, params))
        if "count(" in sql.lower() and params and "purge_floor" in params:
            return _FakeResult([self._totals])
        if sql.strip().upper().startswith("UPDATE"):
            return _FakeResult([])
        return _FakeResult(self._rows)

    async def commit(self):
        self.committed += 1


class _Venue:
    def __init__(self, legs):
        self._legs = legs
        self.asked: list[str] = []

    async def get_event(self, ticker, with_nested_markets=True):
        self.asked.append(ticker)
        return {"markets": [dict(leg) for leg in self._legs]}

    async def close(self):
        return None


ROW = (
    77001,
    "KXLALIGAGAME-26SEP16LEVATH",
    FUTURE,
    NOW - timedelta(days=6),
    5,
)


def _drive(legs, *, apply=True):
    recorder: list = []
    venue = _Venue(legs)

    def maker():
        return _FakeSession(recorder, [ROW], (1, 0, 0, 1, 0))

    report = asyncio.run(
        sweep.run_backfill(
            session_maker=maker,
            client_factory=lambda: venue,
            limit=500,
            apply=apply,
            now=NOW,
        )
    )
    voids = [p for s, p in recorder if "market_metadata" in s]
    return report, voids


class TestTheComposedPath:
    def test_a_voided_event_reaches_a_metadata_write(self):
        report, voids = _drive(VOIDED_LEGS)

        stats = report["stats"]
        assert stats["venue_voided"] == 1
        assert stats["void_writes_applied"] == 1
        assert [v["id"] for v in voids] == [77001]

    def test_the_void_is_a_subset_of_the_settlement_never_a_sibling(self):
        """A void is a settlement the venue declined to grade.

        If this ever reads ``venue_settled == 0`` while ``venue_voided == 1``
        the two derivations have drifted apart and the void is being claimed
        for an event the sweep does not consider over.
        """
        report, _ = _drive(VOIDED_LEGS)
        assert report["stats"]["venue_settled"] == 1
        assert report["stats"]["venue_voided"] == 1

    def test_the_played_control_reaches_no_metadata_write_at_all(self):
        """🔴 THE CONTROL, at the composed layer."""
        report, voids = _drive(PLAYED_LEGS)

        assert report["stats"]["venue_settled"] == 1, (
            "RED-FIRST ANCHOR: the control must still SETTLE, or it is not "
            "exercising the branch the void test sits inside and this class "
            "would pass with the void read deleted."
        )
        assert report["stats"]["venue_voided"] == 0
        assert report["stats"]["void_writes_applied"] == 0
        assert voids == []

    def test_a_dry_run_writes_nothing(self):
        report, voids = _drive(VOIDED_LEGS, apply=False)
        assert report["stats"]["venue_voided"] == 1, (
            "the READ still happens on a dry run — that is what makes the "
            "report auditable before anything is written"
        )
        assert report["stats"]["void_writes_applied"] == 0
        assert voids == []

    def test_the_report_names_the_ticker_so_the_claim_is_checkable(self):
        report, _ = _drive(VOIDED_LEGS)
        samples = report["venue_voided_samples"]
        assert [s["ticker"] for s in samples] == ["KXLALIGAGAME-26SEP16LEVATH"]

    def test_an_unreadable_result_is_counted_loudly_not_silently_skipped(self):
        """Gotcha #53 — a run that voids nothing must say WHY it voided nothing."""
        legs = [dict(leg) for leg in VOIDED_LEGS]
        legs[1].pop("result")
        report, voids = _drive(legs)

        assert report["stats"]["venue_voided"] == 0
        assert report["stats"]["void_refused_result_absent"] == 1
        assert voids == []


class TestTheGradeBoundary:
    """#1852's line, held against the statement text."""

    def test_the_void_write_touches_market_metadata_and_nothing_else(self):
        assignments = VOID_UPDATE_SQL.split("SET", 1)[1].split("WHERE", 1)[0]
        assert assignments.count("=") >= 1
        for column in (
            "status",
            "settled_at",
            "resolution_date",
            "is_winner",
            "current_probability",
            "expiration_time",
        ):
            assert f"{column} =" not in assignments, (
                f"the void write must not assign {column}: a void is a status "
                "fact about the VENUE, and every one of these belongs to a "
                "different rail"
            )

    def test_the_void_write_writes_no_grade(self):
        lowered = VOID_UPDATE_SQL.lower()
        for word in (
            "is_winner",
            "winner",
            "resolution_source",
            "probability",
            "price",
            "yes",
            "no'",
        ):
            assert word not in lowered, (
                f"#1852: {word!r} appears in the void statement. A void says "
                "the venue named NO outcome; it must never be readable as one."
            )

    def test_the_settlement_write_did_not_gain_the_void(self):
        """The hot statement runs for every row and must stay as it was.

        Its bind set is pinned by the real-Postgres contract; a void column
        smuggled in here would run for all 200 rows of every batch and would
        take ``UPDATE_SQL`` out of SQLite, where the band guards drive it.
        """
        assert "market_metadata" not in UPDATE_SQL
        assert "venue_voided" not in UPDATE_SQL

    def test_the_void_write_merges_rather_than_replaces_metadata(self):
        """A plain assignment would blank ``market_metadata["shape"]``."""
        assert "COALESCE(market_metadata" in VOID_UPDATE_SQL
        assert "||" in VOID_UPDATE_SQL


# ---------------------------------------------------------------------------
# CERT-3324's repair — the already-resolved arm's WRITE POLICY
# ---------------------------------------------------------------------------
#
# The selection itself is Postgres-only (it screens on `market_metadata->>`) and
# is gated by `tests/integration/test_kalshi_resolved_void_selection_pg.py`.
# What is checkable here is the other half of the repair: what the arm is
# allowed to WRITE once that selection has handed it a row.


def _drive_mode(legs, *, void_capture_only, apply=True):
    """Same driver as above, with the arm's write policy as the only variable."""
    recorder: list = []
    venue = _Venue(legs)

    def maker():
        return _FakeSession(recorder, [ROW], (1, 0, 0, 1, 0))

    report = asyncio.run(
        sweep.run_backfill(
            session_maker=maker,
            client_factory=lambda: venue,
            limit=500,
            apply=apply,
            now=NOW,
            rows=[ROW],
            void_capture_only=void_capture_only,
        )
    )
    statements = [s for s, _ in recorder]
    return report, statements


def _ran(statements, needle):
    return [s for s in statements if needle in s]


class TestTheAlreadyResolvedArmWritesOneFact:
    """#7035 / CERT-3324. `void_capture_only` bounds the blast radius.

    These rows are ALREADY `resolved`, so `UPDATE_SQL`'s status and `settled_at`
    arms are no-ops on them — but its two date columns are not. This arm exists
    to explain 489 settled rows, not to re-date them.
    """

    def test_the_settlement_write_is_withheld_from_this_population(self):
        report, statements = _drive_mode(VOIDED_LEGS, void_capture_only=True)

        assert _ran(statements, "SET resolution_date") == [], (
            "the already-resolved arm ran the shared settlement UPDATE. Its "
            "COALESCEd date columns OVERWRITE a stored date whenever the venue "
            "yields one, so this would silently re-date every row it explains."
        )
        assert report["stats"]["writes_applied"] == 0

    def test_the_void_fact_is_still_written(self):
        """The withholding above must not cost the arm its entire point."""
        report, statements = _drive_mode(VOIDED_LEGS, void_capture_only=True)

        assert report["stats"]["venue_voided"] == 1
        assert report["stats"]["void_writes_applied"] == 1
        assert len(_ran(statements, "'venue_voided', true")) == 1

    def test_the_default_still_runs_the_settlement_write(self):
        """🔴 THE STRAWMAN. Without this arm the two above pass on a function
        that never writes anything, and the flag would be proven by a mode that
        is broken in both positions."""
        report, statements = _drive_mode(VOIDED_LEGS, void_capture_only=False)

        assert _ran(statements, "SET resolution_date") != []
        assert report["stats"]["writes_applied"] == 1


class TestTheRefusalIsRememberedOnlyWhereItIsTerminal:
    """The idempotency stamp. 10 of 14 sampled rows are graded at the venue, and
    a refusal that leaves no trace is re-asked every 10 minutes for 14 days."""

    def test_a_graded_row_is_stamped_so_it_is_never_asked_again(self):
        report, statements = _drive_mode(PLAYED_LEGS, void_capture_only=True)

        assert report["stats"]["void_refused_graded"] == 1
        assert report["stats"]["void_checked_writes_applied"] == 1
        assert len(_ran(statements, "venue_void_checked_at")) == 1

    def test_a_graded_row_is_never_stamped_voided(self):
        """The two stamps are different facts and must not blur."""
        _, statements = _drive_mode(PLAYED_LEGS, void_capture_only=True)

        assert _ran(statements, "'venue_voided', true") == []

    def test_the_open_row_population_is_never_stamped_checked(self):
        """🔴 THE BLAST-RADIUS CONTROL, and the reason the stamp is gated on the
        mode rather than written wherever a row is graded.

        `run_backfill` classifies EVERY row it reads, including the ~12,000
        healthy open rows of the population sweep and the 200-row batches of the
        10-minute arm. Writing this bookkeeping key there would mark thousands of
        rows "checked" to record a question that arm never asked, and would put a
        jsonb write on a path that must stay SQLite-drivable.
        """
        report, statements = _drive_mode(PLAYED_LEGS, void_capture_only=False)

        assert _ran(statements, "venue_void_checked_at") == []
        assert report["stats"]["void_checked_writes_applied"] == 0

    def test_an_unfinished_event_is_left_re_askable(self):
        """Only the answer that CANNOT change is durable.

        `not_settled` means the venue has not finished, so a stamp here would
        retire a row that may yet void. This is the arm that fails if the
        `graded` branch is ever loosened to a bare `else`.
        """
        open_legs = [dict(leg, status="active", result=None) for leg in VOIDED_LEGS]

        report, statements = _drive_mode(open_legs, void_capture_only=True)

        assert _ran(statements, "venue_void_checked_at") == []
        assert _ran(statements, "'venue_voided', true") == []
        assert report["stats"]["void_checked_writes_applied"] == 0

    def test_a_dry_run_records_nothing(self):
        report, statements = _drive_mode(
            PLAYED_LEGS, void_capture_only=True, apply=False
        )

        assert _ran(statements, "venue_void_checked_at") == []
        assert report["stats"]["void_refused_graded"] == 1, (
            "a dry run must still COUNT the refusal — the counter is how an "
            "operator sees the arm reached anything at all"
        )

    def test_the_checked_stamp_writes_no_grade_and_merges(self):
        lowered = sweep.VOID_CHECKED_UPDATE_SQL.lower()
        for word in ("is_winner", "resolution_source", "probability", "status ="):
            assert word not in lowered, (
                f"#1852: {word!r} appears in the checked stamp. It records that "
                "a question was answered, never what the answer was."
            )
        assert "COALESCE(market_metadata" in sweep.VOID_CHECKED_UPDATE_SQL
        assert "||" in sweep.VOID_CHECKED_UPDATE_SQL


class _TwoPhaseSession:
    """A session that can tell the beat's TWO selections apart.

    `run_recent_finals` now runs two statements with different predicates and
    different write policies. A double that answered both with the same rows
    could not see which one reached the specimen — which is the exact blindness
    CERT-3324 blocked the first presentation for.
    """

    def __init__(self, recorder, recent_rows, resolved_rows):
        self._recorder = recorder
        self._recent = recent_rows
        self._resolved = resolved_rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        sql = str(statement)
        self._recorder.append((sql, params))
        if sql.strip().upper().startswith("UPDATE"):
            return _FakeResult([])
        if "fm.status = 'resolved'" in sql:
            return _FakeResult(self._resolved)
        return _FakeResult(self._recent)

    async def commit(self):
        return None


class TestThePhaseIsReachedFromTheBeat:
    """🔴 THE REACHABILITY CLAIM ITSELF.

    CERT-3324: "Its composed guard injects the specimen after selection, so
    classifier/write correctness cannot make the existing postponed-game card
    acquire `market_metadata.venue_voided`." A repair that adds a selection
    nothing calls repeats that defect with an extra statement. So these arms
    drive `run_resolved_voids` — the function the beat calls, which does its own
    selecting — and never hand it rows.
    """

    def _run(self, *, resolved_rows, legs=None, apply=True):
        recorder: list = []
        venue = _Venue(VOIDED_LEGS if legs is None else legs)

        def maker():
            return _TwoPhaseSession(recorder, [], resolved_rows)

        report = asyncio.run(
            sweep.run_resolved_voids(
                apply=apply,
                session_maker=maker,
                client_factory=lambda: venue,
                now=NOW,
            )
        )
        return report, [s for s, _ in recorder], venue

    def test_the_beat_runs_the_already_resolved_selection(self):
        report, statements, _ = self._run(resolved_rows=[ROW])

        assert [s for s in statements if "fm.status = 'resolved'" in s], (
            "the beat never executed the already-resolved selection: the arm "
            "exists and nothing reaches it"
        )
        assert report["candidates"] == 1

    def test_the_specimen_reaches_the_void_write_through_the_beat(self):
        """End to end on the seam that was missing: selection -> venue -> stamp."""
        report, statements, venue = self._run(resolved_rows=[ROW])

        assert venue.asked == ["KXLALIGAGAME-26SEP16LEVATH"]
        assert report["venue_voided"] == 1
        assert report["void_writes_applied"] == 1
        assert len([s for s in statements if "'venue_voided', true" in s]) == 1

    def test_the_arm_withholds_the_settlement_write_through_the_beat(self):
        """The mode survives the call chain, not just a direct invocation."""
        report, _, _ = self._run(resolved_rows=[ROW])

        assert report["settlement_writes_applied"] == 0

    def test_an_empty_band_reports_a_shape_rather_than_an_absence(self):
        """gotcha #53: "drained" and "never ran" must not read the same."""
        report, _, venue = self._run(resolved_rows=[])

        assert venue.asked == []
        assert report["candidates"] == 0
        assert report["selection"] == "resolved_void"
        assert "venue_voided_samples" in report
        assert report["terminal"] == "complete"

    def test_a_batch_nobody_could_answer_is_partial_not_complete(self):
        """#1515's contract: an invocation that returned is not proof of work.

        Every selected row that gets neither stamp is selected again next run.
        A batch made entirely of those is the CAL-P998 jam, and it must not
        report as a clean pass.
        """
        unfinished = [dict(leg, status="active", result=None) for leg in VOIDED_LEGS]

        report, _, _ = self._run(resolved_rows=[ROW], legs=unfinished)

        assert report["terminal"] == "partial"
        assert report["void_writes_applied"] == 0
        assert report["void_checked_writes_applied"] == 0

    def test_a_draining_batch_is_complete(self):
        """🔴 The strawman for the arm above: `partial` must not be the only
        answer this terminal can give."""
        report, _, _ = self._run(resolved_rows=[ROW])

        assert report["terminal"] == "complete"


class TestTheCaptureSpendsTheFactItWrote:
    """🔴 CERT-3326's BLOCK, in one class: the capture must have a CONSUMER.

    The blocked presentation wrote `market_metadata.venue_voided` and stopped.
    The grader's finding was not that the write was wrong — it was that "the
    SHA has no runtime consumer of that fact outside the capture task", so the
    postponed fixture went on being served with "No result reported" under it.
    These arms prove the consumer is REACHED from the beat; what it then does
    is proved on a real Postgres in `test_venue_void_retirement_pg.py`.

    The discriminator is the report: `_retire_venue_voided_suspended_rows`
    always returns both counters, so their presence cannot be faked by a phase
    that was skipped, and a future edit that makes the call conditional deletes
    them from the report and reddens these arms.
    """

    def _run(self, *, resolved_rows, legs=None):
        recorder: list = []
        venue = _Venue(VOIDED_LEGS if legs is None else legs)

        def maker():
            return _TwoPhaseSession(recorder, [], resolved_rows)

        report = asyncio.run(
            sweep.run_resolved_voids(
                apply=True,
                session_maker=maker,
                client_factory=lambda: venue,
                now=NOW,
            )
        )
        return report, [s for s, _ in recorder]

    def test_the_beat_runs_the_retirement_after_the_capture(self):
        report, statements = self._run(resolved_rows=[ROW])

        assert "venue_voided_suspended_screened" in report, (
            "the capture wrote the fact and nothing spent it — this is the "
            "exact shape CERT-3326 blocked"
        )
        assert "venue_voided_suspended_retired" in report
        assert [s for s in statements if "ORDER BY events.commence_time ASC" in s], (
            "the retirement screen never executed: the consumer exists and the "
            "beat does not reach it"
        )

    def test_the_retirement_runs_on_the_DRAINED_path_too(self):
        """🔴 THE LOAD-BEARING ARM, AND THE ONE A PLAUSIBLE SHIP FAILS.

        The natural place to hang a consumer is the write path — retire what we
        just stamped. That ship works for about four hours. The capture's own
        sizing says a 489-row band drains at 60 a run, after which `rows` is
        empty on every beat forever; that is the intended steady state. A
        consumer reached only when the capture stamped something would then
        never run again, while the rows it exists to retire are exactly the
        ones already stamped — and a stamped row commonly is not retirable
        until the retirement floor passes it, hours after the stamp.

        So the drained path is not an edge case. It is where this ship spends
        almost all of its life.
        """
        report, statements = self._run(resolved_rows=[])

        assert report["candidates"] == 0, "precondition: the band is drained"
        assert "venue_voided_suspended_screened" in report, (
            "the retirement is hung off the write path: once the band drains "
            "it never runs again, and the stamped rows are never spent"
        )
        assert [s for s in statements if "ORDER BY events.commence_time ASC" in s]

    def test_the_retirement_does_not_change_the_captures_terminal(self):
        """A pass that retires nothing is the normal reading, not a fault.

        The terminal is a verdict on the VENUE half — did every selected row
        get a durable answer. Folding the retirement counters into it would
        make a healthy capture that simply had nothing retirable read `partial`.
        """
        report, _ = self._run(resolved_rows=[ROW])

        assert report["venue_voided_suspended_retired"] == 0
        assert report["terminal"] == "complete"
