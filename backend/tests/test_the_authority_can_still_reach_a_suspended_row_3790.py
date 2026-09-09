"""THE ROW WE ADMITTED WE CANNOT SCORE IS THE ONE THE SCORER COULD NOT SEE. #3790.

═══ WHY THIS SUITE EXISTS ═══

Every ESPN backfill keyed its eligibility on ``["completed", "closed"]``:

    espn_sync._backfill_box_scores          both arms
    espn_sync._backfill_espn_ids            the anchor-acquisition path
    espn_sync._backfill_espn_win_probability  the raw-SQL snapshot scan

That list is :data:`SETTLED_STATUSES`, and it answers *"has something declared
this final?"* — a **reader's** question, the one a client asks in order to draw
a Final. The backfills are not readers. The question they mean to ask is **"do
we still owe this row a result?"**, and on that question the two sets point in
opposite directions: a ``suspended`` row is precisely one we have ADMITTED we
cannot score, so it is the row that most needs the authority, and it was the
only one the authority could not reach.

**The general clause, and it is the mirror of CERT-786's.** That cert established
that a new state is not shipped until every consumer that DISPLAYS the
vocabulary has been shown the word. This is the same failure one layer down: a
new state is not shipped until every consumer that REPAIRS on the vocabulary has
been shown it too. The display half is louder — a retrieval surface that omits a
row renders a visibly missing match, which someone eventually reports. A backfill
that omits a row simply never fills it in, and reports a clean run either way
(gotcha #53). It is the quieter half, so it needs the guard more.

═══ WHY IT WAS URGENT RATHER THAN TIDY ═══

#3780's repair moves a measured **8,279** result-less rows ``closed`` →
``suspended`` in one sweep (population re-measured by live/091 against
production at 2026-09-07 05:35Z; they span 2026-08-24 → 2026-09-03). Every one
of them is reachable by these backfills TODAY as ``closed`` and would have
stopped being reachable the moment that sweep ran — so the fix and the sweep
were racing, and the sweep was ahead.

🔴 And they cannot fall back on the resume arm. ``espn_sync``'s suspended→live
ladder is bounded by ``SUSPENDED_RESUME_WINDOW`` (48h) and that whole cohort is
weeks past it. For an unanchored row the backfills are not the best door, they
are the ONLY one: ``espn_helpers``' direct authority door opens off an
``espn_id``, and ``_backfill_espn_ids`` is what goes and gets the ``espn_id``.
Excluding a suspended row there did not delay its repair. It removed the last
path by which the row could ever be scored.

═══ WHAT IS TESTED HERE, AND HOW IT DECOMPOSES ═══

The predicates under test are built inline inside long async task bodies, so
there is no exported predicate object to call the way CERT-786 could call
``candidate_window_conditions``. Rather than hand-copy four WHERE clauses and
assert on the copies — the exact failure mode CERT-786's docstring warns about —
the claim is split into two halves that are jointly sufficient:

    MEMBERSHIP   the shared set really does admit the state, and really does
                 still admit the settled ones  (behavioural, on the real object)
    SPEND        each of the four sites actually spends that shared set rather
                 than a hand-written literal  (structural, over the real AST)

Neither half alone is worth much; together they say "the right set exists and
the sites use it". The structural half is what catches the actual regression
class here, which is not a subtle logic error — it is somebody typing
``["completed", "closed"]`` into a fifth query six months from now.

═══ RED-FIRST ═══

``TestTheDefectReproduces`` runs the PRE-FIX literal over a corpus and shows the
suspended specimen absent from it. Without that, the admission tests could be
passing over a corpus the old code would have admitted too, and the suite would
certify nothing.

``TestTheHealthyDirectionIsUntouched`` holds the controls. The un-settle repairs
are the important ones: they DO mean ``SETTLED_STATUSES`` — you cannot un-settle
a row that was never settled — so widening them would be a real bug, and a
"fix" that widened everything with a grep would go green without them.
"""

import ast
import inspect
import textwrap
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# SQLite cannot render Postgres-native column types. DDL shims for the sqlite
# dialect ONLY — production is Postgres and never reaches them. Same shims, and
# the same reason, as `test_suspended_is_reachable_cert_786`.


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.tasks import espn_sync  # noqa: E402
from app.utils.event_completion import (  # noqa: E402
    AUTHORITY_BACKFILL_STATUS_SQL,
    AUTHORITY_BACKFILL_STATUSES,
    EVENT_SUSPENDED,
    SETTLED_STATUSES,
)

NOW = datetime(2026, 9, 7, 6, 0, 0, tzinfo=timezone.utc)

S_TENNIS = 1

#: The #3790 specimen shape: a result-less row inside #3780's measured cohort
#: (2026-08-24 → 2026-09-03), carrying NO `espn_id`. This is the row that is
#: permanently stranded, because the only path that could give it an anchor is
#: the one that excluded it.
SUSPENDED_NO_ANCHOR_ID = 990_001

#: Suspended but already anchored — reachable by `espn_helpers` directly, and
#: still owed a box score and a win-prob history by the other two backfills.
SUSPENDED_ANCHORED_ID = 990_002

SETTLED_ID = 990_003
LIVE_ID = 990_004
SCHEDULED_ID = 990_005

#: The pre-fix literal, hand-written ON PURPOSE and only here: it is the
#: artefact under test, not a stand-in for the real thing.
_PRE_FIX_STATUSES = ["completed", "closed"]

#: The four call sites the repair had to reach, by the function that owns them.
_REPAIRED_SITES = (
    espn_sync._backfill_box_scores,
    espn_sync._backfill_espn_ids,
    espn_sync._backfill_espn_win_probability,
)

#: The sites that must not be widened BY THIS SUITE'S SET, and why. Spelled out
#: so a future sweep that "fixes them all" fails here with the reason attached.
#:
#: AMENDED #4114: `_is_bogus_future_settled` now admits `suspended`, but on its
#: OWN constant (`espn_sync.FUTURE_SETTLED_STATUSES`) and behind its own
#: `commence_time > now + 1h` gate — never on `AUTHORITY_BACKFILL_STATUSES`,
#: which is what the structural check below actually forbids. The distinction is
#: the whole point: this suite's cohort is PAST-commence rows that are owed a
#: result, and the commence gate has always excluded every one of them. What was
#: forbidden here was spending the BACKFILL set inside a repair, and that is
#: still forbidden.
_DELIBERATELY_SETTLED_ONLY = (
    espn_sync._is_bogus_future_settled,
)


def _event(eid, status, commence_time, *, espn_id=None, home_score=None,
           away_score=None):
    return Event(
        id=eid,
        sport_id=S_TENNIS,
        external_id=f"ext-{eid}",
        espn_id=espn_id,
        home_team_name=f"H{eid}",
        away_team_name=f"A{eid}",
        commence_time=commence_time,
        status=status,
        home_score=home_score,
        away_score=away_score,
    )


def _slate():
    return [
        _event(SUSPENDED_NO_ANCHOR_ID, EVENT_SUSPENDED, NOW - timedelta(days=9)),
        _event(
            SUSPENDED_ANCHORED_ID,
            EVENT_SUSPENDED,
            NOW - timedelta(days=6),
            espn_id="401season1",
        ),
        _event(
            SETTLED_ID,
            "completed",
            NOW - timedelta(hours=4),
            espn_id="401season2",
            home_score=3,
            away_score=1,
        ),
        _event(LIVE_ID, "live", NOW - timedelta(hours=1)),
        _event(SCHEDULED_ID, "scheduled", NOW + timedelta(hours=5)),
    ]


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng, tables=[Sport.__table__, Event.__table__])
    return eng


@pytest.fixture()
def slate(engine):
    with Session(engine) as s:
        s.add(Sport(id=S_TENNIS, key="tennis_atp_us_open", name="US Open"))
        s.add_all(_slate())
        s.commit()
        yield s


def _eligible(session, statuses):
    """Ids a backfill keyed on `statuses` would consider."""
    return {
        r[0]
        for r in session.execute(
            select(Event.id).where(Event.status.in_(list(statuses)))
        ).all()
    }


def _tree(fn):
    """Parse `fn`'s own source.

    `textwrap.dedent`, never `inspect.cleandoc` — cleandoc strips leading
    whitespace from every line after the first, which is right for a docstring
    and destroys a function body.
    """
    return ast.parse(textwrap.dedent(inspect.getsource(fn)))


def _names_used(fn):
    """Every bare identifier appearing in `fn`'s source."""
    return {n.id for n in ast.walk(_tree(fn)) if isinstance(n, ast.Name)}


def _string_constants(fn):
    """Every string literal appearing in `fn`'s source, docstring excluded."""
    tree = _tree(fn)
    doc = ast.get_docstring(tree.body[0]) if tree.body else None
    return {
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != doc
    }


# ---------------------------------------------------------------------------
# 0 — the corpus really does reproduce the defect
# ---------------------------------------------------------------------------


class TestTheDefectReproduces:
    def test_the_pre_fix_key_cannot_see_either_suspended_row(self, slate):
        eligible = _eligible(slate, _PRE_FIX_STATUSES)

        assert SUSPENDED_NO_ANCHOR_ID not in eligible
        assert SUSPENDED_ANCHORED_ID not in eligible

    def test_and_it_could_see_them_before_3780_unsettled_them(self, slate):
        """The regression's shape: these rows are reachable TODAY as `closed`.

        #3780 moves 8,279 of them to `suspended` in one sweep. Re-labelling the
        specimen is exactly what that sweep does, and under the pre-fix key it
        is the difference between reachable and stranded — so the harm is not
        hypothetical, it is a scheduled write.
        """
        row = slate.get(Event, SUSPENDED_NO_ANCHOR_ID)
        row.status = "closed"
        slate.commit()
        assert SUSPENDED_NO_ANCHOR_ID in _eligible(slate, _PRE_FIX_STATUSES)

        row.status = EVENT_SUSPENDED
        slate.commit()
        assert SUSPENDED_NO_ANCHOR_ID not in _eligible(slate, _PRE_FIX_STATUSES)


# ---------------------------------------------------------------------------
# 1 — MEMBERSHIP: the shared set admits the state
# ---------------------------------------------------------------------------


class TestTheSharedSetAdmitsSuspended:
    def test_the_set_contains_suspended(self):
        assert EVENT_SUSPENDED in AUTHORITY_BACKFILL_STATUSES

    def test_it_is_a_strict_superset_of_settled(self):
        """Widening only. Nothing that was reachable may have become unreachable."""
        assert SETTLED_STATUSES < AUTHORITY_BACKFILL_STATUSES
        assert AUTHORITY_BACKFILL_STATUSES == SETTLED_STATUSES | {EVENT_SUSPENDED}

    def test_it_admits_neither_live_nor_scheduled(self):
        """A row still being played is not owed a BACKFILL, it is owed a poll.

        The live poller and the resume ladder own those states; pulling them in
        here would have the backfills racing the poller for the same rows.
        """
        assert "live" not in AUTHORITY_BACKFILL_STATUSES
        assert "scheduled" not in AUTHORITY_BACKFILL_STATUSES

    def test_it_reaches_both_suspended_rows_and_keeps_the_settled_one(self, slate):
        eligible = _eligible(slate, AUTHORITY_BACKFILL_STATUSES)

        assert SUSPENDED_NO_ANCHOR_ID in eligible, "the stranded row is the ship"
        assert SUSPENDED_ANCHORED_ID in eligible
        assert SETTLED_ID in eligible, "widening must not cost the settled rows"
        assert LIVE_ID not in eligible
        assert SCHEDULED_ID not in eligible

    def test_the_raw_sql_rendering_agrees_with_the_set(self):
        """The `text()` site spends a rendered string, so it can drift. Pin it.

        Rendered and parsed rather than eyeballed: a builder's template is only
        as good as what it actually emits.
        """
        rendered = {
            piece.strip().strip("'")
            for piece in AUTHORITY_BACKFILL_STATUS_SQL.split(",")
        }
        assert rendered == AUTHORITY_BACKFILL_STATUSES
        assert AUTHORITY_BACKFILL_STATUS_SQL == "'closed', 'completed', 'suspended'"

    def test_the_rendered_clause_is_valid_sql_that_selects_the_specimen(self, slate):
        """Compose the real fragment into a real IN clause and run it."""
        from sqlalchemy import text

        found = {
            r[0]
            for r in slate.execute(
                text(
                    "SELECT id FROM events WHERE status IN "
                    f"({AUTHORITY_BACKFILL_STATUS_SQL})"
                )
            ).all()
        }
        assert SUSPENDED_NO_ANCHOR_ID in found
        assert SETTLED_ID in found
        assert LIVE_ID not in found


# ---------------------------------------------------------------------------
# 2 — SPEND: the sites actually use it
# ---------------------------------------------------------------------------


class TestEveryBackfillSpendsTheSharedSet:
    """The half that catches the real regression: a fifth hand-written list."""

    @pytest.mark.parametrize("fn", _REPAIRED_SITES, ids=lambda f: f.__name__)
    def test_the_site_references_the_shared_set(self, fn):
        used = _names_used(fn)
        assert used & {
            "AUTHORITY_BACKFILL_STATUSES",
            "AUTHORITY_BACKFILL_STATUS_SQL",
        }, (
            f"{fn.__name__} does not spend the shared eligibility set — if a new "
            f"query was added here, key it on AUTHORITY_BACKFILL_STATUSES so a "
            f"suspended row stays reachable (#3790)"
        )

    @pytest.mark.parametrize("fn", _REPAIRED_SITES, ids=lambda f: f.__name__)
    def test_the_site_no_longer_hand_writes_the_settled_pair(self, fn):
        """Both spellings: the ORM list and the raw-SQL literal."""
        literals = _string_constants(fn)
        assert not ({"completed", "closed"} <= literals), (
            f"{fn.__name__} still hand-writes a completed/closed status list. "
            f"That is the #3790 defect exactly — it asks 'is this final?' when "
            f"it means 'do we still owe this a result?'"
        )

        source = inspect.getsource(fn)
        assert "'completed', 'closed'" not in source
        assert '"completed", "closed"' not in source


# ---------------------------------------------------------------------------
# 3 — the controls
# ---------------------------------------------------------------------------


class TestTheHealthyDirectionIsUntouched:
    """Chosen to be green in BOTH arms: they route only through pre-#3790 symbols.

    A "control" that goes red without the fix proves the fix is absent, not that
    the fix is narrow.
    """

    def test_settled_statuses_itself_did_not_move(self):
        """The reader-facing set is the one clients draw Finals off. Untouched."""
        assert SETTLED_STATUSES == frozenset({"completed", "closed"})
        assert EVENT_SUSPENDED not in SETTLED_STATUSES

    def test_a_suspended_row_is_still_not_settled(self):
        from app.utils.event_completion import SETTLEABLE_STATUSES

        assert EVENT_SUSPENDED in SETTLEABLE_STATUSES
        assert EVENT_SUSPENDED not in SETTLED_STATUSES

    @pytest.mark.parametrize(
        "fn", _DELIBERATELY_SETTLED_ONLY, ids=lambda f: f.__name__
    )
    def test_the_unsettle_repairs_were_not_widened(self, fn):
        """🔴 The control that a grep-and-replace 'fix' would have broken.

        These hunt rows that are wrongly SETTLED and reset them. You cannot
        un-settle a row that is not settled, and a suspended row is already
        un-settled — widening them would have this repair clobbering the very
        state the other half of the fix is trying to make reachable.
        """
        assert "AUTHORITY_BACKFILL_STATUSES" not in _names_used(fn)

    def test_the_bogus_future_settled_guard_spares_this_suites_cohort(self):
        """The same control, run rather than inspected — AMENDED by #4114.

        🔴 WHAT CHANGED AND WHY, because this is another lane's guard.

        This assertion used to read ``not _is_bogus_future_settled(SUSPENDED,
        future, ...)`` — a blanket refusal keyed on the STATUS. The fear behind
        it is real and is unchanged: the 8,279 result-less rows #3780 sweeps
        ``closed`` → ``suspended`` must never be flipped to ``scheduled``, which
        would clobber the very state this suite exists to make reachable.

        But that cohort is protected by the COMMENCE gate, not the status gate.
        Every one of those 8,279 rows is in the PAST (they span 2026-08-24 →
        2026-09-03, and the suite's own header says they are weeks past the 48h
        resume window). ``_is_bogus_future_settled`` requires ``commence_time >
        now + 1h``, so it could never have reached a single one of them. The old
        assertion therefore bought no protection for the rows it names — it only
        pinned a case that is unreachable by design, and when that case DID
        occur it was corruption: Ohio State @ Texas (416569) sat ``suspended``
        with a 2026-09-12 kickoff four days out, on a marquee game, while ESPN
        read STATUS_SCHEDULED for the same fixture. Nothing repaired it, because
        this guard had been told to look away.

        This suite's own general clause is the argument for the amendment: *a
        new state is not shipped until every consumer that REPAIRS on the
        vocabulary has been shown it too.* #3790 showed the four backfills. The
        future-commence repair is a fifth consumer and was never shown the word.

        So the control now pins the cohort instead of the status: a suspended
        row with a PAST commence — every row this suite is about — is still
        untouched, and that is asserted below at both the day and week scales.
        """
        future = NOW + timedelta(days=2)

        assert espn_sync._is_bogus_future_settled(
            "completed", future, 0, 0, NOW
        ), "a settled row with a future kickoff is still the #190 recurrence"

        # THE REAL PROTECTION: this suite's cohort is past-commence, and stays
        # untouched. A day old, and weeks old like the #3780 sweep's rows.
        for age in (timedelta(hours=6), timedelta(days=1), timedelta(days=21)):
            assert not espn_sync._is_bogus_future_settled(
                EVENT_SUSPENDED, NOW - age, 0, 0, NOW
            ), (
                f"a suspended row {age} in the past is one we admitted we "
                "cannot score; the repair must leave it for the authority"
            )

        # And the corruption case #4114 exists for is now reached.
        assert espn_sync._is_bogus_future_settled(
            EVENT_SUSPENDED, future, None, None, NOW
        ), "a suspended row with a future kickoff is not a game, it is a rewrite"
