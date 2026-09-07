"""#3672 acceptance 4 — the repair that takes the NBA's nicknames back off.

Two things are pinned here, and the first is why the second was needed.

THE SECOND HALF OF THE FIX. #3672 shipped at `8c2d2b82` and flipped the default
for every REGISTERED ticker prefix. An UNREGISTERED prefix — one
`_SPORT_ABBREV_SUFFIX` has no entry for at all — still fell through to
`sport_suffix = ""`, and `""` is the NBA's bare namespace. So the bug stayed
live for the sports nobody had registered. Measured on production 2026-09-06,
AFTER the first half shipped: 46 of 126 polluted rows came from unregistered
prefixes, and `KXFIBAGAME-26JUL032000CHICOL` ("Chile vs Colombia") still
resolved **Bulls vs Avalanche** on demand. `TestTheUnregisteredPrefixHalf` is
the guard on the flip, not on a list.

THE REPAIR. `plan_row` decides one event, and every refusal it can make is a
test below. The load-bearing property is that the repair's net is the FIX's net:
the proof a row was minted by this bug is a replay of the fix's own parser in
the namespace it used to read, and the new name is what the matcher itself would
write today. Neither is a regex written for the repair.
"""

import argparse
import asyncio
import datetime as dt

import pytest

import scripts.repair_3672_bare_namespace_event_names as repair
import scripts.restore_3672_bare_namespace_event_names as restore
from app.utils.prediction_market_matching import (
    _ABBREV_NAMESPACE_UNKNOWN,
    _KALSHI_TEAM_ABBREVS,
    _SPORT_ABBREV_SUFFIX,
    extract_matchup,
    extract_matchup_with_ticker_fallback,
    extract_team_codes_from_ticker,
    extract_teams_from_ticker,
)

# ---------------------------------------------------------------------------
# the second half of the fix: an UNREGISTERED prefix is not the NBA's either
# ---------------------------------------------------------------------------


class TestTheUnregisteredPrefixHalf:
    """Every specimen here was measured on production 2026-09-06, after the
    first half of #3672 was already live at `8c2d2b82`."""

    @pytest.mark.parametrize("ticker,stored_as", [
        ("KXFIBAGAME-26JUL032000CHICOL", ("Bulls", "Avalanche")),      # Chile vs Colombia
        ("KXSQUASHMATCH-26MAY12LAKCOL", ("Kings", "Avalanche")),       # Lake vs Coll
        ("KXUFLTOTAL-26MAY29DALSTL", ("Mavericks", "Blues")),          # Renegades vs Battlehawks
        ("KXBIG3GAME-26JUL05DETDAL", ("Pistons", "Mavericks")),        # Amps vs Power
    ])
    def test_an_unregistered_prefix_no_longer_answers_with_nba_teams(
        self, ticker, stored_as,
    ):
        assert not any(ticker.lower().startswith(p) for p in _SPORT_ABBREV_SUFFIX), (
            f"{ticker} is registered now — this specimen belongs in the other file"
        )
        # What it used to do, and what the stored rows still say:
        assert repair.replay_pre_fix_names(ticker) == stored_as
        # What it does now:
        assert extract_teams_from_ticker(ticker) is None

    def test_the_default_is_the_sentinel_not_the_bare_namespace(self):
        """The flip itself. A prefix nobody registered must inherit 'we do not
        know', which is true and harmless, never 'ask the NBA', which is false
        and mints a card."""
        assert extract_team_codes_from_ticker(
            "KXTOTALLYNEWSPORT-26SEP06DENLAC"
        ) is None

    def test_nothing_legitimate_relied_on_the_old_fallthrough(self):
        """Safe to flip precisely because every prefix that owns the bare
        namespace is registered — so a ticker reaching the default is by
        construction a sport we hold no vocabulary for."""
        bare = [p for p, s in _SPORT_ABBREV_SUFFIX.items() if s == ""]
        assert bare, "the bare namespace lost its owner"
        assert all(p.startswith("kxnba") for p in bare)

    def test_the_matcher_now_takes_the_title_for_these(self):
        """The point of refusing: a miss falls through to the market-title parse,
        and for exactly these markets the title carries the right names."""
        matchup = extract_matchup_with_ticker_fallback(
            "Chile vs Colombia", external_id="KXFIBAGAME-26JUL032000CHICOL",
        )
        assert (matchup.team_a, matchup.team_b) == ("Chile", "Colombia")

    def test_a_registered_sport_with_a_vocabulary_still_beats_the_title(self):
        """The flip must not cost the NFL its nicknames. The title of a quarter
        market says "Detroit vs Cincinnati"; the ticker says Lions vs Bengals,
        and the ticker is right — 20 rows in the measured population."""
        title = "Detroit vs Cincinnati: 4th Quarter Winner"
        assert (extract_matchup(title).team_a, extract_matchup(title).team_b) == (
            "Detroit", "Cincinnati",
        )
        matchup = extract_matchup_with_ticker_fallback(
            title, external_id="KXNFL4Q-26AUG13DETCIN",
        )
        assert (matchup.team_a, matchup.team_b) == ("Lions", "Bengals")


class TestTheOverrideSeam:
    def test_the_override_replays_the_pre_fix_namespace(self):
        assert extract_team_codes_from_ticker(
            "KXWTACHALLENGERMATCH-26SEP06DENLAC", sport_suffix_override="",
        ) == (("den", "Nuggets"), ("lac", "Clippers"))

    def test_without_the_override_the_same_ticker_refuses(self):
        assert extract_team_codes_from_ticker(
            "KXWTACHALLENGERMATCH-26SEP06DENLAC"
        ) is None

    def test_the_override_is_not_reachable_from_the_matching_path(self):
        """An override reachable from `extract_matchup_with_ticker_fallback` is a
        way to reintroduce #3672 one caller at a time. The matching path must
        always resolve in the asking sport's own namespace."""
        import inspect

        for fn in (extract_teams_from_ticker, extract_matchup_with_ticker_fallback):
            assert "sport_suffix_override" not in inspect.signature(fn).parameters

    def test_the_unknown_sentinel_still_refuses_through_the_override(self):
        assert extract_team_codes_from_ticker(
            "KXNBAGAME-26FEB21DETCHI",
            sport_suffix_override=_ABBREV_NAMESPACE_UNKNOWN,
        ) is None


# ---------------------------------------------------------------------------
# the candidate name set is DERIVED, never typed
# ---------------------------------------------------------------------------


class TestTheCandidateNameSet:
    def test_it_comes_from_the_table_the_bug_read(self):
        assert repair.BARE_NAMESPACE_NAMES == sorted(
            {n for a, n in _KALSHI_TEAM_ABBREVS.items() if "_" not in a}
        )

    def test_it_is_not_only_the_nba(self):
        """The issue body's predicate is "an NBA nickname". The bare namespace
        also holds NFL, MLB and NHL nicknames, so that predicate under-reports —
        `Seahawks`, `Yankees` and `Avalanche` are all reachable from it."""
        for name in ("Seahawks", "Yankees", "Avalanche", "49ers"):
            assert name in repair.BARE_NAMESPACE_NAMES

    def test_a_name_no_bare_code_produces_is_not_a_candidate(self):
        """`Chicago Hounds` is what one of these rows SHOULD say. If the clean
        names were candidates the repair could re-plan its own output."""
        for name in ("Chicago Hounds", "Dencheva", "Colorado Eagles"):
            assert name not in repair.BARE_NAMESPACE_NAMES


# ---------------------------------------------------------------------------
# plan_row — one event's verdict
# ---------------------------------------------------------------------------

# The live specimen, event 14855623 on production: `/sport/tennis/wta` showed
# `Timberwolves vs Hornets` for Kalshi's "Minnen vs Charaeva".
SPEC_TICKER = "KXWTACHALLENGERMATCH-26JUN02MINCHA"
SPEC_TITLE = "Minnen vs Charaeva"


def test_the_production_specimen_is_planned():
    row, reason = repair.plan_row(1, "Timberwolves", "Hornets", SPEC_TICKER, SPEC_TITLE)
    assert reason is None
    assert (row["new_home"], row["new_away"]) == ("Minnen", "Charaeva")
    assert row["swapped"] is False


def test_a_row_the_replay_does_not_reconstruct_is_left_alone():
    """The stored pair must be what the bug WOULD have written. A row that
    merely contains bare-namespace names is not evidence of anything."""
    row, reason = repair.plan_row(1, "Lakers", "Celtics", SPEC_TICKER, SPEC_TITLE)
    assert row is None and reason == "NO_RECONSTRUCT"


def test_a_row_stored_in_the_opposite_order_keeps_its_orientation():
    """Event 15167733: ticker VAN/CHA, stored `Hornets vs Canucks`. Renaming it
    un-swapped would silently reverse the fixture."""
    row, reason = repair.plan_row(
        1, "Hornets", "Canucks", "KXITFWMATCH-26MAY20VANCHA", "Van Poppel vs Chapman",
    )
    assert reason is None
    assert row["swapped"] is True
    assert (row["new_home"], row["new_away"]) == ("Chapman", "Van Poppel")


def test_a_row_already_carrying_the_right_name_is_not_rewritten():
    """Event 15198926 on production. The bare replay reconstructs `Cardinals vs
    Raiders` — so this row IS in the population — but the NFL namespace answers
    with the same two names, so there is nothing to write. Four rows measured.

    A row that merely reads correctly does not get this far: it fails the
    reconstruction gate first, which is `test_a_row_the_replay_does_not_...`.
    """
    row, reason = repair.plan_row(
        1, "Cardinals", "Raiders", "KXNFL4Q-26AUG13ARILV",
        "Arizona vs Las Vegas: 4th Quarter Winner",
    )
    assert row is None and reason == "ALREADY_CORRECT"


def test_a_row_whose_market_title_yields_no_matchup_is_skipped_not_guessed():
    row, reason = repair.plan_row(
        1, "Nuggets", "Clippers", "KXWTACHALLENGERMATCH-26SEP06DENLAC",
        "Which player wins the most games this season?",
    )
    assert row is None and reason == "NO_NEW_NAME"


def test_an_unparseable_ticker_is_skipped():
    row, reason = repair.plan_row(1, "Nuggets", "Clippers", "NOT-A-TICKER", SPEC_TITLE)
    assert row is None and reason == "NO_RECONSTRUCT"


def test_a_legitimate_nickname_on_another_sport_is_not_touched():
    """`Kiekko-Espoo vs Pelicans` (Finnish Liiga) and `Leinster vs Bulls` (rugby)
    are CORRECT. They are why the selector is a replay and not a name blocklist:
    `Pelicans` and `Bulls` are both in the candidate name set."""
    for home, away, ticker in [
        ("Kiekko-Espoo", "Pelicans", "KXLIIGAGAME-26JAN10KIEPEL"),
        ("Leinster", "Bulls", "KXURCGAME-26JAN10LEIBUL"),
    ]:
        row, reason = repair.plan_row(1, home, away, ticker, f"{home} vs {away}")
        assert row is None, f"{home} vs {away} was planned"
        assert reason == "NO_RECONSTRUCT"


# ---------------------------------------------------------------------------
# planning and collisions, against a fake session
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = rows
        self.rowcount = len(rows)

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return self._rows[0][0] if self._rows else 0


class _FakeSession:
    """Answers by looking at the SQL, so it is order-independent."""

    def __init__(self, events, clash=None, backup_covered=None):
        self.events = events
        self.clash = clash or {}
        self.backup_covered = backup_covered
        self.statements = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.statements.append((sql, params or {}))
        if sql.startswith("SELECT id FROM events WHERE id <>"):
            hit = self.clash.get((params["h"].casefold(), params["a"].casefold()))
            return _Result([(hit,)] if hit else [])
        if "FROM events e JOIN LATERAL" in sql:
            return _Result(self.events)
        if "count(*)" in sql:
            n = self.backup_covered
            return _Result([(n if n is not None else len(self.events),)])
        return _Result([])

    async def commit(self):
        pass


def _event(event_id, home="Timberwolves", away="Hornets",
           ticker=SPEC_TICKER, title=SPEC_TITLE, day="2026-06-16"):
    return (event_id, home, away, dt.datetime.fromisoformat(f"{day}T12:00:00"),
            ticker, title)


#: A second, DISTINCT production specimen. Two copies of `_event` would clean to
#: the same fixture and be dropped as twins, which is correct behaviour and
#: useless as a fixture for anything else.
def _other_event(event_id=2):
    return _event(
        event_id, home="Nuggets", away="Ravens",
        ticker="KXITFMATCH-26MAY24DENBAL", title="Denolly vs Balshaw",
    )


def test_build_plan_reads_ticker_and_title_from_one_market():
    """The LATERAL join is load-bearing: two correlated subqueries could take the
    ticker from one market hanging off the event and the title from another."""
    session = _FakeSession([_event(1)])
    plan, skipped = asyncio.run(repair.build_plan(session))
    assert skipped == []
    assert (plan[0]["new_home"], plan[0]["new_away"]) == ("Minnen", "Charaeva")


def test_the_population_query_binds_the_name_set_rather_than_inlining_it():
    """74 names interpolated into SQL text is an injection surface and defeats
    the plan cache; `= ANY(:names)` is one bind."""
    session = _FakeSession([_event(1)])
    asyncio.run(repair.build_plan(session))
    sql, params = session.statements[0]
    assert "= ANY(:names)" in sql
    assert params["names"] == repair.BARE_NAMESPACE_NAMES
    for name in repair.BARE_NAMESPACE_NAMES:
        assert name not in sql


def _plan_rows(*pairs, day="2026-06-16"):
    return [
        {
            "id": i,
            "old_home": "Timberwolves",
            "old_away": "Hornets",
            "new_home": h,
            "new_away": a,
            "ticker": SPEC_TICKER,
            "swapped": False,
            "commence": dt.datetime.fromisoformat(f"{day}T12:00:00"),
        }
        for i, (h, a) in enumerate(pairs, start=1)
    ]


def test_two_rows_cleaning_to_the_same_fixture_are_both_dropped():
    """Four separate prop markets each minted their own "Colombia vs Portugal"
    event. Renaming them all would turn a visibly-broken cluster into a
    convincing duplicate set — CERT-880, and #2693's twins."""
    session = _FakeSession([])
    kept, dropped = asyncio.run(
        repair.drop_collisions(session, _plan_rows(("Colombia", "Portugal"),
                                                   ("Colombia", "Portugal")))
    )
    assert kept == []
    assert [why for _, why in dropped] == ["TWIN_WITHIN_PLAN"] * 2


def test_a_row_whose_clean_name_already_exists_is_dropped():
    session = _FakeSession([], clash={("colombia", "portugal"): 14495372})
    kept, dropped = asyncio.run(
        repair.drop_collisions(session, _plan_rows(("Colombia", "Portugal")))
    )
    assert kept == []
    assert dropped[0][1] == "CLEAN_COUNTERPART_EXISTS:14495372"


def test_distinct_fixtures_are_both_kept():
    session = _FakeSession([])
    kept, dropped = asyncio.run(
        repair.drop_collisions(session, _plan_rows(("Minnen", "Charaeva"),
                                                   ("Denolly", "Balshaw")))
    )
    assert len(kept) == 2 and dropped == []


def test_the_clash_query_casts_the_timestamp():
    """A bare `:c - interval '2 days'` sends an untyped parameter and Postgres
    resolves it as `interval - interval`, killing the predicate. repair_2947 paid
    for this on the dyno; sqlglot parses the uncast version happily."""
    session = _FakeSession([])
    asyncio.run(repair.drop_collisions(session, _plan_rows(("Minnen", "Charaeva"))))
    sql = session.statements[0][0]
    assert "CAST(:c AS timestamptz)" in sql


# ---------------------------------------------------------------------------
# the disposition guard
# ---------------------------------------------------------------------------


def test_a_matching_run_has_no_drift():
    assert repair.disposition_drift(dict(repair.EXPECTED)) == {}


def test_a_moved_plan_is_drift():
    measured = dict(repair.EXPECTED, plan=repair.EXPECTED["plan"] + 1)
    assert "plan" in repair.disposition_drift(measured)


def test_expect_plan_restates_only_the_plan():
    measured = dict(repair.EXPECTED, plan=42, twin_within_plan=99)
    drift = repair.disposition_drift(measured, expect_plan=42)
    assert "plan" not in drift
    assert "twin_within_plan" in drift, "--expect-plan relaxed an unrelated bucket"


# ---------------------------------------------------------------------------
# run-level: these invoke run(), because unit tests against a fake session
# cannot see an entrypoint that dies on import (CERT-903)
# ---------------------------------------------------------------------------


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
    return argparse.Namespace(**{
        **dict(backup=False, apply=False, limit=0, allow_small=False, expect_plan=None),
        **kw,
    })


def _run(monkeypatch, session, **kw):
    """Run the real `run()`; return (exit code, writes).

    `ensure_backup` and `apply_plan` are the only two functions that write, so
    recording their calls records every write the run made.
    """
    writes = []

    async def _backup(_session, plan):
        writes.append("backup")
        return len(plan)

    async def _apply(_session, plan):
        writes.append("apply")
        return len(plan)

    monkeypatch.setattr(repair, "_session_factory", lambda: _SessionFactory(session))
    monkeypatch.setattr(repair, "ensure_backup", _backup)
    monkeypatch.setattr(repair, "apply_plan", _apply)
    return asyncio.run(repair.run(_args(**kw))), writes


def test_the_production_entrypoint_resolves_a_real_session_factory():
    """The smoke guard. The #2947 pair imported `app.database`, a module that has
    never existed, so the documented heroku command died on import — the repair
    before planning a row, the undo before restoring one — while every unit test
    passed. Identity, so a rename on the app side fails here, not at 2am."""
    from app.services.database import async_session_maker

    assert repair._session_factory() is async_session_maker
    assert restore._session_factory() is async_session_maker


def test_a_limited_apply_writes_absolutely_nothing(monkeypatch):
    session = _FakeSession([_event(1)])
    code, writes = _run(monkeypatch, session, limit=1, backup=True, apply=True)
    assert code != 0, "a limited apply reported success"
    assert writes == [], f"a limited apply reached a write: {writes}"


def test_an_apply_without_a_backup_is_refused(monkeypatch):
    session = _FakeSession([_event(1), _other_event()])
    code, writes = _run(monkeypatch, session, apply=True, allow_small=True,
                        expect_plan=2)
    assert code == 4
    assert writes == []


def test_a_drifted_apply_refuses_before_the_backup_not_after(monkeypatch):
    """The refusal must be decided above the first write of the run. In
    repair_2947 the drift guard sat BELOW `ensure_backup`, so a drifted run
    backed up and renamed before anyone looked."""
    session = _FakeSession([_event(1)])
    code, writes = _run(monkeypatch, session, backup=True, apply=True,
                        allow_small=True)
    assert code == 6
    assert writes == [], f"a drifted apply reached a write: {writes}"


def test_an_empty_population_refuses_rather_than_reporting_success(monkeypatch):
    """gotcha #53 — a repair that finds nothing and exits 0 is the worst outcome.
    The floor says the predicate broke, not that the work is done."""
    session = _FakeSession([])
    code, writes = _run(monkeypatch, session, backup=True, apply=True)
    assert code == 2
    assert writes == []


def _clean_run(monkeypatch, **kw):
    """A two-row population whose disposition MATCHES the registered one.

    `--expect-plan` deliberately restates only `plan`, so it cannot make a
    fixture agree with a disposition measured over 126 production rows — that is
    the point of the guard, and `test_expect_plan_restates_only_the_plan` pins
    it. The honest way to exercise the happy path is to register the fixture's
    own disposition, not to weaken the guard.
    """
    monkeypatch.setattr(repair, "EXPECTED", {
        "candidates": 2, "plan": 2, "no_reconstruct": 0,
        "already_correct": 0, "twin_within_plan": 0, "clean_counterpart": 0,
    })
    session = _FakeSession([_event(1), _other_event()])
    return _run(monkeypatch, session, backup=True, apply=True,
                allow_small=True, **kw)


def test_a_matching_run_backs_up_and_applies(monkeypatch):
    code, writes = _clean_run(monkeypatch)
    assert code == 0, "a clean run refused"
    assert writes == ["backup", "apply"], writes


def test_the_backup_happens_before_the_apply_not_beside_it(monkeypatch):
    """D51's permission to write unattended rests on the undo existing FIRST."""
    _, writes = _clean_run(monkeypatch)
    assert writes.index("backup") < writes.index("apply")


# ---------------------------------------------------------------------------
# the D51 undo
# ---------------------------------------------------------------------------


class _FakeRestoreSession:
    def __init__(self, rows, table="public.bak_3672_event_names"):
        self.rows = rows
        self.table = table
        self.updates = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if "to_regclass" in sql:
            return _Result([(self.table,)] if self.table else [])
        if sql.startswith("UPDATE events"):
            self.updates.append(params)
            return _Result([(1,)])
        if "FROM bak_3672_event_names b" in sql:
            return _Result(self.rows)
        return _Result([])

    async def commit(self):
        pass


def _restore_run(monkeypatch, session, **kw):
    monkeypatch.setattr(restore, "_session_factory", lambda: _SessionFactory(session))
    args = argparse.Namespace(**{**dict(apply=False, drop_backups=False), **kw})
    return asyncio.run(restore.run(args)), session.updates


def test_the_undo_puts_the_repaired_row_back(monkeypatch):
    session = _FakeRestoreSession([
        (1, "Timberwolves", "Hornets", "Minnen", "Charaeva", "Minnen", "Charaeva"),
    ])
    code, updates = _restore_run(monkeypatch, session, apply=True)
    assert code == 0
    assert updates[0]["oh"] == "Timberwolves" and updates[0]["oa"] == "Hornets"


def test_the_undo_leaves_a_row_something_else_renamed_since(monkeypatch):
    """An undo that stomps a later, unrelated decision is not an undo."""
    session = _FakeRestoreSession([
        (1, "Timberwolves", "Hornets", "Minnen", "Charaeva", "Someone", "Else"),
    ])
    code, updates = _restore_run(monkeypatch, session, apply=True)
    assert code == 0
    assert updates == [], "the undo stomped a diverged row"


def test_the_undo_writes_nothing_without_apply(monkeypatch):
    session = _FakeRestoreSession([
        (1, "Timberwolves", "Hornets", "Minnen", "Charaeva", "Minnen", "Charaeva"),
    ])
    code, updates = _restore_run(monkeypatch, session)
    assert code == 0 and updates == []


def test_the_undo_is_a_noop_when_the_backup_table_is_gone(monkeypatch):
    session = _FakeRestoreSession([], table=None)
    code, updates = _restore_run(monkeypatch, session, apply=True)
    assert code == 0 and updates == []


# ════════════════════════════════════════════════════════════════════════════
# The bind contract — #1884's class, recurred (see the module's `SINCE` note)
# ════════════════════════════════════════════════════════════════════════════


class TestEveryTimestamptzBindIsADatetime:
    """🔴 This suite was 20-odd cases green while the script could not run.

    The repair shipped through CERT-2139 and merged (`343eea23`, Heroku v4240)
    binding `SINCE = "2026-06-01"` — an ISO **string** — into
    `CAST(:since AS timestamptz)`. Postgres infers that parameter as
    `timestamptz` and asyncpg refuses a `str` there rather than coercing it, as
    psycopg2 would have. The first statement of every run raised

        asyncpg.exceptions.DataError: invalid input for query argument $1:
        '2026-06-01' (expected a datetime.date or datetime.datetime instance)

    so the script never planned a row and never wrote its backup. Nothing in
    this file could see it: every case here drives the planner through a fake
    session that accepts any params object, and the cert graded the diff rather
    than an execution.

    It is exactly #1884's class — `tests/integration/test_kalshi_cliff_bind_contract.py`
    exists to close it and says so — and it recurred because that file executes
    only the cliff drain's own SQL. The executable half for THIS script is
    `tests/integration/test_repair_3672_bind_contract.py`; these two cases are
    the fast half that runs in every shard.
    """

    def test_the_since_watermark_is_a_datetime_and_not_an_iso_string(self):
        from datetime import datetime

        from scripts.repair_3672_bare_namespace_event_names import SINCE

        assert isinstance(SINCE, datetime), (
            f"SINCE is {type(SINCE).__name__} — it is bound into "
            f"CAST(:since AS timestamptz) and asyncpg refuses a str there, so "
            f"the script dies on its first statement (#1884's class)"
        )
        assert SINCE.tzinfo is not None, (
            "a naive datetime bound to timestamptz takes the server's timezone, "
            "which silently moves the watermark"
        )

    def test_no_timestamptz_cast_in_this_script_is_fed_a_string_literal(self):
        """The specimen above is closed; this catches the NEXT one.

        Reads the source for `CAST(:name AS timestamptz)` and requires every
        module-level constant bound under one of those names to be a datetime.
        A future `SINCE`-alike added as a string fails here rather than on a
        detached dyno whose stdout nobody can read.
        """
        import inspect
        import re
        from datetime import date, datetime

        from scripts import repair_3672_bare_namespace_event_names as mod

        source = inspect.getsource(mod)
        bound = set(re.findall(r"CAST\(:(\w+) AS timestamptz\)", source))
        assert bound, "the timestamptz casts are gone — has the query changed?"
        for name, value in vars(mod).items():
            if name.isupper() and name.lower() in {b.lower() for b in bound}:
                assert isinstance(value, (datetime, date)), (
                    f"{name} is bound to a timestamptz cast but is "
                    f"{type(value).__name__}"
                )

    def test_the_real_asyncpg_bind_gate_is_wired_into_ci(self):
        """The executable half runs in ONE job and only if it is named there.

        `tests/integration/test_repair_3672_bind_contract.py` is `skipif`-gated
        on `SEARCH_TEST_DATABASE_URL`, so it skips in all four `backend-tests`
        shards and pytest exits 0. This assertion lives here, in the always-run
        file, because a wiring check inside the skip-gated file is circular:
        unwire it and the test that would catch that stops running too.
        """
        import pathlib

        workflow = (
            pathlib.Path(__file__).resolve().parents[2]
            / ".github"
            / "workflows"
            / "ci.yml"
        ).read_text()
        assert "tests/integration/test_repair_3672_bind_contract.py" in workflow, (
            "the #3672 bind gate is not named in ci.yml — it would skip in every "
            "shard, and this repair already shipped once without ever executing"
        )
