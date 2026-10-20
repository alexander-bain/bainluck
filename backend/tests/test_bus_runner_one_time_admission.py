"""#1778 rider: one-time input queued during the bus's hourly wait is admitted promptly.

Measured 2026-10-20: the measurement bus sat in `sleep 3150` (drained bucket) while
one-time Measurement038 waited unread in its inbox, because the drained and
abandoned branches slept straight to the hour. These tests run the REAL
bus-runner.sh loop on a scratch tree with a fake clock: `sleep` advances the clock
instead of waiting, and lane_control / the collector / codex are fakes that only
record what they were asked to do. No real sleeps, network, model or Apple process.
"""

import os
import signal
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUS = ROOT / "bus-runner.sh"

HOUR = 1792490400  # 2026-10-20 10:00:00 UTC
T0 = HOUR + 20 * 60  # the run starts at 10:20:00, bucket 20261020-10
DEADLINE = HOUR + 3600  # 11:00:00 UTC, the original bucket boundary
B10 = "20261020-10"
MISSIONS = ("FRESH", "CLAIMS", "THRU-BASELINE")
ONE_TIME_MARK = "ONE-TIME-038 diagnosis brief"

# The fakes share three files in the scratch root: `clock` (epoch seconds),
# `calls.log` (one line per observed action, stamped with the clock) and
# `events` (scheduled scratch-tree changes the fake sleep applies as the clock
# passes them: "<epoch> touch|rm <path>").
FAKE_SLEEP = """\
#!/usr/bin/env python3
import os, signal, sys
root = os.environ["FAKE_ROOT"]
clock = int(open(f"{root}/clock").read()) + int(float(sys.argv[1]))
open(f"{root}/clock", "w").write(str(clock))
open(f"{root}/calls.log", "a").write(f"{clock} sleep {sys.argv[1]}\\n")
keep = []
for line in open(f"{root}/events").read().splitlines():
    at, verb, path = line.split(" ", 2)
    if int(at) > clock:
        keep.append(line)
    elif verb == "touch":
        open(path, "w").write(os.environ.get("FAKE_ITEM", ""))
    else:
        os.path.exists(path) and os.remove(path)
open(f"{root}/events", "w").write("".join(l + "\\n" for l in keep))
if clock >= int(os.environ["FAKE_STOP"]):
    # The runner's pid, not getppid(): `env python3` may run through a shim.
    os.kill(int(open(f"{root}/bus.pid").read()), signal.SIGTERM)
"""
FAKE_DATE = """\
#!/usr/bin/env python3
import os, sys, time
clock = int(open(os.environ["FAKE_ROOT"] + "/clock").read())
fmt = [a for a in sys.argv[1:] if a.startswith("+")][0][1:]
print(str(clock) if fmt == "%s" else time.strftime(fmt, time.gmtime(clock)))
"""
FAKE_CODEX = """\
#!/usr/bin/env python3
import os, sys
root = os.environ["FAKE_ROOT"]
clock = open(f"{root}/clock").read().strip()
kind = "one-time" if sys.argv[-1].startswith("ONE-TIME") else "mission"
open(f"{root}/calls.log", "a").write(f"{clock} codex {kind}\\n")
rc = f"{root}/codex_rc"
sys.exit(int(open(rc).read()) if os.path.exists(rc) else 0)
"""
# Mirrors scripts/lane_control.py's contract for the verbs the bus uses:
# check -> 1 when paused; run -> 75 when refused (capacity), else the command's rc.
FAKE_CONTROL = """\
import os, subprocess, sys
root = os.environ["FAKE_ROOT"]
clock = open(f"{root}/clock").read().strip()
verb, lane, args = sys.argv[1], sys.argv[2], sys.argv[3:]
line = f"{clock} control {verb} {lane} {' '.join(args)[:40]}".rstrip()
open(f"{root}/calls.log", "a").write(line + "\\n")
if verb == "check":
    sys.exit(1 if os.path.exists(f"{root}/paused") else 0)
if verb == "run":
    if os.path.exists(f"{root}/capacity_refused"):
        sys.exit(75)
    sys.exit(subprocess.call(args[1:]))
"""
FAKE_COLLECTOR = """\
import os
root = os.environ["FAKE_ROOT"]
clock = open(f"{root}/clock").read().strip()
open(f"{root}/calls.log", "a").write(f"{clock} collector\\n")
"""


class Rig:
    def __init__(self, tmp_path):
        self.root = tmp_path
        self.home = tmp_path / "home"
        self.handoff = tmp_path / "handoff"
        self.inbox = self.handoff / "runner-inbox" / "measurement"
        self.item = self.inbox / "038-measurement-diagnosis.md"
        scripts = self.home / "bainluck" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "lane_control.py").write_text(FAKE_CONTROL)
        (scripts / "lane_monitor.py").write_text(FAKE_COLLECTOR)
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        for name, body in (("sleep", FAKE_SLEEP), ("date", FAKE_DATE), ("codex", FAKE_CODEX)):
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        self.inbox.mkdir(parents=True)
        (self.handoff / "CODEX-QUEUE.md").write_text("queue\n")
        (tmp_path / "clock").write_text(str(T0))
        (tmp_path / "calls.log").write_text("")
        (tmp_path / "events").write_text("")

    def bank(self, bucket):
        for mission in MISSIONS:
            (self.handoff / f"ARTIFACT-M-R-{mission}-{bucket}.md").write_text("banked")

    def at(self, epoch, verb, path):
        with open(self.root / "events", "a") as f:
            f.write(f"{epoch} {verb} {path}\n")

    def run(self, stop):
        env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.home),
            "BUS_HANDOFF": str(self.handoff),
            "LANE_LEASE_HELD": "measurement",  # the lease exec is not under test
            "FAKE_ROOT": str(self.root),
            "FAKE_STOP": str(stop),
            "FAKE_ITEM": ONE_TIME_MARK,
        }
        proc = subprocess.Popen(
            ["/bin/bash", str(BUS)], env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        # Written before the runner's first sleep can read it: the loop starts
        # lane_control and the collector (two python starts) before any sleep.
        (self.root / "bus.pid").write_text(str(proc.pid))
        try:
            stdout, stderr = proc.communicate(timeout=60)
        finally:
            proc.kill()
        result = subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
        # The fake sleep ends the endless loop with SIGTERM at FAKE_STOP; any other
        # exit is the runner itself failing, not the rig.
        assert result.returncode in (-signal.SIGTERM, 128 + signal.SIGTERM), (
            result.returncode, result.stdout, result.stderr)
        self.stdout = result.stdout
        self.calls = [
            (int(line.split(" ", 1)[0]), line.split(" ", 1)[1])
            for line in (self.root / "calls.log").read_text().splitlines()
        ]
        return self

    def when(self, prefix):
        return [t for t, what in self.calls if what.startswith(prefix)]


def test_one_time_item_queued_during_a_drained_wait_is_admitted_within_one_slice(tmp_path):
    rig = Rig(tmp_path)
    rig.bank(B10)
    arrival = T0 + 130
    rig.at(arrival, "touch", rig.item)
    rig.run(stop=DEADLINE + 1)

    one_time = rig.when("codex one-time")
    assert len(one_time) == 1, rig.calls
    # Before #1778 this item waited until 11:00; now it waits at most one 60 s slice.
    assert arrival <= one_time[0] <= arrival + 60, rig.calls
    assert not rig.item.exists() and Path(f"{rig.item}.consumed").exists()
    # Admission went through the guarded path: check, then run, for this item.
    check_before = [t for t in rig.when("control check") if t <= one_time[0]]
    assert check_before and check_before[-1] == one_time[0], rig.calls
    assert "back to normal admission" in rig.stdout
    # The bucket boundary did not move: the next hour's missions start at 11:00:00
    # exactly, not 40 minutes after the early wake.
    assert rig.when("codex mission") == [DEADLINE], rig.calls


def test_empty_inbox_waits_to_the_original_deadline_and_runs_nothing_meanwhile(tmp_path):
    rig = Rig(tmp_path)
    rig.bank(B10)
    rig.run(stop=DEADLINE + 1)

    during = [(t, what) for t, what in rig.calls if t < DEADLINE and not what.startswith("sleep")]
    # One pass at 10:20 (check + collector), then nothing but sleeps until 11:00.
    assert [what for _, what in during] == ["control check measurement", "collector"], rig.calls
    naps = [int(what.split()[1]) for t, what in rig.calls if what.startswith("sleep") and t <= DEADLINE]
    assert sum(naps) == DEADLINE - T0 and max(naps) <= 60, naps
    assert rig.when("collector")[1] == DEADLINE and rig.when("codex mission") == [DEADLINE]


def test_abandoned_bucket_stays_abandoned_while_the_one_time_item_runs(tmp_path):
    rig = Rig(tmp_path)
    (rig.handoff / ".bus-runner-attempts").write_text(f"{B10} 3\n")
    arrival = T0 + 130
    rig.at(arrival, "touch", rig.item)
    rig.run(stop=DEADLINE - 60)

    assert len(rig.when("codex one-time")) == 1 and rig.when("codex one-time")[0] <= arrival + 60
    # The failed recurring missions are NOT retried by the early wake ...
    assert rig.when("codex mission") == [], rig.calls
    # ... their strike count is untouched, and the loop went straight back to the
    # abandoned branch (banner printed before and after the one-time item).
    assert (rig.handoff / ".bus-runner-attempts").read_text().strip() == f"{B10} 3"
    assert rig.stdout.count(f"ABANDONING bucket {B10}") == 2, rig.stdout


def test_pause_still_refuses_an_item_that_woke_the_wait(tmp_path):
    rig = Rig(tmp_path)
    rig.bank(B10)
    rig.at(T0 + 100, "touch", tmp_path / "paused")
    rig.at(T0 + 130, "touch", rig.item)
    rig.run(stop=T0 + 900)

    # The wake happened (the loop is re-checking every 60 s), but lane_control's
    # pause refuses admission: nothing ran and the item is preserved.
    assert len([t for t in rig.when("control check") if t > T0 + 130]) >= 5, rig.calls
    assert rig.when("control run") == [] and rig.when("codex") == [], rig.calls
    assert rig.item.exists()


def test_capacity_refusal_and_attempt_accounting_stay_on_the_outer_path(tmp_path):
    rig = Rig(tmp_path)
    rig.bank(B10)
    rig.at(T0 + 100, "touch", tmp_path / "capacity_refused")
    rig.at(T0 + 130, "touch", rig.item)
    rig.at(T0 + 400, "rm", tmp_path / "capacity_refused")
    (tmp_path / "codex_rc").write_text("1")
    rig.run(stop=DEADLINE - 60)

    runs = rig.when("control run")
    refused = [t for t in runs if t < T0 + 400]
    # Refused (75) attempts retry every 60 s and are not counted as failures ...
    assert len(refused) >= 3 and all(b - a == 60 for a, b in zip(refused, refused[1:])), runs
    # ... then three real failures, 300 s apart, move the item to .failed with a
    # state line — the unchanged outer accounting, reached from the early wake.
    failures = rig.when("codex one-time")
    assert len(failures) == 3 and all(b - a == 300 for a, b in zip(failures, failures[1:])), rig.calls
    assert Path(f"{rig.item}.failed").exists() and not rig.item.exists()
    assert Path(f"{rig.item}.attempts").read_text().strip() == "3" and rig.when("control state")


def test_non_admissible_files_do_not_wake_the_wait(tmp_path):
    rig = Rig(tmp_path)
    rig.bank(B10)
    for name in ("old.md.consumed", "old.md.attempts", "notes.txt"):
        rig.at(T0 + 130, "touch", rig.inbox / name)
    (rig.inbox / "context").mkdir()
    rig.at(T0 + 130, "touch", rig.inbox / "context" / "fyi.md")
    rig.run(stop=DEADLINE - 1)

    assert rig.when("control run") == [] and len(rig.when("collector")) == 1, rig.calls
    assert "back to normal admission" not in rig.stdout


@pytest.mark.parametrize("past_slice_start", [1, 59])
def test_slice_length_is_the_fixed_documented_bound(tmp_path, past_slice_start):
    # Slices start at T0, T0+60, ...; an item queued just after one starts is the
    # worst case and still waits less than the fixed 60 s bound.
    rig = Rig(tmp_path)
    rig.bank(B10)
    arrival = T0 + 120 + past_slice_start
    rig.at(arrival, "touch", rig.item)
    rig.run(stop=T0 + 600)
    assert 0 < rig.when("codex one-time")[0] - arrival < 60, rig.calls
    naps = [int(w.split()[1]) for t, w in rig.calls if w.startswith("sleep") and t <= arrival]
    assert naps and max(naps) == 60, naps


def test_both_hourly_waits_route_through_the_inbox_aware_wait():
    """Pins the wiring the loop tests exercise: neither hourly branch keeps a bare
    sleep to the hour, admission and the wait share one selector, the slice is a
    fixed bound (no settings flag) and the selector keeps find's error output."""
    source = BUS.read_text()
    assert 'sleep "$NAP"' not in source
    assert source.count('idle_until "$((NOW + NAP))"') == 2
    assert "ONCE=$(next_once)" in source
    assert "INBOX_POLL=60\n" in source and "BUS_INBOX_POLL" not in source
    selector = next(ln for ln in source.splitlines() if ln.startswith("next_once ()"))
    assert "/dev/null" not in selector, selector
