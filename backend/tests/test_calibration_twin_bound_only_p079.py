"""``--bound-only`` — Gate 0's reachable half, and the pass it must never claim.

CAL-P079 split two measurements that ``measure_published_twin`` had always
produced together, because they have different reachability:

* the **bound** is :func:`tolerance_pp` over the payload's ``staged`` block. No
  database, no credentials, no fold.
* the **verdict** needs the fold, and the fold is reachable from neither an
  agent sandbox (TCP 5432 egress blocked) nor the admin ``db-query`` rail
  (measured: its row path hardcodes a 10 s ``statement_timeout``; the twin's own
  default budget is 240 s, and even a single ``(source, category)`` chunk
  exceeded 10 s).

Leaving them fused meant an unreachable measurement was suppressing a reachable
one. Splitting them creates exactly one new hazard, and this suite exists for
it: **a mode that runs no check must never be able to return the value that
means the check passed.** ``VERDICT_AGREES`` is the gate's pass token; the
bound-only path must be structurally incapable of emitting it, and must exit 2
— not 0 — when no bound is earned.
"""

from __future__ import annotations

import json

import pytest

from app.utils.calibration_published_twin import VERDICT_AGREES


def _payload(staged):
    return {
        "generated_at": "2026-08-20T15:17:44.653129+00:00",
        "availability": "stale",
        "staged": staged,
        # Deliberately populated: if the mode ever grew a fold, these buckets
        # would let it silently start comparing. It must ignore them.
        "buckets": [
            {"source": "kalshi", "category": "hockey", "bucket_idx": 3,
             "n": 100, "winners": 35},
        ],
    }


_FROZEN_BANK = {
    "measured": True,
    "staged_at": "2026-08-19T17:16:31.866144+00:00",
    "staged_age_s": 83264,
    "units_banked": 128,
    "units_this_beat": 0,
    "units_drifted": 115,
    "units_drift_checkable": 127,
    "units_drift_unknown": 1,
    "bank_advanced_this_beat": False,
    "frozen_over_drift": True,
}


class TestBoundOnly:
    @pytest.mark.asyncio
    async def test_reports_the_bound_the_frozen_bank_earns(
        self, monkeypatch, capsys
    ):
        """The production reading of 2026-08-20: 128 banked, 115 drifted, 1
        unknown -> 100 * 116/128 = 90.625 pp. The unknown unit counts AS drift,
        which is the direction that cannot invent a pass (CAL-P069)."""
        import scripts.measure_published_twin as mod

        monkeypatch.setattr(
            mod, "_load_payload", lambda args: (_payload(_FROZEN_BANK), None)
        )
        code = await mod.main(["--bound-only"])
        assert code == 0

        out = json.loads(capsys.readouterr().out)
        assert out["tolerance_pp"] == pytest.approx(90.625)
        assert out["mode"] == "bound_only"

    @pytest.mark.asyncio
    async def test_never_claims_the_gate_passed(self, monkeypatch, capsys):
        """The whole reason this suite exists. No fold ran, so ``agrees`` is
        unavailable — and it must be unavailable on the HEALTHIEST input, not
        merely on a broken one."""
        import scripts.measure_published_twin as mod

        clean = dict(_FROZEN_BANK, units_drifted=0, units_drift_unknown=0)
        monkeypatch.setattr(
            mod, "_load_payload", lambda args: (_payload(clean), None)
        )
        code = await mod.main(["--bound-only"])
        assert code == 0

        out = json.loads(capsys.readouterr().out)
        assert out["verdict"] != VERDICT_AGREES
        assert out["verdict"] == "bound_only"
        # A zero-drift bank earns the TIGHT floor, never a bound of 0.0 — a
        # zero tolerance would make any float noise a disagreement.
        assert out["tolerance_pp"] > 0

    @pytest.mark.asyncio
    async def test_no_fold_is_attempted(self, monkeypatch):
        """Reachability is the point: the mode must not touch the database even
        when one happens to be reachable."""
        import scripts.measure_published_twin as mod

        async def exploding_fold(*, timeout_ms):  # pragma: no cover - must not run
            raise AssertionError("--bound-only must not run the fold")

        monkeypatch.setattr(mod, "_fold", exploding_fold)
        monkeypatch.setattr(
            mod, "_load_payload", lambda args: (_payload(_FROZEN_BANK), None)
        )
        assert await mod.main(["--bound-only"]) == 0

    @pytest.mark.asyncio
    async def test_an_unmeasured_bank_exits_2_not_0(self, monkeypatch, capsys):
        """``measured: false`` earns no bound. Exit 2 keeps "could not run"
        distinct from "ran and was fine" — gotcha #54's amendment, where the
        VALUE of a non-zero exit is the story."""
        import scripts.measure_published_twin as mod

        monkeypatch.setattr(
            mod,
            "_load_payload",
            lambda args: (_payload({"measured": False, "reason": "cursor_unreadable"}), None),
        )
        code = await mod.main(["--bound-only"])
        assert code == 2

        out = json.loads(capsys.readouterr().out)
        assert out["tolerance_pp"] is None
        assert out["verdict"] != VERDICT_AGREES
        assert out["unmeasurable_reason"]

    @pytest.mark.asyncio
    async def test_an_unreachable_payload_exits_2_and_names_why(
        self, monkeypatch, capsys
    ):
        import scripts.measure_published_twin as mod

        monkeypatch.setattr(
            mod, "_load_payload", lambda args: ({}, "api_unreachable: URLError: nope")
        )
        code = await mod.main(["--bound-only"])
        assert code == 2

        out = json.loads(capsys.readouterr().out)
        assert "api_unreachable" in out["unmeasurable_reason"]

    @pytest.mark.asyncio
    async def test_writes_the_artifact_when_asked(
        self, monkeypatch, tmp_path, capsys
    ):
        import scripts.measure_published_twin as mod

        monkeypatch.setattr(
            mod, "_load_payload", lambda args: (_payload(_FROZEN_BANK), None)
        )
        out_path = tmp_path / "nested" / "bound.json"
        assert await mod.main(["--bound-only", "--out", str(out_path)]) == 0
        capsys.readouterr()

        written = json.loads(out_path.read_text())
        assert written["tolerance_pp"] == pytest.approx(90.625)
