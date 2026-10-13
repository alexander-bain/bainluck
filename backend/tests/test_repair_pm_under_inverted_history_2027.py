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
