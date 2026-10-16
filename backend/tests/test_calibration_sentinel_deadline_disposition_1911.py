"""#1911 — the run deadline must never skip the published-curve disposition.

The evidence loop used to `break` at the deadline. Every flagged cohort past
that point kept no `disposition` and no `explained_by`, so `_suppressed()` read
it as unexplained and it went to filing on its RAW number alone — the #1142
error the published view exists to prevent. The organic production run of
2026-10-13 00:13Z stopped "after 22 of 218 flagged cohorts" and its sixth
filing attempt (49032741c5d0) was exactly such a cohort.

These tests drive the real `_run_calibration_sentinel` with the deadline
already passed at the FIRST cohort, and pin both directions (gotcha #43):

  * a cohort whose GENUINELY CANONICAL published curve is under threshold (an
    events cohort: the scan's complement is the curve's whole exclusion set)
    is NOT filed — only its disposition suppresses it;
  * the #1142- and #1143-shaped FUTURES cohorts DO file, on their raw number,
    with the published curve stated UNKNOWN and the scan's limited-mask
    survivors named as such (#1911 parity, Root 2026-10-15: a mask complement
    is not what users see, so it may neither suppress nor confirm an alarm).

The control arm runs the same mining rows with no deadline and must file the
identical set: the deadline may cost evidence, never a verdict.
"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace

import pytest

import app.services.durable_snapshots as durable_snapshots
import app.tasks.calibration_sentinel as cs
import app.utils.durable_state as durable_state
from app.tasks.calibration_sentinel import (
    DISP_EXCLUSION_WORKING,
    DISP_PUBLISHED_UNKNOWN,
    PUBLISHED_BASIS_CANONICAL,
    PUBLISHED_BASIS_LIMITED_MASK,
)


def _row(category, series, structure, n, winners, pub_n, pub_winners):
    """One mining-scan row in bucket 8 (cp ~0.85). The excluded rows are
    `n - pub_n`, counted in the union and in the prop-threshold class."""
    return {
        "source": "kalshi", "category": category, "series_family": series,
        "structure_class": structure, "provenance": "futures",
        "bucket": 8, "n": n, "winners": winners, "sum_prob": 0.85 * n,
        "malformed_binary_n": 0, "esports_bundle_n": 0, "mex_norm_n": 0,
        "void_n": 0, "heuristic_n": 0, "kalshi_prop_threshold_n": n - pub_n,
        "any_known_n": n - pub_n,
        "pub_n": pub_n, "pub_winners": pub_winners, "pub_sum_prob": 0.85 * pub_n,
        "min_created_at": None,
    }


# #1142's shape: 23% excluded, and the excluded rows are the ones that lose, so
# raw reads ~19.5pp while the 770 survivors win 85% (published ~0pp). Coverage
# 0.23 is under the 0.4 threshold, so `explained_by` stays None and ONLY the
# disposition can keep this off the board.
_NHL = _row("hockey", "KXNHLGOAL", "binary", n=1000, winners=655, pub_n=770, pub_winners=655)
# #1143's shape: the survivors are still badly calibrated (60% vs 85%).
_MLB = _row("baseball", "KXMLBTB", "multi_nonmex", n=2000, winners=1080, pub_n=1800, pub_winners=1080)
# The canonical arm: an events cohort, same numbers as the #1142 shape, whose
# excluded rows are the soccer two-way ones — the curve's only events exclusion.
_SOC = {
    "provenance": "events", "source": "odds_api", "category": "soccer",
    "series_family": "events_moneyline", "structure_class": "binary",
    "bucket": 8, "n": 1000, "winners": 655, "sum_prob": 850.0,
    "malformed_binary_n": 0, "esports_bundle_n": 0, "mex_norm_n": 0,
    "void_n": 0, "heuristic_n": 0, "kalshi_prop_threshold_n": 0,
    "soccer_2way_n": 230, "any_known_n": 230,
    "pub_n": 770, "pub_winners": 655, "pub_sum_prob": 0.85 * 770,
    "min_created_at": None,
}


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return iter(self._rows)


class _FakeSession:
    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql == cs._FUTURES_MINING_SQL:
            return _Result([dict(_NHL), dict(_MLB)])
        if sql == cs._EVENTS_MINING_SQL:
            return _Result([dict(_SOC)])
        return _Result([])

    async def rollback(self):
        return None


def _run(monkeypatch, deadline_seconds):
    evidence_calls: list[dict] = []
    filed: list[dict] = []

    @contextlib.asynccontextmanager
    async def _session():
        yield _FakeSession()

    async def _placeholder(session, dims):
        evidence_calls.append(dims)
        return None

    async def _samples(session, dims, limit=12):
        evidence_calls.append(dims)
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

    stats = asyncio.run(cs._run_calibration_sentinel(deadline_seconds=deadline_seconds))
    return stats, filed, evidence_calls


def _series(cohorts, series):
    return [c for c in cohorts if c["dims"].get("series") == series]


@pytest.fixture
def past_deadline(monkeypatch):
    return _run(monkeypatch, deadline_seconds=-1.0)


def test_the_specimens_flag_so_the_run_is_not_vacuous(past_deadline):
    stats, _, _ = past_deadline
    assert stats["flagged"] >= 2
    flagged_series = {f["dims"].get("series") for f in stats["findings"]}
    assert {"KXNHLGOAL", "KXMLBTB", "events_moneyline"} <= flagged_series


def test_the_deadline_fired_and_skipped_only_the_evidence_census(past_deadline):
    stats, _, evidence_calls = past_deadline
    deadline = [e["deadline"] for e in stats["errors"] if "deadline" in e]
    assert len(deadline) == 1
    assert deadline[0].startswith("evidence census stopped after 0 of ")
    assert evidence_calls == []


def test_every_flagged_cohort_carries_a_disposition_past_the_deadline(past_deadline):
    stats, _, _ = past_deadline
    assert len(stats["findings"]) == stats["flagged"]
    assert all(f["disposition"] for f in stats["findings"])


def test_a_canonical_published_curve_under_threshold_does_not_file(past_deadline):
    stats, filed, _ = past_deadline
    assert not _series(filed, "events_moneyline")
    soc = [f for f in stats["findings"] if f["dims"].get("series") == "events_moneyline"]
    assert soc and all(f["disposition"] == DISP_EXCLUSION_WORKING for f in soc)
    assert all(f["published_basis"] == PUBLISHED_BASIS_CANONICAL for f in soc)
    # Not explained by coverage: the disposition is the only thing holding it.
    assert all(f["explained_by"] is None for f in soc)


def test_the_1142_shape_files_on_raw_with_published_unknown(past_deadline):
    """The mask complement used to read 'published ~0pp' and suppress this. It
    is a limited mask, so the raw alarm now stands and says so."""
    stats, filed, _ = past_deadline
    (nhl,) = _series(filed, "KXNHLGOAL")
    assert nhl["disposition"] == DISP_PUBLISHED_UNKNOWN
    assert nhl["published_basis"] == PUBLISHED_BASIS_LIMITED_MASK
    assert nhl["published_mce"] is None and nhl["published_n"] is None
    assert nhl["mask_survivor_n"] == 770 and nhl["mask_survivor_mce"] is not None
    assert "not measured by this scan" in nhl["disposition_why"]


def test_the_1143_shape_files_with_raw_and_its_mask_named(past_deadline):
    _, filed, _ = past_deadline
    (mlb,) = _series(filed, "KXMLBTB")
    assert mlb["disposition"] == DISP_PUBLISHED_UNKNOWN
    assert mlb["published_mce"] is None
    assert mlb["mask_survivor_n"] == 1800 and mlb["mask_survivor_mce"] is not None


def test_no_cohort_reaches_filing_without_a_disposition(past_deadline):
    _, filed, _ = past_deadline
    assert filed
    assert all(c.get("disposition") for c in filed)


def test_the_deadline_costs_evidence_never_a_verdict(monkeypatch, past_deadline):
    """Control arm: same rows, no deadline. Evidence runs, and the filed set and
    every disposition are identical to the past-deadline run."""
    late_stats, late_filed, _ = past_deadline
    stats, filed, evidence_calls = _run(monkeypatch, deadline_seconds=3600.0)
    assert evidence_calls, "the control must exercise the evidence census"
    assert not [e for e in stats["errors"] if "deadline" in e]
    assert {c["fingerprint"] for c in filed} == {c["fingerprint"] for c in late_filed}
    assert {f["fingerprint"]: f["disposition"] for f in stats["findings"]} == {
        f["fingerprint"]: f["disposition"] for f in late_stats["findings"]
    }
