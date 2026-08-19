"""The feed audit must never report a rate it did not measure (UX-P102).

THE DEFECT THIS PINS, observed 2026-08-19 against deployed `962f668a`.
`/api/feed` answered **HTTP 200** with `degraded_reason: "futures_timeout"`,
25 concept/tournament cards and ZERO futures. `audit_feed_quality.py` filtered
to `type == "futures"`, classified nothing, and printed:

    Items: 0
    boring-rate@20:          0/20

then exited 0. A total measurement failure rendered as the best possible score,
in the exact metric #1958 is open on — and a reader comparing runs would have
recorded an improvement.

This is gotcha #53 wearing a percentage: the same response shape meant "nothing
was boring" and "nothing was measured", and the code inferred the flattering
one. A rate over an empty window is not zero, it is undefined.

The guard is asserted in BOTH directions, because a refusal that also fires on
a healthy page would just be a different broken instrument.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIT_PATH = ROOT / "scripts" / "audit_feed_quality.py"


def _load_audit():
    spec = importlib.util.spec_from_file_location("audit_feed_quality", AUDIT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _futures_card(i: int) -> dict:
    return {
        "type": "futures",
        "score": 80 - i,
        "reason": f"Something moved {i}",
        "headline": f"Card {i}",
        "context_summary": f"Card {i} context",
        "data": {
            "id": 1000 + i,
            "name": f"Will thing {i} happen?",
            "category": "politics",
            "outcomes": [
                {"name": "Yes", "probability": 0.4},
                {"name": "No", "probability": 0.6},
            ],
        },
    }


@pytest.fixture
def audit(monkeypatch):
    mod = _load_audit()
    monkeypatch.setattr(mod, "_load_polymarket_email_ground_truth",
                        lambda: {"items": [], "metadata": {"configured": False,
                                                           "raw_row_count": 0,
                                                           "latest_date": None,
                                                           "loaded_count": 0,
                                                           "stale": False}})
    monkeypatch.setattr(mod, "_load_external_curator_ground_truth",
                        lambda: {"items": [], "metadata": {"configured": False,
                                                           "raw_row_count": 0,
                                                           "latest_date": None,
                                                           "loaded_count": 0,
                                                           "stale": False}})
    return mod


def _run(audit, monkeypatch, capsys, payload):
    monkeypatch.setattr(audit.httpx, "get", lambda *a, **k: _Resp(payload))
    code = audit.main()
    return code, capsys.readouterr().out


def test_a_degraded_feed_with_no_futures_is_a_failed_audit(
    audit, monkeypatch, capsys
):
    """The exact production shape: 200, degraded, zero futures cards."""
    payload = {
        "items": [{"type": "concept", "data": {"name": "Some fight night"}}] * 25,
        "degraded_reason": "futures_timeout",
        "build_quality": "degraded",
    }
    code, out = _run(audit, monkeypatch, capsys, payload)

    assert code != 0, "a measurement failure must not exit 0"
    assert "NOT MEASURABLE" in out
    assert "futures_timeout" in out, "the reason must reach the reader"
    # The load-bearing assertion: the flattering number must NOT be printed.
    assert "boring-rate@20:          0/20" not in out


def test_an_empty_feed_is_a_failed_audit_even_without_a_degraded_reason(
    audit, monkeypatch, capsys
):
    """An undegraded empty page is still nothing to grade."""
    code, out = _run(audit, monkeypatch, capsys, {"items": []})
    assert code != 0
    assert "NOT MEASURABLE" in out
    assert "0/20" not in out


def test_a_healthy_full_page_still_reports_its_rate(audit, monkeypatch, capsys):
    """The other direction. A refusal that fires on a good page is not a guard."""
    payload = {"items": [_futures_card(i) for i in range(30)]}
    code, out = _run(audit, monkeypatch, capsys, payload)

    assert code == 0
    assert "NOT MEASURABLE" not in out
    assert "boring-rate@20:" in out
    assert "Items: 30" in out
    assert "SHORT window" not in out


def test_a_short_page_reports_its_rate_but_says_it_is_short(
    audit, monkeypatch, capsys
):
    """Between the two: gradeable, but not comparable to a full page.

    Silently averaging a 5-card page into a @20 series is the quieter version
    of the same lie.
    """
    payload = {"items": [_futures_card(i) for i in range(5)]}
    code, out = _run(audit, monkeypatch, capsys, payload)

    assert code == 0
    assert "SHORT window" in out
    assert "boring-rate@20:" in out
