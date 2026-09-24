"""#2526 — the sport-category rail reaches the RESOLVED cohort, reversibly.

PILLAR: TRUTH / MATCHING. SHIP: settled tennis matches stop being filed under
table tennis — a reader opening a finished ITF/Challenger/WTA match stops seeing
a TABLE_TENNIS eyebrow and a "More Table Tennis" rail.

The rail (Q495) was scoped `fm.status = 'open'` and every row it could fix is
fixed: on 2026-09-23 its open population was 1,605 markets, all genuine table
tennis. The mis-filed tennis RESOLVED before the rail reached it, and a resolved
row leaves the open scope without being repaired. So this file guards three
things and nothing else:

1. ``status_scope`` — ``open`` (default) selects exactly what it selected before,
   ``not_open`` selects the complement, in EVERY statement that names the
   population (census, page SELECT, write, remaining count), and an unknown value
   is refused by name rather than defaulted.
2. The undo receipt — staged in the write's own transaction, built from what
   Postgres RETURNED, and taking the write down with it when it cannot persist.
3. The restore — compare-and-set on BOTH columns the apply wrote, counted from
   RETURNING, never from the receipt's length.

The verdict is still `classify_event_payload()` over the venue's payload; a
table-tennis payload in the resolved cohort stays table tennis (the control).
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from app.tasks import repair_polymarket_sport_category as rail
from tests.test_repair_polymarket_sport_category_q496 import (
    _Row,
    _Session,
    _SETKA,
    _TENNIS,
    _Ts,
    _venue,
)


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)


def _norm(sql: str) -> str:
    return " ".join(sql.split())


def _writes_sql(s: _Session) -> list[str]:
    return [sql for sql, _p in s.writes]


def _counts_sql(s: _Session) -> list[str]:
    return [sql for sql, _p in s.statements if sql.upper().startswith("SELECT COUNT(")]


# ---------------------------------------------------------------------------
# 1. status_scope
# ---------------------------------------------------------------------------

#: The page SELECT exactly as it rendered on origin/master before #2526
#: (`f03360d565`), whitespace-normalised. The open scope must still render it
#: byte-for-byte: the default path is the one the Q495–Q497 certs graded.
_OPEN_PAGE_SELECT_BEFORE = _norm(
    """
    SELECT ev.event_id, ev.commence_time, ev.anchor_id, ev.markets
    FROM (
      SELECT
        fm.market_metadata->>'polymarket_event_id' AS event_id,
        max(fm.commence_time)                      AS commence_time,
        min(fm.id)                                 AS anchor_id,
        count(*)                                   AS markets
      FROM futures_markets fm
      WHERE fm.source = 'polymarket'
        AND fm.status = 'open'
        AND fm.llm_sport_category = :cat
        AND fm.market_metadata->>'polymarket_event_id' IS NOT NULL
      GROUP BY 1
    ) ev
    WHERE TRUE
    ORDER BY ev.commence_time DESC NULLS LAST, ev.anchor_id DESC
    LIMIT :cap
    """
)


#: lane1b/550: the ONE addition to the frozen text above — the event's market
#: ids, which the write keys on. Notice 50: the control is split, never
#: re-snapshotted — the remainder must still be the pre-#2526 bytes exactly.
_MARKET_IDS_OUTER = "ev.markets, ev.market_ids FROM"
_MARKET_IDS_INNER = "count(*) AS markets, array_agg(fm.id ORDER BY fm.id) AS market_ids FROM"


async def test_the_open_scope_page_select_is_byte_unchanged(fast, monkeypatch):
    s = _Session(targets=[], remaining=0)
    _venue(monkeypatch, {})
    await rail.repair(s, apply=False)
    sql = s.target_sql
    assert _MARKET_IDS_OUTER in sql and _MARKET_IDS_INNER in sql, sql
    remainder = sql.replace(_MARKET_IDS_OUTER, "ev.markets FROM").replace(
        _MARKET_IDS_INNER, "count(*) AS markets FROM"
    )
    assert remainder == _OPEN_PAGE_SELECT_BEFORE


@pytest.mark.parametrize("scope", ["open", "not_open"])
async def test_the_write_is_keyed_on_the_market_ids_the_page_selected(
    fast, monkeypatch, scope
):
    """lane1b/550: production 2026-09-24 02:29Z — keyed on the event id alone,
    the resolved-cohort UPDATE was a 4.7s sequential scan against its 1.0s
    budget, so every `not_open` apply paused on its first event. The id list is
    what lets the write plan on the primary key."""
    s = _Session(
        targets=[
            _Row("943345", _Ts("2026-08-31T18:55:34+00:00"), 59939103, markets=2,
                 market_ids=[59939103, 59939111]),
        ],
        remaining=40,
        update_rowcount=2,
    )
    _venue(monkeypatch, {"943345": _TENNIS})
    await rail.repair(s, apply=True, status_scope=scope)
    assert len(s.writes) == 1, "the write never ran — the assertions below are vacuous"
    sql, params = s.writes[0]
    assert "fm.id = ANY(CAST(:ids AS integer[]))" in sql, sql
    assert params["ids"] == [59939103, 59939111]
    # The id list narrows the write; it never replaces the compare-and-set.
    # #8460: the event half of the compare-and-set is the scope's own event key.
    for guard in ("fm.llm_sport_category = :cat_old", f"{rail.EVENT_ID_SQL[scope]} = :eid"):
        assert guard in sql, guard


async def test_an_explicit_open_scope_is_the_default_scope(fast, monkeypatch):
    a, b = _Session(), _Session()
    _venue(monkeypatch, {})
    await rail.repair(a, apply=False)
    await rail.repair(b, apply=False, status_scope="open")
    assert a.target_sql == b.target_sql


async def test_not_open_selects_the_complement_in_every_population_statement(
    fast, monkeypatch
):
    s = _Session(
        targets=[_Row("924377", _Ts("2026-08-30T18:00:00+00:00"), 11, markets=3)],
        remaining=40,
        update_rowcount=3,
    )
    _venue(monkeypatch, {"924377": _TENNIS})

    out = await rail.repair(s, apply=True, status_scope="not_open")

    assert out["status_scope"] == "not_open"
    complement = "fm.status IS DISTINCT FROM 'open'"
    assert complement in s.target_sql
    assert "fm.status = 'open'" not in s.target_sql
    assert len(s.writes) == 1, "the write never ran — the scope assertion below is vacuous"
    assert complement in _writes_sql(s)[0], (
        "the write is not scoped to the population the page read — it could "
        "reach rows the operator never selected"
    )
    counts = _counts_sql(s)
    assert counts and all(complement in c for c in counts), counts


async def test_the_census_takes_the_same_scope(monkeypatch):
    s = _Session(remaining=0)
    out = await rail.census(s, status_scope="not_open")
    assert out["measured"] is True
    assert out["status_scope"] == "not_open"
    population = [sql for sql, _p in s.statements if "FROM futures_markets fm" in sql]
    assert len(population) == 2, population
    assert all("fm.status IS DISTINCT FROM 'open'" in q for q in population)

    s2 = _Session(remaining=0)
    out2 = await rail.census(s2)
    assert out2["status_scope"] == "open"
    population2 = [sql for sql, _p in s2.statements if "FROM futures_markets fm" in sql]
    assert all("fm.status = 'open'" in q for q in population2)


@pytest.mark.parametrize("bad", ["resolved", "all", "closed", ""])
async def test_an_unknown_scope_is_refused_by_name_and_reads_nothing(bad, monkeypatch):
    s = _Session()
    _venue(monkeypatch, {})
    out = await rail.repair(s, apply=True, status_scope=bad)
    assert out["terminal"] == "refused_status_scope"
    assert s.statements == [], "an unknown scope was served from some population"

    c = _Session()
    out_c = await rail.census(c, status_scope=bad)
    assert out_c["terminal"] == "refused_status_scope"
    assert c.statements == []


def test_the_dispatcher_can_forward_both_new_params():
    """The dispatcher forwards only names the signature DECLARES; ``**_ignored``
    would swallow an undeclared one silently and serve the open scope."""
    for fn in (rail.repair,):
        params = inspect.signature(fn).parameters
        assert "status_scope" in params and "undo_identity" in params
    assert "status_scope" in inspect.signature(rail.census).parameters


# ---------------------------------------------------------------------------
# 1b. A resumed page binds a datetime (#2526, production 2026-09-24 00:40Z)
#
# The dispatcher passes `after_date` as the string `next_cursor` printed, and
# asyncpg binds `CAST(:after_date AS timestamptz)` as a typed parameter that
# refuses a str — every page after the first failed on production and reported
# itself as a SELECT timeout. A recording session accepts any type, which is how
# the string survived three weeks; the real-Postgres arm is
# `tests/integration/test_sport_category_cursor_resume_2526_real_postgres.py`.
# ---------------------------------------------------------------------------

_BOUND = datetime(2026, 8, 31, 18, 55, 34, tzinfo=timezone.utc)


@pytest.mark.parametrize("given", ["2026-08-31T18:55:34+00:00", "2026-08-31T18:55:34Z"])
async def test_a_resumed_page_binds_a_datetime_not_the_cursor_string(fast, monkeypatch, given):
    s = _Session(targets=[], remaining=5)
    _venue(monkeypatch, {})
    out = await rail.repair(s, apply=False, status_scope="not_open", after_date=given, after_id=59939104)

    bound = s.target_params["after_date"]
    assert isinstance(bound, datetime), f"after_date bound as {type(bound).__name__}"
    assert bound == _BOUND
    # The cursor handed back on an empty page is still the operator's own text.
    assert out["next_cursor"] == {"after_date": given, "after_id": 59939104}


@pytest.mark.parametrize("bad", ["yesterday", "2026-13-01T00:00:00+00:00", "59939104"])
async def test_a_malformed_cursor_date_is_refused_by_name_and_reads_nothing(fast, monkeypatch, bad):
    s = _Session(targets=[], remaining=5)
    _venue(monkeypatch, {})
    out = await rail.repair(s, apply=True, status_scope="not_open", after_date=bad, after_id=1)
    assert out["terminal"] == "refused_cursor"
    assert repr(bad) in out["reason"]
    assert s.statements == [], "a malformed cursor was read as some page"


async def test_the_emitted_cursor_round_trips_as_a_datetime(fast, monkeypatch):
    s1 = _Session(targets=[_Row("943345", _Ts("2026-08-31T18:55:34+00:00"), 59939103)], remaining=5)
    _venue(monkeypatch, {"943345": _TENNIS})
    first = await rail.repair(s1, apply=False, status_scope="not_open")

    s2 = _Session(targets=[], remaining=5)
    await rail.repair(s2, apply=False, status_scope="not_open", **first["next_cursor"])
    assert s2.target_params["after_date"] == _BOUND
    assert s2.target_params["after_id"] == 59939103


# ---------------------------------------------------------------------------
# 2. The undo receipt
# ---------------------------------------------------------------------------


async def test_an_apply_banks_one_receipt_per_event_from_returning(fast, monkeypatch):
    rows = [
        _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11, markets=2),
        _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12, markets=1),
    ]
    s = _Session(targets=rows, remaining=40, update_rowcount=2)
    _venue(monkeypatch, {"1": _TENNIS, "2": _TENNIS})

    out = await rail.repair(s, apply=True, status_scope="not_open")

    assert out["terminal"] == "changed"
    assert len(s.receipts) == 2, "one receipt per re-filed event"
    r0 = s.receipts[0]
    assert r0["event_id"] == "1" and r0["status_scope"] == "not_open"
    assert [c["market_id"] for c in r0["changes"]] == [1000, 1001], (
        "the receipt did not name the rows RETURNING vouched for"
    )
    assert all(
        c["from_llm"] == rail.SUSPECT_CATEGORY and c["to_llm"] == "tennis"
        for c in r0["changes"]
    )
    assert all("from_category" in c and "to_category" in c for c in r0["changes"])
    assert [r["event_id"] for r in out["receipts"]] == ["1", "2"]
    for r in out["receipts"]:
        assert r["restore_command"] == rail.restore_command(r["undo_identity"])
        assert r["undo_identity"].startswith("repair:polymarket_sport_category:undo:")
    assert out["counts"]["markets_written"] == 4
    assert s.commits == 2


async def test_the_receipt_is_staged_between_the_update_and_its_commit(fast, monkeypatch):
    s = _Session(
        targets=[_Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)],
        remaining=40,
        update_rowcount=1,
    )
    order: list[str] = []
    orig_execute, orig_commit = s.execute, s.commit

    async def _exec(stmt, params=None):
        u = _norm(str(stmt)).upper()
        if u.startswith("UPDATE"):
            order.append("update")
        elif "INSERT INTO DURABLE_STATE_SNAPSHOTS" in u:
            order.append("receipt")
        return await orig_execute(stmt, params)

    async def _commit():
        order.append("commit")
        await orig_commit()

    s.execute, s.commit = _exec, _commit
    _venue(monkeypatch, {"1": _TENNIS})
    await rail.repair(s, apply=True, status_scope="not_open")
    assert order == ["update", "receipt", "commit"], order


async def test_a_receipt_that_cannot_persist_takes_the_write_down_with_it(
    fast, monkeypatch
):
    rows = [
        _Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11),
        _Row("2", _Ts("2026-08-30T17:00:00+00:00"), 12),
    ]
    s = _Session(targets=rows, remaining=40, update_rowcount=1)
    s.receipt_generation = None  # the store reads this as a failed publish
    _venue(monkeypatch, {"1": _TENNIS, "2": _TENNIS})

    out = await rail.repair(s, apply=True, status_scope="not_open")

    assert len(s.writes) == 1, "the write never ran, so this path was not exercised"
    assert out["terminal"] == "paused_receipt_unpersisted"
    assert s.commits == 0, "a write with no receipt was committed"
    assert s.rollbacks >= 1
    assert out["receipts"] == []
    assert out["counts"]["write_failed"] == 1
    assert out["counts"]["markets_written"] == 0
    assert out["next_cursor"] is None, "the cursor crossed the rolled-back event"
    assert out["scan_exhausted"] is False
    assert out["stopped_at_receipt_unpersisted"].startswith("event_id=1")


async def test_a_raced_write_banks_no_receipt_and_still_advances(fast, monkeypatch):
    s = _Session(
        targets=[_Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)],
        remaining=40,
        update_rowcount=0,
    )
    _venue(monkeypatch, {"1": _TENNIS})
    out = await rail.repair(s, apply=True, status_scope="not_open")
    assert s.receipts == [] and out["receipts"] == []
    assert out["next_cursor"] == {"after_date": "2026-08-30T18:00:00+00:00", "after_id": 11}


async def test_a_table_tennis_payload_in_the_resolved_cohort_stays_put(fast, monkeypatch):
    """The control. The verdict is the venue's tag, not the scope."""
    s = _Session(targets=[_Row("945534", _Ts("2026-08-20T10:00:00+00:00"), 7)], remaining=5)
    _venue(monkeypatch, {"945534": _SETKA})
    out = await rail.repair(s, apply=True, status_scope="not_open")
    assert out["counts"]["unchanged"] == 1
    assert s.writes == [] and s.receipts == []


async def test_a_dry_run_banks_nothing(fast, monkeypatch):
    s = _Session(targets=[_Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)], remaining=5)
    _venue(monkeypatch, {"1": _TENNIS})
    out = await rail.repair(s, apply=False, status_scope="not_open")
    assert out["terminal"] == "dry_run"
    assert s.writes == [] and s.receipts == [] and s.commits == 0


def test_the_last_events_three_write_units_fit_the_reserve_that_claims_them():
    charged = (
        rail.client_db_budget_seconds(rail.WRITE_BUDGET_SECONDS)
        + rail.RECEIPT_BUDGET_SECONDS
        + rail.client_db_budget_seconds(rail.COMMIT_BUDGET_SECONDS)
        + rail.ROLLBACK_BUDGET_SECONDS
    )
    assert 0 < charged < rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS, charged
    assert rail.budget_headroom_seconds() > 0


def test_this_rails_receipts_cannot_be_read_by_the_leg_label_rail():
    from app.tasks import repair_polymarket_leg_label as leg

    assert rail.UNDO_SCHEMA != leg.UNDO_SCHEMA
    assert "polymarket-sport-category?" in rail.restore_command("x")
    assert "polymarket-leg-label" not in rail.restore_command("x")


# ---------------------------------------------------------------------------
# 3. The restore
# ---------------------------------------------------------------------------


class _Res:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def fetchall(self):
        return self._rows


class _RestoreSession:
    """Keyed on the (llm_sport_category, category) each market carries NOW.

    The fake reads the compare-and-set OFF THE STATEMENT: a fake that honoured
    it in Python would keep every test green with the clause deleted.
    """

    def __init__(self, rows: dict):
        self.rows = dict(rows)
        self.writes: list[tuple[str, dict]] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = _norm(str(stmt))
        params = dict(params or {})
        upper = sql.upper()
        if upper.startswith("SET LOCAL"):
            return _Res()
        if upper.startswith("SELECT FM.ID, FM.LLM_SPORT_CATEGORY"):
            return _Res([(i, *self.rows[i]) for i in params["ids"] if i in self.rows])
        if upper.startswith("UPDATE"):
            self.writes.append((sql, params))
            guard_llm = "FM.LLM_SPORT_CATEGORY IS NOT DISTINCT FROM V.NEW_LLM" in upper
            guard_cat = "FM.CATEGORY IS NOT DISTINCT FROM V.NEW_CAT" in upper
            landed, i = [], 0
            while f"id{i}" in params:
                mid = params[f"id{i}"]
                if mid in self.rows:
                    llm, cat = self.rows[mid]
                    if (not guard_llm or llm == params[f"nllm{i}"]) and (
                        not guard_cat or cat == params[f"ncat{i}"]
                    ):
                        self.rows[mid] = (params[f"ollm{i}"], params[f"ocat{i}"])
                        landed.append(mid)
                i += 1
            return _Res([(m,) for m in landed])
        return _Res()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def invalidate(self):
        pass


def _change(mid, to_cat="futures"):
    return {
        "market_id": mid,
        "from_llm": "table_tennis",
        "to_llm": "tennis",
        "from_category": "futures",
        "to_category": to_cat,
    }


@pytest.fixture
def receipt(monkeypatch):
    state = {"status": "ok", "payload": None}

    async def _read(identity, expected_version=None, max_age_s=None):
        from app.utils.durable_state import DurableEnvelope, EnvelopeRead

        if state["status"] != "ok":
            return EnvelopeRead(status=state["status"], tier="durable")
        return EnvelopeRead(
            status="ok",
            tier="durable",
            envelope=DurableEnvelope.build(
                identity=identity,
                schema_version=rail.UNDO_SCHEMA,
                payload=state["payload"],
                complete=True,
                source="test",
            ),
        )

    monkeypatch.setattr("app.services.durable_snapshots.read_snapshot_standalone", _read)
    return state


def _payload(changes):
    return {
        rail.UNDO_OWNER_KEY: "abc",
        "taken_at": "2026-09-23T22:00:00+00:00",
        "repair": "polymarket-sport-category",
        "status_scope": "not_open",
        "event_id": "1",
        "changes": list(changes),
    }


async def test_restore_puts_back_only_rows_still_carrying_what_we_wrote(receipt):
    receipt["payload"] = _payload([_change(1), _change(2), _change(3), _change(4)])
    s = _RestoreSession(
        {
            1: ("tennis", "futures"),        # ours — restorable
            2: ("table_tennis", "futures"),  # already back
            3: ("golf", "futures"),          # someone moved it since
            # 4 is gone
        }
    )
    out = await rail.repair(s, apply=True, undo_identity="id-1")
    assert out["mode"] == "restore" and out["applied"] is True
    assert out["counts"] == {
        "in_receipt": 4,
        "restored": 1,
        "already_old": 1,
        "refused_changed_since": 1,
        "missing": 1,
    }
    assert s.rows[1] == ("table_tennis", "futures")
    assert s.rows[3] == ("golf", "futures"), "a later correction was dragged back"
    assert s.commits == 1


async def test_restore_checks_the_category_as_well_as_the_sport(receipt):
    """The apply can promote `category` to championship; a row whose category
    moved since must be refused even if its sport still reads ours."""
    receipt["payload"] = _payload([_change(1, to_cat="championship")])
    s = _RestoreSession({1: ("tennis", "futures")})
    out = await rail.repair(s, apply=True, undo_identity="id-1")
    assert out["counts"]["restored"] == 0
    assert out["counts"]["refused_changed_since"] == 1


@pytest.mark.parametrize(
    "raced_to",
    [("tennis", "championship"), ("golf", "futures")],
    ids=["category-moved", "sport-moved"],
)
async def test_the_restore_statement_itself_carries_both_compares(receipt, raced_to):
    """Mutation arm for the SQL, one per column: the Python pre-check agrees with
    the row, and the row changes between the read and the write — only the
    statement's own compare-and-set can refuse it. Both arms were measured to
    redden with their clause deleted."""
    receipt["payload"] = _payload([_change(1)])
    s = _RestoreSession({1: ("tennis", "futures")})
    orig = s.execute

    async def _race(stmt, params=None):
        if _norm(str(stmt)).upper().startswith("UPDATE"):
            s.rows[1] = raced_to
        return await orig(stmt, params)

    s.execute = _race
    out = await rail.repair(s, apply=True, undo_identity="id-1")
    assert out["counts"]["restored"] == 0, "the restore counted the receipt, not RETURNING"
    assert out["counts"]["refused_changed_since"] == 1
    assert s.rows[1] == raced_to


async def test_a_restore_dry_run_changes_nothing(receipt):
    receipt["payload"] = _payload([_change(1)])
    s = _RestoreSession({1: ("tennis", "futures")})
    out = await rail.repair(s, apply=False, undo_identity="id-1")
    assert out["would_restore"] == 1 and out["applied"] is False
    assert s.writes == [] and s.commits == 0


async def test_restore_round_trips_an_apply(fast, monkeypatch, receipt):
    """The receipt an apply stages is the receipt a restore can read back."""
    s = _Session(
        targets=[_Row("1", _Ts("2026-08-30T18:00:00+00:00"), 11)],
        remaining=40,
        update_rowcount=2,
    )
    _venue(monkeypatch, {"1": _TENNIS})
    await rail.repair(s, apply=True, status_scope="not_open")
    assert len(s.receipts) == 1
    receipt["payload"] = s.receipts[0]
    written = {
        c["market_id"]: (c["to_llm"], c["to_category"]) for c in s.receipts[0]["changes"]
    }
    rs = _RestoreSession(written)
    out = await rail.repair(rs, apply=True, undo_identity="id-1")
    assert out["counts"]["restored"] == 2
    assert all(v == ("table_tennis", "futures") for v in rs.rows.values())


async def test_a_store_outage_is_unreadable_never_missing(receipt):
    receipt["status"] = "unavailable"
    out = await rail.repair(_RestoreSession({}), apply=True, undo_identity="id-1")
    assert out["refused"] == rail.REASON_UNDO_UNREADABLE


async def test_a_genuinely_absent_receipt_is_missing(receipt):
    from app.utils.durable_state import MISSING

    receipt["status"] = MISSING
    out = await rail.repair(_RestoreSession({}), apply=True, undo_identity="id-1")
    assert out["refused"] == rail.REASON_UNDO_MISSING


async def test_restore_mode_never_calls_the_venue_or_selects_a_page(monkeypatch, receipt):
    async def _boom(*_a, **_k):
        raise AssertionError("restore called the venue")

    monkeypatch.setattr(rail, "_fetch_event", _boom)
    receipt["payload"] = _payload([_change(1)])
    s = _RestoreSession({1: ("tennis", "futures")})
    # A stale, even invalid, selector in the operator's shell must not block it.
    out = await rail.repair(s, apply=True, undo_identity="id-1", status_scope="bogus")
    assert out["counts"]["restored"] == 1
