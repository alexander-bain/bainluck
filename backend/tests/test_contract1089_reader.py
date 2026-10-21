"""#1089 — the one-archived-contract reader pays only on one complete, exact response.

PILLAR: TRUTH. SHIP: settled NHL player questions use the correct game's pregame
forecast and result.

``tools/contract1089/reader.py`` makes at most one public GET to one fixed Kalshi
URL, behind an exclusive ``ATTEMPT-STARTED`` fence, inside one 15 s deadline and
one 262,144-byte cap. These tests never open a network connection: every
"network child" here is a real subprocess that writes canned bytes, sleeps or
exits, so the parent's real fence, process-group kill, reap, byte cap, framing
and deadline all run. The real child's network half is driven in-process
through a fake TLS socket. Every response body below is a SYNTHETIC fixture,
not venue evidence.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import signal
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
READER = BACKEND.parent / "tools" / "contract1089" / "reader.py"
TICKER = "KXNHLGOAL-26JUN11VGKCAR-VGKWKARLSSON71-2"
CAP = 262_144

FAKE_CHILD = r"""
import os, sys, time
data = open(sys.argv[1], "rb").read()
step, gap, pause, code = int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
if sys.argv[6] != "-":
    import subprocess
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    with open(sys.argv[6], "w") as f:
        f.write(str(p.pid))
for i in range(0, len(data), step):
    os.write(1, data[i:i + step])
    if gap:
        time.sleep(gap)
time.sleep(pause)
sys.exit(code)
"""


@pytest.fixture
def reader():
    spec = importlib.util.spec_from_file_location("contract1089_reader_under_test", READER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def inert(monkeypatch):
    """No socket and no name lookup in the test process, for every arm."""

    def refuse(*a, **k):
        raise AssertionError("the test process touched the network")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("KALSHI_API_KEY", "inert-fake-key")


@pytest.fixture
def cdir(tmp_path):
    root = Path(os.path.realpath(tmp_path))
    d = root / "calibration-1089-plan-admission-20261018" / "ONE-ARCHIVED-CONTRACT"
    d.mkdir(parents=True)
    d.chmod(0o700)
    return d


def market(**over):
    m = {
        "ticker": TICKER,
        "event_ticker": "SYNTHETIC-EVENT-TICKER",
        "title": "SYNTHETIC FIXTURE title",
        "subtitle": "",
        "yes_sub_title": "SYNTHETIC yes label",
        "no_sub_title": "SYNTHETIC no label",
        "rules_primary": "SYNTHETIC FIXTURE rules text; not venue evidence.",
        "rules_secondary": "",
        "open_time": "2026-01-01T00:00:00Z",
        "close_time": "2026-01-02T00:00:00Z",
        "expiration_time": "2026-01-03T00:00:00Z",
        "status": "finalized",
        "result": "no",
    }
    m.update(over)
    return {k: v for k, v in m.items() if v is not _DROP}


_DROP = object()


def body_of(doc) -> bytes:
    return json.dumps(doc).encode()


def http(body: bytes, status: str = "200 OK", extra: str = "", *, framing: str = "length") -> bytes:
    head = f"HTTP/1.1 {status}\r\nContent-Type: application/json; charset=utf-8\r\n{extra}"
    if framing == "length":
        return f"{head}Content-Length: {len(body)}\r\n\r\n".encode() + body
    if framing == "chunked":
        mid = len(body) // 2
        parts = [body[:mid], body[mid:]]
        chunks = b"".join(f"{len(p):x}\r\n".encode() + p + b"\r\n" for p in parts if p)
        return f"{head}Transfer-Encoding: chunked\r\n\r\n".encode() + chunks + b"0\r\n\r\n"
    return f"{head}\r\n".encode() + body  # framed only by the connection closing


class Spawner:
    """A real child process standing in for the network child: it inherits the
    marker exactly as the real one does and writes canned bytes."""

    def __init__(self, tmp: Path, data: bytes, *, step: int = 65_536, gap: float = 0.0,
                 pause: float = 0.0, code: int = 0, grandchild: bool = False) -> None:
        self.tmp, self.data = tmp, data
        self.step, self.gap, self.pause, self.code = step, gap, pause, code
        self.grandchild = tmp / "grandchild.pid" if grandchild else None
        self.calls: list[float] = []
        self.procs: list[subprocess.Popen] = []

    def __call__(self, marker_fd, marker_path, seconds):
        self.calls.append(seconds)
        src = self.tmp / f"served-{len(self.calls)}.bin"
        src.write_bytes(self.data)
        argv = [sys.executable, "-c", FAKE_CHILD, str(src), str(self.step), str(self.gap),
                str(self.pause), str(self.code), str(self.grandchild or "-")]
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, start_new_session=True,
                                pass_fds=(marker_fd,), env={})
        self.procs.append(proc)
        return proc


def run(reader, cdir, spawner, *, deadline=15.0, extra=()):
    clock = reader.Clock(deadline)
    code = reader.main(["--contract-dir", str(cdir), "--send-the-one-request", *extra],
                       spawn=spawner, clock=clock)
    receipt_path = cdir / reader.RECEIPT_NAME
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    return code, receipt, clock


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


# ── the request itself ───────────────────────────────────────────────────────


def test_the_request_is_one_exact_public_get_with_no_credential_and_no_proxy(reader):
    assert reader.URL == ("https://api.elections.kalshi.com/trade-api/v2/historical/markets/"
                          f"{TICKER}")
    lines = reader.REQUEST.decode("ascii").split("\r\n")
    assert lines[0] == f"GET /trade-api/v2/historical/markets/{TICKER} HTTP/1.1"
    assert lines[-2:] == ["", ""]
    names = {ln.split(":", 1)[0].lower() for ln in lines[1:-2]}
    assert names == {"host", "user-agent", "accept", "accept-encoding", "connection"}
    assert "Host: api.elections.kalshi.com" in lines
    assert "Connection: close" in lines and "Accept-Encoding: identity" in lines
    assert (reader.DEADLINE_S, reader.CAP_BYTES) == (15.0, CAP)


def test_the_module_imports_no_http_client_library_and_takes_no_target_argument(reader):
    tree = ast.parse(READER.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert not imported & {"urllib", "requests", "httpx", "aiohttp", "netrc", "pycurl"}
    for flag in ("--url", "--ticker", "--host", "--proxy"):
        with pytest.raises(SystemExit) as e:
            reader.main(["--contract-dir", "/x", "--send-the-one-request", flag, "y"],
                        spawn=lambda *a: pytest.fail("spawned"))
        assert e.value.code == reader.HOLD


def test_the_real_spawn_passes_an_empty_environment_and_only_the_marker(reader, monkeypatch, tmp_path):
    seen = {}

    def fake_popen(argv, **kw):
        seen.update(argv=argv, **kw)
        return "proc"

    monkeypatch.setenv("SSL_CERT_FILE", "/etc/ssl/cert.pem")
    monkeypatch.setenv("NETRC", "/home/x/.netrc")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    assert reader.spawn_pump(7, tmp_path / "ATTEMPT-STARTED", 13.5) == "proc"
    assert seen["argv"][:4] == [sys.executable, "-I", str(READER.resolve()), "--pump"]
    assert seen["argv"][4:] == ["7", str(tmp_path / "ATTEMPT-STARTED"), "13.500"]
    assert seen["env"] == {"SSL_CERT_FILE": "/etc/ssl/cert.pem"}
    assert seen["pass_fds"] == (7,) and seen["close_fds"] is True
    assert seen["start_new_session"] is True
    assert seen["stderr"] is subprocess.DEVNULL and seen["stdin"] is subprocess.DEVNULL


# ── what pays ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("framing", ["length", "chunked"])
def test_one_complete_exact_response_is_observed_and_retained_whole(reader, cdir, tmp_path, framing):
    served = http(body_of({"market": market()}), framing=framing)
    sp = Spawner(tmp_path, served, pause=30.0)  # the child never closes: framing decides
    code, r, clock = run(reader, cdir, sp)
    assert code == reader.OBSERVED, r
    assert r["verdict"] == "OBSERVED" and r["pays_exact_response_gate"] is True
    assert r["http_status"] == 200 and r["transfer_ended_by"] == "framing"
    assert (cdir / reader.RAW_NAME).read_bytes() == served
    assert r["raw_bytes"] == len(served)
    assert r["raw_sha256"] == __import__("hashlib").sha256(served).hexdigest()
    assert r["returned"]["ticker"] == TICKER
    assert r["returned"]["rules_primary"].startswith("SYNTHETIC FIXTURE")
    assert set(r["time_and_fixture_fields"]) == {"open_time", "close_time", "expiration_time"}
    assert r["derived_identity"] is None
    assert "not actual puck-drop" in r["timestamp_note"]
    assert r["occurrence_evidence"].startswith("NOT DECIDED BY THIS READER")
    assert r["request_started_at"] and r["response_observed_at"]
    assert len(sp.calls) == 1 and 0 < sp.calls[0] <= 14.0
    assert not alive(sp.procs[0].pid)
    assert clock.elapsed() < 5.0


def test_a_close_delimited_body_pays_only_on_a_clean_close(reader, cdir, tmp_path):
    served = http(body_of({"market": market()}), framing="close")
    code, r, _ = run(reader, cdir, Spawner(tmp_path, served, code=0))
    assert code == reader.OBSERVED, r
    assert r["transfer_ended_by"] == "eof" and r["child_exit"] == "clean_eof"


def test_a_close_delimited_body_ended_without_tls_close_is_truncated(reader, cdir, tmp_path):
    served = http(body_of({"market": market()}), framing="close")
    code, r, _ = run(reader, cdir, Spawner(tmp_path, served, code=3))
    assert code == reader.NO_RESULT and r["reason"] == "TRUNCATED"
    assert r["pays_exact_response_gate"] is False
    assert (cdir / reader.RAW_NAME).read_bytes() == served  # retained, never paid


def test_the_cap_boundary_exactly_262144_bytes_is_observed(reader, cdir, tmp_path):
    shell = http(body_of({"market": market(rules_primary="SYNTHETIC ")}))
    pad = CAP - len(shell)
    # Content-Length grows by its own digits as the body grows: solve once.
    served = http(body_of({"market": market(rules_primary="SYNTHETIC " + "x" * pad)}))
    served = http(body_of({"market": market(rules_primary="SYNTHETIC " + "x" * (pad - (len(served) - CAP)))}))
    assert len(served) == CAP
    code, r, _ = run(reader, cdir, Spawner(tmp_path, served, pause=30.0))
    assert code == reader.OBSERVED, r
    assert r["raw_bytes"] == CAP


def test_one_byte_past_the_cap_is_oversized_and_never_taken_in_whole(reader, cdir, tmp_path):
    served = http(body_of({"market": market(rules_primary="x" * CAP)}))
    code, r, _ = run(reader, cdir, Spawner(tmp_path, served, pause=30.0))
    assert code == reader.NO_RESULT and r["reason"] == "OVERSIZED"
    assert r["raw_bytes"] == CAP + 1
    assert r["transfer_ended_by"] == "oversized"  # stopped at the cap, not by a zero-byte read
    assert len((cdir / reader.RAW_NAME).read_bytes()) == CAP + 1


# ── what refuses ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status,needle", [
    ("404 Not Found", "does not prove the contract never existed"),
    ("301 Moved Permanently", "never followed"),
    ("429 Too Many Requests", "HTTP 429"),
    ("500 Internal Server Error", "HTTP 500"),
])
def test_a_non_200_is_no_result_and_nothing_else_is_requested(reader, cdir, tmp_path, status, needle):
    extra = "Location: https://example.invalid/elsewhere\r\n" if status.startswith("301") else ""
    sp = Spawner(tmp_path, http(b'{"error":{"code":"not_found"}}', status, extra))
    code, r, _ = run(reader, cdir, sp)
    assert code == reader.NO_RESULT and r["reason"] == "HTTP_STATUS"
    assert needle in r["detail"]
    assert len(sp.calls) == 1


@pytest.mark.parametrize("doc,reason", [
    ({"market": market(ticker="KXNHLGOAL-26JUN11VGKCAR-VGKWKARLSSON71-1")}, "IDENTITY_MISMATCH"),
    ({"market": market(ticker=_DROP)}, "IDENTITY_MISMATCH"),
    ({"markets": [market()]}, "SCHEMA"),
    ({"market": market(rules_primary=_DROP)}, "RULES_MISSING"),
    ({"market": market(rules_primary="   ")}, "RULES_MISSING"),
    ({"market": market(title=7)}, "SCHEMA"),
    ([market()], "SCHEMA"),
])
def test_identity_shape_and_rules_refusals(reader, cdir, tmp_path, doc, reason):
    code, r, _ = run(reader, cdir, Spawner(tmp_path, http(body_of(doc))))
    assert code == reader.NO_RESULT and r["reason"] == reason, r
    assert r["http_status"] == 200  # what was established is kept


@pytest.mark.parametrize("body", [
    b'{"market": {"ticker": "' + TICKER.encode() + b'", "ticker": "x"}}',
    b'{"market": {"ticker": NaN}}',
    b'{"market": {"ticker": "' + TICKER.encode() + b'"}',
    b"\xff\xfe",
])
def test_malformed_json_is_no_result(reader, cdir, tmp_path, body):
    code, r, _ = run(reader, cdir, Spawner(tmp_path, http(body)))
    assert code == reader.NO_RESULT and r["reason"] == "MALFORMED_JSON"


@pytest.mark.parametrize("served,reason", [
    (lambda b: http(b, extra="Content-Encoding: gzip\r\n"), "UNEXPECTED_ENCODING"),
    (lambda b: http(b, extra=f"Content-Length: {len(b)}\r\n"), "MALFORMED_HTTP"),
    (lambda b: http(b, extra="Transfer-Encoding: chunked\r\n"), "MALFORMED_HTTP"),
    (lambda b: http(b) + b"HTTP/1.1 200 OK\r\n", "EXTRA_BYTES"),
    (lambda b: b"SSH-2.0-not-http\r\n\r\n", "MALFORMED_HTTP"),
])
def test_framing_ambiguity_and_extra_bytes_are_no_result(reader, cdir, tmp_path, served, reason):
    code, r, _ = run(reader, cdir, Spawner(tmp_path, served(body_of({"market": market()}))))
    assert code == reader.NO_RESULT and r["reason"] == reason, r


@pytest.mark.parametrize("cut", ["length", "chunked"])
def test_a_response_cut_short_is_truncated(reader, cdir, tmp_path, cut):
    full = http(body_of({"market": market()}), framing=cut)
    trim = 40 if cut == "length" else 5  # chunked: drop the terminal "0\r\n\r\n"
    code, r, _ = run(reader, cdir, Spawner(tmp_path, full[:-trim], code=0))
    assert code == reader.NO_RESULT and r["reason"] == "TRUNCATED"


def test_no_bytes_is_never_an_empty_provider_response(reader, cdir, tmp_path):
    code, r, _ = run(reader, cdir, Spawner(tmp_path, b"", code=5))
    assert code == reader.NO_RESULT and r["reason"] == "NO_RESPONSE_BYTES"
    assert "resolve_failed" in r["detail"] and "not an empty provider response" in r["detail"]


# ── the deadline is a hard bound on the network child ────────────────────────


def test_a_silent_child_is_killed_with_its_whole_session_inside_the_deadline(reader, cdir, tmp_path):
    sp = Spawner(tmp_path, b"", pause=60.0, grandchild=True)
    t0 = time.monotonic()
    code, r, clock = run(reader, cdir, sp, deadline=2.0)
    took = time.monotonic() - t0
    assert code == reader.NO_RESULT and r["reason"] == "DEADLINE"
    assert took < 2.0, took  # killed at deadline - 1 s, finalized inside the rest
    assert r["child_reaped"] is True and not alive(sp.procs[0].pid)
    grandchild = int((tmp_path / "grandchild.pid").read_text())
    for _ in range(50):  # the killed grandchild is reaped by init, not by us
        if not alive(grandchild):
            break
        time.sleep(0.02)
    assert not alive(grandchild), "the child's session outlived the deadline"


def test_a_trickling_child_is_killed_at_the_deadline_and_never_paid(reader, cdir, tmp_path):
    served = http(body_of({"market": market()}))
    code, r, _ = run(reader, cdir, Spawner(tmp_path, served, step=16, gap=0.05), deadline=2.0)
    assert code == reader.NO_RESULT and r["reason"] == "DEADLINE"
    assert 0 < r["raw_bytes"] < len(served)


def test_a_result_whose_receipt_write_returns_late_is_rewritten_no_result(reader, cdir, tmp_path, monkeypatch):
    served = http(body_of({"market": market()}))
    clock = reader.Clock(15.0)
    real_rewrite = reader._rewrite
    calls = []

    def slow_rewrite(fd, body):
        real_rewrite(fd, body)
        calls.append(json.loads(body)["verdict"])
        if len(calls) == 1:
            clock._t0 = tuple(x - 100.0 for x in clock._t0)  # the first write "returned" at 100 s

    monkeypatch.setattr(reader, "_rewrite", slow_rewrite)
    code = reader.main(["--contract-dir", str(cdir), "--send-the-one-request"],
                       spawn=Spawner(tmp_path, served, pause=30.0), clock=clock)
    r = json.loads((cdir / reader.RECEIPT_NAME).read_text())
    assert calls[0] == "OBSERVED"
    assert code == reader.NO_RESULT == r["exit_code"]
    assert r["reason"] == "LATE_FINALIZATION" and r["original_verdict"] == "OBSERVED"
    assert r["finalize_stage"] == "receipt_write" and r["pays_exact_response_gate"] is False


def test_a_result_whose_raw_write_returns_late_never_pays(reader, cdir, tmp_path, monkeypatch):
    served = http(body_of({"market": market()}))
    clock = reader.Clock(15.0)
    real_fsync = os.fsync
    calls = []

    def slow_fsync(fd):
        real_fsync(fd)
        calls.append(fd)
        if len(calls) == 3:  # marker, its directory, then the raw file
            clock._t0 = tuple(x - 100.0 for x in clock._t0)

    monkeypatch.setattr(reader.os, "fsync", slow_fsync)
    sp = Spawner(tmp_path, served, pause=30.0)
    code = reader.main(["--contract-dir", str(cdir), "--send-the-one-request"], spawn=sp, clock=clock)
    r = json.loads((cdir / reader.RECEIPT_NAME).read_text())
    assert len(sp.calls) == 1
    assert code == reader.NO_RESULT == r["exit_code"]
    assert r["reason"] == "LATE_FINALIZATION" and r["finalize_stage"] == "raw_write"
    assert r["original_verdict"] == "OBSERVED" and r["pays_exact_response_gate"] is False
    assert (cdir / reader.RAW_NAME).read_bytes() == served


def test_a_deadline_gone_before_the_request_holds_and_sends_nothing(reader, cdir, monkeypatch):
    clock = reader.Clock(15.0)
    real_fsync = os.fsync

    def slow_fsync(fd):
        real_fsync(fd)
        clock._t0 = tuple(x - 100.0 for x in clock._t0)

    monkeypatch.setattr(reader.os, "fsync", slow_fsync)
    code = reader.main(["--contract-dir", str(cdir), "--send-the-one-request"],
                       spawn=lambda *a: pytest.fail("spawned after the deadline"), clock=clock)
    r = json.loads((cdir / reader.RECEIPT_NAME).read_text())
    assert code == reader.HOLD == r["exit_code"] and r["request_sent"] == "no"
    assert (cdir / reader.MARKER_NAME).exists()  # the attempt is spent, nothing was sent


# ── the attempt fence ────────────────────────────────────────────────────────


def test_the_marker_is_durable_before_the_child_starts_and_is_never_removed(reader, cdir, tmp_path):
    seen = {}
    inner = Spawner(tmp_path, http(body_of({"market": market()})))

    def spawn(fd, path, seconds):
        seen["marker"] = json.loads(Path(path).read_text())
        seen["files"] = sorted(p.name for p in cdir.iterdir())
        return inner(fd, path, seconds)

    code, r, _ = run(reader, cdir, spawn)
    assert code == reader.OBSERVED
    assert seen["files"] == sorted([reader.MARKER_NAME, reader.RAW_NAME, reader.RECEIPT_NAME])
    assert seen["marker"]["url"] == reader.URL and seen["marker"]["pid"] == os.getpid()
    assert (cdir / reader.MARKER_NAME).exists()
    assert r["marker_sha256"] == __import__("hashlib").sha256(
        (cdir / reader.MARKER_NAME).read_bytes()).hexdigest()


def test_a_second_run_never_becomes_a_second_request(reader, cdir, tmp_path):
    sp = Spawner(tmp_path, http(b"", "404 Not Found"))
    first, _, _ = run(reader, cdir, sp)
    before = {p.name: p.read_bytes() for p in cdir.iterdir()}
    second = reader.main(["--contract-dir", str(cdir), "--send-the-one-request"], spawn=sp)
    assert first == reader.NO_RESULT and second == reader.ATTEMPT_SPENT
    assert len(sp.calls) == 1
    assert {p.name: p.read_bytes() for p in cdir.iterdir()} == before  # nothing written


def test_the_exclusive_create_alone_refuses_a_marker_that_appears_after_the_check(reader, cdir, monkeypatch):
    real_state = reader.fence_state

    def racing_state(d):
        state = real_state(d)
        (d / reader.MARKER_NAME).write_text("another run's marker")  # lands after the look
        return state

    monkeypatch.setattr(reader, "fence_state", racing_state)
    code = reader.main(["--contract-dir", str(cdir), "--send-the-one-request"],
                       spawn=lambda *a: pytest.fail("spawned past an existing marker"))
    assert code == reader.ATTEMPT_SPENT
    assert (cdir / reader.MARKER_NAME).read_text() == "another run's marker"  # never overwritten
    assert [p.name for p in cdir.iterdir()] == [reader.MARKER_NAME]


def test_check_sends_nothing_writes_nothing_and_reports_the_fence(reader, cdir, capsys):
    never = lambda *a: pytest.fail("check spawned the network child")  # noqa: E731
    assert reader.main(["--contract-dir", str(cdir), "--check"], spawn=never) == 0
    assert list(cdir.iterdir()) == []
    out = json.loads(capsys.readouterr().out.splitlines()[0])
    assert out["present"] == {reader.MARKER_NAME: False, reader.RAW_NAME: False,
                              reader.RECEIPT_NAME: False}
    (cdir / reader.MARKER_NAME).write_text("{}")
    assert reader.main(["--contract-dir", str(cdir), "--check"], spawn=never) == reader.ATTEMPT_SPENT


@pytest.mark.parametrize("leftover", ["RAW-RESPONSE.bin", "READER-RECEIPT.json"])
def test_leftover_output_without_a_marker_holds_before_the_fence(reader, cdir, leftover):
    (cdir / leftover).write_bytes(b"old")
    code = reader.main(["--contract-dir", str(cdir), "--send-the-one-request"],
                       spawn=lambda *a: pytest.fail("spawned"))
    assert code == reader.HOLD
    assert not (cdir / reader.MARKER_NAME).exists()


def test_a_contract_directory_that_is_not_the_one_holds(reader, tmp_path, cdir):
    never = lambda *a: pytest.fail("spawned")  # noqa: E731
    root = Path(os.path.realpath(tmp_path))
    other = root / "elsewhere" / "ONE-ARCHIVED-CONTRACT"
    other.mkdir(parents=True)
    link_parent = root / "linked" / "calibration-1089-plan-admission-20261018"
    link_parent.mkdir(parents=True)
    (link_parent / "ONE-ARCHIVED-CONTRACT").symlink_to(cdir)
    loose = root / "loose" / "calibration-1089-plan-admission-20261018" / "ONE-ARCHIVED-CONTRACT"
    loose.mkdir(parents=True)
    loose.chmod(0o777)
    for bad in (other, link_parent / "ONE-ARCHIVED-CONTRACT", loose,
                Path("calibration-1089-plan-admission-20261018/ONE-ARCHIVED-CONTRACT"),
                cdir.parent / ".." / cdir.parent.name / cdir.name):
        assert reader.main(["--contract-dir", str(bad), "--send-the-one-request"], spawn=never) == reader.HOLD
    assert list(cdir.iterdir()) == []


def test_a_marker_that_cannot_be_created_holds_with_no_request(reader, cdir):
    cdir.chmod(0o500)
    try:
        code = reader.main(["--contract-dir", str(cdir), "--send-the-one-request"],
                           spawn=lambda *a: pytest.fail("spawned"))
    finally:
        cdir.chmod(0o700)
    assert code == reader.HOLD and list(cdir.iterdir()) == []


def test_a_marker_created_but_not_durable_stays_and_holds_with_no_request(reader, cdir, monkeypatch):
    def broken_fsync(fd):
        raise OSError("disk")

    monkeypatch.setattr(reader.os, "fsync", broken_fsync)
    code = reader.main(["--contract-dir", str(cdir), "--send-the-one-request"],
                       spawn=lambda *a: pytest.fail("spawned"))
    assert code == reader.HOLD
    assert [p.name for p in cdir.iterdir()] == [reader.MARKER_NAME]  # spent, never removed


# ── the network child ────────────────────────────────────────────────────────


class FakeTLS:
    def __init__(self, replies):
        self.replies, self.sent, self.asked, self.timeouts = list(replies), [], [], []
        self.closed = False

    def settimeout(self, t):
        self.timeouts.append(t)

    def sendall(self, data):
        self.sent.append(bytes(data))

    def recv(self, n):
        self.asked.append(n)
        item = self.replies.pop(0) if self.replies else b""
        if isinstance(item, BaseException):
            raise item
        if item == "forever":
            self.replies.insert(0, "forever")
            return b"x" * n
        return item

    def close(self):
        self.closed = True


def pumped(reader, replies, tmp_path, seconds=5.0):
    tls = FakeTLS(replies)
    sink = tmp_path / "child-stdout.bin"
    w = os.open(sink, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # a file: no pipe to fill
    try:
        code = reader.pump(seconds, w, opener=lambda s: (tls, lambda: 1.0))
    finally:
        os.close(w)
    return code, tls, sink.read_bytes()


def test_the_child_sends_once_and_copies_every_byte_through(reader, tmp_path):
    code, tls, out = pumped(reader, [b"HTTP/1.1 200 OK\r\n", b"\r\n{}", b""], tmp_path)
    assert code == reader.PUMP_CLEAN_EOF
    assert tls.sent == [reader.REQUEST] and tls.closed
    assert out == b"HTTP/1.1 200 OK\r\n\r\n{}"


def test_the_child_never_asks_for_more_than_one_byte_past_the_cap(reader, tmp_path):
    code, tls, out = pumped(reader, ["forever"], tmp_path)
    assert code == reader.PUMP_OVERSIZED
    assert len(out) == CAP + 1
    got = 0
    for n in tls.asked:
        assert n <= CAP + 1 - got
        got += n


@pytest.mark.parametrize("exc,want", [
    (ssl.SSLEOFError(8, "eof"), "PUMP_RAGGED_EOF"),
    (TimeoutError(), "PUMP_TIMEOUT"),
    (ConnectionResetError(), "PUMP_RECV"),
])
def test_child_transport_failures_are_coded(reader, exc, want, tmp_path):
    code, _, out = pumped(reader, [b"HTTP/1.1 2", exc], tmp_path)
    assert code == getattr(reader, want) and out == b"HTTP/1.1 2"


def test_the_child_fence_refuses_without_its_parents_marker(reader, cdir, monkeypatch):
    monkeypatch.setattr(reader, "pump", lambda *a, **k: pytest.fail("the fence let the child run"))
    marker = cdir / reader.MARKER_NAME
    marker.write_text(json.dumps({"pid": os.getppid() + 1, "url": reader.URL}))
    other = cdir / "OTHER"
    other.write_text(json.dumps({"pid": os.getppid(), "url": reader.URL}))
    fd_marker, fd_other = os.open(marker, os.O_RDONLY), os.open(other, os.O_RDONLY)
    try:
        cases = [
            [str(fd_marker), str(marker), "5"],         # marker names another parent
            [str(fd_other), str(marker), "5"],          # the fd is not the marker
            [str(fd_other), str(other), "5"],           # the path is not ATTEMPT-STARTED
            ["999", str(marker), "5"],                  # nothing inherited
            [str(fd_marker), str(marker), "16"],        # longer than the deadline
            [str(fd_marker), str(marker)],              # malformed
        ]
        for argv in cases:
            assert reader.pump_main(argv) == reader.PUMP_FENCE, argv
    finally:
        os.close(fd_marker)
        os.close(fd_other)


def test_the_child_runs_under_the_marker_its_parent_created(reader, cdir, monkeypatch):
    monkeypatch.setattr(reader, "pump", lambda seconds, out: 0 if (seconds, out) == (5.0, 1) else 99)
    marker = cdir / reader.MARKER_NAME
    marker.write_text(json.dumps({"pid": os.getppid(), "url": reader.URL}))
    fd = os.open(marker, os.O_RDONLY)
    assert reader.pump_main([str(fd), str(marker), "5"]) == 0  # pump_main closes the fd


def test_the_real_child_process_refuses_a_marker_it_did_not_inherit_from_its_parent(reader, cdir):
    """End to end through the real ``spawn_pump``: a marker naming another pid
    stops the real child before any network step. Nothing is written to stdout."""
    marker = cdir / reader.MARKER_NAME
    marker.write_text(json.dumps({"pid": 1, "url": reader.URL}))
    fd = os.open(marker, os.O_RDONLY)
    try:
        proc = reader.spawn_pump(fd, marker, 2.0)
    finally:
        os.close(fd)
    out, _ = proc.communicate(timeout=10)
    assert proc.returncode == reader.PUMP_FENCE and out == b""


def test_python_crashes_never_read_as_a_verdict(reader):
    src = READER.read_text()
    assert "raise SystemExit(NO_RESULT)" in src and "raise SystemExit(PUMP_HARNESS)" in src
    assert {reader.OBSERVED, reader.HOLD, reader.NO_RESULT, reader.ATTEMPT_SPENT}.isdisjoint({1, 2})
    assert signal.SIGKILL  # the child is SIGKILLed, never asked
