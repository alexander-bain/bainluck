"""#5621 residual — guards on the relink that puts two settled props back on their games.

The UPDATE is one column on two rows. Everything that can go wrong with this
repair is around the edges, and each of those is a test here:

* the market id and the ticker are TRANSPOSED — the commissioning directive's own
  pairing, which would have put each prop on the other team's game
  (`TestIdentityIsPinnedToTheTicker`);
* the derivation and the pre-registered table disagree, or the derivation finds
  no target or two (`TestTheTargetIsDerivedAndChecked`);
* the row is already linked somewhere this plan did not predict, and gets
  overwritten (`TestARefusedOverwrite`);
* the row is not the one that was measured — re-sported, or its child count moved
  (`TestChangedStateRefuses`);
* it writes from the wrong app, before the prevention is live, or before an undo
  exists (`TestTheWriteRefusals`, `TestTheBackupComesFirst`);
* a child row is touched, or an unrelated market is (`TestNothingElseIsTouched`);
* plan, apply and undo are not idempotent (`TestIdempotence`);
* the undo cannot start, which retroactively removes the D51(b) permission the
  repair was applied under (`TestTheUndoTakesTheSameGate`).

The two specimens, their tickers, event ids, ESPN ids and outcome counts are
production rows read 2026-09-17; the fourteen siblings in
:data:`FAMILY_ORIENTATION` are the rest of the series, read the same way, and
they are the control for the away-first orientation claim.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
from datetime import date
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPAIR_PATH = _SCRIPTS / "repair_5621_settled_ffpts_relink.py"
RESTORE_PATH = _SCRIPTS / "restore_5621_settled_ffpts_relink.py"


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


# ── the production rows, read 2026-09-17 ────────────────────────────────────

NESEA = "KXNFLFFPTS-26SEP09NESEA"
SFLAR = "KXNFLFFPTS-26SEP10SFLAR"

#: ticker -> (market id, event id, espn id, outcomes, away name, home name, ET date)
SPECIMENS = {
    NESEA: (
        60617788,
        14780138,
        "401872656",
        14,
        "New England Patriots",
        "Seattle Seahawks",
        date(2026, 9, 9),
    ),
    SFLAR: (
        60617215,
        14632820,
        "401872657",
        13,
        "San Francisco 49ers",
        "Los Angeles Rams",
        date(2026, 9, 10),
    ),
}

#: The whole `KXNFLFFPTS` series as production stores it — the two specimens plus
#: the fourteen the MATCHER linked by itself. `(ticker, away nickname, home
#: nickname)`. This is the control for "Kalshi writes the away side first": the
#: claim is not that the convention is documented somewhere, it is that fourteen
#: rows a healthy writer linked all store the ticker's first code as the away
#: team. Read on production 2026-09-17, 14/14 agreement and 0 disagreements.
FAMILY_ORIENTATION = [
    (NESEA, "Patriots", "Seahawks"),
    (SFLAR, "49ers", "Rams"),
    ("KXNFLFFPTS-26SEP13ARILAC", "Cardinals", "Chargers"),
    ("KXNFLFFPTS-26SEP13ATLPIT", "Falcons", "Steelers"),
    ("KXNFLFFPTS-26SEP13BALIND", "Ravens", "Colts"),
    ("KXNFLFFPTS-26SEP13BUFHOU", "Bills", "Texans"),
    ("KXNFLFFPTS-26SEP13CHICAR", "Bears", "Panthers"),
    ("KXNFLFFPTS-26SEP13CLEJAC", "Browns", "Jaguars"),
    ("KXNFLFFPTS-26SEP13DALNYG", "Cowboys", "Giants"),
    ("KXNFLFFPTS-26SEP13GBMIN", "Packers", "Vikings"),
    ("KXNFLFFPTS-26SEP13MIALV", "Dolphins", "Raiders"),
    ("KXNFLFFPTS-26SEP13NODET", "Saints", "Lions"),
    ("KXNFLFFPTS-26SEP13NYJTEN", "Jets", "Titans"),
    ("KXNFLFFPTS-26SEP13TBCIN", "Buccaneers", "Bengals"),
    ("KXNFLFFPTS-26SEP13WASPHI", "Commanders", "Eagles"),
    ("KXNFLFFPTS-26SEP14DENKC", "Broncos", "Chiefs"),
]


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _market(ticker, *, event_id=None, **over):
    mid, eid, espn, n, away, home, _d = SPECIMENS[ticker]
    base = dict(
        id=mid,
        external_id=ticker,
        event_id=event_id,
        source="kalshi",
        status="resolved",
        market_tier=5,
        llm_sport_category="football",
        sport_id=1,
        sport_key="americanfootball_nfl",
        outcome_count=n,
    )
    base.update(over)
    return _Row(**base)


def _event(ticker, **over):
    _m, eid, espn, _n, away, home, d = SPECIMENS[ticker]
    base = dict(
        id=eid,
        espn_id=espn,
        home_team_name=home,
        away_team_name=away,
        commence_time="2026-09-10 00:20:00+00:00",
        status="completed",
        _et_date=d,
    )
    base.update(over)
    return _Row(**base)


def _default_markets():
    return [_market(NESEA), _market(SFLAR)]


def _default_events():
    return [_event(NESEA), _event(SFLAR)]


# ── the fake session ────────────────────────────────────────────────────────


class _Result:
    def __init__(self, rows, rowcount=None):
        self._rows = rows
        self.rowcount = len(rows) if rowcount is None else rowcount

    def all(self):
        return self._rows

    def scalar(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Answers by looking at the SQL, so it is order-independent.

    It emulates the two SELECTs' WHERE clauses rather than returning canned
    rows, because the predicate — which market the id and ticker together name,
    and which event the resolver's nicknames and date reach — is the thing under
    test. A fixture that returns "the right row" whatever was asked for would
    pass while the script asked for anything at all.
    """

    def __init__(
        self,
        markets=None,
        events=None,
        *,
        backup_exists=True,
        unbacked=0,
        outcomes=(27, 27),
        update_rowcount=1,
    ):
        self.markets = _default_markets() if markets is None else markets
        self.events = _default_events() if events is None else events
        self.backup_exists = backup_exists
        self.unbacked = unbacked
        self._outcomes = list(outcomes)
        self.update_rowcount = update_rowcount
        self.statements: list[tuple[str, dict]] = []
        self.committed = 0
        self.rolled_back = 0
        #: Commit/rollback in ORDER. `--backup` commits legitimately before the
        #: apply, so "did it commit" cannot distinguish a backup from a write —
        #: the first cut of these tests asserted `committed == 0` and failed on
        #: runs the script had correctly refused. What the refusal claims is that
        #: NOTHING was committed AFTER the rollback.
        self.txn_log: list[str] = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        p = params or {}
        self.statements.append((sql, p))

        if "to_regclass" in sql:
            return _Result([self.backup_exists])
        if "FROM futures_markets f" in sql and "LEFT JOIN sports s" in sql:
            hits = [
                m
                for m in self.markets
                if m.id == p.get("mid") or m.external_id == p.get("ticker")
            ]
            return _Result(hits)
        if "FROM events e" in sql and "JOIN sports s" in sql:
            hits = [
                e
                for e in self.events
                if e.home_team_name.lower().endswith(p["home_nick"].lower())
                and e.away_team_name.lower().endswith(p["away_nick"].lower())
                and e._et_date == p["game_date"]
                and e.espn_id is not None
                and e.status in ("completed", "closed")
            ]
            return _Result(hits)
        if "count(*) FROM futures_outcomes" in sql:
            return _Result([self._outcomes.pop(0) if self._outcomes else 27])
        if "count(*) FROM futures_markets f" in sql:
            return _Result([self.unbacked])
        if sql.startswith("UPDATE futures_markets"):
            return _Result([], rowcount=self.update_rowcount)
        return _Result([])

    async def commit(self):
        self.committed += 1
        self.txn_log.append("commit")

    async def rollback(self):
        self.rolled_back += 1
        self.txn_log.append("rollback")

    # convenience for the assertions
    def sql_starting(self, prefix):
        return [s for s, _ in self.statements if s.startswith(prefix)]

    @property
    def committed_after_rollback(self):
        """Commits that happened after the last rollback — the real question."""
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


# ── the correspondence ──────────────────────────────────────────────────────


class TestTheCorrespondenceComesFromTheProvider:
    def test_the_registered_pairs_are_what_the_shipped_resolver_reads(self, repair):
        """No hand-typed abbreviation table — the matcher's own parser."""
        from app.utils.prediction_market_matching import (
            extract_team_codes_from_ticker,
        )

        for ticker, away_nick, home_nick in FAMILY_ORIENTATION:
            codes = extract_team_codes_from_ticker(ticker)
            assert codes is not None, ticker
            (_a_ab, a_nick), (_h_ab, h_nick) = codes
            assert (a_nick, h_nick) == (away_nick, home_nick), ticker

    def test_kalshi_writes_the_away_side_first(self, repair):
        """The orientation claim, on the fourteen rows the matcher linked itself.

        If this ever inverts, every pair in `EXPECTED` is backwards and the two
        props land on the wrong games — which is precisely the failure the
        transposed directive would have produced by another route.
        """
        for ticker in SPECIMENS:
            _m, _e, _espn, _n, away, home, _d = SPECIMENS[ticker]
            from app.utils.prediction_market_matching import (
                extract_team_codes_from_ticker,
            )

            (_a, a_nick), (_h, h_nick) = extract_team_codes_from_ticker(ticker)
            assert away.endswith(a_nick), ticker
            assert home.endswith(h_nick), ticker

    @pytest.mark.parametrize(
        "ticker,expected",
        [
            (NESEA, date(2026, 9, 9)),
            (SFLAR, date(2026, 9, 10)),
            ("KXNFLFFPTS-26SEP14DENKC", date(2026, 9, 14)),
        ],
    )
    def test_the_ticker_date_is_the_venues_calendar_date(
        self, repair, ticker, expected
    ):
        assert repair.ticker_game_date(ticker) == expected

    @pytest.mark.parametrize(
        "bad", ["", "KXNFLFFPTS", "KXNFLFFPTS-XX", "KXNFLFFPTS-26ZZZ09NESEA"]
    )
    def test_an_unparseable_ticker_is_not_given_a_default_date(self, repair, bad):
        """A date this cannot read must be `None`, never today's."""
        assert repair.ticker_game_date(bad) is None


# ── the headline guard: the directive's own transposition ───────────────────


class TestIdentityIsPinnedToTheTicker:
    def test_expected_is_keyed_on_the_provider_identity(self, repair):
        assert set(repair.EXPECTED) == {NESEA, SFLAR}
        for ticker, (mid, eid, espn, n, *_r) in SPECIMENS.items():
            assert repair.EXPECTED[ticker] == (mid, eid, espn, n)

    def test_the_transposed_pairing_is_refused_not_silently_swapped(
        self, monkeypatch, repair
    ):
        """The commissioning directive paired 60617215 with `-26SEP09NESEA`.

        Production has it the other way round. Acting on the ids alone would put
        each prop on the other team's game — two wrong links replacing two absent
        ones, which gotcha #15 then makes permanent. A run whose registered id
        does not carry the registered ticker must refuse.
        """
        transposed = dict(repair.EXPECTED)
        transposed[NESEA] = (60617215, 14780138, "401872656", 14)
        transposed[SFLAR] = (60617788, 14632820, "401872657", 13)
        monkeypatch.setattr(repair, "EXPECTED", transposed)

        session = _FakeSession()
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2
        assert session.committed == 0
        assert not session.sql_starting("UPDATE futures_markets")

    def test_a_vanished_market_row_refuses(self, monkeypatch, repair):
        session = _FakeSession(markets=[_market(SFLAR)])
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2
        assert not session.sql_starting("UPDATE futures_markets")

    def test_a_row_whose_id_matches_but_ticker_does_not_refuses(
        self, monkeypatch, repair
    ):
        """The registered id now carries a DIFFERENT ticker — one row, not two.

        This is the branch the transposition test does not reach: there, the id
        and the ticker name two separate rows and the row-count clause catches
        it. Here they name ONE row whose ticker has changed under us, and only
        `m.external_id != ticker` can say so. Without this test, deleting that
        clause outright kept all 62 guards green (measured 2026-09-17) — the
        headline guard of this file was vacuous from birth.
        """
        renamed = _market(NESEA, external_id="KXNFLFFPTS-26SEP09NESEA-RETIRED")
        session = _FakeSession(markets=[renamed, _market(SFLAR)])
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2
        assert not session.sql_starting("UPDATE futures_markets")

    def test_a_reused_id_carrying_another_series_refuses(self, monkeypatch, repair):
        """Same branch, the other way: the id is right, the row is not ours."""
        foreign = _market(NESEA, external_id="KXNBAGAME-26FEB21DETCHI")
        session = _FakeSession(markets=[foreign, _market(SFLAR)])
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2
        assert not session.sql_starting("UPDATE futures_markets")


# ── the target ──────────────────────────────────────────────────────────────


class TestTheTargetIsDerivedAndChecked:
    def test_the_happy_plan_is_the_two_measured_pairs(self, monkeypatch, repair):
        session = _FakeSession()
        assert _run(monkeypatch, repair, session) == 0
        assert session.committed == 0  # a dry run writes nothing

    def test_a_missing_target_refuses(self, monkeypatch, repair):
        session = _FakeSession(events=[_event(SFLAR)])
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2
        assert not session.sql_starting("UPDATE futures_markets")

    def test_an_unanchored_target_is_not_a_target(self, monkeypatch, repair):
        """Ruling 048 / gotcha #32 — an id-less row may never receive a relink."""
        session = _FakeSession(events=[_event(NESEA, espn_id=None), _event(SFLAR)])
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2

    def test_two_candidates_refuse_rather_than_pick(self, monkeypatch, repair):
        twin = _event(NESEA, id=99_000_001)
        session = _FakeSession(events=[_event(NESEA), twin, _event(SFLAR)])
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2
        assert not session.sql_starting("UPDATE futures_markets")

    def test_a_derivation_disagreeing_with_the_table_refuses(self, monkeypatch, repair):
        """Both statements must hold. A table that is never re-derived is a note."""
        session = _FakeSession(events=[_event(NESEA, id=14_999_999), _event(SFLAR)])
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2

    def test_a_wrong_espn_id_refuses_even_when_the_event_id_agrees(
        self, monkeypatch, repair
    ):
        session = _FakeSession(
            events=[_event(NESEA, espn_id="999999999"), _event(SFLAR)]
        )
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2

    def test_an_unplayed_target_is_refused(self, monkeypatch, repair):
        session = _FakeSession(
            events=[_event(NESEA, status="scheduled"), _event(SFLAR)]
        )
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2


# ── overwrite and changed state ─────────────────────────────────────────────


class TestARefusedOverwrite:
    def test_a_link_this_plan_did_not_predict_is_never_overwritten(
        self, monkeypatch, repair
    ):
        session = _FakeSession(
            markets=[_market(NESEA, event_id=12_345_678), _market(SFLAR)]
        )
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2
        assert session.committed == 0
        assert not session.sql_starting("UPDATE futures_markets")

    def test_the_write_is_a_compare_and_set(self, monkeypatch, repair):
        """A row linked between the plan and the write must not be stomped."""
        session = _FakeSession(update_rowcount=0)
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2
        assert session.rolled_back == 1
        assert session.committed_after_rollback == 0

    def test_the_guarded_update_pins_the_ticker_and_the_null(self, monkeypatch, repair):
        session = _FakeSession()
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 0
        updates = session.sql_starting("UPDATE futures_markets")
        assert updates, "the apply wrote nothing"
        for sql in updates:
            assert "external_id = :ticker" in sql
            assert "event_id IS NULL" in sql


class TestChangedStateRefuses:
    @pytest.mark.parametrize(
        "field,value",
        [
            ("llm_sport_category", "basketball"),
            ("sport_key", "basketball_other"),
            ("market_tier", 1),
            ("status", "open"),
            ("source", "polymarket"),
        ],
    )
    def test_a_resported_row_refuses(self, monkeypatch, repair, field, value):
        session = _FakeSession(
            markets=[_market(NESEA, **{field: value}), _market(SFLAR)]
        )
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2
        assert not session.sql_starting("UPDATE futures_markets")

    def test_a_moved_child_count_refuses(self, monkeypatch, repair):
        """These rows are settled and out of every scan; a new leg means it is
        not the row this plan was built on."""
        session = _FakeSession(
            markets=[_market(NESEA, outcome_count=99), _market(SFLAR)]
        )
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2

    def test_one_surprise_blocks_the_other_row_too(self, monkeypatch, repair):
        """Two rows measured together are one claim about one state of the world."""
        session = _FakeSession(
            markets=[_market(NESEA, llm_sport_category="basketball"), _market(SFLAR)]
        )
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2
        assert not session.sql_starting("UPDATE futures_markets")


# ── child data and blast radius ─────────────────────────────────────────────


class TestNothingElseIsTouched:
    def test_only_event_id_is_ever_written(self, monkeypatch, repair):
        session = _FakeSession()
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 0
        writes = [
            s
            for s, _ in session.statements
            if s.startswith(("UPDATE", "DELETE", "INSERT"))
        ]
        for sql in writes:
            if sql.startswith("INSERT"):
                assert repair.BACKUP_TABLE in sql  # the D51 copy only
                continue
            assert sql.startswith("UPDATE futures_markets SET event_id")

    def test_no_child_table_is_ever_written(self, monkeypatch, repair):
        session = _FakeSession()
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 0
        for sql, _ in session.statements:
            if sql.startswith(("UPDATE", "DELETE")):
                assert "futures_outcomes" not in sql
                assert "events" not in sql.split("SET")[0]

    def test_the_apply_refuses_if_the_outcome_count_moves_mid_transaction(
        self, monkeypatch, repair
    ):
        session = _FakeSession(outcomes=(27, 26))
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2
        assert session.rolled_back == 1
        assert session.committed_after_rollback == 0

    def test_only_the_two_registered_ids_are_ever_asked_for(self, monkeypatch, repair):
        """The population is pinned. Nothing widens it to 'the series'."""
        session = _FakeSession()
        _run(monkeypatch, repair, session, backup=True, apply=True)
        asked = {
            p.get("mid") for s, p in session.statements if p.get("mid") is not None
        }
        assert asked == {60617788, 60617215}
        tickers = {
            p.get("ticker")
            for s, p in session.statements
            if p.get("ticker") is not None
        }
        assert tickers == {NESEA, SFLAR}


# ── idempotence ─────────────────────────────────────────────────────────────


class TestIdempotence:
    def test_a_correctly_linked_pair_is_a_no_op(self, monkeypatch, repair):
        session = _FakeSession(
            markets=[
                _market(NESEA, event_id=14780138),
                _market(SFLAR, event_id=14632820),
            ]
        )
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 0
        assert not session.sql_starting("UPDATE futures_markets")

    def test_a_half_applied_run_converges(self, monkeypatch, repair):
        session = _FakeSession(
            markets=[_market(NESEA, event_id=14780138), _market(SFLAR)]
        )
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 0
        assert len(session.sql_starting("UPDATE futures_markets")) == 1

    def test_the_dry_run_is_repeatable_and_writes_nothing(self, monkeypatch, repair):
        for _ in range(2):
            session = _FakeSession()
            assert _run(monkeypatch, repair, session) == 0
            assert session.committed == 0
            assert not session.sql_starting("UPDATE futures_markets")


# ── the write gates ─────────────────────────────────────────────────────────


class TestTheWriteRefusals:
    def test_a_dry_run_needs_no_app_at_all(self, repair, monkeypatch):
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        assert repair.wrong_app_refusal(_args()) is None

    @pytest.mark.parametrize("flag", ["apply", "backup"])
    def test_an_unset_app_refuses_to_write(self, repair, monkeypatch, flag):
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        assert repair.wrong_app_refusal(_args(**{flag: True})) is not None

    @pytest.mark.parametrize("app", ["bainluck", "bainluck-staging"])
    def test_the_web_app_may_not_write(self, repair, monkeypatch, app):
        monkeypatch.setenv("HEROKU_APP_NAME", app)
        assert repair.wrong_app_refusal(_args(apply=True)) is not None

    def test_the_producer_app_may_write(self, repair, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)
        assert repair.wrong_app_refusal(_args(apply=True)) is None

    def test_the_gate_survives_a_caller_with_no_backup_flag(self, repair, monkeypatch):
        """The undo's parser defines no `--backup`; one refusal serves both."""
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        assert repair.wrong_app_refusal(argparse.Namespace(apply=True)) is not None

    def test_the_prevention_must_be_live_on_this_interpreter(self, monkeypatch, repair):
        """If `kxnflffpts` is unmapped here the series still reads as basketball
        and a relink builds on a sport assignment that is about to move."""
        monkeypatch.setattr(repair, "tap_is_off", lambda: False)
        session = _FakeSession()
        assert _run(monkeypatch, repair, session, backup=True, apply=True) == 2
        assert not session.sql_starting("UPDATE futures_markets")

    def test_the_tap_check_reads_the_real_shipped_map(self, repair):
        """Not a stub: the prevention really is in this tree's ticker map."""
        assert repair.tap_is_off() is True


class TestTheBackupComesFirst:
    def test_apply_without_a_backup_table_refuses(self, monkeypatch, repair):
        session = _FakeSession(backup_exists=False)
        assert _run(monkeypatch, repair, session, apply=True) == 2
        assert not session.sql_starting("UPDATE futures_markets")

    def test_a_stale_backup_refuses(self, monkeypatch, repair):
        """Content-exact, not existence-exact: a backup taken before the row
        moved would have the undo restore a value that was never overwritten."""
        session = _FakeSession(unbacked=1)
        assert _run(monkeypatch, repair, session, apply=True) == 2
        assert not session.sql_starting("UPDATE futures_markets")

    def test_the_reconciliation_compares_content_not_existence(
        self, monkeypatch, repair
    ):
        session = _FakeSession()
        _run(monkeypatch, repair, session, backup=True, apply=True)
        recon = [
            s for s, _ in session.statements if "count(*) FROM futures_markets f" in s
        ]
        assert recon, "no reconciliation ran"
        assert "IS NOT DISTINCT FROM" in recon[0]

    def test_the_first_dry_run_survives_an_absent_backup_table(
        self, monkeypatch, repair
    ):
        """`to_regclass`, not a bare SELECT — the sibling script crashed here on
        exactly the run the runbook's step 0 is."""
        session = _FakeSession(backup_exists=False)
        assert _run(monkeypatch, repair, session) == 0

    def test_the_backup_refreshes_on_conflict(self, monkeypatch, repair):
        session = _FakeSession()
        _run(monkeypatch, repair, session, backup=True)
        inserts = [s for s, _ in session.statements if s.startswith("INSERT")]
        assert inserts
        assert "DO UPDATE" in inserts[0]
        assert "DO NOTHING" not in inserts[0]


# ── the undo ────────────────────────────────────────────────────────────────


class TestTheUndoTakesTheSameGate:
    def test_the_undo_shares_the_repairs_app_gate(self, restore, monkeypatch):
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        assert restore.wrong_app_refusal(argparse.Namespace(apply=True)) is not None

    def test_the_undo_imports_a_session_factory_that_really_resolves(self, restore):
        """CERT-903: the #2947 pair shipped importing a module that never
        existed, so both entrypoints died while every unit test passed."""
        assert restore._session_factory() is not None

    def test_the_repairs_session_factory_really_resolves(self, repair):
        assert repair._session_factory() is not None

    def test_the_undo_puts_the_nulls_back(self, monkeypatch, restore):
        session = _RestoreSession(
            [
                _RestoreRow(60617788, NESEA, 14780138, None, False),
                _RestoreRow(60617215, SFLAR, 14632820, None, False),
            ]
        )
        assert _run(monkeypatch, restore, session, apply=True) == 0
        assert len(session.sql_starting("UPDATE futures_markets")) == 2
        assert session.committed == 1

    def test_the_undo_leaves_a_row_something_else_linked(self, monkeypatch, restore):
        """Most likely the matcher finally doing its job — never undone here."""
        session = _RestoreSession(
            [
                _RestoreRow(60617788, NESEA, 77_777_777, None, False),
                _RestoreRow(60617215, SFLAR, 14632820, None, False),
            ]
        )
        _run(monkeypatch, restore, session, apply=True)
        assert len(session.sql_starting("UPDATE futures_markets")) == 1

    def test_the_undo_is_idempotent(self, monkeypatch, restore):
        session = _RestoreSession(
            [
                _RestoreRow(60617788, NESEA, None, None, False),
                _RestoreRow(60617215, SFLAR, None, None, False),
            ]
        )
        assert _run(monkeypatch, restore, session, apply=True) == 0
        assert not session.sql_starting("UPDATE futures_markets")

    def test_an_unbacked_row_is_not_guessed_at(self, monkeypatch, restore):
        session = _RestoreSession([_RestoreRow(60617788, NESEA, 14780138, None, True)])
        _run(monkeypatch, restore, session, apply=True)
        assert not session.sql_starting("UPDATE futures_markets")

    def test_an_absent_backup_table_is_reported_not_crashed(self, monkeypatch, restore):
        session = _RestoreSession([], backup_exists=False)
        assert _run(monkeypatch, restore, session, apply=True) == 0

    def test_the_undo_writes_no_child_row(self, monkeypatch, restore):
        session = _RestoreSession([_RestoreRow(60617788, NESEA, 14780138, None, False)])
        _run(monkeypatch, restore, session, apply=True)
        for sql, _ in session.statements:
            if sql.startswith(("UPDATE", "DELETE", "INSERT")):
                assert "futures_outcomes" not in sql


def _RestoreRow(mid, ticker, now_eid, was_eid, unbacked):
    return _Row(
        id=mid,
        external_id=ticker,
        now_eid=now_eid,
        was_eid=was_eid,
        unbacked=unbacked,
    )


class _RestoreSession(_FakeSession):
    def __init__(self, rows, *, backup_exists=True):
        super().__init__(backup_exists=backup_exists)
        self._rows = rows

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.statements.append((sql, params or {}))
        if "to_regclass" in sql:
            return _Result([self.backup_exists])
        if sql.startswith("SELECT f.id"):
            return _Result(self._rows)
        if sql.startswith("UPDATE futures_markets"):
            return _Result([], rowcount=1)
        return _Result([])


# ── the runbook the reviewer and the operator read ──────────────────────────


class TestTheHeaderStatesWhatItCannotDeliver:
    def test_the_runbook_waits_for_the_heavy_release(self):
        header = REPAIR_PATH.read_text()
        assert "notice 48" in header
        assert "bainluck-heavy" in header

    def test_the_header_says_the_relink_is_not_the_display_fix(self):
        """Measured before building: 0 of the 14 already-linked siblings reach a
        reader. A repair whose header lets the next session believe the page
        will change is how an after-check gets written against the wrong claim.
        """
        header = REPAIR_PATH.read_text()
        assert "necessary and it is not sufficient" in header.lower()
        assert "prop_window_closed" in header

    def test_the_header_records_the_transposition(self):
        header = REPAIR_PATH.read_text()
        assert "transpos" in header.lower()
