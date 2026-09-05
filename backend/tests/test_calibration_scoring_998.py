"""CAL-P998 / D46 — the cells-at-bar number is published by the app.

Until this queue the needle existed only while
``backend/scripts/calibration_scorecard.py`` was running. The measurement bus,
having no served field to read, invented its own script-free cut off
``by_category`` — ``14/36 cats ece<=3.0`` — while the lane quoted ``34/48`` off
the script. Both numbers were right. Nothing said they were different cuts.

So these tests pin three things, in this order:

1. **The fixture can tell the two cuts apart.** The CAL-P105 lesson: a specimen
   that returns the same number under both treatments is green for reasons
   unrelated to the claim. ``odds_api_bookmaker/tennis`` here is QUEUED as a
   cell and AT BAR as a category — same ECE, different bar — so every later
   assertion about "which cut" is actually load-bearing.
2. **The served block says what it means.** ``cells_total`` on the wire is the
   MATERIAL count, because the needle Alex reads is "34 of 48" and 48 is the
   material count; the all-cells figure is published beside it as
   ``cells_scored``. That rename is the one place this could silently lie, so
   it is asserted against the script's own keys rather than described.
3. **There is ONE definition of the bar.** The script imports the app's
   constants — asserted by object identity, not by equality, because two dicts
   that happen to hold 2.5/3.0/3.0 today are exactly the state this change
   exists to prevent.

Plus the route: a score is a statement about the numbers, never a reason the
page cannot serve them (ruling CAL-P017).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import calibration_scoring as scoring
from app.utils import request_cache as rc

# ---------------------------------------------------------------------------
# The fixture
# ---------------------------------------------------------------------------


def _bucket(source, category, n, winners, avg_prob, idx=5, price_moved=False):
    return {
        "bucket_idx": idx,
        "source": source,
        "category": category,
        "price_moved": price_moved,
        "n": n,
        "winners": winners,
        "avg_prob": avg_prob,
        "sum_prob": round(n * avg_prob, 4),
    }


#: Five cells, chosen so the cell cut and the category cut disagree in
#: membership AND in denominator. One bin per cell keeps the arithmetic
#: readable: a cell's ECE is just ``|winners/n - avg_prob| * 100``.
#:
#: * ``odds_api_bookmaker/basketball`` 3.00 pp high  ─┐ pooled by category these
#: * ``kalshi/basketball``             3.00 pp low   ─┘ cancel to 0.00 pp
#: * ``polymarket/politics``          10.00 pp — queued in both cuts
#: * ``odds_api_bookmaker/tennis``     2.80 pp — QUEUED as a class-A cell
#:   (bar 2.5, n large enough to establish it), AT BAR as a category (bar 3.0)
#: * ``kalshi/weather``               20.00 pp over 500 rows — under the floor
#:   in both cuts, so it is measured and never queued
_BUCKETS = [
    _bucket("odds_api_bookmaker", "basketball", 10_000, 5_300, 0.50),
    _bucket("kalshi", "basketball", 10_000, 4_700, 0.50),
    _bucket("polymarket", "politics", 10_000, 6_000, 0.50),
    _bucket("odds_api_bookmaker", "tennis", 1_000_000, 528_000, 0.50),
    _bucket("kalshi", "weather", 500, 350, 0.50),
]

#: The payload's own pre-aggregates, consistent with the buckets above — the
#: category cut reads THESE, exactly as the bus does.
_BY_CATEGORY = [
    {"category": "basketball", "ece": 0.00, "n": 20_000, "outcomes": 20_000},
    {"category": "politics", "ece": 10.00, "n": 10_000, "outcomes": 10_000},
    {"category": "tennis", "ece": 2.80, "n": 1_000_000, "outcomes": 1_000_000},
    # Under `min_category_outcomes`; the real payload drops these into
    # `small_sample_categories` and this cut must not count them either.
    {"category": "weather", "ece": 20.00, "n": 500, "outcomes": 500},
]


def _at(*, days_ago: float = 0.05) -> str:
    """A stamp N days back that is always in the PAST (gotcha #44)."""
    base = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )
    return (base - timedelta(days=days_ago)).isoformat()


def _payload(**over) -> dict:
    from app.tasks.precompute_calibration import CALIBRATION_POPULATION_VERSION

    out = {
        "buckets": list(_BUCKETS),
        "by_category": [dict(c) for c in _BY_CATEGORY],
        "by_source": [{"source": "kalshi", "outcomes": 1_040_500}],
        "total_outcomes": 1_040_500,
        "total_markets": 260_125,
        "total_winners": 549_350,
        "min_category_outcomes": 1000,
        "mce_closing_line": 1.71,
        "liquidity_filter": {"applies_to": "kalshi"},
        "mex_normalization": {"applies_to": "all"},
        "truth_evidence": {"contract_ok": True},
        "population_version": CALIBRATION_POPULATION_VERSION,
        "generated_at": _at(),
    }
    out.update(over)
    return out


# ---------------------------------------------------------------------------
# 1. The fixture's warrant — it SEPARATES the two cuts
# ---------------------------------------------------------------------------


class TestTheFixtureSeparatesTheTwoCuts:
    def test_one_ece_is_queued_as_a_cell_and_at_bar_as_a_category(self):
        """2.80 pp on ``odds_api_bookmaker/tennis``, scored twice.

        As a CELL it carries the ratified class-A bar of 2.5 pp, and a million
        rows establish the 0.3 pp excess at 6 sigma — queued. As a CATEGORY it
        carries the flat reader bar of 3.0 pp — at bar. Neither reading is
        wrong, and a board that prints one of them without the other is what
        made the bus and the lane look like they disagreed.
        """
        block = scoring.scorecard(_payload())
        queued = {c["cell"] for c in block["queued_cells"]}
        assert "odds_api_bookmaker/tennis" in queued
        over = {c["category"] for c in block["categories_over_bar"]}
        assert "tennis" not in over

    def test_the_two_cuts_do_not_report_the_same_fraction(self):
        """If they did, every assertion below would be untestable."""
        block = scoring.scorecard(_payload())
        assert (block["cells_at_bar"], block["cells_total"]) == (2, 4)
        assert (block["categories_at_bar"], block["categories_total"]) == (2, 3)

    def test_the_floor_excludes_the_same_rows_from_both_cuts(self):
        """``kalshi/weather`` is 20 pp wrong over 500 rows.

        Material-exempt as a cell, below ``min_category_outcomes`` as a
        category. A floor that applied to only one cut would put a cell in one
        denominator and not the other, and the two numbers could never
        reconcile.
        """
        block = scoring.scorecard(_payload())
        assert block["cells_exempt"] == 1
        assert block["cells_scored"] == block["cells_total"] + block["cells_exempt"]
        assert "weather" not in {c["category"] for c in block["categories_over_bar"]}
        assert block["categories_total"] == 3


# ---------------------------------------------------------------------------
# 2. The served block
# ---------------------------------------------------------------------------


class TestTheServedBlock:
    def test_it_carries_the_four_fields_d46_named(self):
        block = scoring.scorecard(_payload())
        for field in ("cells_at_bar", "cells_total", "bar", "computed_at"):
            assert field in block, field
        assert block["status"] == scoring.STATUS_MEASURED

    def test_cells_total_on_the_wire_is_the_material_count(self):
        """The rename, pinned against the script's own keys.

        The script's ``counts.cells_total`` is EVERY folded cell and its
        ``counts.cells_material`` is the needle's denominator. D46 names the
        served field ``cells_total`` and the needle is "34 of 48", so on the
        wire ``cells_total`` must be the material count and the all-cells figure
        must still be published — under ``cells_scored``.
        """
        from scripts import calibration_scorecard as sc

        payload = _payload()
        script = sc.score(payload)["counts"]
        block = scoring.scorecard(payload)

        assert block["cells_total"] == script["cells_material"]
        assert block["cells_scored"] == script["cells_total"]
        assert block["cells_at_bar"] == script["cells_at_bar"]
        assert block["cells_queued"] == script["cells_queued"]

    def test_computed_at_and_generated_at_are_different_facts(self):
        """A score taken now off a curve built days ago is exactly the shape
        that let a stale reading read as a current one. Both stamps ship."""
        payload = _payload(generated_at=_at(days_ago=3))
        block = scoring.scorecard(payload)
        assert block["generated_at"] == payload["generated_at"]
        assert block["computed_at"] != block["generated_at"]
        assert datetime.fromisoformat(block["computed_at"]) > datetime.fromisoformat(
            block["generated_at"]
        )

    def test_bar_carries_every_threshold_that_produced_the_number(self):
        """A published count whose bar is not published beside it cannot be
        checked, and a threshold that moves out from under a number is the
        failure the 2026-08-28 ratification is guarded against."""
        bar = scoring.scorecard(_payload())["bar"]
        assert bar["class_bars_pp"] == {
            scoring.CLASS_A: 2.5,
            scoring.CLASS_B: 3.0,
            scoring.CLASS_C: 3.0,
        }
        assert bar["reader_bar_pp"] == 3.0
        assert bar["min_cell_n"] == 1000
        assert bar["sigma_gate"] == 2.0
        # The category cut's bar travels with the category numbers too.
        assert scoring.scorecard(_payload())["categories_bar_pp"] == 3.0

    def test_a_moved_payload_floor_is_declared_not_absorbed(self):
        """gotcha #53. ``MIN_CELL_N`` mirrors the payload's own
        ``min_category_outcomes``; if the payload's value moves, the two cuts
        are scoring different populations and the block says so rather than
        quietly picking one."""
        assert scoring.scorecard(_payload())["floor_matches_payload"] is True
        moved = scoring.scorecard(_payload(min_category_outcomes=500))
        assert moved["floor_matches_payload"] is False
        assert moved["payload_min_category_outcomes"] == 500

    def test_the_needle_line_names_both_cuts(self):
        line = scoring.needle(scoring.scorecard(_payload()))
        assert "2/4 cells-at-bar" in line
        assert "2/3 categories-at-bar" in line


# ---------------------------------------------------------------------------
# 3. ONE definition of the bar
# ---------------------------------------------------------------------------


class TestOneDefinition:
    def test_the_script_uses_the_apps_objects_not_its_own_copies(self):
        """Identity, not equality.

        Two dicts that both read 2.5/3.0/3.0 today are precisely the state this
        change removes: an equality assertion stays green through the first
        divergent edit, which is the moment it is supposed to catch.
        """
        from scripts import calibration_scorecard as sc

        assert sc.CLASS_BARS_PP is scoring.CLASS_BARS_PP
        assert sc.GAME_CATEGORIES is scoring.GAME_CATEGORIES
        assert sc.fold is scoring.fold
        assert sc.classify is scoring.classify
        assert sc.cell_se_pp is scoring.cell_se_pp
        assert sc.BAR_PP == scoring.BAR_PP
        assert sc.MIN_CELL_N == scoring.MIN_CELL_N
        assert sc.SIGMA_GATE == scoring.SIGMA_GATE

    def test_the_app_module_imports_only_leaves_that_import_nothing(self):
        """Same rule as ``sport_keys.py``: this module is consumed by a route, a
        script and (via the route) the request path, so a circular import would
        be discovered at dyno boot.

        AMENDED CAL-P1002. The rule was "imports nothing from the app" and D62
        made that unsatisfiable: the measured-sigma overlay decides a served
        number, so it has to be read here, and its reader is an app module.
        Loosening the rule to "one import is fine" would give up the property
        the rule protects, so the test asserts the property instead — every
        app module this one imports must ITSELF import nothing from the app.
        Two leaves cannot form a cycle. A third leaf is admissible on the same
        terms; a non-leaf is not, and this fails if one appears.
        """
        from pathlib import Path

        def _app_imports(path: Path) -> list[str]:
            return [
                ln.strip()
                for ln in path.read_text().splitlines()
                if ln.startswith(("import app", "from app"))
            ]

        direct = _app_imports(Path(scoring.__file__))
        assert direct == ["from app.utils import calibration_sigma as sigma_ledger"], (
            f"new app import in calibration_scoring: {direct}. Every one of these "
            "runs at dyno boot; add it only with the leaf argument above made again."
        )
        from app.utils import calibration_sigma

        assert _app_imports(Path(calibration_sigma.__file__)) == [], (
            "calibration_sigma must stay a leaf — it is the only thing that makes "
            "calibration_scoring's one app import safe."
        )

    def test_the_script_still_reports_its_historical_shape(self):
        """CONTROL — green before this queue and after it.

        The script's consumers (``calibration_threshold_table``,
        ``calibration_cluster_sigma``, the history ledger) read these keys. The
        refactor moved where they are computed, not what they are.
        """
        from scripts import calibration_scorecard as sc

        result = sc.score(_payload())
        assert result["counts"]["cells_total"] == 5
        assert result["counts"]["cells_material"] == 4
        assert result["counts"]["cells_at_bar"] == 2
        assert set(result["per_class"]) == set(scoring.CLASS_BARS_PP)
        assert result["thresholds"]["class_bars_pp"] == dict(scoring.CLASS_BARS_PP)


# ---------------------------------------------------------------------------
# 4. The route — a score never costs the reader the curve
# ---------------------------------------------------------------------------


class _FakeRedis:
    def __init__(self, *, main=None, last_good=None):
        self._values = {
            "bainluck:calibration:main": main,
            "bainluck:calibration:main:last_good": last_good,
        }

    async def get(self, key):
        return self._values.get(key)


def _use(monkeypatch, client):
    async def _getter():
        return client

    monkeypatch.setattr(rc, "get_shared_async_redis", _getter)
    return client


def _no_compute(monkeypatch):
    from app.tasks import precompute_calibration

    async def _boom(db):
        raise AssertionError("the request path must never build")

    monkeypatch.setattr(precompute_calibration, "compute_calibration_payload", _boom)


@pytest.fixture(autouse=True)
def _fresh_process():
    from app.routes import calibration

    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()
    yield
    calibration._cache["data"] = None
    calibration._cache["timestamp"] = 0
    rc._reset_last_good_for_tests()


class TestTheRouteServesIt:
    async def test_the_served_payload_carries_the_score(
        self, monkeypatch, healthy_staged_bank
    ):
        from app.routes import calibration

        _use(monkeypatch, _FakeRedis(main=json.dumps(_payload())))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=object())

        block = out[scoring.SCORECARD_FIELD]
        assert block["status"] == scoring.STATUS_MEASURED
        assert block["cells_at_bar"] == 2
        assert block["cells_total"] == 4
        assert block["categories_at_bar"] == 2
        assert block["categories_total"] == 3

    async def test_the_score_describes_the_copy_actually_served(
        self, monkeypatch, healthy_staged_bank
    ):
        """Derived at the serving exit, not baked in by the producer.

        A producer-baked score rides into the dated fallback tiers still
        describing whichever curve was current when it was baked. Here the
        artifact arrives carrying a WRONG score and the served answer overwrites
        it, because the only defensible score is one taken off the rows in the
        same response.
        """
        from app.routes import calibration

        lying = _payload()
        lying[scoring.SCORECARD_FIELD] = {
            "status": scoring.STATUS_MEASURED,
            "cells_at_bar": 49,
            "cells_total": 49,
        }
        _use(monkeypatch, _FakeRedis(main=json.dumps(lying)))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=object())
        assert out[scoring.SCORECARD_FIELD]["cells_at_bar"] == 2

    async def test_a_malformed_bucket_array_costs_the_score_not_the_page(
        self, monkeypatch
    ):
        """Ruling CAL-P017 is standing: stale-with-declaration beats dark.

        A six-day-old last-good copy with a bucket array the fold cannot read
        must still reach the reader. The scorecard degrades to an explicit
        ``unavailable`` with its reason — never an absent key, which a consumer
        using ``.get(..., 0)`` reads as zero (gotcha #53).
        """
        from app.routes import calibration

        broken = _payload(buckets=[1, 2])
        _use(monkeypatch, _FakeRedis(main=json.dumps(broken)))
        _no_compute(monkeypatch)

        out = await calibration.public_calibration(db=object())

        assert out["total_outcomes"] == 1_040_500  # the page still serves
        block = out[scoring.SCORECARD_FIELD]
        assert block["status"] == scoring.STATUS_UNAVAILABLE
        assert block["reason"].startswith("score_failed:")
        assert block["cells_at_bar"] is None
        assert block["cells_total"] is None

    def test_an_unavailable_block_reads_as_absent_never_as_zero(self):
        block = scoring.unavailable("no_buckets")
        assert block["cells_at_bar"] is None
        assert block["categories_at_bar"] is None
        assert scoring.needle(block).startswith("NEEDLE: calibration UNMEASURED")
