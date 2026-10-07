"""A full Watch verdict cannot be assembled from partial or mixed-source runs."""

import ast
import subprocess
import importlib.util
import json
import os
import shlex
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "watch_ui_shards", ROOT / "tools/watch_ui_shards.py"
)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class WatchUIShardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.groups = gate.manifest()
        self.sha = "a" * 40
        for index, (shard, cases) in enumerate(self.groups.items()):
            part = self.root / shard
            part.mkdir()
            rows = [
                f"Test Case '-[BainLuckWatchUITests.{case.replace('/', ' ')}]' passed (1.0 seconds)."
                for case in cases
            ]
            rows += [
                "Test Suite 'Selected tests' passed at now.",
                f" Executed {len(cases)} tests, with 0 failures (0 unexpected)",
                "** TEST EXECUTE SUCCEEDED **",
            ]
            (part / "tests.log").write_text("\n".join(rows))
            (part / "test-exit.txt").write_text("0")
            (part / "source.txt").write_text(self.sha)
            (part / "destination.txt").write_text(f"watch-{index}")
            (part / "phone-destination.txt").write_text(f"phone-{index}")
            (part / "simulator-widget-signing.json").write_text(
                json.dumps({"sha": self.sha, "verdict": "PASS"})
            )
            self.save_receipt(shard)

    def save_receipt(self, shard):
        part = self.root / shard
        receipt = gate.shard_receipt(part, shard, self.sha, 0, self.groups)
        (part / "receipt.json").write_text(json.dumps(receipt))

    def verify(self):
        return gate.aggregate(self.root, self.sha, self.groups, verify_markers=False)

    def test_complete_distinct_pairs_cover_all_36_debug_cases(self):
        self.assertEqual(self.verify()["tests"], 36)
        self.assertEqual(self.groups["corner"], ["WidgetTapJourneyTests/testActualCornerSavedReadingAndTap"])
        self.assertEqual(len(self.groups["readings"]), 15)
        self.assertEqual(len(self.groups["navigation"]), 6)
        self.assertEqual(len(self.groups["controls"]), 8)
        self.assertEqual(len(self.groups["widgets"]), 6)

    def test_preparation_builds_selected_architecture_in_fresh_runs(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        setup = "RUN=" + harness.split("RUN=", 1)[1].split("RESULT=", 1)[0]
        builds = (
            "XCODE_ARGS=("
            + harness.split("XCODE_ARGS=(", 1)[1].split("# Give the system host", 1)[0]
        )
        record = self.root / "build-commands.jsonl"
        capture = (
            "import json,os,sys; "
            "open(os.environ['RECORD'], 'a').write(json.dumps(sys.argv[1:])+'\\n')"
        )
        shell = (
            "set -eu\n"
            "xcodebuild() { "
            + shlex.quote(sys.executable)
            + " -c "
            + shlex.quote(capture)
            + ' "$@"; }\n'
            + setup
            + builds
        )
        environment = dict(
            os.environ,
            ROOT=str(self.root),
            OUT=str(self.root),
            RECORD=str(record),
            TEST_UDID="owned-watch",
            PHONE_UDID="owned-phone",
            SIM_ARCH="arm64",
        )
        roots = []
        for _ in range(2):
            record.write_text("")
            subprocess.run(["bash", "-c", shell], env=environment, check=True)
            calls = [json.loads(line) for line in record.read_text().splitlines()]
            self.assertEqual(
                [call[0] for call in calls], ["build-for-testing", "build"]
            )
            derived = [call[call.index("-derivedDataPath") + 1] for call in calls]
            for call in calls:
                self.assertEqual(call.count("ARCHS=arm64"), 1)
            roots.append(derived)
            self.assertTrue(Path(derived[0]).parent.is_dir())
        self.assertNotEqual(
            roots[0], roots[1], "New runs must never reuse old products"
        )

    def test_missing_failed_or_wrong_source_shard_is_unpaid(self):
        path = self.root / "readings/receipt.json"
        original = path.read_text()
        for mutation in (
            {"verdict": "UNPAID"},
            {"sha": "b" * 40},
            {"shard": "navigation"},
        ):
            with self.subTest(mutation=mutation):
                receipt = json.loads(original)
                receipt.update(mutation)
                path.write_text(json.dumps(receipt))
                with self.assertRaises(ValueError):
                    self.verify()
        path.unlink()
        with self.assertRaises(OSError):
            self.verify()

    def test_duplicate_missing_failed_skipped_or_interrupted_execution_is_unpaid(self):
        part = self.root / "readings"
        log = (part / "tests.log").read_text()
        first = log.splitlines()[0]
        for broken in (
            log + "\n" + first,
            log.replace(first, ""),
            log.replace("passed (", "failed ("),
            log.replace("passed (", "skipped ("),
            log.replace("** TEST EXECUTE SUCCEEDED **", ""),
            log + "\n** TEST EXECUTE FAILED **",
        ):
            with self.subTest(broken=broken):
                with self.assertRaises(ValueError):
                    gate.completed_cases(broken, 0, self.groups["readings"])
        with self.assertRaises(ValueError):
            gate.completed_cases(log, 65, self.groups["readings"])

    def test_retained_log_or_signature_cannot_disagree_with_receipt(self):
        part = self.root / "readings"
        (part / "simulator-widget-signing.json").write_text(
            json.dumps({"sha": self.sha, "verdict": "UNPAID"})
        )
        with self.assertRaises(ValueError):
            self.verify()

    def test_reused_pair_cannot_claim_isolation(self):
        (self.root / "readings/destination.txt").write_text(
            (self.root / "navigation/destination.txt").read_text()
        )
        self.save_receipt("readings")
        with self.assertRaises(ValueError):
            self.verify()

    def test_aggregate_requires_existing_markers_and_consent_receipt(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        code = ast.parse(
            harness.split("<<'PYVERIFY'\n", 1)[1].split("\nPYVERIFY", 1)[0]
        )
        markers = next(
            ast.literal_eval(node.iter)
            for node in ast.walk(code)
            if isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and node.target.id == "marker"
        )
        path = self.root / "readings/tests.log"
        original = path.read_text()
        rows = [
            *markers,
            "WATCH_UI_ACTUAL_CORNER_SAVED=PASS",
            "WATCH_UI_CORNER_FALLBACK=PASS",
            "WATCH_UI_CORNER_MAIN_FIT=PASS",
            "WATCH_UI_STRESS_TYPE=accessibility5",
            "WATCH_UI_STANDARD_TYPE=xLarge",
            "WATCH_UI_DISCOVERIES_POLISH_STANDARD=PASS",
            "WATCH_UI_DISCOVERIES_POLISH_LARGE=PASS",
            "WATCH_UI_DISCOVERIES_POLISH_SELECTED=PASS",
            "WATCH_UI_DIAGNOSTICS_STANDARD=PASS",
            "WATCH_UI_DIAGNOSTICS_LARGE=PASS",
        ]
        complete = original + "\n" + "\n".join(rows)
        path.write_text(complete)
        self.assertEqual(gate.aggregate(self.root, self.sha, self.groups)["tests"], 36)
        for marker in (
            "WATCH_UI_ACTUAL_CORNER_SAVED=PASS",
            "WATCH_UI_CORNER_FALLBACK=PASS",
            "WATCH_UI_CORNER_MAIN_FIT=PASS",
            "WATCH_UI_DISCOVERIES_POLISH_STANDARD=PASS",
            "WATCH_UI_RECTANGULAR_ACTUAL_TYPED=PASS",
            "WATCH_UI_RECTANGULAR_MONOCHROME=PASS",
            "WATCH_UI_GAME_UPDATING_LARGE=PASS",
            "WATCH_UI_DIAGNOSTICS_LARGE=PASS",
        ):
            with self.subTest(marker=marker):
                path.write_text(complete.replace(marker, ""))
                with self.assertRaises(subprocess.CalledProcessError):
                    gate.aggregate(self.root, self.sha, self.groups)
        path.write_text(complete + "\nWATCH_UI_DIAGNOSTICS_LARGE=PASS")
        with self.assertRaises(subprocess.CalledProcessError):
            gate.aggregate(self.root, self.sha, self.groups)

    def test_workflow_runs_every_shard_and_always_checks_aggregate(self):
        import re

        workflow = (ROOT / ".github/workflows/watch-mvp.yml").read_text()
        split = workflow.split("  watch-ui-journey:", 1)[1].split(
            "  watch-ui-complete:", 1
        )[0]
        matrix = re.search(r"shard: \[(.*?)\]", split).group(1)
        self.assertEqual(set(matrix.split(", ")), set(self.groups))
        self.assertIn("fail-fast: false", split)
        self.assertIn("timeout-minutes: 60", split)
        self.assertIn("group: watch-ui-${{ matrix.shard }}-", split)
        complete = workflow.split("  watch-ui-complete:", 1)[1].split(
            "  companion-archive:", 1
        )[0]
        self.assertIn("needs: watch-ui-journey", complete)
        self.assertIn("if: always()", complete)
        downloads = set(re.findall(r"name: (watch-ui-journey-\w+)", complete))
        self.assertEqual(
            downloads, {f"watch-ui-journey-{shard}" for shard in self.groups}
        )

    def test_actual_corner_cannot_share_a_pair_with_other_cases(self):
        tools = self.root / "tools"
        source = self.root / "ios/Bain Luck/BainLuckWatchUITests"
        tools.mkdir()
        source.mkdir(parents=True)
        groups = {name: list(cases) for name, cases in self.groups.items()}
        groups["corner"].append(groups["readings"].pop())
        (tools / "watch_ui_cases.json").write_text(json.dumps(groups))
        suites = {}
        for cases in groups.values():
            for case in cases:
                suite, method = case.split("/")
                suites.setdefault(suite, []).append(f"func {method}() {{}}")
        for suite, methods in suites.items():
            (source / f"{suite}.swift").write_text("\n".join(methods))
        with self.assertRaisesRegex(ValueError, "own fresh pair"):
            gate.manifest(self.root)

    def test_manifest_cannot_omit_or_duplicate_a_future_source_case(self):
        tools = self.root / "tools"
        source = self.root / "ios/Bain Luck/BainLuckWatchUITests"
        tools.mkdir()
        source.mkdir(parents=True)
        readings = self.groups["readings"][0]
        (tools / "watch_ui_cases.json").write_text(
            json.dumps(
                {
                    "corner": self.groups["corner"],
                    "readings": [readings],
                    "navigation": [],
                    "controls": [],
                    "widgets": [],
                }
            )
        )
        (source / "WidgetTapJourneyTests.swift").write_text(
            "#if DEBUG\nfunc testActualCornerSavedReadingAndTap() {}\nfunc testNewCoverage() {}\n#endif"
        )
        with self.assertRaises(ValueError):
            gate.manifest(self.root)
        (tools / "watch_ui_cases.json").write_text(
            json.dumps(
                {
                    "corner": self.groups["corner"],
                    "readings": [readings],
                    "navigation": [readings],
                    "controls": [],
                    "widgets": [],
                }
            )
        )
        with self.assertRaises(ValueError):
            gate.manifest(self.root)


if __name__ == "__main__":
    unittest.main()
