import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from score import decide, score
import compare


def fixture():
    return {"window_ms": [0, 5000], "coverage": {"scope": "synthetic scorer control"},
            "checks": {}, "eligible": [{"id": "a", "stream": "event:1", "at_ms": [0, 0],
                                        "evidence": "control"}],
            "displays": [{"surface": s, "covers": ["a"], "at_ms": [700, 800]}
                         for s in ("headline", "chart")]}


class ScoreControls(unittest.TestCase):
    def test_separate_surfaces_and_no_double_charge(self):
        t = fixture()
        t["displays"][1]["at_ms"] = [1100, 1200]
        s = score(t)
        self.assertEqual(s["surfaces"]["headline"]["worst_delay_ms"], [700, 800])
        self.assertEqual(s["surfaces"]["chart"]["under_one_second"]["definite"], 0)
        self.assertEqual(s["both_surfaces_cumulative_trailing_ms"], [1100, 1200])

    def test_superseding_ticks_are_not_double_counted(self):
        t = fixture()
        t["eligible"].append({"id": "b", "stream": "event:1", "at_ms": [300, 300],
                              "evidence": "control", "supersedes": ["a"]})
        for d in t["displays"]:
            d["covers"] = ["b"]
        s = score(t)
        self.assertEqual(s["both_surfaces_cumulative_trailing_ms"], [700, 800])
        h = s["surfaces"]["headline"]
        self.assertEqual(h["under_one_second"]["denominator"], 1)
        self.assertEqual(h["coalesced"], ["a"])
        self.assertEqual(h["unresolved_at_end"], [])

    def test_equal_probability_cannot_erase_missing_identity(self):
        t = fixture()
        t["eligible"].append({"id": "b", "stream": "event:1", "at_ms": [300, 300],
                              "evidence": "control"})
        s = score(t)
        self.assertEqual(s["surfaces"]["chart"]["unresolved_at_end"], ["b"])
        self.assertTrue(s["worst_is_lower_bound"])
        self.assertEqual(s["both_surfaces_cumulative_trailing_ms"], [5000, 5000])

    def test_one_second_boundary_is_not_rounded_to_pass(self):
        for interval, expected in [([999, 1001], (0, 0, 1)), ([1000, 1000], (0, 1, 0)),
                                   ([990, 999], (1, 0, 0))]:
            t = fixture()
            t["displays"][0]["at_ms"] = interval
            s = score(t)["surfaces"]["headline"]["under_one_second"]
            self.assertEqual((s["definite"], s["over"], s["uncertain"]), expected)

    def test_no_eligibility_is_unknown_not_perfect(self):
        t = fixture()
        t.update(eligible=[], displays=[])
        s = score(t)
        self.assertIsNone(s["surfaces"]["headline"]["under_one_second"]["percent_bounds"])
        self.assertEqual(decide(s, s), "experiment_invalid")

    def test_clock_and_identity_refusals(self):
        for corrupt in [lambda t: t["eligible"][0].update(at_ms=[float('nan'), 0]),
                        lambda t: t["eligible"].append(copy.deepcopy(t["eligible"][0])),
                        lambda t: t["eligible"][0].update(supersedes=["a"]),
                        lambda t: t["displays"][0].update(covers=["unknown"]),
                        lambda t: t["eligible"][0].update(evidence="")]:
            t = fixture()
            corrupt(t)
            with self.assertRaises(ValueError):
                score(t)

    def test_no_cross_event_supersession(self):
        t = fixture()
        t["eligible"].append({"id": "b", "stream": "event:2", "at_ms": [300, 300],
                              "evidence": "control", "supersedes": ["a"]})
        with self.assertRaises(ValueError):
            score(t)

    def test_improvement_below_one_second_is_not_required(self):
        t, c = fixture(), fixture()
        for d in t["displays"]:
            d["at_ms"] = [3000, 3100]
        for d in c["displays"]:
            d["at_ms"] = [2000, 2100]
        self.assertEqual(decide(score(t), score(c)), "improvement_supported")
        c["violations"] = ["expired state displayed"]
        self.assertEqual(decide(score(t), score(c)), "no_improvement_or_regression")

    def test_worst_guard_rejects_cumulative_only_gain(self):
        b, c = score(fixture()), score(fixture())
        c["surfaces"]["chart"]["worst_delay_ms"] = [900, 950]
        c["surfaces"]["chart"]["cumulative_trailing_ms"] = [400, 500]
        self.assertEqual(decide(b, c), "no_improvement_or_regression")

    def test_overlapping_uncertainty_does_not_claim_gain(self):
        self.assertEqual(decide(score(fixture()), score(fixture())), "no_improvement_demonstrated")

    def test_first_display_uses_all_overlapping_bounds(self):
        baseline, candidate = fixture(), fixture()
        baseline["displays"] = [
            {"surface": surface, "covers": ["a"], "at_ms": bounds}
            for surface in ("headline", "chart") for bounds in ([100, 500], [200, 400])]
        for d in candidate["displays"]:
            d["at_ms"] = [120, 180]
        result = score(baseline)
        self.assertEqual(result["surfaces"]["headline"]["worst_delay_ms"], [100, 400])
        self.assertEqual(decide(result, score(candidate)), "no_improvement_demonstrated")

    def test_truncated_capture_cannot_win(self):
        b, c = fixture(), fixture()
        c.update(window_ms=[0, 500], displays=[])
        self.assertEqual(decide(score(b), score(c)), "experiment_invalid")

    def test_different_cohort_cannot_win(self):
        b, c = fixture(), fixture()
        c["eligible"][0]["id"] = "unrelated"
        for d in c["displays"]:
            d["covers"] = ["unrelated"]
        self.assertEqual(decide(score(b), score(c)), "experiment_invalid")


class EntryControls(unittest.TestCase):
    def prepared_pair(self, root):
        spec = {"mode": "controlled-admission", "hypothesis": "test", "baseline_release_evidence": "test"}
        for arm in ("baseline", "candidate"):
            path = root/arm
            (path/"source").mkdir(parents=True)
            (path/"source/code.py").write_text(arm)
            compare.write(path/"PREPARED.json", {"sha": arm, "files": {"code.py": compare.digest(path/"source/code.py")}})
            spec[arm+"_prepared"], spec[arm+"_sha"] = str(path), arm
        for key in ("helper", "transition_scorer"):
            path = root/(key+".py")
            path.write_text("# pinned control")
            spec[key], spec[key+"_sha256"] = str(path), compare.digest(path)
        (root/"backend_lab.py").write_text("# lab")
        spec["lab_files"] = {"backend_lab.py": compare.digest(root/"backend_lab.py")}
        return spec

    def test_all_source_preflight_precedes_either_arm(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec = self.prepared_pair(root)
            (root/"candidate/source/code.py").write_text("drift")
            with patch.object(compare, "load_module") as loader:
                with self.assertRaisesRegex(ValueError, "source drift"):
                    compare.run_existing(spec, root/"out")
                loader.assert_not_called()

    def test_failed_arm_stops_pair_and_retains_pointer(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec = self.prepared_pair(root)
            run = root/"failed-run"
            run.mkdir()
            compare.write(run/"RUN.json", {"status": "NO_RESULT"})
            with patch.object(compare, "load_module") as loader:
                loader.return_value.arm.return_value = run
                with self.assertRaisesRegex(ValueError, "did not complete"):
                    compare.run_existing(spec, root/"out", stable_backend_clock=True)
                self.assertEqual(loader.return_value.arm.call_count, 1)
                self.assertEqual(loader.return_value.arm.call_args.kwargs["dnpl_sources"], "kalshi,polymarket")
                self.assertEqual(loader.return_value.arm.call_args.kwargs["fixture"], "singleton")
            failure = compare.read(root/"out/INVALID.json")
            self.assertEqual(failure["spec"]["baseline"], str(run))
            self.assertEqual(failure["completed_arms"], [])
            self.assertEqual(failure["failed_arm"]["path"], str(run))
            self.assertEqual(compare.read(root/"out/RUNS.json")["completed"], [])

    def test_cleanup_exception_preserves_helpers_printed_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec = self.prepared_pair(root)
            def failed_cleanup(*args, **kwargs):
                print(root/"run-with-cleanup-error")
                raise RuntimeError("cleanup failed")
            with patch.object(compare, "load_module") as loader:
                loader.return_value.arm.side_effect = failed_cleanup
                with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                    compare.run_existing(spec, root/"out", stable_backend_clock=True)
            failure = compare.read(root/"out/INVALID.json")
            self.assertEqual(failure["completed_arms"], [])
            self.assertIn("run-with-cleanup-error", Path(failure["failed_arm"]["stdout"]).read_text())

    def test_run_refuses_clock_pair_before_reserving_output_or_any_arm(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec = self.prepared_pair(root)
            with patch.object(compare, "load_module") as loader:
                with self.assertRaisesRegex(ValueError, "timing_unknown"):
                    compare.run_existing(spec, root/"out")
                loader.assert_not_called()
            self.assertFalse((root/"out").exists())

    def test_recorder_extension_is_passive_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ("warm_helper.py", "backend_lab.py", "proxy.py", "FIXTURE-INPUT.json"):
                (root/name).write_text("retained")
            original = "for (const t of ['probability','folded_probability','preview']) listen(t);"
            (root/"observe.cjs").write_text(original)
            spec = {"helper": str(root/"warm_helper.py"), "helper_sha256": compare.digest(root/"warm_helper.py"),
                    "lab_files": {name: compare.digest(root/name) for name in
                                  ("backend_lab.py", "proxy.py", "observe.cjs", "FIXTURE-INPUT.json")}}
            compare.stage_recorder(spec, root/"staged")
            self.assertEqual((root/"observe.cjs").read_text(), original)
            self.assertIn("'preview_v3'", (root/"staged/observe.cjs").read_text())
            self.assertEqual((root/"staged/backend_lab.py").read_text(), "retained")

    def test_recorder_refuses_each_drifted_dependency_before_output(self):
        for drift in ("backend_lab.py", "proxy.py", "observe.cjs", "FIXTURE-INPUT.json"):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                names = ("backend_lab.py", "proxy.py", "observe.cjs", "FIXTURE-INPUT.json")
                for name in ("warm_helper.py", *names):
                    (root/name).write_text("['probability','folded_probability','preview']")
                spec = {"helper": str(root/"warm_helper.py"), "helper_sha256": compare.digest(root/"warm_helper.py"),
                        "lab_files": {name: compare.digest(root/name) for name in names}}
                with (root/drift).open("a") as f:
                    f.write("\n// unreviewed drift")
                with self.assertRaisesRegex(ValueError, "dependency drift"):
                    compare.stage_recorder(spec, root/"out")
                self.assertFalse((root/"out").exists())

    def test_display_recorder_is_opt_in_and_does_not_change_stream_url(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            names = ("backend_lab.py", "proxy.py", "observe.cjs", "FIXTURE-INPUT.json")
            for name in ("warm_helper.py", *names):
                (root/name).write_text("retained")
            original = """['probability','folded_probability','preview'];
 let prior='',prev=performance.now();
const r={visibility:document.visibilityState,gap:now-prev};
super(...args); const frame={payload:JSON.parse(e.data)};
"""
            (root/"observe.cjs").write_text(original)
            spec = {"helper": str(root/"warm_helper.py"), "helper_sha256": compare.digest(root/"warm_helper.py"),
                    "lab_files": {name: compare.digest(root/name) for name in names}}
            compare.stage_recorder(spec, root/"ordinary")
            self.assertNotIn("displayIdentity:", (root/"ordinary/observe.cjs").read_text())
            compare.stage_recorder(spec, root/"display", display_identity=True)
            changed = (root/"display/observe.cjs").read_text()
            self.assertIn("displayIdentity:readDisplayIdentity10090()", changed)
            self.assertIn("super(...args);", changed)
            self.assertIn("url:this.url,payload:", changed)
            self.assertNotIn("searchParams", changed)
            self.assertEqual((root/"observe.cjs").read_text(), original)
            self.assertEqual(compare.read(root/"display/RECORDER-DELTA.json")["display_schema"],
                             "display-identity-sample/1")
            (root/"observe.cjs").write_text(original.replace("gap:now-prev}", "gap:0}"))
            spec["lab_files"]["observe.cjs"] = compare.digest(root/"observe.cjs")
            with self.assertRaisesRegex(ValueError, "display recorder source changed"):
                compare.stage_recorder(spec, root/"refused", display_identity=True)
            self.assertFalse((root/"refused").exists())

    def test_render_failure_never_leaves_success_decision(self):
        arm = {"source": {"backend_ref": "x", "frontend_build_source_sha": "x"},
               "input_identity": [], "initial_values": {}, "score": score(fixture()),
               "raw_input_hash": "x", "input_relative_ms": [0], "compute": None}
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/"report"
            with patch.object(compare, "admission_arm", return_value=arm), patch("view.render", side_effect=RuntimeError("render failed")):
                with self.assertRaisesRegex(RuntimeError, "render failed"):
                    compare.consume({"baseline": "b", "candidate": "c", "baseline_sha": "x", "candidate_sha": "x"}, out)
            self.assertFalse((out/"comparison.json").exists())
            self.assertEqual(compare.read(out/"INVALID.json")["reason"], "render failed")

    def test_consume_forwards_and_records_the_clock_opt_in(self):
        arm = {"source": {"backend_ref": "x", "frontend_build_source_sha": "x"},
               "input_identity": [], "initial_values": {}, "score": score(fixture()),
               "raw_input_hash": "x", "input_relative_ms": [0], "compute": None}
        spec = {"baseline": "b", "candidate": "c", "baseline_sha": "x", "candidate_sha": "x"}
        for opt_in in (False, True):
            with tempfile.TemporaryDirectory() as d:
                with patch.object(compare, "admission_arm", return_value=arm) as adapter, patch("view.render"):
                    result = compare.consume(spec, Path(d)/"report", stable_backend_clock=opt_in)
                self.assertEqual({c.kwargs["stable_backend_clock"] for c in adapter.call_args_list}, {opt_in})
                self.assertIs(result["backend_clock_opt_in"], opt_in)
                self.assertIs(compare.read(Path(d)/"report/comparison.json")["backend_clock_opt_in"], opt_in)

    def test_never_overwrite_earned_result(self):
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaises(FileExistsError):
                compare.consume({}, out)

    def test_new_mode_cannot_silently_run_synthetic_control(self):
        for mode in ["captured-gap", "live-shadow", "off"]:
            with self.assertRaisesRegex(ValueError, "adapter"):
                compare.run_existing({"mode": mode}, Path("/unused"))

    def test_failed_arm_retains_invalid_reason(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/"result"
            with patch.object(compare, "admission_arm", side_effect=ValueError("backend failed")):
                with self.assertRaises(ValueError):
                    compare.consume({"baseline": "b", "candidate": "c"}, out)
            self.assertEqual(json.loads((out/"INVALID.json").read_text())["reason"], "backend failed")


if __name__ == "__main__":
    unittest.main()
