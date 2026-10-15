"""Mocked and portable-subprocess controls; never invokes xcrun or any Apple tool."""

import importlib.util
import io
import json
import os
import signal
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from contextlib import redirect_stderr

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/watch_failure_evidence.py"
SPEC = importlib.util.spec_from_file_location("watch_failure_evidence", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

WATCH = "11111111-2222-4333-8444-555555555555"
PHONE = "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE"
STOCK = "99999999-8888-4777-8666-555555555555"
OTHER_PHONE = "12121212-3434-4565-8787-909090909090"


def devices_json(*, watch_available=True):
    return json.dumps(
        {
            "devices": {
                "com.apple.CoreSimulator.SimRuntime.watchOS-11-0": [
                    {
                        "udid": WATCH.lower(),
                        "name": "codex-watch-ui-journey",
                        "state": "Booted",
                        "isAvailable": watch_available,
                        "availabilityError": (
                            None if watch_available else "runtime profile not found"
                        ),
                        "deviceTypeIdentifier": "watch-type",
                        "dataPath": "/private/should-not-be-copied",
                    },
                    {
                        "udid": STOCK,
                        "name": "Stock Watch",
                        "state": "Shutdown",
                        "isAvailable": True,
                    },
                ],
                "com.apple.CoreSimulator.SimRuntime.iOS-18-0": [
                    {
                        "udid": PHONE,
                        "name": "codex-watch-ui-companion",
                        "state": "Shutdown",
                        "isAvailable": True,
                    }
                ],
            }
        }
    ).encode()


def pairs_json():
    return json.dumps(
        {
            "pairs": {
                "PAIR-EXACT": {
                    "watch": {"udid": WATCH, "name": "w", "state": "Booted"},
                    "phone": {"udid": PHONE, "name": "p", "state": "Shutdown"},
                    "state": "(active, connected)",
                },
                "PAIR-STOCK": {
                    "watch": {"udid": STOCK, "name": "s", "state": "Shutdown"},
                    "phone": {"udid": OTHER_PHONE, "name": "o", "state": "Shutdown"},
                    "state": "(unpaired)",
                },
            }
        }
    ).encode()


class FakeRunner:
    def __init__(self, responses=None, clock=None, costs=None):
        self.calls = []
        self.responses = responses or {
            MODULE.DEVICES_COMMAND: (0, devices_json(), b""),
            MODULE.PAIRS_COMMAND: (0, pairs_json(), b""),
        }
        self.clock = clock
        self.costs = costs or {}

    def __call__(self, argv, timeout):
        self.calls.append((tuple(argv), timeout))
        if self.clock is not None:
            self.clock.now += self.costs.get(tuple(argv), 0.0)
        response = self.responses[tuple(argv)]
        if isinstance(response, BaseException):
            raise response
        return response


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class RefusingRunner:
    def __call__(self, argv, timeout):
        raise AssertionError(f"No RPC may run here: {argv}")


class Base(unittest.TestCase):
    def setUp(self):
        handlers = {
            sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)
        }
        self.addCleanup(self.restore_signal_handlers, handlers)
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.out = self.tmp / "out"
        self.logs = self.tmp / "logs"
        self.logs.mkdir()

    @staticmethod
    def restore_signal_handlers(handlers):
        for signum, handler in handlers.items():
            signal.signal(signum, handler)

    def tearDown(self):
        for path in self.tmp.rglob("*"):
            try:
                if not path.is_symlink():
                    path.chmod(0o700)
            except OSError:
                pass
        self._tmp.cleanup()

    def write_logs(
        self, host=b"host line\n", watch=b"watch line\n", phone=b"phone line\n"
    ):
        if host is not None:
            (self.logs / "CoreSimulator.log").write_bytes(host)
        for udid, body in ((WATCH, watch), (PHONE, phone)):
            if body is not None:
                (self.logs / udid).mkdir(exist_ok=True)
                (self.logs / udid / "system.log").write_bytes(body)

    def collect(self, watch=WATCH, phone=PHONE, runner=None, clock=None, exit_code=149):
        return MODULE.collect_failure(
            self.out,
            watch,
            phone,
            "preinstall",
            exit_code,
            "77cb03bb092475ce76d378565b7611a8815263f0",
            runner=runner if runner is not None else FakeRunner(),
            clock=clock or FakeClock(),
            log_root=self.logs,
        )

    def tail(self, evidence, role):
        return next(t for t in evidence["log_tails"] if t["role"] == role)


class PositiveExactPairTests(Base):
    def test_exact_pair_records_failure_identity_filtered_devices_pair_and_tails(self):
        self.write_logs()
        runner = FakeRunner()
        evidence = self.collect(runner=runner)
        on_disk = json.loads((self.out / "failure-evidence.json").read_text())
        self.assertEqual(on_disk, evidence)
        self.assertEqual(
            evidence["original_failure"],
            {
                "status": "unpaid",
                "phase": "preinstall",
                "exit_code": 149,
                "sha": "77cb03bb092475ce76d378565b7611a8815263f0",
            },
        )
        self.assertIs(evidence["test_receipt"], False)
        self.assertTrue(evidence["identity"]["complete"])
        self.assertEqual(evidence["devices"]["watch"]["udid"], WATCH.lower())
        self.assertEqual(evidence["devices"]["watch"]["state"], "Booted")
        self.assertEqual(evidence["devices"]["phone"]["state"], "Shutdown")
        self.assertNotIn("dataPath", evidence["devices"]["watch"])
        self.assertEqual(evidence["pairs"]["selected_pair"]["pair_id"], "PAIR-EXACT")
        self.assertEqual(evidence["pairs"]["exact_pair_count"], 1)
        self.assertEqual(evidence["pairs"]["pairs_with_only_one_device"], [])
        serialized = (self.out / "failure-evidence.json").read_text()
        for absent in (
            STOCK,
            OTHER_PHONE,
            "PAIR-STOCK",
            "Stock Watch",
            "PASS",
            "verdict",
        ):
            self.assertNotIn(absent, serialized)
        self.assertEqual(evidence["diagnostics_unavailable"], [])
        for role, body in (
            ("coresimulator", "host line\n"),
            ("watch-system", "watch line\n"),
            ("phone-system", "phone line\n"),
        ):
            record = self.tail(evidence, role)
            self.assertEqual(record["outcome"], "ok")
            self.assertEqual((self.out / record["output_file"]).read_text(), body)
            self.assertTrue(record["output_file"].endswith(".log"))
        self.assertEqual(
            self.tail(evidence, "watch-system")["source"],
            str(self.logs / WATCH / "system.log"),
        )

    def test_lowercase_ids_are_canonicalised_for_matching_and_exact_paths(self):
        self.write_logs()
        evidence = self.collect(watch=WATCH.lower(), phone=PHONE.lower())
        self.assertEqual(evidence["identity"]["watch_id"], WATCH)
        self.assertEqual(evidence["pairs"]["selected_pair"]["pair_id"], "PAIR-EXACT")
        self.assertEqual(self.tail(evidence, "phone-system")["outcome"], "ok")

    def test_pair_of_only_one_device_is_not_selected(self):
        pairs = json.dumps(
            {
                "pairs": {
                    "P": {
                        "watch": {"udid": WATCH},
                        "phone": {"udid": OTHER_PHONE},
                        "state": "(active, connected)",
                    }
                }
            }
        ).encode()
        runner = FakeRunner(
            {
                MODULE.DEVICES_COMMAND: (0, devices_json(), b""),
                MODULE.PAIRS_COMMAND: (0, pairs, b""),
            }
        )
        evidence = self.collect(runner=runner)
        self.assertIsNone(evidence["pairs"]["selected_pair"])
        self.assertEqual(evidence["pairs"]["exact_pair_count"], 0)
        self.assertEqual(
            evidence["pairs"]["pairs_with_only_one_device"][0]["pair_id"], "P"
        )


class IdentityGuardTests(Base):
    CASES = {
        "watch_missing": ("", PHONE, ["watch_id_missing"]),
        "phone_missing": (WATCH, "", ["phone_id_missing"]),
        "both_missing": ("", "", ["watch_id_missing", "phone_id_missing"]),
        "watch_not_uuid": ("../" + PHONE, PHONE, ["watch_id_not_uuid"]),
        "phone_braced": (WATCH, "{" + PHONE + "}", ["phone_id_not_uuid"]),
        "phone_unhyphenated": (WATCH, PHONE.replace("-", ""), ["phone_id_not_uuid"]),
        "nil": ("00000000-0000-0000-0000-000000000000", PHONE, ["watch_id_nil_uuid"]),
        "same_id": (WATCH, WATCH.lower(), ["ids_not_distinct"]),
    }

    def test_incomplete_identity_skips_every_rpc_and_device_tail(self):
        for name, (watch, phone, problems) in self.CASES.items():
            with self.subTest(name):
                self.write_logs()
                evidence = self.collect(
                    watch=watch, phone=phone, runner=RefusingRunner()
                )
                self.assertFalse(evidence["identity"]["complete"])
                self.assertEqual(evidence["identity"]["problems"], problems)
                self.assertEqual(evidence["rpc"]["skipped"], "missing_identity")
                self.assertEqual(evidence["rpc"]["calls"], [])
                self.assertIsNone(evidence["devices"])
                self.assertIsNone(evidence["pairs"])
                self.assertEqual(
                    [t["role"] for t in evidence["log_tails"]], ["coresimulator"]
                )
                self.assertEqual(self.tail(evidence, "coresimulator")["outcome"], "ok")
                self.assertFalse(
                    (self.out / "failure-evidence-watch-system.log").exists()
                )
                self.assertIn("simctl_devices", evidence["diagnostics_unavailable"])
                self.assertEqual(evidence["original_failure"]["exit_code"], 149)


class MissingFileAndModeTests(Base):
    def test_missing_files_are_recorded_unavailable_without_altering_failure(self):
        evidence = self.collect()
        for role in ("coresimulator", "watch-system", "phone-system"):
            self.assertEqual(self.tail(evidence, role)["outcome"], "missing")
            self.assertIn(f"log_{role}", evidence["diagnostics_unavailable"])
            self.assertNotIn("output_file", self.tail(evidence, role))
        self.assertEqual(evidence["original_failure"]["status"], "unpaid")
        self.assertEqual(
            sorted(p.name for p in self.out.iterdir()), ["failure-evidence.json"]
        )

    def test_symlink_directory_and_fifo_are_not_read(self):
        secret = self.tmp / "elsewhere.log"
        secret.write_text("must not be copied")
        (self.logs / "CoreSimulator.log").symlink_to(secret)
        (self.logs / WATCH / "system.log").mkdir(parents=True)
        (self.logs / PHONE).mkdir()
        os.mkfifo(self.logs / PHONE / "system.log")
        started = time.monotonic()
        evidence = self.collect()
        self.assertLess(time.monotonic() - started, 5)
        for role in ("coresimulator", "watch-system", "phone-system"):
            self.assertEqual(self.tail(evidence, role)["outcome"], "not_regular_file")
        self.assertNotIn(
            "must not be copied", "".join(p.read_text() for p in self.out.iterdir())
        )

    @unittest.skipIf(os.geteuid() == 0, "root ignores file modes")
    def test_permission_denied_is_recorded(self):
        self.write_logs()
        (self.logs / "CoreSimulator.log").chmod(0)
        (self.logs / WATCH).chmod(0)
        evidence = self.collect()
        self.assertEqual(
            self.tail(evidence, "coresimulator")["outcome"], "permission_denied"
        )
        self.assertEqual(
            self.tail(evidence, "watch-system")["outcome"], "permission_denied"
        )
        self.assertEqual(self.tail(evidence, "phone-system")["outcome"], "ok")

    def test_never_more_than_three_tails_and_no_other_file_is_read(self):
        self.write_logs()
        (self.logs / "other.log").write_text("not named")
        (self.logs / WATCH / "older.log").write_text("not named")
        evidence = self.collect()
        self.assertEqual(len(evidence["log_tails"]), MODULE.MAX_TAILS)
        written = "".join(p.read_text() for p in self.out.iterdir())
        self.assertNotIn("not named", written)


class TailCapTests(Base):
    def test_large_file_keeps_exactly_the_last_cap_bytes_and_source_is_untouched(self):
        body = b"".join(b"line %06d\n" % i for i in range(5000))
        self.assertGreater(len(body), MODULE.TAIL_BYTES)
        self.write_logs(host=body)
        source = self.logs / "CoreSimulator.log"
        os.utime(source, (1_000_000, 1_000_000))
        before = (source.stat().st_mode, source.stat().st_mtime, source.read_bytes())
        evidence = self.collect()
        record = self.tail(evidence, "coresimulator")
        self.assertEqual(record["bytes_read"], MODULE.TAIL_BYTES)
        self.assertEqual(record["file_size"], len(body))
        self.assertTrue(record["truncated"])
        self.assertEqual(
            (self.out / record["output_file"]).read_bytes(), body[-MODULE.TAIL_BYTES :]
        )
        self.assertEqual(
            (source.stat().st_mode, source.stat().st_mtime, source.read_bytes()), before
        )

    def test_small_file_is_whole_and_not_truncated(self):
        self.write_logs(host=b"short\n")
        record = self.tail(self.collect(), "coresimulator")
        self.assertEqual((record["bytes_read"], record["truncated"]), (6, False))

    def test_cut_inside_a_multibyte_character_still_decodes(self):
        body = b"x" * 10 + "é".encode() * MODULE.TAIL_BYTES + b"\n"
        self.assertEqual(
            (len(body) - MODULE.TAIL_BYTES - 10) % 2, 1
        )  # cut lands mid-character
        self.write_logs(host=body)
        record = self.tail(self.collect(), "coresimulator")
        self.assertEqual(record["outcome"], "ok")
        text = (self.out / record["output_file"]).read_text()
        self.assertTrue(set(text) <= {"é", "\n"})

    def test_invalid_utf8_is_encoding_unavailable(self):
        self.write_logs(watch=b"ok\n\xff\xfe broken\n")
        evidence = self.collect()
        self.assertEqual(
            self.tail(evidence, "watch-system")["outcome"], "encoding_error"
        )
        self.assertIn("log_watch-system", evidence["diagnostics_unavailable"])
        self.assertFalse((self.out / "failure-evidence-watch-system.log").exists())
        self.assertEqual(self.tail(evidence, "phone-system")["outcome"], "ok")


class ReadOnlyCommandTests(Base):
    def test_only_the_two_list_commands_run_once_each_in_order(self):
        runner = FakeRunner()
        self.collect(runner=runner)
        self.assertEqual(
            [argv for argv, _ in runner.calls],
            [MODULE.DEVICES_COMMAND, MODULE.PAIRS_COMMAND],
        )
        self.assertEqual(
            MODULE.READ_ONLY_COMMANDS,
            {
                ("xcrun", "simctl", "list", "devices", "--json"),
                ("xcrun", "simctl", "list", "pairs", "--json"),
            },
        )
        mutating = {
            "create",
            "boot",
            "pair",
            "install",
            "launch",
            "erase",
            "shutdown",
            "delete",
            "terminate",
            "spawn",
            "unpair",
            "kill",
        }
        for argv in MODULE.READ_ONLY_COMMANDS:
            self.assertFalse(mutating & set(argv))

    def test_call_refuses_anything_outside_the_read_only_set(self):
        for argv in (
            ("xcrun", "simctl", "boot", WATCH),
            ("xcrun", "simctl", "list", "--json"),
            (sys.executable, "-c", "pass"),
        ):
            with self.subTest(argv), self.assertRaises(ValueError):
                MODULE._call(argv, RefusingRunner(), FakeClock(), 1e9)


class RpcBoundTests(Base):
    def test_timeout_is_recorded_and_never_retried(self):
        runner = FakeRunner(
            {
                MODULE.DEVICES_COMMAND: subprocess.TimeoutExpired("xcrun", 2),
                MODULE.PAIRS_COMMAND: subprocess.TimeoutExpired("xcrun", 2),
            }
        )
        evidence = self.collect(runner=runner)
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(
            [c["outcome"] for c in evidence["rpc"]["calls"]], ["timeout", "timeout"]
        )
        self.assertEqual([c["attempts"] for c in evidence["rpc"]["calls"]], [1, 1])
        self.assertEqual(evidence["rpc"]["retries"], 0)
        self.assertIn("simctl_pairs", evidence["diagnostics_unavailable"])

    def test_each_call_is_bounded_and_both_share_one_budget(self):
        clock = FakeClock()
        runner = FakeRunner(clock=clock, costs={MODULE.DEVICES_COMMAND: 3.5})
        evidence = self.collect(runner=runner, clock=clock)
        (_, first), (_, second) = runner.calls
        self.assertEqual(first, MODULE.RPC_TIMEOUT_SECONDS)
        self.assertAlmostEqual(second, MODULE.RPC_BUDGET_SECONDS - 3.5)
        self.assertLessEqual(first, 2.0)
        self.assertLessEqual(MODULE.RPC_BUDGET_SECONDS, 4.0)
        self.assertEqual(evidence["rpc"]["calls"][1]["outcome"], "ok")

    def test_exhausted_budget_skips_the_second_call(self):
        clock = FakeClock()
        runner = FakeRunner(clock=clock, costs={MODULE.DEVICES_COMMAND: 4.0})
        evidence = self.collect(runner=runner, clock=clock)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(evidence["rpc"]["calls"][1]["outcome"], "budget_exhausted")
        self.assertEqual(evidence["rpc"]["calls"][1]["attempts"], 0)
        self.assertIn("simctl_pairs", evidence["diagnostics_unavailable"])

    def test_default_spawn_kills_its_own_session_at_the_timeout(self):
        marker = self.tmp / "survived"
        grandchild = f"import time,pathlib;time.sleep(1.5);pathlib.Path({str(marker)!r}).write_text('x')"
        code = f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{grandchild!r}]);time.sleep(30)"
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            MODULE.spawn_bounded((sys.executable, "-c", code), 0.4)
        self.assertLess(time.monotonic() - started, 3)
        time.sleep(2)
        self.assertFalse(
            marker.exists(), "descendant in the helper's session outlived the bound"
        )

    def test_default_spawn_returns_status_and_output(self):
        status, out, err = MODULE.spawn_bounded(
            (
                sys.executable,
                "-c",
                "import sys;print('o');sys.stderr.write('e');sys.exit(5)",
            ),
            5,
        )
        self.assertEqual((status, out.strip(), err), (5, b"o", b"e"))

    def test_interruption_closes_pipes_and_stops_only_the_private_rpc_group(self):
        process = mock.Mock(pid=345678)
        process.communicate.side_effect = KeyboardInterrupt()
        with mock.patch.object(
            MODULE.subprocess, "Popen", return_value=process
        ), mock.patch.object(MODULE.os, "killpg") as stop:
            with self.assertRaises(KeyboardInterrupt):
                MODULE.spawn_bounded(MODULE.DEVICES_COMMAND, 2)
        stop.assert_called_once_with(process.pid, signal.SIGKILL)
        process.stdout.close.assert_called_once()
        process.stderr.close.assert_called_once()
        process.wait.assert_called_once()
        self.assertLessEqual(process.wait.call_args.kwargs["timeout"], 2)

    def test_sigterm_stops_the_helpers_private_rpc_child(self):
        pid_file = self.tmp / "rpc-child.pid"
        child = (
            "import os,time;from pathlib import Path;"
            f"Path({str(pid_file)!r}).write_text(str(os.getpid()));time.sleep(30)"
        )
        script = (
            "import importlib.util,sys;"
            f"s=importlib.util.spec_from_file_location('helper',{str(SCRIPT)!r});"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
            "getattr(m,'install_interrupt_handlers',lambda:None)();"
            f"m.spawn_bounded([sys.executable,'-c',{child!r}],20)"
        )
        helper = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            until = time.monotonic() + 5
            while (
                not pid_file.exists()
                and helper.poll() is None
                and time.monotonic() < until
            ):
                time.sleep(0.01)
            self.assertTrue(
                pid_file.exists(), "fixture RPC child must start before SIGTERM"
            )
            helper.terminate()  # Only this test's helper process receives SIGTERM.
            helper.communicate(timeout=3)
            observed = subprocess.run(
                ["ps", "-p", pid_file.read_text(), "-o", "stat="],
                capture_output=True,
                text=True,
                timeout=2,
            )
            self.assertFalse(
                observed.stdout.strip(), "private RPC child survived helper SIGTERM"
            )
        finally:
            if helper.poll() is None:
                helper.kill()
                helper.communicate(timeout=3)
            if pid_file.exists():
                try:
                    os.killpg(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_cli_entry_installs_interruption_handlers(self):
        with mock.patch.object(MODULE, "install_interrupt_handlers") as install:
            with redirect_stderr(io.StringIO()):
                MODULE.main(
                    [
                        "--output-dir",
                        str(self.out),
                        "--watch-id",
                        "",
                        "--phone-id",
                        "",
                        "--phase",
                        "fixture",
                        "--exit-code",
                        "149",
                        "--sha",
                        "abc",
                    ],
                    runner=RefusingRunner(),
                    log_root=self.logs,
                )
        install.assert_called_once()

    def test_timeout_cleanup_uses_remaining_bound_and_does_not_wait_for_pipe_eof(self):
        process = mock.Mock(pid=345678)
        process.communicate.side_effect = subprocess.TimeoutExpired("fixture", 2)
        with mock.patch.object(
            MODULE.subprocess, "Popen", return_value=process
        ), mock.patch.object(MODULE.os, "killpg"), mock.patch.object(
            MODULE.time, "monotonic", side_effect=[10, 10.05, 11.95]
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                MODULE.spawn_bounded(MODULE.DEVICES_COMMAND, 2)
        self.assertEqual(process.communicate.call_count, 1)
        self.assertAlmostEqual(process.wait.call_args.kwargs["timeout"], 0.05)

    def test_escaped_pipe_holder_does_not_add_a_second_cleanup_budget(self):
        pid_path = self.tmp / "escaped.pid"
        escaped = (
            "import os,pathlib,time;"
            f"pathlib.Path({str(pid_path)!r}).write_text(str(os.getpid()));time.sleep(30)"
        )
        command = (
            "import subprocess,sys,time;"
            f"subprocess.Popen([sys.executable,'-c',{escaped!r}],start_new_session=True);time.sleep(30)"
        )
        started = time.monotonic()
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                MODULE.spawn_bounded((sys.executable, "-c", command), 0.4)
            self.assertLess(time.monotonic() - started, 0.9)
        finally:
            # Only this test's explicitly recorded escaped session is stopped.
            if pid_path.exists():
                try:
                    os.killpg(int(pid_path.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass


class ToolFailureTests(Base):
    def test_malformed_nonzero_missing_tool_and_unavailable_device(self):
        cases = {
            "malformed": ((0, b"{not json", b""), "malformed_json"),
            "not_object": ((0, b"[]", b""), "malformed_json"),
            "wrong_shape": ((0, b'{"devices": []}', b""), "malformed_json"),
            "nonzero": (
                (72, b"", b"x" * 5000 + b"CoreSimulatorService connection invalid"),
                "nonzero_exit",
            ),
            "no_xcrun": (FileNotFoundError(2, "No such file", "xcrun"), "unavailable"),
        }
        for name, (response, outcome) in cases.items():
            with self.subTest(name):
                runner = FakeRunner(
                    {
                        MODULE.DEVICES_COMMAND: response,
                        MODULE.PAIRS_COMMAND: (0, pairs_json(), b""),
                    }
                )
                evidence = self.collect(runner=runner)
                call = evidence["rpc"]["calls"][0]
                self.assertEqual(call["outcome"], outcome)
                self.assertIn("simctl_devices", evidence["diagnostics_unavailable"])
                self.assertEqual(evidence["rpc"]["calls"][1]["outcome"], "ok")
                self.assertEqual(evidence["original_failure"]["exit_code"], 149)
                if name == "nonzero":
                    self.assertEqual(
                        len(runner.calls), 2, "Nonzero RPC must not be retried"
                    )
                    self.assertEqual(call["returncode"], 72)
                    self.assertEqual(len(call["stderr_tail"]), MODULE.STDERR_BYTES)
                    self.assertTrue(call["stderr_tail"].endswith("connection invalid"))

    def test_malformed_pairs_shape_is_unavailable(self):
        runner = FakeRunner(
            {
                MODULE.DEVICES_COMMAND: (0, devices_json(), b""),
                MODULE.PAIRS_COMMAND: (0, b'{"pairs": []}', b""),
            }
        )
        evidence = self.collect(runner=runner)
        self.assertEqual(evidence["rpc"]["calls"][1]["outcome"], "malformed_json")
        self.assertIn("simctl_pairs", evidence["diagnostics_unavailable"])

    def test_unavailable_and_absent_devices_are_recorded_as_listed(self):
        devices = json.dumps(
            {
                "devices": {
                    "r": [
                        {
                            "udid": WATCH,
                            "isAvailable": False,
                            "availabilityError": "runtime profile not found",
                        }
                    ]
                }
            }
        ).encode()
        runner = FakeRunner(
            {
                MODULE.DEVICES_COMMAND: (0, devices, b""),
                MODULE.PAIRS_COMMAND: (0, b'{"pairs": {}}', b""),
            }
        )
        evidence = self.collect(runner=runner)
        self.assertEqual(evidence["devices"]["watch"]["isAvailable"], False)
        self.assertEqual(
            evidence["devices"]["watch"]["availabilityError"],
            "runtime profile not found",
        )
        self.assertEqual(evidence["devices"]["phone"], {"found": False})
        self.assertIsNone(evidence["pairs"]["selected_pair"])


class WriteErrorTests(Base):
    def test_unwritable_output_raises_write_error_and_leaves_no_pending_file(self):
        blocker = self.tmp / "file"
        blocker.write_text("x")
        with self.assertRaises(MODULE.WriteError):
            MODULE.collect_failure(
                blocker / "out",
                WATCH,
                PHONE,
                "p",
                149,
                "s",
                runner=FakeRunner(),
                clock=FakeClock(),
                log_root=self.logs,
            )
        self.out.mkdir()
        (self.out / "failure-evidence.json").mkdir()
        with self.assertRaises(MODULE.WriteError):
            self.collect()
        self.assertEqual(
            [p.name for p in self.out.iterdir() if p.name.endswith(".pending")], []
        )

    def test_tail_write_error_is_recorded_and_evidence_still_written(self):
        self.write_logs()
        self.out.mkdir()
        (self.out / "failure-evidence-watch-system.log").mkdir()
        evidence = self.collect()
        self.assertEqual(self.tail(evidence, "watch-system")["outcome"], "write_error")
        self.assertIn("log_watch-system", evidence["diagnostics_unavailable"])
        self.assertTrue((self.out / "failure-evidence.json").is_file())

    def test_cli_reports_write_error_with_its_own_status(self):
        blocker = self.tmp / "file"
        blocker.write_text("x")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            status = MODULE.main(
                [
                    "--output-dir",
                    str(blocker / "o"),
                    "--watch-id",
                    WATCH,
                    "--phone-id",
                    PHONE,
                    "--phase",
                    "p",
                    "--exit-code",
                    "149",
                    "--sha",
                    "s",
                ],
                runner=FakeRunner(),
                log_root=self.logs,
            )
        self.assertEqual(status, 3)
        self.assertIn("not written", stderr.getvalue())


class FailureIdentityTests(Base):
    def test_original_exit_is_preserved_and_never_becomes_the_helper_status(self):
        for code in (1, 124, 149, 405, -9):
            with self.subTest(code):
                with redirect_stderr(io.StringIO()):
                    status = MODULE.main(
                        [
                            "--output-dir",
                            str(self.out),
                            "--watch-id",
                            WATCH,
                            "--phone-id",
                            PHONE,
                            "--phase",
                            "preinstall",
                            "--exit-code",
                            str(code),
                            "--sha",
                            "abc",
                        ],
                        runner=FakeRunner(),
                        log_root=self.logs,
                    )
                self.assertEqual(status, 0)
                record = json.loads((self.out / "failure-evidence.json").read_text())
                self.assertEqual(record["original_failure"]["exit_code"], code)
                self.assertEqual(record["original_failure"]["status"], "unpaid")

    def test_zero_or_unusable_failure_identity_is_refused(self):
        for kwargs in (
            {"exit_code": 0},
            {"exit_code": True},
            {"exit_code": "149"},
            {"phase": "  "},
            {"sha": ""},
        ):
            args = dict(exit_code=149, phase="p", sha="s")
            args.update(kwargs)
            with self.subTest(kwargs), self.assertRaises(ValueError):
                MODULE.collect_failure(
                    self.out,
                    WATCH,
                    PHONE,
                    args["phase"],
                    args["exit_code"],
                    args["sha"],
                    runner=RefusingRunner(),
                    log_root=self.logs,
                )
        self.assertFalse(self.out.exists())

    def test_isolated_cli_subprocess_with_empty_ids_runs_no_tool(self):
        host_log = self.logs / "CoreSimulator.log"
        host_log.parent.mkdir(parents=True, exist_ok=True)
        host_log.write_text("service line\n")
        env = dict(os.environ, PATH="")
        launch = [
            sys.executable,
            "-c",
            "import importlib.util,sys;from pathlib import Path;"
            "s=importlib.util.spec_from_file_location('helper',sys.argv[1]);"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
            "raise SystemExit(m.main(sys.argv[3:],log_root=Path(sys.argv[2])))",
            str(SCRIPT),
            str(self.logs),
        ]
        result = subprocess.run(
            [
                *launch,
                "--output-dir",
                str(self.out),
                "--watch-id",
                "",
                "--phone-id",
                "",
                "--phase",
                "preinstall",
                "--exit-code",
                "149",
                "--sha",
                "77cb03bb09",
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        record = json.loads((self.out / "failure-evidence.json").read_text())
        self.assertEqual(record["rpc"]["skipped"], "missing_identity")
        self.assertEqual(
            (self.out / "failure-evidence-coresimulator.log").read_text(),
            "service line\n",
        )
        for bad in (["--exit-code", "0"], ["--exit-code", "x"]):
            argv = [
                *launch,
                "--output-dir",
                str(self.out),
                "--watch-id",
                "",
                "--phone-id",
                "",
                "--phase",
                "p",
                "--sha",
                "s",
            ] + bad
            refused = subprocess.run(
                argv, capture_output=True, text=True, env=env, timeout=30
            )
            self.assertEqual(refused.returncode, 2, refused.stderr)

    def test_outputs_match_the_existing_preparation_upload_globs(self):
        self.write_logs()
        self.collect()
        for path in self.out.iterdir():
            self.assertIn(path.suffix, {".json", ".log"})
            self.assertTrue(stat.S_ISREG(path.stat().st_mode))


if __name__ == "__main__":
    unittest.main()
