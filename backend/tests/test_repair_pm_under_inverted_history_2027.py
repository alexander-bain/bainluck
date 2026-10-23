"""#2027 / #10955 — the Under-history repair withdraws only what the old rail
filed from the Over token, and refuses every leg it cannot prove.

Specimen: /futures/31519211 (Devin Vassell Total 3-Pointers O/U 2.5, Polymarket,
resolved, Under won). Live's saved read of 2026-10-12 (root inbox,
FROM-live-20261012T2355Z-10955-SCOPE-*) quotes the Under leg's hourly history
rows beside the Over leg's poll captures taken about 21 minutes later:
0.745/0.745, 0.74/0.74, 0.47/0.465, 0.48/0.455, 0.59/0.59, 0.0005/0.0005. Those
six pairs are the fixture; the stamps are the issue's (June 3 15:00 onward,
06:00:04 on June 4). Nothing else about the market is assumed.

Control: an active O/U whose Under rows are the Under token's own history, so
each reads as its Over sibling's complement.
"""

from datetime import datetime, timedelta, timezone

import pytest

import app.tasks.repair_pm_under_inverted_history as rp

UTC = timezone.utc
T0 = datetime(2026, 6, 3, 15, 0, tzinfo=UTC)

#: (Under history row, Over poll capture ~21 min later), as quoted.
SPECIMEN_PAIRS = [(0.745, 0.745), (0.74, 0.74), (0.47, 0.465),
                  (0.48, 0.455), (0.59, 0.59), (0.0005, 0.0005)]


def _rows(pairs, exact=False, start_id=1000):
    out = []
    for i, (p, q) in enumerate(pairs):
        at = T0 + timedelta(hours=i)
        out.append({
            "id": start_id + i, "probability": p, "captured_at": at,
            "exact_p": q if exact else None,
            "near_p": None if exact else q,
            "near_at": None if exact else at + timedelta(minutes=21, microseconds=102953),
        })
    return out


SPECIMEN_ROWS = _rows(SPECIMEN_PAIRS)
#: The same leg as the Under token's own history would read.
CONTROL_ROWS = _rows([(round(1 - q, 4), q) for _, q in SPECIMEN_PAIRS])


class TestTestimony:
    def test_the_specimen_reads_as_the_over_price(self):
        t = rp.testify(SPECIMEN_ROWS)
        assert t == {"kind": "near", "equal": 6, "complement": 0}
        assert rp.classify_testimony(t) == (rp.INVERTED, None)

    def test_the_control_reads_as_its_complement_and_is_refused(self):
        t = rp.testify(CONTROL_ROWS)
        assert t["equal"] == 0 and t["complement"] >= 5
        assert rp.classify_testimony(t) == (rp.COMPLEMENT, None)

    def test_one_contradicting_pair_makes_the_leg_ambiguous(self):
        mixed = SPECIMEN_ROWS + _rows([(0.2, 0.8)], start_id=2000)
        assert rp.classify_testimony(rp.testify(mixed)) == (rp.AMBIGUOUS, "mixed_testimony")

    def test_prices_at_even_money_say_nothing(self):
        flat = _rows([(0.5, 0.5), (0.51, 0.49), (0.495, 0.5)])
        t = rp.testify(flat)
        assert t["equal"] == t["complement"] == 0
        assert rp.classify_testimony(t) == (rp.AMBIGUOUS, "no_testimony")

    def test_fewer_than_three_near_testimonies_is_not_enough(self):
        assert rp.classify_testimony(rp.testify(SPECIMEN_ROWS[:2])) == (
            rp.AMBIGUOUS, "too_few_testimonies")

    def test_one_exact_same_second_twin_is_enough(self):
        rows = _rows([(0.745, 0.745)], exact=True)
        assert rp.classify_testimony(rp.testify(rows)) == (rp.INVERTED, None)

    def test_exact_pairs_outrank_near_pairs(self):
        rows = _rows([(0.3, 0.7)], exact=True) + SPECIMEN_ROWS
        t = rp.testify(rows)
        assert t["kind"] == "exact" and t == {"kind": "exact", "equal": 0, "complement": 1}

    def test_an_exact_pair_must_agree_to_six_places(self):
        assert rp.pair_testimony(0.745, 0.7451, exact=True) is None
        assert rp.pair_testimony(0.745, 0.745, exact=True) == "equal"
        assert rp.pair_testimony(0.745, 0.26, exact=True) == "complement"

    def test_a_row_with_no_over_observation_says_nothing(self):
        rows = [{**r, "near_p": None, "exact_p": None} for r in SPECIMEN_ROWS]
        assert rp.classify_testimony(rp.testify(rows)) == (rp.AMBIGUOUS, "no_testimony")


class TestSiblings:
    SIBS = [{"id": 1, "external_id": "0xabc"}, {"id": 2, "external_id": "0xabcd"},
            {"id": 3, "external_id": "0xabc_yes"}, {"id": 4, "external_id": "0xdef"}]

    def test_bare_and_yes_spellings_of_the_same_condition(self):
        assert rp.over_sibling_ids("0xabc_no", self.SIBS) == [1, 3]
        assert rp.over_sibling_ids("0xdef_no", self.SIBS) == [4]

    def test_a_lookalike_condition_never_testifies(self):
        # `rstrip` is what caused this defect; the suffix is removed, not a set.
        assert rp.over_sibling_ids("0xabcd_no", self.SIBS) == [2]
        assert rp.over_sibling_ids("0xe_no", [{"id": 9, "external_id": "0x"}]) == []


def _leg(**kw):
    base = {"opening_probability": None, "opening_american_odds": None,
            "opening_captured_at": None, "opening_source": None,
            "calibration_probability": None}
    return {**base, **kw}


class TestOpening:
    def test_the_old_rails_opening_is_the_first_false_row(self):
        leg = _leg(opening_probability=0.745, opening_source="clob_history")
        assert rp.opening_derivation(leg, SPECIMEN_ROWS) == ("withdraw", "clob_history_raw")

    def test_the_sign_flip_beats_complement_of_it_is_withdrawn_too(self):
        leg = _leg(opening_probability=0.255, opening_source="clob_history")
        assert rp.opening_derivation(leg, SPECIMEN_ROWS) == (
            "withdraw", "clob_history_complemented")

    def test_an_old_rail_opening_that_matches_nothing_refuses_the_leg(self):
        leg = _leg(opening_probability=0.61, opening_source="clob_history")
        assert rp.opening_derivation(leg, SPECIMEN_ROWS) == (
            "ambiguous", "old_rail_opening_value_unexplained")

    def test_phase_0c_promoted_a_false_row(self):
        r = SPECIMEN_ROWS[2]
        leg = _leg(opening_probability=r["probability"], opening_source="first_snapshot",
                   opening_captured_at=r["captured_at"])
        assert rp.opening_derivation(leg, SPECIMEN_ROWS) == ("withdraw", "first_snapshot_raw")
        flipped = {**leg, "opening_probability": 1 - r["probability"]}
        assert rp.opening_derivation(flipped, SPECIMEN_ROWS) == (
            "withdraw", "first_snapshot_complemented")

    def test_an_opening_at_a_false_instant_with_another_value_refuses(self):
        r = SPECIMEN_ROWS[0]
        leg = _leg(opening_probability=0.33, opening_source="first_snapshot",
                   opening_captured_at=r["captured_at"])
        assert rp.opening_derivation(leg, SPECIMEN_ROWS) == (
            "ambiguous", "opening_instant_matches_value_does_not")

    @pytest.mark.parametrize("source,at", [
        ("polymarket_poll", T0 + timedelta(minutes=21, microseconds=5)),
        # The FIXED rail stamps its capture time; it is not a false row's.
        ("clob_history", T0 - timedelta(hours=3)),
    ])
    def test_an_opening_with_its_own_provenance_is_kept(self, source, at):
        leg = _leg(opening_probability=0.745, opening_source=source, opening_captured_at=at)
        assert rp.opening_derivation(leg, SPECIMEN_ROWS) == ("keep", None)

    def test_no_opening_nothing_to_do(self):
        assert rp.opening_derivation(_leg(), SPECIMEN_ROWS) == ("keep", None)


class TestCalibrationPrice:
    def test_a_copy_of_the_withdrawn_opening(self):
        leg = _leg(opening_probability=0.745, calibration_probability=0.745)
        assert rp.cp_candidates(leg, SPECIMEN_ROWS, True) == "copy_of_withdrawn_opening"

    def test_a_false_row_or_its_complement(self):
        assert rp.cp_candidates(_leg(calibration_probability=0.59), SPECIMEN_ROWS,
                                False) == "false_row_raw"
        assert rp.cp_candidates(_leg(calibration_probability=0.41), SPECIMEN_ROWS,
                                False) == "false_row_complemented"

    def test_an_unrelated_price_is_left(self):
        assert rp.cp_candidates(_leg(calibration_probability=0.123), SPECIMEN_ROWS,
                                False) is None


class TestPlanIdentity:
    PLAN = [{"outcome_id": 7, "market_id": 70, "over_sibling": 8,
             "rows": [[1, "2026-06-03T15:00:00+00:00", "0.745000"]],
             "prior": {"opening_probability": 0.745, "opening_american_odds": None,
                       "opening_captured_at": None, "opening_source": "clob_history",
                       "calibration_probability": 0.745},
             "withdraw_opening": "clob_history_raw",
             "withdraw_cp": "copy_of_withdrawn_opening"}]

    def test_order_independent(self):
        two = self.PLAN + [{**self.PLAN[0], "outcome_id": 9}]
        assert rp.plan_hash_for(two, 5) == rp.plan_hash_for(list(reversed(two)), 5)

    @pytest.mark.parametrize("path,value", [
        (("rows",), [[1, "2026-06-03T15:00:00+00:00", "0.740000"]]),
        (("rows",), [[2, "2026-06-03T15:00:00+00:00", "0.745000"]]),
        (("prior", "calibration_probability"), 0.74),
        (("prior", "opening_source"), "first_snapshot"),
        (("withdraw_cp",), None),
        (("over_sibling",), 9),
    ])
    def test_every_fact_the_apply_rechecks_moves_the_hash(self, path, value):
        moved = {**self.PLAN[0], "prior": dict(self.PLAN[0]["prior"])}
        target = moved
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        assert rp.plan_hash_for([moved], 5) != rp.plan_hash_for(self.PLAN, 5)

    def test_the_era_bound_is_inside_the_address(self):
        assert rp.plan_hash_for(self.PLAN, 5) != rp.plan_hash_for(self.PLAN, 6)
        assert rp.plan_hash_for(self.PLAN, 5) != rp.plan_hash_for(self.PLAN, None)

    def test_only_ids_parsing(self):
        assert rp.parse_only_ids(None) is None
        assert rp.parse_only_ids("3, 4") == {3, 4}
        for bad in ("", "3,", "x"):
            with pytest.raises(ValueError):
                rp.parse_only_ids(bad)


class _NoSession:
    async def execute(self, *a, **k):
        raise AssertionError("a refused call must not touch the database")


@pytest.mark.asyncio
class TestRefusalsWriteNothing:
    async def test_an_unpinned_era_refuses_every_apply(self, monkeypatch):
        monkeypatch.setattr(rp, "PRE_FIX_MAX_SNAPSHOT_ID", None)
        out = await rp.repair(_NoSession(), apply=True, plan_hash="x")
        assert out["terminal"] == "refused_boundary_unpinned" and out["legs_written"] == 0

    async def test_apply_without_a_reviewed_plan_is_refused(self, monkeypatch):
        monkeypatch.setattr(rp, "PRE_FIX_MAX_SNAPSHOT_ID", 10)
        out = await rp.repair(_NoSession(), apply=True)
        assert out["terminal"] == "refused_no_plan_hash" and out["legs_written"] == 0

    async def test_a_malformed_pin_is_refused(self):
        out = await rp.repair(_NoSession(), apply=True, only_ids="", plan_hash="x")
        assert out["terminal"] == "refused_bad_only_ids"


def test_the_shipped_boundary_is_unpinned_until_root_reads_it():
    # Pinning is its own reviewed change, from the read named in the comment.
    assert rp.PRE_FIX_MAX_SNAPSHOT_ID is None


def test_the_rail_is_registered_and_never_scheduled():
    from app.routes.admin_repairs import _REPAIRS
    assert _REPAIRS["pm-under-inverted-history"] == (rp.__name__, "repair")
    assert _REPAIRS["pm-under-inverted-history-restore"] == (rp.__name__, "restore")
    from app.tasks import celery_app
    beat = repr(celery_app.conf.beat_schedule)
    assert "under_inverted_history" not in beat and "under-inverted-history" not in beat


def test_the_shipped_history_rail_now_reads_the_under_token():
    """The forward half the repair relies on: a `_no` leg is priced from the
    SECOND token, never the first (the defect the repair cleans up after)."""
    from app.tasks.polymarket import history_token_for_outcome
    tokens = {"0xabce": ["over-token", "under-token"]}
    assert history_token_for_outcome("0xabce_no", tokens) == "under-token"
    assert history_token_for_outcome("0xabce", tokens) == "over-token"


# ---------------------------------------------------------------------------
# the writer census the era bound rests on
# ---------------------------------------------------------------------------

def _snapshot_write_sites():
    """Every `FuturesOddsSnapshot(...)` / `insert(FuturesOddsSnapshot).values(...)`
    under app/: (file, outermost function, keyword args or None for a batch)."""
    import ast
    import pathlib

    app_dir = pathlib.Path(rp.__file__).resolve().parents[1]
    sites = []
    for path in sorted(app_dir.rglob("*.py")):
        tree = ast.parse(path.read_text())
        owner = {}
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(fn):
                    owner.setdefault(id(sub), fn.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            orm = isinstance(f, ast.Name) and f.id == "FuturesOddsSnapshot"
            ins = (isinstance(f, ast.Attribute) and f.attr == "values"
                   and isinstance(f.value, ast.Call) and f.value.args
                   and isinstance(f.value.args[0], ast.Name)
                   and f.value.args[0].id == "FuturesOddsSnapshot")
            if not (orm or ins):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            sites.append((path.name, owner.get(id(node)), kw or None))
    return sites


def test_only_the_history_rails_write_snapshot_batches():
    """The era bound is sound only while the CLOB history rail is the one
    Polymarket writer that can stamp a whole-second, odds-less, book-less row.
    The other batch writers are Kalshi's. A new batch writer must be read
    against this rail before it is added here."""
    batches = {(f, fn) for f, fn, kw in _snapshot_write_sites() if kw is None}
    assert batches == {
        ("polymarket.py", "_backfill_polymarket_price_history"),
        ("kalshi.py", "_backfill_kalshi_price_history"),
        ("kalshi.py", "_backfill_from_settled_events"),
        ("kalshi_cliff.py", "_drain_one"),
    }


def test_every_other_polymarket_capable_writer_stamps_odds():
    import ast

    for f, fn, kw in _snapshot_write_sites():
        if kw is None:
            continue
        bm = kw.get("bookmaker")
        if isinstance(bm, ast.Constant) and bm.value != "polymarket":
            continue
        # Each stamps `captured_at` at write time and passes odds (sportsbook
        # writers always carry them; the venue writers also pass the book).
        assert "american_odds" in kw and "captured_at" in kw, (f, fn)


# ---------------------------------------------------------------------------
# #11158 — a leg whose rows sit only above the era bound
# ---------------------------------------------------------------------------

BOUND = 5000


class _Row:
    def __init__(self, m):
        self._mapping = m

    def __getattr__(self, k):
        try:
            return self.__dict__["_mapping"][k]
        except KeyError:
            raise AttributeError(k) from None


class _Result:
    def __init__(self, rows=(), scalar=None, rowcount=0):
        self._rows, self._scalar, self.rowcount = list(rows), scalar, rowcount

    def all(self):
        return [_Row(r) for r in self._rows]

    def one_or_none(self):
        return _Row(self._rows[0]) if self._rows else None

    def scalar_one(self):
        return self._scalar


class _PageSession:
    """Answers the planner's reads, and one leg's apply, by their exact SQL text.
    ``legs`` maps an Under outcome id to (rows as `_ROWS_SQL` returns them, has
    an Over sibling). Any other statement fails the test."""

    def __init__(self, legs):
        self.page, self.siblings, self.rows = [], [], {}
        for oid, (rows, has_sib) in sorted(legs.items()):
            mid = oid * 10
            self.page.append({**_leg(), "outcome_id": oid, "market_id": mid,
                              "external_id": f"0x{oid}_no", "name": "Under",
                              "market_status": "resolved", "resolution_date": None})
            if has_sib:
                self.siblings.append({"id": oid + 1, "market_id": mid,
                                      "external_id": f"0x{oid}"})
            self.rows[oid] = rows
        self.deleted, self.withdrawn = [], []

    async def execute(self, stmt, params=None):
        sql, p = stmt.text, params or {}
        if sql.startswith("SET LOCAL") or sql in (
                rp._BAK_ROWS_CREATE, rp._BAK_FIELDS_CREATE, rp._BAK_ROWS_COPY,
                rp._BAK_FIELDS_COPY):
            return _Result()
        if sql == rp._PAGE_SQL:
            return _Result([lg for lg in self.page if lg["outcome_id"] > p["after_id"]]
                           [:p["scan"]])
        if sql == rp._SIBLINGS_SQL:
            return _Result([s for s in self.siblings if s["market_id"] in p["mids"]])
        if sql == rp._ROWS_SQL:
            return _Result([{**r, "outcome_id": oid} for oid in p["legs"]
                            for r in self.rows.get(oid, [])])
        if sql == rp._KEPT_VALUE_SQL:
            return _Result(scalar=False)
        if sql == rp._LOCK_ROWS:
            return _Result([r for r in self.rows[p["oid"]] if r["id"] in p["ids"]])
        if sql == rp._LOCK_FIELDS:
            return _Result([lg for lg in self.page if lg["outcome_id"] == p["oid"]])
        if sql == rp._BAK_ROWS_UNPAIRED:
            return _Result([])
        if sql == rp._BAK_FIELDS_PAIRED:
            return _Result(scalar=True)
        if sql == rp._DELETE_ROWS:
            self.deleted.append((p["oid"], sorted(p["ids"])))
            return _Result(rowcount=len(p["ids"]))
        if sql in (rp._WITHDRAW_OPENING, rp._WITHDRAW_CP):
            self.withdrawn.append(p["oid"])
            return _Result()
        raise AssertionError(f"unexpected statement: {sql.strip()[:80]}")

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _post(rows):
    """The same rows with ids above :data:`BOUND` (the fixed writer's era)."""
    return [{**r, "id": BOUND + 1 + i} for i, r in enumerate(rows)]


#: Post-only rows that read as the Over price, at each tier.
SUSPECT_NEAR = _post(SPECIMEN_ROWS)
SUSPECT_EXACT = _post(_rows([(0.745, 0.745)], exact=True))
#: One contradicting pair: mixed testimony, still partly the Over price.
SUSPECT_MIXED = _post(SPECIMEN_ROWS + _rows([(0.2, 0.8)], start_id=2000))


async def _dry(monkeypatch, legs, boundary=BOUND):
    monkeypatch.setattr(rp, "PRE_FIX_MAX_SNAPSHOT_ID", boundary)
    return await rp.repair(_PageSession(legs), limit=50)


@pytest.mark.asyncio
class TestPostFixOnlyLegs:
    @pytest.mark.parametrize("rows,tally", [
        (SUSPECT_NEAR, {"kind": "near", "equal": 6, "complement": 0}),
        (SUSPECT_EXACT, {"kind": "exact", "equal": 1, "complement": 0}),
        (SUSPECT_MIXED, {"kind": "near", "equal": 6, "complement": 1}),
    ])
    async def test_a_post_only_leg_that_reads_as_over_is_reported_not_skipped(
            self, monkeypatch, rows, tally):
        out = await _dry(monkeypatch, {21: (rows, True)})
        assert out["verdicts"] == {rp.AMBIGUOUS: 1}
        assert out["ambiguous_reasons"] == {"post_fix_only_reads_as_over": 1}
        assert out["legs_with_history_rows"] == 1
        assert out["planned_outcome_ids"] == [] and out["rows_planned"] == 0
        (ex,) = out["examples"][rp.AMBIGUOUS]
        assert ex["outcome_id"] == 21 and ex["reason"] == "post_fix_only_reads_as_over"
        assert ex["testimony"] == tally
        assert ex["rows"] == 0 and ex["post_fix_rows"] == len(rows)
        assert [s["id"] for s in ex["sample"]] == [r["id"] for r in rows][:rp._ROW_SAMPLE]
        assert ex["withdraw_opening"] is None and ex["withdraw_cp"] is None

    @pytest.mark.parametrize("rows,has_sib", [
        # The fixed rail's own Under history: each row is its Over's complement.
        (_post(CONTROL_ROWS), True),
        (_post(_rows([(0.5, 0.5), (0.51, 0.49), (0.495, 0.5)])), True),
        # No Over sibling: the rows query pairs it with no observation at all.
        (_post([{**r, "near_p": None, "near_at": None} for r in SPECIMEN_ROWS]), False),
        # The exact tier selects the testimony: one same-second complement
        # outranks six near pairs that read as Over, which are not counted.
        (_post(_rows([(0.3, 0.7)], exact=True, start_id=999) + SPECIMEN_ROWS), True),
    ], ids=["genuine_complement", "near_even", "no_over_sibling", "exact_complement_selects"])
    async def test_post_only_legs_the_fixed_writer_explains_stay_unreported(
            self, monkeypatch, rows, has_sib):
        out = await _dry(monkeypatch, {31: (rows, has_sib)})
        assert out["verdicts"] == {} and out["ambiguous_reasons"] == {}
        assert out["legs_with_history_rows"] == 0 and out["planned_outcome_ids"] == []

    async def test_unpinned_every_row_is_pre_fix_as_before(self, monkeypatch):
        out = await _dry(monkeypatch, {21: (SUSPECT_NEAR, True),
                                       31: (_post(CONTROL_ROWS), True)}, boundary=None)
        assert out["verdicts"] == {rp.INVERTED: 1, rp.COMPLEMENT: 1}
        assert out["ambiguous_reasons"] == {}
        assert out["planned_outcome_ids"] == [21] and out["rows_planned"] == 6

    async def test_a_leg_with_pre_fix_rows_keeps_its_existing_post_fix_refusal(
            self, monkeypatch):
        over = _post(_rows([(0.745, 0.745)], exact=True))
        comp = _post(_rows([(0.255, 0.745)], exact=True))
        out = await _dry(monkeypatch, {11: (SPECIMEN_ROWS + over, True),
                                       12: (SPECIMEN_ROWS + comp, True)})
        assert out["ambiguous_reasons"] == {"post_fix_row_reads_as_over": 1}
        assert out["planned_outcome_ids"] == [12]

    async def test_the_report_moves_no_planned_row_hash_or_apply(self, monkeypatch):
        alone = await _dry(monkeypatch, {11: (SPECIMEN_ROWS, True)})
        legs = {11: (SPECIMEN_ROWS, True), 21: (SUSPECT_NEAR, True)}
        both = await _dry(monkeypatch, legs)
        assert both["ambiguous_reasons"] == {"post_fix_only_reads_as_over": 1}
        for key in ("planned_outcome_ids", "rows_planned", "openings_planned",
                    "cp_planned", "plan_hash"):
            assert both[key] == alone[key], key
        session = _PageSession(legs)
        out = await rp.repair(session, apply=True, limit=50, plan_hash=both["plan_hash"])
        assert out["terminal"] == "applied" and out["legs_written"] == 1
        assert session.deleted == [(11, [r["id"] for r in SPECIMEN_ROWS])]
        assert session.withdrawn == []
