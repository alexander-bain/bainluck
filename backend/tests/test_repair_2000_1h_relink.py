"""#2000 — guards on the relink that puts the May 9 first-half market back on the May 9 game.

The UPDATE is one column on one row, and it is an OVERWRITE of a non-null link
rather than a NULL fill — which is what makes it worth this many tests. The
sibling repair (#5621) could guard its write with `event_id IS NULL`; this one
has to name the value it is replacing, and every way that can go wrong is a test
here:

* the derivation's two arms are not really independent, or one of them is a
  restatement of the pinned table (`TestTheCorrespondenceIsDerivedTwice`);
* the sibling query matches a ticker by SUBSTRING, so a team-code pair spells the
  game token and a foreign market is counted as a sibling — calibration/2748's
  measured trap, one dash away from this script
  (`TestTheTokenIsAnchoredNotASubstring`);
* the row is linked somewhere this plan did not predict, and gets overwritten
  anyway (`TestARefusedOverwrite`);
* the premise is gone — the shipped predicate no longer disputes the current
  link, or disputes the target too (`TestTheShippedPredicateIsTheGate`);
* the target is unfit to receive it: unanchored, unplayed, or already holding a
  market of the same series (`TestTheTargetMustBeFit`);
* the row is not the one that was measured — re-sported, child count moved,
  id/ticker no longer one row (`TestChangedStateRefuses`);
* it writes from the wrong app, or before an undo exists
  (`TestTheWriteRefusals`, `TestTheBackupComesFirst`);
* a child row is touched, or an unrelated market is (`TestNothingElseIsTouched`);
* plan, apply and undo are not idempotent (`TestIdempotence`);
* the undo cannot start, which retroactively removes the D51(b) permission the
  repair was applied under, or it undoes a decision it did not make
  (`TestTheUndo`).

The specimen — market id, ticker, both event ids, the ESPN id, the outcome count
and the four siblings — is production, read 2026-09-22.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPAIR_PATH = _SCRIPTS / "repair_2000_1h_relink.py"
RESTORE_PATH = _SCRIPTS / "restore_2000_1h_relink.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def repair():
    return _load(REPAIR_PATH)


@pytest.fixture(scope="module")
def restore():
    return _load(RESTORE_PATH)


# ── the production rows, read 2026-09-22 ────────────────────────────────────

TICKER = "KXLALIGA1H-26MAY09RSORBB"
MARKET_ID = 15207269
FROM_EVENT_ID = 15011303  # Aug 26, completed 4-1 — the wrong one
TO_EVENT_ID = 14623338  # May 9, completed 2-2 — what the ticker says
TARGET_ESPN_ID = "748485"

#: The four siblings, all on TO_EVENT_ID. Production, same read.
SIBLINGS = [
    (15207257, "KXLALIGATOTAL-26MAY09RSORBB"),
    (15207258, "KXLALIGASPREAD-26MAY09RSORBB"),
    (15207259, "KXLALIGABTTS-26MAY09RSORBB"),
    (15207268, "KXLALIGAGAME-26MAY09RSORBB"),
]

AUG_KICKOFF = datetime(2026, 8, 26, 19, 0, tzinfo=timezone.utc)
MAY_KICKOFF = datetime(2026, 5, 9, 19, 0, tzinfo=timezone.utc)


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _market(**over):
    base = dict(
        id=MARKET_ID,
        external_id=TICKER,
        event_id=FROM_EVENT_ID,
        source="kalshi",
        status="resolved",
        market_tier=5,
        # 🔴 THESE TWO WERE ONE FIELD, AND THE FAKE IS WHY THE BUG SURVIVED.
        # `llm_sport_category="game_prop"` was written to satisfy the CODE rather
        # than copied off production, where the row reads `category=game_prop`
        # and `llm_sport_category=soccer`. A fake built from the code cannot
        # disagree with the code, so every arm below was green while the guard
        # compared a constant to the wrong column — found only by the first real
        # production dry run (`RESPORTED: category=soccer`, 2026-09-23 01:32Z,
        # which could not run until `bainluck-heavy` carried the script).
        # Re-measured on production 2026-09-23 01:4xZ across all five siblings.
        category="game_prop",
        llm_sport_category="soccer",
        sport_key="soccer_spain_la_liga",
        outcome_count=3,
    )
    base.update(over)
    return _Row(**base)


def _sibling_rows(event_id=TO_EVENT_ID, rows=None):
    """The four siblings as `futures_markets` rows the fake can group."""
    return [
        _Row(id=mid, external_id=ext, event_id=event_id, source="kalshi")
        for mid, ext in (SIBLINGS if rows is None else rows)
    ]


def _event(eid, commence, **over):
    base = dict(
        id=eid,
        espn_id=TARGET_ESPN_ID if eid == TO_EVENT_ID else None,
        home_team_name="Real Sociedad",
        away_team_name="Real Betis",
        commence_time=commence,
        status="completed",
        home_score=2 if eid == TO_EVENT_ID else 4,
        away_score=2 if eid == TO_EVENT_ID else 1,
        sport_key="soccer_spain_la_liga",
    )
    base.update(over)
    return _Row(**base)


def _default_events():
    return [_event(FROM_EVENT_ID, AUG_KICKOFF), _event(TO_EVENT_ID, MAY_KICKOFF)]


# ── the fake session ────────────────────────────────────────────────────────


class _Result:
    def __init__(self, rows, rowcount=None):
        self._rows = rows
        self.rowcount = len(rows) if rowcount is None else rowcount

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None


def _split_part(s: str, sep: str, n: int) -> str:
    """Postgres `split_part`, faithfully — 1-indexed, '' past the end.

    Implemented rather than approximated because it is the thing under test in
    `TestTheTokenIsAnchoredNotASubstring`: a fake that used `in` would pass a
    script that used `LIKE '%…'`, which is the bug.
    """
    parts = s.split(sep)
    return parts[n - 1] if 0 < n <= len(parts) else ""


class _FakeSession:
    """Answers by looking at the SQL, so it is order-independent.

    It emulates the WHERE clauses rather than returning canned rows, because the
    predicates — which market the id and ticker together name, which markets
    share the game token, which series already sits on the target — are the
    things under test. A fixture that returned "the right row" whatever was
    asked for would pass while the script asked for anything at all.
    """

    def __init__(
        self,
        markets=None,
        siblings=None,
        events=None,
        *,
        collisions=None,
        backup_exists=True,
        unbacked=0,
        outcomes=(3, 3),
        update_rowcount=1,
    ):
        self.markets = [_market()] if markets is None else markets
        self.siblings = _sibling_rows() if siblings is None else siblings
        self.events = _default_events() if events is None else events
        self.collisions = collisions or []
        self.backup_exists = backup_exists
        self.unbacked = unbacked
        self._outcomes = list(outcomes)
        self.update_rowcount = update_rowcount
        self.statements: list[tuple[str, dict]] = []
        self.committed = 0
        self.rolled_back = 0
        #: Commit/rollback in ORDER. `--backup` commits legitimately before the
        #: apply, so "did it commit" cannot distinguish a backup from a write.
        #: What a refusal claims is that nothing was committed AFTER the
        #: rollback.
        self.txn_log: list[str] = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        p = params or {}
        self.statements.append((sql, p))

        if "to_regclass" in sql:
            return _Result([self.backup_exists])
        # `startswith`, not `in`: the market SELECT carries a
        # `count(*) FROM futures_outcomes` SUBQUERY for its outcome_count, so a
        # containment test here swallows the market read and hands the script an
        # int where it expects a row.
        if sql.startswith("SELECT count(*) FROM futures_outcomes"):
            return _Result([self._outcomes.pop(0) if self._outcomes else 3])
        if "NOT EXISTS" in sql:
            return _Result([self.unbacked])
        if "GROUP BY f.event_id" in sql:
            hits = [
                s
                for s in self.siblings
                if _split_part(s.external_id, "-", 2) == p.get("token")
                and s.source == "kalshi"
                and s.id != p.get("mid")
            ]
            grouped: dict[int, int] = {}
            for s in hits:
                grouped[s.event_id] = grouped.get(s.event_id, 0) + 1
            return _Result(
                [
                    _Row(event_id=eid, n=n)
                    for eid, n in sorted(grouped.items(), key=lambda kv: -kv[1])
                ]
            )
        if "split_part(f.external_id, '-', 1)" in sql:
            return _Result(
                [
                    c
                    for c in self.collisions
                    if c.event_id == p.get("eid")
                    and _split_part(c.external_id, "-", 1) == p.get("prefix")
                    and c.id != p.get("mid")
                ]
            )
        if "FROM futures_markets f" in sql and "LEFT JOIN sports s" in sql:
            return _Result(
                [
                    m
                    for m in self.markets
                    if m.id == p.get("mid") or m.external_id == p.get("ticker")
                ]
            )
        if "FROM events e" in sql:
            return _Result([e for e in self.events if e.id in p.get("ids", [])])
        if sql.startswith("UPDATE futures_markets"):
            return _Result([], rowcount=self.update_rowcount)
        return _Result([])

    async def commit(self):
        self.committed += 1
        self.txn_log.append("commit")

    async def rollback(self):
        self.rolled_back += 1
        self.txn_log.append("rollback")

    def sql_starting(self, prefix):
        return [s for s, _ in self.statements if s.startswith(prefix)]

    @property
    def committed_after_rollback(self):
        if "rollback" not in self.txn_log:
            return self.committed
        tail = self.txn_log[len(self.txn_log) - self.txn_log[::-1].index("rollback") :]
        return tail.count("commit")


class _SessionFactory:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _args(**kw):
    return argparse.Namespace(**{**dict(backup=False, apply=False), **kw})


def _run(monkeypatch, mod, session, **kw):
    monkeypatch.setenv("HEROKU_APP_NAME", mod.PRODUCER_APP)
    monkeypatch.setattr(mod, "_session_factory", lambda: _SessionFactory(session))
    return asyncio.run(mod.run(_args(**kw)))


def _plan(mod, session):
    return asyncio.run(mod.plan(session))


# ── the correspondence ──────────────────────────────────────────────────────


class TestTheCorrespondenceIsDerivedTwice:
    def test_the_shipped_predicate_answers_both_pinned_questions(self):
        """Arm B is production code, and this is the assertion that it still says
        what the repair's header claims. Not a fake: the real function, the real
        ticker, the two real kick-off times."""
        from app.utils.market_identity import (
            eastern_game_date,
            market_identity_disputed,
            ticker_game_date,
        )

        assert ticker_game_date(TICKER).isoformat() == "2026-05-09"
        assert market_identity_disputed(TICKER, AUG_KICKOFF) is True
        assert market_identity_disputed(TICKER, MAY_KICKOFF) is False
        assert eastern_game_date(MAY_KICKOFF).isoformat() == "2026-05-09"

    def test_the_sane_check_gates_the_run(self, repair, monkeypatch):
        """If the imported predicate stops answering those questions, both arms
        move silently and only the pinned table is left. The run must refuse."""
        assert repair.shipped_predicate_is_sane() is True

        monkeypatch.setattr(repair, "shipped_predicate_is_sane", lambda: False)
        session = _FakeSession()
        assert _run(monkeypatch, repair, session, apply=True) == 2
        assert session.sql_starting("UPDATE") == []
        assert session.committed == 0

    def test_arm_a_derives_the_target_rather_than_reading_the_constant(
        self, repair, monkeypatch
    ):
        """Point the four siblings at a DIFFERENT event that is otherwise fit.
        If the target were taken from `TO_EVENT_ID` the plan would sail through;
        it must instead notice the derivation and the table disagree."""
        other = 14623999
        session = _FakeSession(
            siblings=_sibling_rows(event_id=other),
            events=[
                _event(FROM_EVENT_ID, AUG_KICKOFF),
                _event(other, MAY_KICKOFF, espn_id="999111"),
            ],
        )
        verdict, detail = _plan(repair, session)
        assert verdict == repair.PLAN_DISAGREES
        assert str(other) in detail

    def test_the_plan_is_the_specimen_production_holds(self, repair):
        session = _FakeSession()
        verdict, detail = _plan(repair, session)
        assert verdict == repair.RELINK
        assert f"{FROM_EVENT_ID}" in detail and f"{TO_EVENT_ID}" in detail


class TestTheTokenIsAnchoredNotASubstring:
    """calibration/2748, measured 2026-09-22: of 10,833 Kalshi rows whose ticker
    CONTAINS `btts`, three are basketball moneylines that hit it inside their
    trailing team-code pair. `RSORBB` is a team-code pair too, so a substring
    match here is the same class of bug one dash away."""

    def test_a_foreign_ticker_ending_in_the_token_is_not_a_sibling(
        self, repair, monkeypatch
    ):
        decoy = _Row(
            id=99999001,
            external_id="KXFOOGAME-99XXX26MAY09RSORBB",
            event_id=777001,
            source="kalshi",
        )
        session = _FakeSession(siblings=_sibling_rows() + [decoy])
        verdict, _ = _plan(repair, session)
        # With an anchored whole-token compare the decoy is invisible and the
        # four real siblings still answer cleanly. A `LIKE '%RSORBB'` would pull
        # the decoy in, span two events and blow up as SIBLINGS_DISAGREE.
        assert verdict == repair.RELINK

    def test_the_sibling_query_compares_the_whole_token(self, repair):
        sql = " ".join(repair._SIBLINGS_SQL.split())
        assert "split_part(f.external_id, '-', 2) = :token" in sql
        assert "LIKE" not in sql.upper()

    def test_the_collision_query_is_anchored_on_the_series_prefix(self, repair):
        sql = " ".join(repair._COLLISION_SQL.split())
        assert "split_part(f.external_id, '-', 1) = :prefix" in sql
        assert "LIKE" not in sql.upper()

    def test_the_tokens_are_derived_from_the_ticker_not_retyped(self, repair):
        assert repair.SERIES_PREFIX == "KXLALIGA1H"
        assert repair.GAME_TOKEN == "26MAY09RSORBB"
        assert repair.TICKER == f"{repair.SERIES_PREFIX}-{repair.GAME_TOKEN}"

    def test_siblings_spanning_two_events_refuse(self, repair):
        split = _sibling_rows()[:2] + [
            _Row(id=mid, external_id=ext, event_id=777002, source="kalshi")
            for mid, ext in SIBLINGS[2:]
        ]
        session = _FakeSession(siblings=split)
        verdict, detail = _plan(repair, session)
        assert verdict == repair.SIBLINGS_DISAGREE
        assert "span 2 events" in detail

    def test_a_missing_sibling_refuses(self, repair):
        session = _FakeSession(siblings=_sibling_rows(rows=SIBLINGS[:3]))
        verdict, detail = _plan(repair, session)
        assert verdict == repair.SIBLINGS_DISAGREE
        assert "3 siblings" in detail


class TestTheShippedPredicateIsTheGate:
    def test_a_current_link_the_predicate_accepts_refuses(self, repair):
        """The premise is gone: something already fixed the row's event, or the
        event's kick-off moved onto the ticker's date. Stop and look."""
        session = _FakeSession(
            events=[
                _event(FROM_EVENT_ID, MAY_KICKOFF),
                _event(TO_EVENT_ID, MAY_KICKOFF),
            ]
        )
        verdict, detail = _plan(repair, session)
        assert verdict == repair.NOT_DISPUTED
        assert "premise" in detail

    def test_a_target_the_predicate_also_disputes_refuses(self, repair):
        session = _FakeSession(
            events=[
                _event(FROM_EVENT_ID, AUG_KICKOFF),
                _event(TO_EVENT_ID, datetime(2026, 7, 1, 19, 0, tzinfo=timezone.utc)),
            ]
        )
        verdict, _ = _plan(repair, session)
        assert verdict == repair.TARGET_DISPUTED


class TestTheTargetMustBeFit:
    def test_an_unanchored_target_refuses(self, repair):
        """gotcha #32 / ruling 048 — an id-less row may never be a relink target."""
        session = _FakeSession(
            events=[
                _event(FROM_EVENT_ID, AUG_KICKOFF),
                _event(TO_EVENT_ID, MAY_KICKOFF, espn_id=None),
            ]
        )
        verdict, detail = _plan(repair, session)
        assert verdict == repair.TARGET_UNFIT
        assert "espn_id" in detail

    def test_an_unplayed_target_refuses(self, repair):
        session = _FakeSession(
            events=[
                _event(FROM_EVENT_ID, AUG_KICKOFF),
                _event(TO_EVENT_ID, MAY_KICKOFF, status="scheduled"),
            ]
        )
        verdict, _ = _plan(repair, session)
        assert verdict == repair.TARGET_UNFIT

    def test_a_target_already_holding_the_series_refuses(self, repair):
        """This repair ADDS a first-half market; it never creates a second one."""
        session = _FakeSession(
            collisions=[
                _Row(
                    id=15207270,
                    external_id="KXLALIGA1H-26MAY09RSORBB",
                    event_id=TO_EVENT_ID,
                )
            ]
        )
        verdict, detail = _plan(repair, session)
        assert verdict == repair.TARGET_UNFIT
        assert "already holds" in detail

    def test_a_missing_target_refuses(self, repair):
        session = _FakeSession(events=[_event(FROM_EVENT_ID, AUG_KICKOFF)])
        verdict, _ = _plan(repair, session)
        assert verdict == repair.TARGET_UNFIT


class TestARefusedOverwrite:
    def test_a_third_event_is_never_overwritten(self, repair):
        """A link this script did not predict is a decision by something it
        cannot see. This is the case `event_id IS NULL` would have caught for
        free in #5621 and which this repair has to name."""
        session = _FakeSession(markets=[_market(event_id=777003)])
        verdict, detail = _plan(repair, session)
        assert verdict == repair.UNEXPECTED_LINKAGE
        assert "not overwritten" in detail

    def test_an_unlinked_row_is_not_this_plan(self, repair):
        """NULL is not the registered wrong value either — the matcher may be
        about to link it itself, which is the outcome everyone wants."""
        session = _FakeSession(markets=[_market(event_id=None)])
        verdict, _ = _plan(repair, session)
        assert verdict == repair.UNEXPECTED_LINKAGE

    def test_the_update_names_the_value_it_replaces(self, repair, monkeypatch):
        session = _FakeSession()
        assert _run(monkeypatch, repair, session, apply=True) == 0
        updates = [(s, p) for s, p in session.statements if s.startswith("UPDATE")]
        assert len(updates) == 1
        sql, params = updates[0]
        assert "event_id = :from_eid" in sql
        assert "external_id = :ticker" in sql
        assert params["from_eid"] == FROM_EVENT_ID
        assert params["to_eid"] == TO_EVENT_ID
        assert params["mid"] == MARKET_ID
        assert params["ticker"] == TICKER

    def test_a_compare_and_set_that_matches_nothing_rolls_back(
        self, repair, monkeypatch
    ):
        session = _FakeSession(update_rowcount=0)
        assert _run(monkeypatch, repair, session, apply=True) == 2
        assert session.rolled_back == 1
        assert session.committed_after_rollback == 0


class TestChangedStateRefuses:
    def test_a_moved_child_count_refuses(self, repair):
        session = _FakeSession(markets=[_market(outcome_count=4)])
        verdict, detail = _plan(repair, session)
        assert verdict == repair.CHILD_COUNT_MOVED
        assert "4 outcomes" in detail

    @pytest.mark.parametrize(
        "field,value",
        [
            ("source", "polymarket"),
            ("status", "open"),
            ("market_tier", 3),
            # BOTH category columns, because the guard checks both and a
            # parametrize naming only one is how the mismatch stayed invisible.
            ("category", "player_prop"),
            ("llm_sport_category", "basketball"),
            ("sport_key", "soccer_epl"),
        ],
    )
    def test_a_resported_row_refuses(self, repair, field, value):
        session = _FakeSession(markets=[_market(**{field: value})])
        verdict, _ = _plan(repair, session)
        assert verdict == repair.RESPORTED

    def test_the_registered_shape_is_the_one_production_actually_carries(self, repair):
        """🔴 THE ARM THAT WOULD HAVE CAUGHT IT, AND IT IS NOT A TAUTOLOGY.

        The two constants are asserted against the values MEASURED on production
        (2026-09-23 01:4xZ, all five `26MAY09RSORBB` siblings), on the columns
        they are compared against in the plan. Written as literals rather than
        by reading the constants, so the file states the reading and a future
        edit to either constant has to disagree with a number somebody took.
        """
        assert repair.TARGET_CATEGORY == "game_prop"
        assert repair.TARGET_LLM_SPORT_CATEGORY == "soccer"
        # And the happy path must clear the guard with exactly those values.
        session = _FakeSession(
            markets=[_market(category="game_prop", llm_sport_category="soccer")]
        )
        verdict, _ = _plan(repair, session)
        assert verdict == repair.RELINK

    def test_the_id_and_the_ticker_must_name_one_row(self, repair):
        session = _FakeSession(
            markets=[_market(), _market(id=99999002, external_id=TICKER)]
        )
        verdict, _ = _plan(repair, session)
        assert verdict == repair.IDENTITY_CHANGED

    def test_the_id_carrying_a_different_ticker_refuses(self, repair):
        session = _FakeSession(
            markets=[_market(external_id="KXLALIGA1H-26JUN01RSORBB")]
        )
        verdict, detail = _plan(repair, session)
        assert verdict == repair.IDENTITY_CHANGED
        assert "carries" in detail

    def test_a_missing_row_refuses(self, repair):
        session = _FakeSession(markets=[])
        verdict, _ = _plan(repair, session)
        assert verdict == repair.IDENTITY_CHANGED

    def test_every_blocking_verdict_stops_the_apply(self, repair, monkeypatch):
        """The verdict list and the BLOCKING tuple must not drift apart."""
        session = _FakeSession(markets=[_market(outcome_count=4)])
        assert _run(monkeypatch, repair, session, apply=True) == 2
        assert session.sql_starting("UPDATE") == []
        assert session.committed == 0


class TestTheWriteRefusals:
    def test_the_wrong_app_refuses_to_write(self, repair, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        monkeypatch.setattr(
            repair, "_session_factory", lambda: _SessionFactory(_FakeSession())
        )
        assert asyncio.run(repair.run(_args(apply=True))) == 2
        assert asyncio.run(repair.run(_args(backup=True))) == 2

    def test_an_unset_app_refuses_to_write(self, repair, monkeypatch):
        """Unset means a laptop pointed at the production database."""
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        monkeypatch.setattr(
            repair, "_session_factory", lambda: _SessionFactory(_FakeSession())
        )
        assert asyncio.run(repair.run(_args(apply=True))) == 2

    def test_a_dry_run_is_allowed_anywhere(self, repair, monkeypatch):
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        session = _FakeSession()
        monkeypatch.setattr(
            repair, "_session_factory", lambda: _SessionFactory(session)
        )
        assert asyncio.run(repair.run(_args())) == 0
        assert session.sql_starting("UPDATE") == []
        assert session.committed == 0

    def test_the_producer_app_is_the_heavy_one(self, repair):
        """`match_prediction_markets` owns this column and is a HEAVY_TASK, so
        the web app's deploy says nothing about the code that would race it."""
        assert repair.PRODUCER_APP == "bainluck-heavy"

    def test_the_real_session_factory_resolves(self, repair):
        """CERT-903: `repair_2947` shipped importing a module that has never
        existed and died on import while every unit test passed against a fake."""
        assert repair._session_factory() is not None


class TestTheBackupComesFirst:
    def test_apply_refuses_when_the_backup_table_is_absent(self, repair, monkeypatch):
        session = _FakeSession(backup_exists=False)
        assert _run(monkeypatch, repair, session, apply=True) == 2
        assert session.sql_starting("UPDATE") == []

    def test_apply_refuses_when_the_backup_is_stale(self, repair, monkeypatch):
        """Content-exact, not existence-exact: a backup taken before an unrelated
        writer moved the row would have the undo restore a value that was never
        overwritten."""
        session = _FakeSession(unbacked=1)
        assert _run(monkeypatch, repair, session, apply=True) == 2
        assert session.sql_starting("UPDATE") == []

    def test_the_reconciliation_compares_content_not_existence(
        self, repair, monkeypatch
    ):
        session = _FakeSession()
        _run(monkeypatch, repair, session)
        recon = [s for s, _ in session.statements if "NOT EXISTS" in s]
        assert recon, "no reconciliation query ran"
        assert "b.event_id IS NOT DISTINCT FROM f.event_id" in recon[0]
        assert "b.external_id IS NOT DISTINCT FROM f.external_id" in recon[0]

    def test_the_first_dry_run_survives_an_absent_table(self, repair, monkeypatch):
        """`to_regclass` answers without raising — the runbook's step 1 happens
        before any `--backup` has ever run."""
        session = _FakeSession(backup_exists=False)
        assert _run(monkeypatch, repair, session) == 0

    def test_the_backup_refreshes_on_conflict(self, repair, monkeypatch):
        session = _FakeSession()
        _run(monkeypatch, repair, session, backup=True)
        inserts = [s for s, _ in session.statements if s.startswith("INSERT")]
        assert inserts and "ON CONFLICT (id) DO UPDATE" in inserts[0]
        assert "DO NOTHING" not in inserts[0]


class TestNothingElseIsTouched:
    def test_only_one_row_is_written_and_only_one_column(self, repair, monkeypatch):
        session = _FakeSession()
        assert _run(monkeypatch, repair, session, apply=True) == 0
        writes = [
            s
            for s, _ in session.statements
            if s.startswith(("UPDATE", "DELETE", "INSERT"))
        ]
        assert len(writes) == 1
        assert writes[0].startswith("UPDATE futures_markets SET event_id =")
        assert "futures_outcomes" not in writes[0]

    def test_no_child_row_is_ever_written(self, repair, monkeypatch):
        session = _FakeSession()
        _run(monkeypatch, repair, session, apply=True)
        for sql, _ in session.statements:
            if "futures_outcomes" in sql:
                assert sql.lstrip().upper().startswith("SELECT")

    def test_a_child_count_that_moves_inside_the_transaction_rolls_back(
        self, repair, monkeypatch
    ):
        session = _FakeSession(outcomes=(3, 2))
        assert _run(monkeypatch, repair, session, apply=True) == 2
        assert session.rolled_back == 1
        assert session.committed_after_rollback == 0

    def test_the_backup_copies_only_the_one_market(self, repair, monkeypatch):
        session = _FakeSession()
        _run(monkeypatch, repair, session, backup=True)
        inserts = [(s, p) for s, p in session.statements if s.startswith("INSERT")]
        assert inserts[0][1]["mid"] == MARKET_ID
        assert "WHERE id = :mid" in inserts[0][0]


class TestIdempotence:
    def test_a_row_already_on_the_target_is_a_no_op(self, repair, monkeypatch):
        session = _FakeSession(markets=[_market(event_id=TO_EVENT_ID)])
        verdict, _ = _plan(repair, session)
        assert verdict == repair.ALREADY_RELINKED
        assert verdict not in repair.BLOCKING

        assert _run(monkeypatch, repair, session, apply=True) == 0
        assert session.sql_starting("UPDATE") == []

    def test_already_relinked_is_checked_before_the_dispute_arms(self, repair):
        """Once the row is on the target the current link is correctly
        undisputed, so an arm-first ordering would report NOT_DISPUTED on a run
        that has simply already happened."""
        session = _FakeSession(markets=[_market(event_id=TO_EVENT_ID)])
        verdict, _ = _plan(repair, session)
        assert verdict == repair.ALREADY_RELINKED

    def test_a_second_dry_run_writes_nothing(self, repair, monkeypatch):
        session = _FakeSession()
        assert _run(monkeypatch, repair, session) == 0
        assert _run(monkeypatch, repair, session) == 0
        assert session.committed == 0


# ── the undo ────────────────────────────────────────────────────────────────


class _RestoreSession(_FakeSession):
    def __init__(
        self,
        *,
        now_eid=TO_EVENT_ID,
        was_eid=FROM_EVENT_ID,
        unbacked=False,
        exists=True,
        missing=False,
        update_rowcount=1,
        **kw,
    ):
        # Handed to the base rather than re-assigned after it: overwriting an
        # inherited attribute works but reads as a bug (CodeQL
        # `py/overwritten-inherited-attribute`), and the base already takes both.
        super().__init__(backup_exists=exists, update_rowcount=update_rowcount, **kw)
        self._now = now_eid
        self._was = was_eid
        self._unbacked = unbacked
        self._missing = missing

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        p = params or {}
        self.statements.append((sql, p))
        if "to_regclass" in sql:
            return _Result([self.backup_exists])
        if "LEFT JOIN" in sql and "futures_markets f" in sql:
            if self._missing:
                return _Result([])
            return _Result(
                [
                    _Row(
                        id=MARKET_ID,
                        external_id=TICKER,
                        now_eid=self._now,
                        was_eid=self._was,
                        unbacked=self._unbacked,
                    )
                ]
            )
        if sql.startswith("UPDATE futures_markets"):
            return _Result([], rowcount=self.update_rowcount)
        return _Result([])


class TestTheUndo:
    def test_the_undo_imports_and_its_session_factory_resolves(self, restore):
        """D51 permits an unattended production write BECAUSE a one-command undo
        exists. An undo that cannot start retroactively removes the permission."""
        assert restore._session_factory() is not None
        assert restore.BACKUP_TABLE == "backup_2000_1h_relink_markets"
        assert restore.MARKET_ID == MARKET_ID

    def test_it_takes_the_same_app_gate(self, restore, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        monkeypatch.setattr(
            restore, "_session_factory", lambda: _SessionFactory(_RestoreSession())
        )
        assert asyncio.run(restore.run(argparse.Namespace(apply=True))) == 2

    def test_the_app_gate_does_not_raise_on_a_parser_without_backup(self, restore):
        """One refusal serving two programs: the undo's parser defines no
        `--backup`, so a bare attribute read would AttributeError."""
        assert restore.wrong_app_refusal(argparse.Namespace(apply=False)) is None

    def test_it_puts_the_row_back(self, restore, monkeypatch):
        session = _RestoreSession()
        monkeypatch.setenv("HEROKU_APP_NAME", restore.PRODUCER_APP)
        monkeypatch.setattr(
            restore, "_session_factory", lambda: _SessionFactory(session)
        )
        assert asyncio.run(restore.run(argparse.Namespace(apply=True))) == 0
        updates = [(s, p) for s, p in session.statements if s.startswith("UPDATE")]
        assert len(updates) == 1
        assert updates[0][1]["was"] == FROM_EVENT_ID
        assert updates[0][1]["now"] == TO_EVENT_ID
        assert session.committed == 1

    def test_it_refuses_to_undo_a_decision_it_did_not_make(self, restore, monkeypatch):
        """Most likely the matcher finally doing its job — never stomped."""
        session = _RestoreSession(now_eid=777004)
        monkeypatch.setenv("HEROKU_APP_NAME", restore.PRODUCER_APP)
        monkeypatch.setattr(
            restore, "_session_factory", lambda: _SessionFactory(session)
        )
        assert asyncio.run(restore.run(argparse.Namespace(apply=True))) == 0
        assert session.sql_starting("UPDATE") == []

    def test_an_unbacked_row_is_never_guessed(self, restore, monkeypatch):
        session = _RestoreSession(unbacked=True, was_eid=None)
        monkeypatch.setenv("HEROKU_APP_NAME", restore.PRODUCER_APP)
        monkeypatch.setattr(
            restore, "_session_factory", lambda: _SessionFactory(session)
        )
        assert asyncio.run(restore.run(argparse.Namespace(apply=True))) == 0
        assert session.sql_starting("UPDATE") == []

    def test_an_absent_backup_table_is_not_a_crash(self, restore, monkeypatch):
        session = _RestoreSession(exists=False)
        monkeypatch.setenv("HEROKU_APP_NAME", restore.PRODUCER_APP)
        monkeypatch.setattr(
            restore, "_session_factory", lambda: _SessionFactory(session)
        )
        assert asyncio.run(restore.run(argparse.Namespace(apply=True))) == 0

    def test_a_second_run_is_a_no_op(self, restore, monkeypatch):
        session = _RestoreSession(now_eid=FROM_EVENT_ID)
        monkeypatch.setenv("HEROKU_APP_NAME", restore.PRODUCER_APP)
        monkeypatch.setattr(
            restore, "_session_factory", lambda: _SessionFactory(session)
        )
        assert asyncio.run(restore.run(argparse.Namespace(apply=True))) == 0
        assert session.sql_starting("UPDATE") == []

    def test_a_dry_run_writes_nothing(self, restore, monkeypatch):
        session = _RestoreSession()
        monkeypatch.setenv("HEROKU_APP_NAME", restore.PRODUCER_APP)
        monkeypatch.setattr(
            restore, "_session_factory", lambda: _SessionFactory(session)
        )
        assert asyncio.run(restore.run(argparse.Namespace(apply=False))) == 0
        assert session.sql_starting("UPDATE") == []
        assert session.committed == 0

    def test_the_guarded_restore_that_matches_nothing_rolls_back(
        self, restore, monkeypatch
    ):
        session = _RestoreSession(update_rowcount=0)
        monkeypatch.setenv("HEROKU_APP_NAME", restore.PRODUCER_APP)
        monkeypatch.setattr(
            restore, "_session_factory", lambda: _SessionFactory(session)
        )
        assert asyncio.run(restore.run(argparse.Namespace(apply=True))) == 2
        assert session.rolled_back == 1
        assert session.committed_after_rollback == 0
