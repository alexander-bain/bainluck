"""#1853 — the plan-output reader pays only on a complete, exact, digest-true plan.

PILLAR: TRUTH. SHIP: settled markets in the original never-graded cohort can show
their venue-confirmed results instead of remaining blank.

``tools/plan1853/reader.py`` reads ONE no-flag plan run's output from
bainluck-heavy. Every output it judges here is the REAL planner's own print:
``repair_1853_archive_grades.main([])`` driven through the plan-bounds fake
session (``test_repair_1853_plan_bounds``) on the retained archive and the
2026-10-15 stored read — the ordinary 22-leg plan, a changed-population stop,
a refusal, and a statement-timeout traceback. Those prints are framed as logplex
lines and served through an inert socketpair "Heroku", so the reader's real
``http.client`` path, byte metering and shared deadline all run. No test opens a
network connection, reads a real credential or starts a process.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
import socket
import ssl
import subprocess
import threading
import time
import traceback
from pathlib import Path

import pytest

from tests import test_repair_1853_plan_bounds as bounds

BACKEND = Path(__file__).resolve().parents[1]
READER = BACKEND.parent / "tools" / "plan1853" / "reader.py"
TOKEN = "inert-fake-token-0123456789"
LOG_PATH = "/sessions/0f0e0d0c-inert?srv=1700000000"
LOG_URL = f"https://logplex.heroku.com{LOG_PATH}"
RUN = "run.4321"
ROOMY = 65_536  # a TEST cap that proves the parser; not a proposed envelope
LAUNCH = (
    "Running python3 scripts/repair_1853_archive_grades.py on ⬢ bainluck-heavy... "
    f"done, {RUN} (Standard-1X)\n"
    f"Use heroku logs --app bainluck-heavy --dyno {RUN} to view the output.\n"
).encode()


@pytest.fixture
def reader():
    spec = importlib.util.spec_from_file_location("plan1853_reader_under_test", READER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def repair():
    spec = importlib.util.spec_from_file_location("repair_1853_for_reader", bounds.SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def inert(monkeypatch, tmp_path):
    """No process, no real home, no live connection, for every arm."""

    def refuse(*a, **k):
        raise AssertionError("the reader started a process")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(os, "posix_spawn", refuse, raising=False)
    monkeypatch.setattr(os, "fork", refuse)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:9")


@pytest.fixture
def netrc(tmp_path):
    path = tmp_path / "netrc"
    path.write_text(
        "machine api.heroku.com\n  login operator@example.invalid\n"
        f"  password {TOKEN}\n"
        "machine git.heroku.com\n  login operator@example.invalid\n  password other-inert-token-xyz\n"
    )
    return path


# ── the real planner's prints ────────────────────────────────────────────────


class _MovedSession(bounds.PlanSession):
    """The stored legs moved: the first ungraded leg was graded since 10/15."""

    async def execute(self, statement, params=None):
        res = await super().execute(statement, params)
        if bounds._kind(str(statement)) == "stored_legs":
            first = bounds.UNGRADED[0]
            return bounds._Result([(r[0], r[1], "api_settlement", False) if r[0] == first else r
                                   for r in res.all()])
        return res


class _ChangedSession(bounds.PlanSession):
    """A planned leg changed between the two plan reads: the script refuses."""

    async def execute(self, statement, params=None):
        res = await super().execute(statement, params)
        if bounds._kind(str(statement)) == "approved":
            return bounds._Result(res.all()[1:])
        return res


def real_print(kind, repair, monkeypatch, capsys) -> tuple[str, int]:
    """What the real script prints (stdout, or the traceback Python would print)
    and the exit status Python would report, for one plan-mode run."""
    calls: list[str] = []
    session = {
        "plan": lambda: bounds.PlanSession(calls),
        "stop": lambda: _MovedSession(calls),
        "refusal": lambda: _ChangedSession(calls),
        "timeout": lambda: bounds.PlanSession(calls, fault=bounds._timeout(), fault_at="stored_legs"),
    }[kind]()
    bounds._wire(repair, monkeypatch, [session])
    capsys.readouterr()
    try:
        code = repair.main([])
        text = capsys.readouterr().out
    except Exception:
        capsys.readouterr()
        text, code = traceback.format_exc(), 1  # Python prints this and exits 1
    return text, code


def frame(text, status, *, run=RUN, command="python3 scripts/repair_1853_archive_grades.py",
          extra_platform=(), nul=False) -> bytes:
    lines = [f"heroku[{run}]: Starting process with command `{command}`",
             f"heroku[{run}]: State changed from starting to up"]
    lines += [f"app[{run}]: {ln}" for ln in text.splitlines()]
    lines += list(extra_platform)
    if status is not None:
        lines += [f"heroku[{run}]: Process exited with status {status}",
                  f"heroku[{run}]: State changed from up to complete"]
    out = []
    for i, ln in enumerate(lines):
        row = f"2026-10-20T20:{10 + i // 60:02d}:{i % 60:02d}.{i:06d}+00:00 {ln}".encode()
        out.append(b"\x00\x00" + row + b"\x00" if nul else row)
    return b"\n".join(out) + b"\n"


# ── an inert Heroku ───────────────────────────────────────────────────────────


class FakeHeroku:
    """Answers the reader over socketpairs. Records every host it was asked for
    and every request it received."""

    def __init__(self, log=b"", *, api_status=201, api_body=None, log_status=200,
                 keep_open=False, delay=0.0, log_url=LOG_URL, chunk=1000):
        self.log, self.api_status, self.api_body = log, api_status, api_body
        self.log_status, self.keep_open, self.delay = log_status, keep_open, delay
        self.log_url, self.chunk = log_url, chunk
        self.hosts: list[str] = []
        self.requests: dict[str, list[bytes]] = {}
        self._threads: list[threading.Thread] = []
        self._socks: list[socket.socket] = []

    def connect(self, host, port, budget):
        assert port == 443
        self.hosts.append(host)
        a, b = socket.socketpair()
        self._socks += [a, b]
        t = threading.Thread(target=self._serve, args=(host, b), daemon=True)
        t.start()
        self._threads.append(t)
        return a

    @staticmethod
    def _request(s) -> bytes:
        data = b""
        while b"\r\n\r\n" not in data:
            got = s.recv(65536)
            if not got:
                return data
            data += got
        head, _, body = data.partition(b"\r\n\r\n")
        m = re.search(rb"(?i)\r\ncontent-length: (\d+)", head)
        while m and len(body) < int(m.group(1)):
            body += s.recv(65536)
        return head + b"\r\n\r\n" + body

    def _serve(self, host, s):
        s.settimeout(10)
        try:
            self.requests.setdefault(host, []).append(self._request(s))
            if host == "api.heroku.com":
                body = self.api_body if self.api_body is not None else json.dumps(
                    {"id": "inert", "logplex_url": self.log_url}).encode()
                s.sendall(b"HTTP/1.1 %d X\r\nContent-Type: application/json\r\n"
                          b"Content-Length: %d\r\n\r\n" % (self.api_status, len(body)) + body)
                return
            if self.log_status != 200:
                s.sendall(b"HTTP/1.1 %d X\r\nContent-Length: 0\r\n\r\n" % self.log_status)
                return
            s.sendall(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n")
            for i in range(0, len(self.log), self.chunk):
                if self.delay:
                    time.sleep(self.delay)
                part = self.log[i:i + self.chunk]
                s.sendall(b"%x\r\n" % len(part) + part + b"\r\n")
            if self.keep_open:  # a tail session: nothing more, until the reader leaves
                while s.recv(65536):
                    pass
            else:
                s.sendall(b"0\r\n\r\n")
        except OSError:
            pass  # the reader left first (it stops once the evidence is whole): a broken pipe is expected
        finally:
            s.close()

    def close(self):
        for s in self._socks:
            s.close()
        for t in self._threads:
            t.join(5)


@pytest.fixture
def heroku():
    made: list[FakeHeroku] = []

    def make(*a, **k):
        made.append(FakeHeroku(*a, **k))
        return made[-1]

    yield make
    for h in made:
        h.close()


def read(reader, fake, netrc, launcher=LAUNCH, **kw):
    return reader.read_plan(launcher, netrc, connector=fake.connect, **kw)


# ── 1. the ordinary 22-leg plan ──────────────────────────────────────────────


def test_the_ordinary_22_leg_plan_is_admissible_with_the_scripts_own_digest(
    reader, repair, monkeypatch, capsys, netrc, heroku
):
    text, code = real_print("plan", repair, monkeypatch, capsys)
    assert code == 0
    fake = heroku(frame(text, 0))
    r = read(reader, fake, netrc, cap=ROOMY)
    assert (r["verdict"], r["exit_code"], r["pays_plan_gate"], r["apply_authorized"]) == (
        "ADMISSIBLE_PLAN", 0, True, False)
    printed = json.loads(text)
    assert r["document"] == printed and r["planned_count"] == 22
    # The digest came from the real plan_digest over the real ApprovedGrades.
    assert r["plan_digest"] == printed["plan_digest"]
    assert reader.script_digest(repair, printed["planned"]) == printed["plan_digest"]
    # One session for the launched dyno on bainluck-heavy, one read; nothing else.
    assert fake.hosts == ["api.heroku.com", "logplex.heroku.com"]
    post = fake.requests["api.heroku.com"][0]
    head, _, body = post.partition(b"\r\n\r\n")
    assert head.startswith(b"POST /apps/bainluck-heavy/log-sessions HTTP/1.1\r\n")
    assert json.loads(body) == {"dyno": RUN, "lines": 1500, "tail": True}
    assert f"Authorization: Bearer {TOKEN}".encode() in head
    assert fake.requests["logplex.heroku.com"][0].startswith(f"GET {LOG_PATH} HTTP/1.1\r\n".encode())
    assert r["run"] == RUN and r["log_host"] == "logplex.heroku.com"
    raw = base64.b64decode(r["log"]["raw_b64"])
    assert frame(text, 0).startswith(raw) and b"Process exited with status 0\n" in raw
    blob = json.dumps(r)
    assert TOKEN not in blob and LOG_PATH not in blob and "0f0e0d0c-inert" not in blob


def test_the_ordinary_plan_does_not_fit_the_proposed_16384_byte_envelope(
    reader, repair, monkeypatch, capsys, netrc, heroku
):
    """The exact source limitation: logplex frames every one of the plan's 195
    printed lines, so the honest ordinary read is larger than 16,384 bytes. At
    the proposed cap the reader fails closed rather than truncate the plan."""
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    framed = frame(text, 0)
    assert len(text.encode()) < reader.CAP_BYTES < len(framed)
    r = read(reader, heroku(framed), netrc)
    assert r["cap_bytes"] == 16_384
    assert (r["verdict"], r["reason"], r["exit_code"]) == ("UNCERTAIN", "OVERSIZED", 30)
    assert "document" not in r and r["bytes"]["used"] <= reader.CAP_BYTES + 1


# ── 2. stop, refusal, and the exit 1 that is NOT a stop ──────────────────────


def test_a_changed_population_is_a_stop_result_that_must_never_be_applied(
    reader, repair, monkeypatch, capsys, netrc, heroku
):
    text, code = real_print("stop", repair, monkeypatch, capsys)
    assert code == 1 and "stop" in json.loads(text)
    r = read(reader, heroku(frame(text, 1)), netrc, cap=ROOMY)
    assert (r["verdict"], r["exit_code"], r["pays_plan_gate"], r["apply_authorized"]) == (
        "STOP_RESULT", 10, False, False)
    assert r["stop_population_must_never_be_applied"] is True
    assert r["planned_count"] == 21 and r["document"]["stop"].startswith("plan holds 21 legs")


def test_an_exit_1_document_whose_stop_is_not_the_scripts_own_is_not_a_stop(
    reader, repair, monkeypatch, capsys, netrc, heroku
):
    text, _ = real_print("stop", repair, monkeypatch, capsys)
    forged = text.replace("do not apply this plan", "safe to apply")
    assert forged != text
    r = read(reader, heroku(frame(forged, 1)), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "SCHEMA")


def test_the_scripts_own_refusal_is_a_refusal(reader, repair, monkeypatch, capsys, netrc, heroku):
    text, code = real_print("refusal", repair, monkeypatch, capsys)
    assert code == 2 and text.startswith('{"refused": "legs [')
    r = read(reader, heroku(frame(text, 2)), netrc)
    assert (r["verdict"], r["exit_code"], r["pays_plan_gate"], r["apply_authorized"]) == (
        "REFUSAL", 20, False, False)
    assert r["refusal"] == json.loads(text)["refused"]


def test_a_timed_out_plan_exits_1_with_a_traceback_and_is_uncertain_not_a_stop(
    reader, repair, monkeypatch, capsys, netrc, heroku
):
    """In plan mode a non-Refused failure escapes main(), so Python exits 1 —
    the stop's own code. Only the script's complete stop document pays exit 1."""
    text, code = real_print("timeout", repair, monkeypatch, capsys)
    assert code == 1 and "statement timeout" in text and "plan_digest" not in text
    r = read(reader, heroku(frame(text, 1)), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"], r["exit_code"]) == ("UNCERTAIN", "TRACEBACK", 30)


def test_a_refusal_shaped_line_under_exit_1_or_python_exit_2_text_is_not_a_refusal(
    reader, repair, monkeypatch, capsys, netrc, heroku
):
    text, _ = real_print("refusal", repair, monkeypatch, capsys)
    r = read(reader, heroku(frame(text, 1)), netrc)
    assert r["verdict"] == "UNCERTAIN"
    cant_open = "python3: can't open file '/app/scripts/repair_1853_archive_grades.py': [Errno 2]"
    r = read(reader, heroku(frame(cant_open, 2)), netrc)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "MALFORMED_JSON")


# ── 3. the launch evidence names the run ─────────────────────────────────────


@pytest.mark.parametrize("launcher", [
    LAUNCH.replace(b"bainluck-heavy...", b"bainluck..."),
    LAUNCH.replace(b"grades.py on", b"grades.py --backup --apply --digest a9e73455dcaad6ae on"),
    LAUNCH.replace(b"grades.py on", b"grades.py --status on"),
    LAUNCH + LAUNCH.replace(RUN.encode(), b"run.9999"),
    LAUNCH.replace(b"Use heroku logs", b"previous run.6892 -- Use heroku logs"),
    LAUNCH.replace(b"done, ", b"up, "),
    b"",
    LAUNCH + b"x" * 5000,
    LAUNCH.replace(b"Running", b"Running\x00"),
], ids=["wrong-app", "apply-flags", "status-flag", "two-launches", "echoed-old-run",
        "no-done-line", "empty", "oversized", "nul"])
def test_launch_evidence_that_is_not_exactly_one_no_flag_heavy_launch_reads_nothing(
    reader, netrc, heroku, launcher
):
    fake = heroku(b"")
    r = read(reader, fake, netrc, launcher=launcher)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "LAUNCHER")
    assert fake.hosts == [] and "run" not in r


def test_the_run_comes_from_the_done_line_not_an_echoed_argument(reader):
    assert reader.parse_launcher(LAUNCH) == RUN
    coloured = LAUNCH.replace(b"python3 scripts", b"\x1b[36mpython3 scripts").replace(
        b"grades.py on", b"grades.py\x1b[39m on")
    assert reader.parse_launcher(coloured) == RUN


def test_log_lines_for_another_run_are_mismatched(reader, repair, monkeypatch, capsys, netrc, heroku):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    r = read(reader, heroku(frame(text, 0, run="run.4322")), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "MISMATCHED_RUN")


def test_a_log_for_a_different_command_is_mismatched(reader, repair, monkeypatch, capsys, netrc, heroku):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    log = frame(text, 0, command="python3 scripts/repair_1853_archive_grades.py --status")
    r = read(reader, heroku(log), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "MISMATCHED_COMMAND")


# ── 4. NUL-bearing framing ───────────────────────────────────────────────────


def test_nul_bytes_at_line_ends_are_framing_and_the_plan_still_pays(
    reader, repair, monkeypatch, capsys, netrc, heroku
):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    log = frame(text, 0, nul=True)
    assert log.count(b"\x00") > 500
    r = read(reader, heroku(log, chunk=333), netrc, cap=ROOMY)
    assert r["verdict"] == "ADMISSIBLE_PLAN"
    raw = base64.b64decode(r["log"]["raw_b64"])  # retained as read, NULs and all
    assert log.startswith(raw) and raw.count(b"\x00") > 500 and b"status 0\x00\n" in raw


def test_a_nul_inside_a_line_is_malformed(reader, repair, monkeypatch, capsys, netrc, heroku):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    log = frame(text, 0).replace(b'"is_winner": false', b'"is_winner": f\x00alse', 1)
    r = read(reader, heroku(log), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "MALFORMED_FRAME")


def test_an_unframed_line_or_a_stream_ending_inside_a_line_is_malformed(
    reader, repair, monkeypatch, capsys, netrc, heroku
):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    log = frame(text, 0)
    r = read(reader, heroku(log.replace(b"\n", b"\nunframed text\n", 1)), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "MALFORMED_FRAME")
    cut = frame(text, None)[:-40]
    r = read(reader, heroku(cut), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "MALFORMED_FRAME")


# ── 5. JSON boundaries ───────────────────────────────────────────────────────


@pytest.mark.parametrize("mutate,reason", [
    (lambda t: "warning: something\n" + t, "EXTRA_TEXT"),
    (lambda t: t + "trailing text\n", "EXTRA_TEXT"),
    (lambda t: t + t, "EXTRA_TEXT"),
    (lambda t: t.rsplit("}", 1)[0], "INCOMPLETE_JSON"),
    (lambda t: t.replace('\n  "plan_digest"', '\n    "plan_digest"', 1), "NONCANONICAL"),
    (lambda t: t.replace('"event_ticker"', '"plan_digest": "0000000000000000",\n  "event_ticker"', 1),
     "MALFORMED_JSON"),
], ids=["text-before", "text-after", "two-documents", "truncated", "reindented",
        "duplicate-key"])
def test_only_exactly_one_complete_printed_document_pays(
    reader, repair, monkeypatch, capsys, netrc, heroku, mutate, reason
):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    r = read(reader, heroku(frame(mutate(text), 0)), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", reason)


def test_a_write_mode_receipt_under_exit_0_is_not_a_plan(reader, repair, monkeypatch, capsys, netrc, heroku):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    doc = json.loads(text)
    doc["applied"] = {"written_ids": [], "skipped_changed_since_backup": []}
    r = read(reader, heroku(frame(json.dumps(doc, indent=2), 0)), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "SCHEMA")


def test_an_exit_0_document_that_is_not_22_legs_is_not_admissible(
    reader, repair, monkeypatch, capsys, netrc, heroku
):
    text, _ = real_print("stop", repair, monkeypatch, capsys)
    doc = json.loads(text)
    del doc["stop"]
    r = read(reader, heroku(frame(json.dumps(doc, indent=2), 0)), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "SCHEMA")


# ── 6. digest drift ──────────────────────────────────────────────────────────


def test_digest_drift_is_refused(reader, repair, monkeypatch, capsys, netrc, heroku):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    doc = json.loads(text)
    doc["planned"][3]["approved_before_sha256"] = "0" * 64
    r = read(reader, heroku(frame(json.dumps(doc, indent=2), 0)), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "DIGEST_INVALID")
    doc = json.loads(text)
    doc["plan_digest"] = "f" * 16
    r = read(reader, heroku(frame(json.dumps(doc, indent=2), 0)), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "DIGEST_INVALID")


def test_a_self_consistent_plan_the_archive_does_not_grade_is_refused(
    reader, repair, monkeypatch, capsys, netrc, heroku
):
    """Flip a verdict AND recompute the digest: only the archive check catches it."""
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    doc = json.loads(text)
    doc["planned"][0]["is_winner"] = True
    doc["plan_digest"] = reader.script_digest(repair, doc["planned"])
    r = read(reader, heroku(frame(json.dumps(doc, indent=2), 0)), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "ARCHIVE_MISMATCH")


# ── 7. terminal evidence ─────────────────────────────────────────────────────


def test_no_exit_line_is_never_a_result(reader, repair, monkeypatch, capsys, netrc, heroku):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    r = read(reader, heroku(frame(text, None)), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "NO_TERMINAL")
    t0 = time.monotonic()
    r = read(reader, heroku(frame(text, None), keep_open=True), netrc, cap=ROOMY, deadline_s=0.8)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "DEADLINE")
    assert time.monotonic() - t0 < 3 and r["elapsed_s"] < 1.5
    assert "does not prove the run stopped" in r["remote_run_state"]


@pytest.mark.parametrize("extra,status,reason", [
    ((), 143, "EXIT_UNKNOWN"),
    ((), 3, "EXIT_UNKNOWN"),
    ((f"heroku[{RUN}]: Error R14 (Memory quota exceeded)",), 0, "UNRECOGNIZED_LIFECYCLE"),
    ((f"heroku[{RUN}]: Process exited with status 0",), 0, "AMBIGUOUS_TERMINAL"),
])
def test_unknown_or_ambiguous_terminal_evidence_is_uncertain(
    reader, repair, monkeypatch, capsys, netrc, heroku, extra, status, reason
):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    r = read(reader, heroku(frame(text, status, extra_platform=extra)), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", reason)


def test_a_complete_plan_with_the_exit_line_first_still_pays_once_the_document_closes(
    reader, repair, monkeypatch, capsys, netrc, heroku
):
    """Logplex does not order the platform and app sources: the reader waits for
    the document even when the exit line arrives before it."""
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    log = frame(text, 0).split(b"\n")
    exit_line = next(ln for ln in log if b"Process exited" in ln)
    log.remove(exit_line)
    log.insert(2, exit_line)
    r = read(reader, heroku(b"\n".join(log), keep_open=True), netrc, cap=ROOMY, deadline_s=5)
    assert r["verdict"] == "ADMISSIBLE_PLAN" and r["elapsed_s"] < 4


# ── 8. transport and credential ──────────────────────────────────────────────


@pytest.mark.parametrize("kw", [{"api_status": 403}, {"api_status": 429}, {"log_status": 404},
                                {"api_body": b'{"id": "inert"}'}], ids=["403", "429", "log-404", "no-url"])
def test_a_failed_response_is_uncertain_and_never_retried(
    reader, repair, monkeypatch, capsys, netrc, heroku, kw
):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    fake = heroku(frame(text, 0), **kw)
    r = read(reader, fake, netrc, cap=ROOMY)
    assert r["verdict"] == "UNCERTAIN" and r["reason"] in ("HTTP_STATUS", "HTTP_BODY")
    assert fake.hosts == (["api.heroku.com", "logplex.heroku.com"] if "log_status" in kw
                          else ["api.heroku.com"])


def test_a_refused_connection_is_one_attempt(reader, netrc):
    attempts = []

    def connector(host, port, budget):
        attempts.append(host)
        raise ConnectionRefusedError("inert")

    r = reader.read_plan(LAUNCH, netrc, connector=connector)
    assert (r["verdict"], r["reason"], attempts) == ("UNCERTAIN", "TRANSPORT", ["api.heroku.com"])


@pytest.mark.parametrize("stage", ["api.heroku.com", "logplex.heroku.com"])
def test_an_operator_interrupt_propagates_as_itself_never_as_a_verdict(reader, netrc, heroku, stage):
    fake = heroku(b"")

    def connector(host, port, budget):
        if host == stage:
            raise KeyboardInterrupt
        return fake.connect(host, port, budget)

    with pytest.raises(KeyboardInterrupt):
        reader.read_plan(LAUNCH, netrc, connector=connector)


@pytest.mark.parametrize("url", [
    "http://logplex.heroku.com/sessions/x", "https://logplex.example.com/sessions/x",
    "https://logplex.heroku.com.example.com/x", "https://u:p@logplex.heroku.com/x",
    "https://logplex.heroku.com:8443/x", "https://[::1/x",
])
def test_the_log_endpoint_must_be_https_on_a_heroku_host(reader, netrc, heroku, url):
    fake = heroku(b"", log_url=url)
    r = read(reader, fake, netrc)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "UNEXPECTED_ENDPOINT")
    assert fake.hosts == ["api.heroku.com"]


@pytest.mark.parametrize("written", [b"", b"machine api.heroku.com\n"])
def test_a_stalling_credential_source_is_refused_without_waiting(reader, tmp_path, heroku, written):
    """A FIFO whose writer stays open (and may have written part of an entry)
    would block a plain read forever: it is refused as not a regular file."""
    fifo = tmp_path / "netrc-fifo"
    os.mkfifo(fifo)
    writer = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)  # holds a writer open, never closes it
    try:
        os.write(writer, written) if written else None
        fake = heroku(b"")
        t0 = time.monotonic()
        r = read(reader, fake, fifo)
    finally:
        os.close(writer)
    assert (r["verdict"], r["reason"], r["detail"]) == (
        "UNCERTAIN", "CREDENTIAL", "netrc is not a regular file")
    assert time.monotonic() - t0 < 1 and fake.hosts == []


@pytest.mark.parametrize("body", [
    "machine git.heroku.com\n  password only-git-token-123\n",
    "machine api.heroku.com\n  login a\n",
    "machine api.heroku.com\n  password x y\n",
    "machine api.heroku.com\n  password t0k3n-one-12345\nmachine api.heroku.com\n  password t0k3n-two-12345\n",
    "macdef init\n  cd /\n\nmachine api.heroku.com\n  password t0k3n-one-12345\n",
])
def test_a_netrc_without_one_usable_api_entry_is_refused(reader, tmp_path, heroku, body):
    path = tmp_path / "netrc"
    path.write_text(body)
    fake = heroku(b"")
    r = read(reader, fake, path)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "CREDENTIAL") and fake.hosts == []


def test_a_credential_file_past_the_cap_is_oversized(reader, tmp_path, heroku):
    path = tmp_path / "netrc"
    path.write_text(f"machine api.heroku.com\n  password {TOKEN}\n" + "# pad\n" * 4000)
    r = read(reader, heroku(b""), path)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "OVERSIZED")
    assert r["bytes"]["by_stage"]["credential"] == reader.CAP_BYTES + 1


# ── 9. overflow, deadline and cleanup ────────────────────────────────────────


def test_output_past_the_cap_stops_one_byte_past_it(reader, repair, monkeypatch, capsys, netrc, heroku):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    r = read(reader, heroku(frame(text * 6, 0), chunk=8192), netrc, cap=ROOMY)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "OVERSIZED")
    assert r["bytes"]["used"] == ROOMY + 1


def test_a_slow_drip_cannot_stretch_the_shared_deadline(reader, repair, monkeypatch, capsys, netrc, heroku):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    t0 = time.monotonic()
    r = read(reader, heroku(frame(text, 0), chunk=200, delay=0.1), netrc, cap=ROOMY, deadline_s=1.0)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "DEADLINE")
    assert time.monotonic() - t0 < 2.5


def test_a_resolver_that_answers_late_is_abandoned_at_the_deadline(reader, netrc):
    answered = threading.Event()

    def slow_getaddrinfo(*a, **k):
        time.sleep(1.5)
        answered.set()
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 443))]

    def connector(host, port, budget):
        reader._resolve(host, port, budget, getaddrinfo=slow_getaddrinfo)
        raise AssertionError("a late answer was used")

    t0 = time.monotonic()
    r = reader.read_plan(LAUNCH, netrc, connector=connector, deadline_s=0.5)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "DEADLINE")
    assert time.monotonic() - t0 < 1.0 and not answered.is_set()
    answered.wait(3)  # the abandoned thread finishes later and changes nothing


def test_a_close_that_raises_never_changes_the_verdict(reader, repair, monkeypatch, capsys, netrc, heroku):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    fake = heroku(frame(text, 0))

    class Raising:
        def __init__(self, s):
            self._s = s

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            self._s.close()
            raise OSError("inert close failure")

    r = reader.read_plan(LAUNCH, netrc, connector=lambda h, p, b: Raising(fake.connect(h, p, b)),
                         cap=ROOMY)
    assert r["verdict"] == "ADMISSIBLE_PLAN"


# ── 10. secrecy, pins, transport policy, exit codes ──────────────────────────


def test_no_credential_or_bearer_url_leaves_the_reader(
    reader, repair, monkeypatch, capsys, netrc, heroku, tmp_path
):
    text, _ = real_print("plan", repair, monkeypatch, capsys)
    fake = heroku(frame(text, 0))
    monkeypatch.setattr(reader, "connect_tls", fake.connect)
    home = tmp_path / "home"
    home.mkdir()
    (home / ".netrc").write_text(netrc.read_text())
    (tmp_path / "launch.txt").write_bytes(LAUNCH)
    receipt = tmp_path / "receipt.json"
    code = reader.main(["--launcher", str(tmp_path / "launch.txt"), "--receipt", str(receipt)])
    captured = capsys.readouterr()
    assert code == 30  # the CLI reads at the proposed 16,384 cap: the ordinary plan is OVERSIZED
    blob = receipt.read_bytes() + captured.out.encode() + captured.err.encode()
    for secret in (TOKEN, LOG_PATH, "0f0e0d0c-inert", "srv=1700000000"):
        assert secret.encode() not in blob
    assert oct(receipt.stat().st_mode & 0o777) == "0o600"
    assert json.loads(receipt.read_text())["reason"] == "OVERSIZED"


def test_proxy_variables_are_ignored_and_tls_is_verified(reader, monkeypatch):
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:9"
    seen = []

    def resolve(host, port, budget, **k):
        seen.append(host)
        raise reader.Uncertain("TRANSPORT", "inert")

    monkeypatch.setattr(reader, "_resolve", resolve)
    with pytest.raises(reader.Uncertain):
        reader.connect_tls("api.heroku.com", 443, reader.Budget())
    assert seen == ["api.heroku.com"]
    ctx = reader.tls_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_the_pins_are_the_bytes_in_this_checkout_and_a_drifted_pin_reads_nothing(
    reader, netrc, heroku, monkeypatch
):
    import hashlib

    assert hashlib.sha256(bounds.SCRIPT.read_bytes()).hexdigest() == reader.SCRIPT_SHA256
    assert hashlib.sha256(reader.KMS_PATH.read_bytes()).hexdigest() == reader.KMS_SHA256
    monkeypatch.setattr(reader, "SCRIPT_SHA256", "0" * 64)
    fake = heroku(b"")
    r = read(reader, fake, netrc)
    assert (r["verdict"], r["reason"]) == ("UNCERTAIN", "SOURCE_PIN") and fake.hosts == []


def test_the_reader_names_no_app_command_or_endpoint_argument(reader):
    import inspect

    assert set(inspect.signature(reader.read_plan).parameters) == {
        "launcher", "netrc_path", "connector", "deadline_s", "cap"}
    src = READER.read_text()
    assert "add_argument" in src and src.count("add_argument(") == 2
    assert (reader.APP, reader.API_HOST, reader.DEADLINE_S, reader.CAP_BYTES) == (
        "bainluck-heavy", "api.heroku.com", 30.0, 16_384)
    code = src.split('"""', 2)[2]  # everything after the module docstring
    for word in ("subprocess", "os.system", "posix_spawn", "ps:stop",
                 "ps:kill", "--apply", "--backup", "--restore", "HEROKU_API_KEY"):
        assert word not in code, word


def test_usage_errors_and_an_existing_receipt_are_uncertain_not_a_verdict(reader, tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        reader.main(["--launcher", "x"])
    assert e.value.code == 30
    existing = tmp_path / "r.json"
    existing.write_text("{}")
    assert reader.main(["--launcher", str(tmp_path / "nope"), "--receipt", str(existing)]) == 30
    assert existing.read_text() == "{}"
