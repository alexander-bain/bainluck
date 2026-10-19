"""#1057 — the placeholder-price SUB-COHORT: a candidate by price, confirmed by evidence.

PILLAR: TRUTH. SHIP: Accuracy diagnostics identify placeholder-price artifacts
clearly, so a real forecast failure is told apart from missing trading evidence.

`poly_placeholder` was the one known exclusion class the sentinel's backtest did
not rediscover. A Polymarket placeholder break lives ONLY in the curve's
near-0.50 band (POLY_PLACEHOLDER_EXCLUDE: cp in [0.45, 0.55], no bid or trade in
any snapshot), and every cohort view mixed that band with the rest of the
source, so the band's error was diluted under the flag threshold.

The sub-cohort is selected by PRICE alone, which is a candidate and never a
verdict: a near-0.50 price does not prove nobody traded. Confirmation is the
existing bounded snapshot census, restricted to the band. Four arms, each its
own run of the real ``_run_calibration_sentinel``:

  * ARTIFACT  — the band misses and the census reads no bid/trade: the class is
    rediscovered (backtest) and suppressed as known work (live).
  * TRADED    — the same miss, but the census reads bids/trades: it files, and
    its no-bid fraction is reported as measured and below the threshold.
  * CONTROL   — a healthy traded 0.50 band: nothing flags, nothing is labelled.
  * UNRELATED — a high-cp miss outside the band: flags under its own views and
    is never called a placeholder.
  * UNKNOWN   — the census could not read the band: the diagnosis says UNKNOWN,
    the cohort is NOT suppressed, and the body says price alone proves nothing.
  * BOUNDED   — a mixed 40/60 sample meets the threshold and a 20% sample falls
    below it: neither headline makes an all-cohort claim, both report the
    measured fraction and its traded remainder, and the published curve stays
    UNKNOWN (root's review of 5512155).

The census itself runs on SQLite (its SQL is portable, as #10516's sample SQL
is), so the candidate/confirmed split is proven on the real query, not a fake.
"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

import app.services.durable_snapshots as durable_snapshots
import app.tasks.calibration_sentinel as cs
import app.utils.durable_state as durable_state

#: The curve's own label for the band (SOURCE_LIQUIDITY_EXCLUSIONS) — written
#: out here so a fixture never depends on the code under test to name itself.
BAND = "placeholder_band_0.45_0.55"


def _row(source, bucket, n, winners, cp, *, band, category="basketball"):
    """One futures mining-scan row. Nothing in it is a scan-counted class, so
    any explanation has to come from the placeholder census."""
    return {
        "provenance": "futures", "source": source, "category": category,
        "series_family": category, "structure_class": "binary",
        "bucket": bucket, "n": n, "winners": winners, "sum_prob": cp * n,
        "malformed_binary_n": 0, "esports_bundle_n": 0, "mex_norm_n": 0,
        "void_n": 0, "heuristic_n": 0, "kalshi_prop_threshold_n": 0,
        "any_known_n": 0,
        "pub_n": n, "pub_winners": winners, "pub_sum_prob": cp * n,
        "min_created_at": None,
        "price_band": BAND if band else None,
    }


# Healthy Polymarket rows outside the band — the bulk that diluted the band's
# error in every existing view.
_HEALTHY_TAILS = [
    _row("polymarket", 1, 20000, 3000, 0.15, band=False),
    _row("polymarket", 8, 20000, 17000, 0.85, band=False),
]
# The band resolving at 15% against a 50% price: #151's placeholder signature.
_BAND_MISS = [
    _row("polymarket", 4, 800, 120, 0.48, band=True),
    _row("polymarket", 5, 800, 128, 0.52, band=True),
]
# The band resolving at its price: a genuine traded coin-flip.
_BAND_HEALTHY = [
    _row("polymarket", 4, 800, 384, 0.48, band=True),
    _row("polymarket", 5, 800, 416, 0.52, band=True),
]
# An unrelated break: high-cp outcomes outside the band losing half the time.
_HIGH_CP_MISS = [_row("polymarket", 8, 20000, 10000, 0.85, band=False)]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return iter(self._rows)


def _run(monkeypatch, futures_rows, *, band_fraction, file_issues=True,
         suppress_known=True, evidence_budget=None):
    """Drive the real run over synthetic mining rows. ``band_fraction`` is what
    the bounded snapshot census returns for the band cohort: a float, ``None``
    (it read nothing) or an exception instance (it failed)."""
    census_dims: list[dict] = []
    filed: list[dict] = []

    class _Session:
        async def execute(self, stmt, params=None):
            if str(stmt) == cs._FUTURES_MINING_SQL:
                return _Result([dict(r) for r in futures_rows])
            return _Result([])

        async def rollback(self):
            return None

    @contextlib.asynccontextmanager
    async def _session():
        yield _Session()

    async def _placeholder(session, dims):
        census_dims.append(dict(dims))
        if "price_band" not in dims:
            return None
        if isinstance(band_fraction, Exception):
            raise band_fraction
        return band_fraction

    async def _samples(session, dims, limit=12):
        return []

    async def _no_capture(session, prev):
        return {"findings": []}

    async def _publish(**kwargs):
        return {"durable": "ok", "volatile": "ok"}

    def _file(cohort, explained_by, coverage):
        filed.append(cohort)
        return {"fingerprint": cohort["fingerprint"], "action": "filed"}

    monkeypatch.setattr(cs, "_load_overrides", lambda: None)
    monkeypatch.setattr(cs, "get_task_session", _session)
    monkeypatch.setattr(cs, "_placeholder_fraction", _placeholder)
    monkeypatch.setattr(cs, "_sample_rows", _samples)
    monkeypatch.setattr(cs, "_read_capture_baseline", lambda: None)
    monkeypatch.setattr(cs, "_write_capture_baseline", lambda snap: None)
    monkeypatch.setattr(cs, "_mine_capture_cohorts", _no_capture)
    monkeypatch.setattr(cs, "file_cohort_issue", _file)
    monkeypatch.setattr(durable_snapshots, "publish_sentinel_evidence", _publish)
    monkeypatch.setattr(
        durable_state, "evaluate_publication",
        lambda **kw: SimpleNamespace(raise_if_failed=lambda label: None),
    )
    if evidence_budget is not None:
        monkeypatch.setattr(cs, "SENTINEL_MAX_EVIDENCE_COHORTS", evidence_budget)

    stats = asyncio.run(cs._run_calibration_sentinel(
        file_issues=file_issues, suppress_known=suppress_known,
    ))
    return stats, filed, census_dims


def _band_findings(stats):
    return [f for f in stats["findings"] if "price_band" in f["dims"]]


def _band_cohorts(filed):
    return [c for c in filed if "price_band" in c["dims"]]


# ---------------------------------------------------------------------------
# The band is the curve's band — one definition, pinned against its source.
# ---------------------------------------------------------------------------
class TestTheBandIsTheCurves:
    def test_the_numbers_are_the_ones_the_curve_writes(self):
        from app.tasks.precompute_calibration import POLY_PLACEHOLDER_EXCLUDE

        lo, hi = cs.POLY_PLACEHOLDER_BAND
        assert (lo, hi) == (0.45, 0.55)
        # Inclusive at both ends, exactly as the curve's first clause reads.
        assert f") >= {lo}\n" in POLY_PLACEHOLDER_EXCLUDE
        assert f") <= {hi}\n" in POLY_PLACEHOLDER_EXCLUDE
        assert "vm.source = 'polymarket'" in POLY_PLACEHOLDER_EXCLUDE

    def test_the_label_is_the_curves_own(self):
        from app.tasks.precompute_calibration import SOURCE_LIQUIDITY_EXCLUSIONS

        label = SOURCE_LIQUIDITY_EXCLUSIONS["polymarket"]["never_traded_excluded"]
        assert cs.PRICE_BAND_PLACEHOLDER == label == BAND

    def test_the_mining_scan_tags_the_band_from_those_numbers(self):
        sql = cs._FUTURES_MINING_SQL
        assert "AS price_band" in sql
        assert "cp BETWEEN 0.45 AND 0.55" in sql
        assert f"'{BAND}'" in sql
        assert "source IN ('polymarket')" in sql
        # One more grouping key, so a band row never folds into its neighbour.
        assert "GROUP BY 1, 2, 3, 4, 5, 6, 7" in sql

    def test_the_census_reads_the_same_band(self):
        import inspect

        src = inspect.getsource(cs._placeholder_fraction)
        assert "BETWEEN 0.45 AND 0.55" not in src, "a second hand-typed band drifts"
        assert "_band_predicate" in src


# ---------------------------------------------------------------------------
# The view: Polymarket only, and only for band rows.
# ---------------------------------------------------------------------------
class TestTheSubCohortView:
    def test_a_polymarket_band_row_gets_its_own_cohort(self):
        views = cs._cohort_views(_row("polymarket", 4, 10, 1, 0.48, band=True))
        assert (("provenance", "futures"), ("source", "polymarket"),
                ("price_band", BAND)) in views

    def test_an_out_of_band_row_gets_no_band_cohort(self):
        views = cs._cohort_views(_row("polymarket", 8, 10, 9, 0.85, band=False))
        assert not [v for v in views if dict(v).get("price_band")]

    def test_kalshi_is_not_eligible_even_if_a_row_says_otherwise(self):
        # Kalshi's liquidity filter is all-bands; a mid-band Kalshi cohort is
        # not this class, whatever a row carries.
        views = cs._cohort_views(_row("kalshi", 4, 10, 1, 0.48, band=True))
        assert not [v for v in views if dict(v).get("price_band")]

    def test_an_events_row_without_the_column_keeps_its_six_views(self):
        row = _row("odds_api", 4, 10, 1, 0.48, band=False)
        row.pop("price_band")
        row["provenance"] = "events"
        assert len(cs._cohort_views(row)) == 6


# ---------------------------------------------------------------------------
# #1903 identity: the band cohort's evidence is drawn from the band.
# ---------------------------------------------------------------------------
class TestEvidenceIsDrawnFromTheBand:
    def test_cohort_where_honours_the_band(self):
        where, params = cs._cohort_where(
            {"provenance": "futures", "source": "polymarket", "price_band": BAND}
        )
        assert "BETWEEN 0.45 AND 0.55" in where
        assert params == {"src": "polymarket"}

    def test_an_unknown_band_refuses_rather_than_widening(self):
        with pytest.raises(ValueError):
            cs._cohort_where({"source": "polymarket", "price_band": "band_0.4_0.6"})

    def test_cohort_where_without_a_band_is_unchanged(self):
        where, params = cs._cohort_where({"source": "polymarket", "category": "mma"})
        assert "BETWEEN" not in where
        assert params == {"src": "polymarket", "cat": "mma"}


class _SyncBackedSession:
    def __init__(self, conn):
        self._conn = conn

    async def execute(self, stmt, params=None):
        return self._conn.execute(stmt, params or {})


def _sqlite(outcomes):
    """``outcomes``: (outcome_id, market_id, cp, has_bid_or_trade, is_winner)."""
    eng = create_engine("sqlite://")
    conn = eng.connect()
    conn.execute(text("""
        CREATE TABLE futures_markets (
            id INTEGER PRIMARY KEY, source TEXT, external_id TEXT, status TEXT,
            llm_sport_category TEXT, mutually_exclusive BOOLEAN
        )"""))
    conn.execute(text("""
        CREATE TABLE futures_outcomes (
            id INTEGER PRIMARY KEY, market_id INTEGER, name TEXT,
            calibration_probability REAL, opening_probability REAL,
            is_winner BOOLEAN, resolution_source TEXT
        )"""))
    conn.execute(text("""
        CREATE TABLE futures_odds_snapshots (
            id INTEGER PRIMARY KEY, outcome_id INTEGER, yes_bid REAL, last_price REAL
        )"""))
    for oid, mid, cp, traded, win in outcomes:
        conn.execute(text(
            "INSERT OR IGNORE INTO futures_markets VALUES "
            "(:m, 'polymarket', :ext, 'resolved', 'basketball', 1)"
        ), {"m": mid, "ext": f"pm-{mid}"})
        conn.execute(text(
            "INSERT INTO futures_outcomes VALUES (:o, :m, :name, :cp, :cp, :w, 'api_settlement')"
        ), {"o": oid, "m": mid, "name": f"leg {oid}", "cp": cp, "w": win})
        conn.execute(text(
            "INSERT INTO futures_odds_snapshots (outcome_id, yes_bid, last_price) "
            "VALUES (:o, :b, :b)"
        ), {"o": oid, "b": 0.5 if traded else 0.0})
    return conn


_BAND_DIMS = {"provenance": "futures", "source": "polymarket", "price_band": BAND}


class TestTheCensusConfirmsOrRefutesTheCandidate:
    """The real ``_placeholder_fraction`` SQL. Every band row is a CANDIDATE;
    only snapshot evidence separates a placeholder from a traded coin-flip."""

    # Two-leg markets: legs at 0.48 / 0.52 (in band) plus out-of-band 0.90 / 0.10.
    def _outcomes(self, *, band_traded, tail_traded=False):
        rows = []
        for m in range(1, 5):
            rows.append((m * 10 + 1, m, 0.48, band_traded, False))
            rows.append((m * 10 + 2, m, 0.52, band_traded, True))
        for m in range(5, 9):
            rows.append((m * 10 + 1, m, 0.90, tail_traded, True))
            rows.append((m * 10 + 2, m, 0.10, tail_traded, False))
        return rows

    def test_no_bid_band_rows_are_confirmed(self):
        conn = _sqlite(self._outcomes(band_traded=False, tail_traded=True))
        ph = asyncio.run(cs._placeholder_fraction(_SyncBackedSession(conn), _BAND_DIMS))
        assert ph == 1.0

    def test_traded_band_rows_are_not_placeholders(self):
        conn = _sqlite(self._outcomes(band_traded=True))
        ph = asyncio.run(cs._placeholder_fraction(_SyncBackedSession(conn), _BAND_DIMS))
        assert ph == 0.0

    def test_the_band_census_is_not_diluted_by_out_of_band_rows(self):
        # The same no-bid band rows, read over the WHOLE source, are half the
        # population — the dilution that hid the class. Over the band they are
        # all of it.
        conn = _sqlite(self._outcomes(band_traded=False, tail_traded=True))
        session = _SyncBackedSession(conn)
        whole = asyncio.run(cs._placeholder_fraction(
            session, {"provenance": "futures", "source": "polymarket"}))
        band = asyncio.run(cs._placeholder_fraction(session, _BAND_DIMS))
        assert (whole, band) == (0.5, 1.0)

    def test_an_empty_band_is_an_absent_reading_not_a_zero(self):
        conn = _sqlite([(1, 1, 0.90, False, True), (2, 1, 0.10, False, False)])
        ph = asyncio.run(cs._placeholder_fraction(_SyncBackedSession(conn), _BAND_DIMS))
        assert ph is None

    def test_the_sample_rows_come_from_the_band(self):
        # The high-cp floor (>= 0.6) would leave a band cohort with no rows.
        conn = _sqlite(self._outcomes(band_traded=False))
        rows = asyncio.run(cs._sample_rows(_SyncBackedSession(conn), _BAND_DIMS))
        assert rows and all(0.45 <= r["cp"] <= 0.55 for r in rows)
        # Non-winners first, as #10516 requires.
        assert rows[0]["is_winner"] is False


# ---------------------------------------------------------------------------
# The four arms through the real run.
# ---------------------------------------------------------------------------
class TestArtifact:
    def test_the_broad_views_were_diluted_so_only_the_band_flags(self, monkeypatch):
        stats, _, _ = _run(monkeypatch, _HEALTHY_TAILS + _BAND_MISS,
                           band_fraction=0.9, file_issues=False, suppress_known=False)
        flagged = [f["dims"] for f in stats["findings"]]
        assert flagged == [_BAND_DIMS], flagged

    def test_backtest_rediscovers_poly_placeholder(self, monkeypatch):
        stats, filed, census = _run(monkeypatch, _HEALTHY_TAILS + _BAND_MISS,
                                    band_fraction=0.9, file_issues=False,
                                    suppress_known=False)
        (f,) = _band_findings(stats)
        assert f["explained_by"] == "poly_placeholder"
        assert f["placeholder_band"]["verdict"] == cs.PLACEHOLDER_ARTIFACT
        assert f["placeholder_band"]["no_bid_fraction"] == 0.9
        assert f["placeholder_band"]["evidence"] == "read"
        assert _BAND_DIMS in census
        assert filed == []

    def test_live_run_suppresses_it_as_known_work(self, monkeypatch):
        stats, filed, _ = _run(monkeypatch, _HEALTHY_TAILS + _BAND_MISS, band_fraction=0.9)
        assert _band_findings(stats), "it still surfaces in the findings"
        assert _band_cohorts(filed) == []


class TestTraded:
    def test_a_traded_band_miss_is_a_forecast_failure_and_files(self, monkeypatch):
        stats, filed, _ = _run(monkeypatch, _HEALTHY_TAILS + _BAND_MISS, band_fraction=0.05)
        (f,) = _band_findings(stats)
        assert f["explained_by"] is None
        assert f["placeholder_band"]["verdict"] == cs.PLACEHOLDER_NOT_PLACEHOLDER
        (c,) = _band_cohorts(filed)
        body = cs.build_issue_body(c, c.get("explained_by"), c.get("coverage", 0.0))
        assert "BELOW the 40% explanation threshold (5.0% of a bounded sample)" in body
        assert "PLACEHOLDER ARTIFACT" not in body

    def test_a_partial_reading_is_said_as_partial(self, monkeypatch):
        # 37% lies inside the existing 5-point margin under the 40% threshold.
        stats, filed, _ = _run(monkeypatch, _HEALTHY_TAILS + _BAND_MISS, band_fraction=0.37)
        (f,) = _band_findings(stats)
        assert f["placeholder_band"]["verdict"] == cs.PLACEHOLDER_PARTIAL
        assert len(_band_cohorts(filed)) == 1


class TestHealthyTradedControl:
    def test_a_calibrated_band_flags_nothing(self, monkeypatch):
        stats, filed, census = _run(monkeypatch, _HEALTHY_TAILS + _BAND_HEALTHY,
                                    band_fraction=0.0)
        assert stats["findings"] == []
        assert filed == []
        assert census == [], "an unflagged band spends no evidence budget"


class TestUnrelatedFailure:
    def test_a_high_cp_miss_is_never_labelled_a_placeholder(self, monkeypatch):
        stats, filed, _ = _run(monkeypatch, _HEALTHY_TAILS[:1] + _HIGH_CP_MISS + _BAND_HEALTHY,
                               band_fraction=0.9)
        assert stats["findings"], "the unrelated break must flag (non-vacuous)"
        assert _band_findings(stats) == []
        for f in stats["findings"]:
            assert f["placeholder_band"] is None
            assert f["explained_by"] is None
        assert filed
        for c in filed:
            body = cs.build_issue_body(c, c.get("explained_by"), c.get("coverage", 0.0))
            assert "Placeholder-price check" not in body


class TestUnavailableEvidence:
    @pytest.mark.parametrize("reading, reason", [
        (None, "no_sample"),
        (RuntimeError("snapshot census timed out"), "error"),
    ])
    def test_unread_evidence_is_unknown_and_files(self, monkeypatch, reading, reason):
        stats, filed, _ = _run(monkeypatch, _HEALTHY_TAILS + _BAND_MISS, band_fraction=reading)
        (f,) = _band_findings(stats)
        assert f["placeholder_band"]["verdict"] == cs.PLACEHOLDER_UNKNOWN
        assert f["placeholder_band"]["evidence"] == reason
        assert f["placeholder_band"]["no_bid_fraction"] is None
        assert "poly_placeholder" not in f["overlap_fractions"]
        assert f["explained_by"] is None
        (c,) = _band_cohorts(filed)
        body = cs.build_issue_body(c, c.get("explained_by"), c.get("coverage", 0.0))
        assert "UNKNOWN" in body
        assert "does not prove" in body
        assert "PLACEHOLDER ARTIFACT" not in body

    def test_outside_the_evidence_budget_is_unknown_not_skipped(self, monkeypatch):
        stats, filed, census = _run(monkeypatch, _HEALTHY_TAILS + _BAND_MISS,
                                    band_fraction=0.9, evidence_budget=0)
        (f,) = _band_findings(stats)
        assert census == [], "the budget is the existing one; nothing extra was read"
        assert f["placeholder_band"]["verdict"] == cs.PLACEHOLDER_UNKNOWN
        assert f["placeholder_band"]["evidence"] == "outside_evidence_budget"
        assert len(_band_cohorts(filed)) == 1

    def test_the_recurrence_comment_carries_the_unknown_too(self, monkeypatch):
        _, filed, _ = _run(monkeypatch, _HEALTHY_TAILS + _BAND_MISS, band_fraction=None)
        (c,) = _band_cohorts(filed)
        comment = cs.build_reobservation_comment(c)
        assert "UNKNOWN" in comment


# ---------------------------------------------------------------------------
# Root's review of 5512155: the census measures ONE fraction of a bounded
# sample. Meeting the threshold is the explanation policy's bar, not proof that
# the traded remainder is forecast-correct, and the published curve is a
# separate measurement. Each arm is rendered in the filed body AND the
# recurrence, and the disposition stays published_unknown throughout.
# ---------------------------------------------------------------------------
def _section(text_):
    lines = text_.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("### Placeholder-price check"))
    return "\n".join(lines[start:start + 2])


def _rendered(monkeypatch, fraction):
    # suppress_known=False so a threshold-meeting cohort reaches the renderer:
    # the bar it meets is the one the live run suppresses on, and its prose is
    # what a backtest or recurrence prints.
    stats, filed, _ = _run(monkeypatch, _HEALTHY_TAILS + _BAND_MISS,
                           band_fraction=fraction, suppress_known=False)
    (f,) = _band_findings(stats)
    (c,) = _band_cohorts(filed)
    body = cs.build_issue_body(c, c.get("explained_by"), c.get("coverage", 0.0))
    return f, c, body, cs.build_reobservation_comment(c)


class TestTheHeadlineIsBoundedByItsEvidence:
    def test_a_mixed_40_60_sample_meets_the_bar_and_claims_no_more(self, monkeypatch):
        f, c, body, comment = _rendered(monkeypatch, 0.4)
        # The standing policy is untouched: 40% is the bar and it is met.
        assert f["explained_by"] == "poly_placeholder"
        assert f["placeholder_band"]["verdict"] == cs.PLACEHOLDER_ARTIFACT
        assert c["disposition"] == cs.DISP_PUBLISHED_UNKNOWN
        for text_ in (body, comment):
            sec = _section(text_)
            assert "MEETS the 40% explanation threshold (40.0% of a bounded sample)" in sec
            assert "The other 60.0% of the sample did show a bid or a trade" in sec
            assert "published curve's error" in sec and "unresolved" in sec
            assert "forecast failure" not in sec.lower()
            assert "PLACEHOLDER ARTIFACT" not in text_
            assert f"`{cs.DISP_PUBLISHED_UNKNOWN}`" in text_

    def test_a_below_threshold_nonzero_fraction_stays_measured(self, monkeypatch):
        f, c, body, comment = _rendered(monkeypatch, 0.2)
        assert f["explained_by"] is None
        assert f["placeholder_band"]["verdict"] == cs.PLACEHOLDER_NOT_PLACEHOLDER
        assert c["disposition"] == cs.DISP_PUBLISHED_UNKNOWN
        for text_ in (body, comment):
            sec = _section(text_)
            assert "BELOW the 40% explanation threshold (20.0% of a bounded sample)" in sec
            assert "20.0% of a bounded sample never showed a bid or a trade — measured" in sec
            assert "The other 80.0% of the sample did show a bid or a trade" in sec
            assert "unresolved" in sec
            assert "the band traded" not in sec
            assert "NOT a placeholder artifact" not in sec
            assert f"`{cs.DISP_PUBLISHED_UNKNOWN}`" in text_

    def test_a_near_threshold_fraction_names_its_remainder(self, monkeypatch):
        _, _, body, comment = _rendered(monkeypatch, 0.37)
        for text_ in (body, comment):
            sec = _section(text_)
            assert "NEAR the 40% explanation threshold (37.0% of a bounded sample)" in sec
            assert "The other 63.0% of the sample" in sec


# ---------------------------------------------------------------------------
# #1057 clause 2 — same-root-cause grouping, reconciled against CURRENT rules.
#
# The 28 `mex_normalization` findings were a BACKTEST report (file_issues=False,
# suppress_known=False), which lists every flagged cohort by design. Under the
# live rules a cohort the shipped exclusion explains is suppressed before
# dedup, so a systemic explained class files nothing; and independent
# unexplained failures are not merged because they share a dominant label.
# These pin that boundary; no grouping code is added.
# ---------------------------------------------------------------------------
def _mex_row(category, n=2000):
    r = _row("kalshi", 8, n, int(0.3 * n), 0.85, band=False, category=category)
    r["structure_class"] = "mex_multi"
    r["mex_norm_n"] = r["any_known_n"] = n
    r["pub_n"] = r["pub_winners"] = 0
    r["pub_sum_prob"] = 0.0
    return r


_CATEGORIES = ["football", "basketball", "baseball", "hockey", "soccer", "golf",
               "tennis", "mma", "politics", "economics", "tech", "culture"]


class TestSameRootCauseBoundary:
    def test_an_explained_systemic_class_reports_every_cohort_in_backtest(self, monkeypatch):
        stats, filed, _ = _run(monkeypatch, [_mex_row(c) for c in _CATEGORIES],
                               band_fraction=None, file_issues=False, suppress_known=False)
        mex = [f for f in stats["findings"] if f["explained_by"] == "mex_normalization"]
        assert len(mex) >= len(_CATEGORIES)
        assert filed == []

    def test_the_same_class_live_files_nothing(self, monkeypatch):
        stats, filed, _ = _run(monkeypatch, [_mex_row(c) for c in _CATEGORIES],
                               band_fraction=None)
        assert stats["flagged"] >= len(_CATEGORIES)
        assert filed == []

    def test_independent_unexplained_failures_are_not_merged_by_label(self, monkeypatch):
        rows = []
        for c in ("tech", "culture"):
            r = _mex_row(c)
            r["mex_norm_n"] = r["any_known_n"] = 200   # 10%: dominant, not explaining
            r["pub_n"], r["pub_winners"], r["pub_sum_prob"] = 1800, 540, 0.85 * 1800
            rows.append(r)
        stats, filed, _ = _run(monkeypatch, rows, band_fraction=None)
        cats = {c["dims"].get("category") for c in filed}
        assert {"tech", "culture"} <= cats
