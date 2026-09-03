"""CAL-P989 / CERT-766: the catch-up script must actually run, and must not starve.

WHY THIS FILE EXISTS. The `resolution_date = close_time` fix reaches only rows the
poller re-upserts, and the poller enumerates the venue with `status="open"` — so the
10,187 already-finalized rows that motivated #2660 can be repaired ONLY by
`scripts/backfill_kalshi_resolution_window.py`. The first cut of that script had two
defects that the 19 derivation guards could not see, because not one of them imported
it:

1. ``from app.services.kalshi_api import KalshiAPIClient`` — a name that has never
   existed. The script raised ImportError before argparse ran. The named
   ``KXWTA-26MONTER`` card could not have been repaired by a merge of that branch.
2. The retention floor was applied in PYTHON, AFTER the ``LIMIT``. A batch of
   provably-purged tier-1 rows consumed the entire limit, prepared zero writes, and
   wrote nothing — so the next run selected the same dead rows and a recoverable
   lower-tier row was stranded forever. A skip that does not free its slot is a
   permanent starvation, not a skip (gotcha #41: an expiring population needs BOTH
   bounds, and the floor is one of them).

So the guards here are deliberately *executable* rather than textual. The starvation
guard runs the module's real ``SELECT_SQL`` string against a seeded table, and the
composed guard drives the real ``run_backfill`` through selection, derivation and the
two-column UPDATE with a faked venue. Both carry an explicit DEFECT ARM that runs the
pre-repair shape against the same fixture, so neither can pass vacuously.

CLOCK DISCIPLINE (gotcha #44). ``run_backfill`` takes ``now`` as a parameter and the
fixtures below pin it to a literal. No assertion here reads the wall clock, so none
can flip with the calendar.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS  # noqa: E402


def _mod():
    """Import the script LAZILY, inside each test that needs it.

    Deliberately not a module-level import. On the CERT-766 head the script
    raises ImportError, and a top-level import would turn that into a COLLECTION
    error for the whole file — every starvation and apply-path guard below would
    then be "red" without ever having executed, which proves nothing about them.
    With the import deferred, each defect reds exactly the guards that measure it.
    """
    import scripts.backfill_kalshi_resolution_window as mod

    return mod


#: The instant the population was measured. A literal, never `utcnow()`.
NOW = datetime(2026, 9, 2, 19, 30, tzinfo=timezone.utc)
PURGE_FLOOR = NOW - timedelta(days=PROVABLY_PURGED_AGE_DAYS)


# --- the pre-repair SELECT, kept verbatim as the defect arm ------------------
#
# Identical to `SELECT_SQL` except that it has no floor in the predicate. This is
# what CERT-766 reproduced. It is here so the starvation guard proves the fixture
# can distinguish the two shapes; without it, "the control row was selected" might
# just mean the fixture was too small to fill the limit.
DEFECT_SELECT_SQL = """
    SELECT id, external_id, resolution_date, commence_time, market_tier
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND expiration_time IS NULL
    ORDER BY market_tier ASC NULLS LAST, commence_time DESC NULLS LAST
    LIMIT :limit OFFSET :offset
"""

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
            :resolution_date, NULL, NULL)
"""

#: The batch size the starvation reproduction uses. Equal to the number of purged
#: rows seeded, so the purged cohort fills the limit EXACTLY — one row fewer and the
#: control would ride along by luck rather than by the floor.
BATCH = 500


@pytest.fixture
def seeded_starvation_db():
    """500 provably-purged tier-1 rows plus one recoverable tier-2 control.

    This is CERT-766's reproduction, seeded as data rather than described in prose.
    The purged rows are all tier 1, so the `market_tier ASC` ordering puts every one
    of them ahead of the control; there are exactly `BATCH` of them, so under the
    pre-repair SQL they consume the whole limit.
    """
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))
        for i in range(BATCH):
            # Well past the purge horizon: Kalshi no longer holds these at all.
            commence = PURGE_FLOOR - timedelta(days=10 + i)
            conn.execute(
                text(INSERT),
                {
                    "id": i + 1,
                    "external_id": f"KXPURGED-{i:04d}",
                    "market_tier": 1,
                    "commence_time": commence.isoformat(),
                    "resolution_date": (commence + timedelta(days=14)).isoformat(),
                },
            )
        # The control: inside the floor, recoverable, and a LOWER-priority tier so
        # every purged row sorts ahead of it.
        conn.execute(
            text(INSERT),
            {
                "id": 9001,
                "external_id": "KXWTA-26MONTER",
                "market_tier": 2,
                "commence_time": (NOW - timedelta(days=3)).isoformat(),
                "resolution_date": (NOW + timedelta(days=31)).isoformat(),
            },
        )
    return engine


class TestTheScriptCanRunAtAll:
    """CERT-766 defect 1. The cheapest possible guard, absent for a whole cert round."""

    def test_the_module_imports(self):
        """Red-first anchor: this failed with ImportError on the blocked head.

        `run_backfill` is referenced so the import cannot be elided as unused, and
        so an import that succeeds but exports nothing still fails here.
        """
        import scripts.backfill_kalshi_resolution_window as mod

        assert callable(mod.run_backfill)
        assert callable(mod.main)

    def test_it_binds_the_api_service_that_actually_exists(self):
        """The name, checked against the module that defines it — not against prose.

        Asserting `KalshiAPIService` is importable is not enough: the script could
        still hold the wrong name. So resolve the symbol the script bound.
        """
        import scripts.backfill_kalshi_resolution_window as mod
        from app.services.kalshi_api import KalshiAPIService

        assert mod.KalshiAPIService is KalshiAPIService
        assert not hasattr(mod, "KalshiAPIClient"), (
            "RED-FIRST ANCHOR: `KalshiAPIClient` does not exist in "
            "app.services.kalshi_api. Its presence means the catch-up raises "
            "ImportError before it selects a row, and the finalized cohort — "
            "which the poller can never re-enumerate (gotcha #33) — silently "
            "does not get repaired."
        )

    def test_the_client_is_not_used_as_a_context_manager(self):
        """`BaseAPIClient` has `close()` and no `__aenter__`.

        A latent AttributeError sitting one line past the ImportError: fixing only
        the name would have moved the failure, not removed it.
        """
        import inspect

        from app.services.base_api import BaseAPIClient
        from app.services.kalshi_api import KalshiAPIService

        import scripts.backfill_kalshi_resolution_window as mod

        assert issubclass(KalshiAPIService, BaseAPIClient)
        assert not hasattr(BaseAPIClient, "__aenter__"), (
            "control: if BaseAPIClient ever grows async-context support this "
            "guard is measuring nothing and should be re-read, not deleted"
        )
        src = inspect.getsource(mod)
        assert "async with KalshiAPIService" not in src
        assert "async with client" not in src


class TestTheFloorIsInThePredicate:
    """CERT-766 defect 2, reproduced as data and then closed."""

    def test_the_defect_arm_starves_the_recoverable_row(self, seeded_starvation_db):
        """The pre-repair SQL, on the same fixture. This is the failure, shown.

        Without it, the guard below could pass on a fixture that never filled the
        limit — "the control was selected" would be true for the wrong reason.
        """
        with seeded_starvation_db.begin() as conn:
            rows = conn.execute(
                text(DEFECT_SELECT_SQL), {"limit": BATCH, "offset": 0}
            ).all()

        tickers = {r[1] for r in rows}
        assert len(rows) == BATCH
        assert "KXWTA-26MONTER" not in tickers, (
            "fixture check: the purged cohort must fill the whole limit under the "
            "pre-repair SQL, or this file is not reproducing CERT-766"
        )
        assert all(t.startswith("KXPURGED-") for t in tickers)

    def test_the_repaired_sql_selects_the_recoverable_row(self, seeded_starvation_db):
        """The ship: the floor frees the slots, so the tail is reachable."""
        with seeded_starvation_db.begin() as conn:
            rows = conn.execute(
                text(_mod().SELECT_SQL),
                {
                    "purge_floor": PURGE_FLOOR.isoformat(),
                    "limit": BATCH,
                    "offset": 0,
                },
            ).all()

        tickers = [r[1] for r in rows]
        assert tickers == ["KXWTA-26MONTER"], (
            "the 500 provably-purged tier-1 rows must be excluded BEFORE the "
            "LIMIT, leaving the recoverable tier-2 row selectable. Getting "
            "KXPURGED-* rows here means the floor moved back to Python and the "
            "recoverable tail is stranded forever."
        )

    def test_a_null_commence_time_is_not_excluded(self, seeded_starvation_db):
        """Fail-open: unknown age is not evidence of death (gotcha #35's upper bound).

        A NULL `commence_time` says nothing about retention. Dropping those rows
        would quietly shrink the population the sweep claims to cover.
        """
        with seeded_starvation_db.begin() as conn:
            conn.execute(
                text(INSERT),
                {
                    "id": 9002,
                    "external_id": "KXNOCOMMENCE-01",
                    "market_tier": 3,
                    "commence_time": None,
                    "resolution_date": (NOW + timedelta(days=5)).isoformat(),
                },
            )
            rows = conn.execute(
                text(_mod().SELECT_SQL),
                {
                    "purge_floor": PURGE_FLOOR.isoformat(),
                    "limit": BATCH,
                    "offset": 0,
                },
            ).all()

        assert "KXNOCOMMENCE-01" in {r[1] for r in rows}

    def test_the_excluded_rows_are_counted_not_silently_dropped(
        self, seeded_starvation_db
    ):
        """A bounded sweep must never read as a complete one (no silent caps)."""
        with seeded_starvation_db.begin() as conn:
            totals = conn.execute(
                text(_mod().COUNT_SQL), {"purge_floor": PURGE_FLOOR.isoformat()}
            ).first()

        assert totals[0] == BATCH + 1, "eligible_total counts the whole population"
        assert totals[1] == BATCH, (
            "excluded_purged must report exactly the rows the floor removed, or "
            "an operator reads 1 candidate and concludes 1 row was left to do"
        )

    def test_an_already_repaired_row_is_not_reselected(self, seeded_starvation_db):
        """`expiration_time IS NULL` is the durable progress marker.

        This is what makes the sweep converge: a written row leaves the population.
        If it did not, the floor alone would not save the tail.
        """
        with seeded_starvation_db.begin() as conn:
            conn.execute(
                text(_mod().UPDATE_SQL),
                {
                    "id": 9001,
                    "resolution_date": (NOW - timedelta(days=3)).isoformat(),
                    "expiration_time": (NOW + timedelta(days=31)).isoformat(),
                    "updated_at": NOW.isoformat(),
                },
            )
            rows = conn.execute(
                text(_mod().SELECT_SQL),
                {
                    "purge_floor": PURGE_FLOOR.isoformat(),
                    "limit": BATCH,
                    "offset": 0,
                },
            ).all()

        assert rows == [], (
            "once the backstop column is written the row must drop out of the "
            "candidate set; otherwise every run reselects its own finished work"
        )


# --- CAL-P992: the sweep must be able to come BACK to a row it already wrote --
#
# The pre-CAL-P992 candidate test, kept verbatim as the defect arm. `expiration_time
# IS NULL` reads "have I ever touched this row", which is not the same question as
# "is this row's date final" — and Kalshi makes the difference load-bearing, because
# it publishes the backstop AS `close_time` while a market is active and rewrites it
# to the settlement instant on finalize.
SEALED_DEFECT_SELECT_SQL = """
    SELECT id, external_id, resolution_date, commence_time, market_tier
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND expiration_time IS NULL
      AND (commence_time IS NULL OR commence_time >= :purge_floor)
    ORDER BY market_tier ASC NULLS LAST, commence_time DESC NULLS LAST
    LIMIT :limit OFFSET :offset
"""

INSERT_SWEPT = """
    INSERT INTO futures_markets
        (id, external_id, source, status, market_tier, commence_time,
         resolution_date, expiration_time, updated_at)
    VALUES (:id, :external_id, 'kalshi', 'open', :market_tier, :commence_time,
            :resolution_date, :expiration_time, :updated_at)
"""

#: The backstop these fixtures share. Kalshi hands the same legal expiry to every leg
#: of a tennis prop event, which is why a mid-life sweep writes it into BOTH columns.
BACKSTOP = NOW + timedelta(days=11)


@pytest.fixture
def seeded_sealed_db():
    """Production's shape on 2026-09-02, seeded: 600 sealed tier-1 rows + the tail.

    * 600 tier-1 rows the sweep wrote while their markets were still trading, so
      `resolution_date == expiration_time == BACKSTOP`. Freshly stamped, because the
      2h poller is still enumerating them as open.
    * `KXWTASETWINNER-26AUG30JOVFRE-1` — tier 5, same sealed shape, but Kalshi
      finalized it, so the poller stopped enumerating it (gotcha #33) and its
      `updated_at` is FROZEN two days back. This is the row the whole change exists
      for; there are more than `BATCH` tier-1 rows ahead of it precisely so that a
      tier-first ordering cannot reach it.
    * `KXCONVERGED-01` — the sweep already read a real `close_time` for it, so
      `resolution_date < expiration_time`. The control: it must stay OUT.
    """
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))
        for i in range(600):
            conn.execute(
                text(INSERT_SWEPT),
                {
                    "id": i + 1,
                    "external_id": f"KXSEALEDT1-{i:04d}",
                    "market_tier": 1,
                    "commence_time": BACKSTOP.isoformat(),
                    "resolution_date": BACKSTOP.isoformat(),
                    "expiration_time": BACKSTOP.isoformat(),
                    "updated_at": (NOW - timedelta(minutes=20)).isoformat(),
                },
            )
        conn.execute(
            text(INSERT_SWEPT),
            {
                "id": 9101,
                "external_id": "KXWTASETWINNER-26AUG30JOVFRE-1",
                "market_tier": 5,
                # Poisoned by the same backstop: measured on production, 4,954 of
                # the 5,143 sealed rows carry `commence_time = expiration_time`, so
                # a "has it commenced yet" gate would miss this row entirely.
                "commence_time": BACKSTOP.isoformat(),
                "resolution_date": BACKSTOP.isoformat(),
                "expiration_time": BACKSTOP.isoformat(),
                "updated_at": (NOW - timedelta(days=2)).isoformat(),
            },
        )
        conn.execute(
            text(INSERT_SWEPT),
            {
                "id": 9102,
                "external_id": "KXCONVERGED-01",
                "market_tier": 1,
                "commence_time": (NOW - timedelta(days=4)).isoformat(),
                "resolution_date": (NOW - timedelta(days=3)).isoformat(),
                "expiration_time": BACKSTOP.isoformat(),
                "updated_at": (NOW - timedelta(days=9)).isoformat(),
            },
        )
    return engine


def _select(engine, sql, limit=BATCH, offset=0):
    with engine.begin() as conn:
        return conn.execute(
            text(sql),
            {
                "purge_floor": PURGE_FLOOR.isoformat(),
                "limit": limit,
                "offset": offset,
            },
        ).all()


class TestASweptRowIsNotFinishedUntilItsDateIs:
    """CAL-P992. The first sweep drained the backlog and re-created it silently."""

    def test_the_defect_arm_cannot_see_the_sealed_row(self, seeded_sealed_db):
        """The failure, shown: `expiration_time IS NULL` selects nothing at all.

        Every row in this fixture has been written once. Under the pre-CAL-P992
        predicate the whole population — including the finalized US Open leg still
        advertising a date eleven days out — is invisible forever.
        """
        rows = _select(seeded_sealed_db, SEALED_DEFECT_SELECT_SQL)

        assert rows == [], (
            "fixture check: if the pre-CAL-P992 SQL selects anything here, this "
            "file is not reproducing the seal and the guard below proves nothing"
        )

    def test_the_sealed_finalized_row_is_selectable_again(self, seeded_sealed_db):
        """The ship: a provisional date is a candidate, however often it was written."""
        tickers = [r[1] for r in _select(seeded_sealed_db, _mod().SELECT_SQL)]

        assert "KXWTASETWINNER-26AUG30JOVFRE-1" in tickers, (
            "RED-FIRST ANCHOR: this is the row the venue finalized an hour after "
            "the sweep sealed it. If it is not selectable the card keeps a date "
            "eleven days out forever, because the open-market poll can never "
            "re-enumerate a finalized event (gotcha #33)."
        )

    def test_a_row_with_a_real_close_time_stays_out(self, seeded_sealed_db):
        """The control, and the reason the sweep still converges.

        Without this the change would merely swap one starvation for an infinite
        loop: every row ever written would be re-read on every run.
        """
        tickers = {r[1] for r in _select(seeded_sealed_db, _mod().SELECT_SQL)}

        assert "KXCONVERGED-01" not in tickers, (
            "once the venue has moved `resolution_date` EARLIER than the backstop "
            "the date is final and the row is done. Selecting it again means the "
            "sweep never terminates."
        )

    def test_the_sealed_row_is_reached_within_the_first_batch(self, seeded_sealed_db):
        """A predicate that selects a row the ORDER BY never reaches is not a fix.

        600 sealed tier-1 rows sit ahead of the tier-5 leg under the old
        `market_tier ASC` key — production's real shape, where tier 1+2 hold 2,951
        provisional rows and tier 5 holds 2,038. `updated_at ASC` puts the leg
        first instead, because its stamp froze when Kalshi stopped enumerating it.
        """
        tickers = [r[1] for r in _select(seeded_sealed_db, _mod().SELECT_SQL)]

        assert len(tickers) == BATCH, "the batch must still be full — no silent cap"
        assert tickers[0] == "KXWTASETWINNER-26AUG30JOVFRE-1", (
            "least-recently-enumerated must come first. Under `market_tier ASC` "
            "this row sorts at position 601 and a --limit 500 run never sees it."
        )
        assert all(t.startswith("KXSEALEDT1-") for t in tickers[1:]), (
            "control: the rest of the batch is the tier-1 sealed cohort, so the "
            "ordering assertion above is about position and not about a fixture "
            "that only had one candidate"
        )

    def test_the_two_selection_reasons_are_counted_apart(self, seeded_sealed_db):
        """An operator must be able to tell a shrinking tail from a refilling one."""
        with seeded_sealed_db.begin() as conn:
            conn.execute(
                text(INSERT),
                {
                    "id": 9103,
                    "external_id": "KXNEVERSWEPT-01",
                    "market_tier": 3,
                    "commence_time": (NOW - timedelta(days=2)).isoformat(),
                    "resolution_date": BACKSTOP.isoformat(),
                },
            )
            totals = conn.execute(
                text(_mod().COUNT_SQL), {"purge_floor": PURGE_FLOOR.isoformat()}
            ).first()

        eligible_total, _excluded, never_swept, provisional = totals
        assert never_swept == 1, "the legacy tail: rows the sweep has never touched"
        assert provisional == 601, (
            "600 sealed tier-1 rows plus the finalized tier-5 leg. KXCONVERGED-01 "
            "is excluded because its date is final."
        )
        assert eligible_total == never_swept + provisional, (
            "the two reasons must partition the eligible population; if they "
            "overlap or leave a gap the report is not readable as a census"
        )


# --- composed path: selection -> venue -> the two-column UPDATE --------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Records every statement and its parameters. Answers the two reads by shape."""

    def __init__(self, recorder, rows, totals):
        self._recorder = recorder
        self._rows = rows
        self._totals = totals
        self.committed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self._recorder.append((sql, params))
        if sql.strip().upper().startswith("UPDATE"):
            return _FakeResult([])
        if "count(*)" in sql:
            return _FakeResult([self._totals])
        return _FakeResult(self._rows)

    async def commit(self):
        self.committed += 1


class _FakeVenue:
    """One finalized WTA event — the real payload shape, 14-day legal backstop."""

    def __init__(self):
        self.closed = False
        self.asked = []

    async def get_event(self, ticker, with_nested_markets=True):
        self.asked.append(ticker)
        return {
            "markets": [
                {
                    "close_time": "2026-09-01T22:54:02Z",
                    "expiration_time": "2026-09-15T16:40:00Z",
                },
                {
                    "close_time": "2026-09-01T22:54:02Z",
                    "expiration_time": "2026-09-15T16:40:00Z",
                },
            ]
        }

    async def close(self):
        self.closed = True


STALE_ROW = (
    9001,
    "KXWTA-26MONTER",
    datetime(2026, 10, 3, 16, 40, tzinfo=timezone.utc),  # the stored backstop
    NOW - timedelta(days=3),
    2,
)


def _drive(apply: bool, rows=(STALE_ROW,)):
    import asyncio

    recorder: list = []
    venue = _FakeVenue()
    sessions: list[_FakeSession] = []

    def maker():
        # The totals tuple must have the same arity as `COUNT_SQL` returns
        # (eligible_total, excluded_purged, never_swept, provisional_recheck). A
        # fake that is narrower than the real result set would let a widened
        # COUNT_SQL ship with an IndexError nobody executed.
        s = _FakeSession(recorder, list(rows), (len(rows), 0, len(rows), 0))
        sessions.append(s)
        return s

    report = asyncio.run(
        _mod().run_backfill(
            session_maker=maker,
            client_factory=lambda: venue,
            limit=BATCH,
            apply=apply,
            now=NOW,
        )
    )
    return report, recorder, venue, sessions


class TestTheComposedApplyPath:
    """The named card reaches the two-column update. Nothing else moves."""

    def test_the_named_stale_row_reaches_the_update_with_close_time(self):
        report, recorder, venue, _ = _drive(apply=True)

        assert venue.asked == ["KXWTA-26MONTER"]
        updates = [
            (s, p) for s, p in recorder if s.strip().upper().startswith("UPDATE")
        ]
        assert len(updates) == 1, (
            "exactly one row was selected, so exactly one UPDATE must be issued; "
            f"got {len(updates)}"
        )
        _sql, params = updates[0]
        assert params["id"] == 9001
        assert params["resolution_date"] == datetime(
            2026, 9, 1, 22, 54, 2, tzinfo=timezone.utc
        ), (
            "the card must be dated when trading STOPPED. 2026-09-15 here is the "
            "legal backstop and the card keeps renting Discover page one."
        )
        assert params["expiration_time"] == datetime(
            2026, 9, 15, 16, 40, tzinfo=timezone.utc
        ), "no data loss: the backstop moves to its own column"
        assert report["stats"]["writes_applied"] == 1
        assert report["stats"]["newly_past"] == 1, (
            "the whole point: the stored date was in the future at NOW and the "
            "derived one is in the past, so #1818's `past resolution_date` "
            "predicate can finally select it"
        )

    def test_the_update_touches_only_the_two_date_columns(self):
        """A wrong date and a wrong grade are different defects (#1852's lesson)."""
        _report, recorder, _venue, _ = _drive(apply=True)

        sql = next(s for s, _ in recorder if s.strip().upper().startswith("UPDATE"))
        lowered = sql.lower()
        for forbidden in ("status", "is_winner", "current_price", "probability"):
            assert forbidden not in lowered, (
                f"the catch-up must never write `{forbidden}`: moving a date and "
                "a grade in one pass is how #1852 happened"
            )

    def test_dry_run_is_the_default_and_writes_nothing(self):
        report, recorder, venue, sessions = _drive(apply=False)

        assert report["mode"] == "DRY_RUN"
        assert report["stats"]["writes_prepared"] == 1
        assert report["stats"]["writes_applied"] == 0
        assert not any(s.strip().upper().startswith("UPDATE") for s, _ in recorder)
        assert sum(s.committed for s in sessions) == 0
        assert venue.closed, "the venue client must be closed even on a dry run"

    def test_the_venue_client_is_closed(self):
        _report, _recorder, venue, _ = _drive(apply=True)
        assert venue.closed, (
            "the client is constructed, not entered — so it must be closed in a "
            "finally, or every run leaks an httpx pool"
        )

    def test_the_select_is_bound_with_the_retention_floor(self):
        """The floor must reach the driver, not merely exist in the SQL text."""
        _report, recorder, _venue, _ = _drive(apply=False)

        select = next(s for s, _ in recorder if s.strip().upper().startswith("SELECT"))
        params = next(p for s, p in recorder if s.strip().upper().startswith("SELECT"))
        assert ":purge_floor" in select
        assert select.index(":purge_floor") < select.upper().index("ORDER BY"), (
            "RED-FIRST ANCHOR: the floor must be in the WHERE clause, ahead of "
            "the ORDER BY and the LIMIT. Applying it after the LIMIT is CERT-766's "
            "permanent starvation."
        )
        assert params["purge_floor"] == PURGE_FLOOR

    def test_zero_candidates_is_a_reported_outcome_not_a_success(self):
        """Gotcha #53: an empty result is a response shape, not an absence."""
        report, _recorder, _venue, _ = _drive(apply=True, rows=())

        assert report["zero_yield"] is True
        assert "eligible" in report["zero_yield_reason"]
        assert report["stats"]["writes_applied"] == 0
