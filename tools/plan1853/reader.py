#!/usr/bin/env python3
"""#1853 — read ONE no-flag plan run's output from bainluck-heavy, and nothing else.

PILLAR: TRUTH. SHIP: settled markets in the original never-graded cohort can
show their venue-confirmed results instead of remaining blank.

WHAT IT DOES. Given the saved output of the operator's own launch of exactly

    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_1853_archive_grades.py

it takes the created dyno from that launch's ``done, run.N`` line, opens ONE
Platform API log session for that dyno on ``bainluck-heavy``, reads it once, and
says what the run printed: a complete admissible plan, a complete STOP result,
a complete refusal, or UNCERTAIN. It writes one receipt file.

WHAT IT NEVER DOES. It launches no dyno, runs no repair, apply or restore, stops
no remote process, reserves nothing and grants no admission. It takes no app,
command, SQL, URL, proxy or provider argument: the app, the command and both
endpoints are constants below. It never retries, never polls, never tries a
second address or route. Its only network peers are ``api.heroku.com`` and the
``logplex_url`` that endpoint returns, which must be HTTPS on a ``.heroku.com``
host. It ignores proxy environment variables (it opens its own sockets), so an
operator whose only egress is an HTTP proxy cannot use it.

THE ENVELOPE (Root's proposal, 2026-10-20). One 30 s deadline is shared by every
stage: credential read, name resolution, connect, TLS, request, response and
log stream. One 16,384-byte cap is shared by every byte the reader takes in:
the credential file, both responses' status lines, headers and bodies (chunk
framing included), and error bodies. Running out of either is UNCERTAIN, never
a truncated plan. A reader timeout does not prove the remote run stopped.

THE CREDENTIAL. The ``api.heroku.com`` password from the operator's netrc file,
read in-process (no ``heroku auth:token`` child, so nothing can outlive the
reader through the CLI's detached telemetry or update workers). The token goes
only into one request header. The bearer ``logplex_url`` goes only into one
request line. Neither reaches argv, the environment, stdout, stderr or the
receipt.

WHAT PAYS. The reader judges only against the actual script and helpers in this
checkout, pinned by sha256 below: the schema is the script's own output, the
digest is recomputed by the script's own ``plan_digest`` code, and every planned
leg is checked against the script's retained archive through the shared
``gradeable_winner`` rule. Reader exit codes:

    0  ADMISSIBLE_PLAN  run exited 0; the complete 22-leg plan, digest verified
    10 STOP_RESULT      run exited 1 with the script's own stop: NEVER apply it
    20 REFUSAL          run exited 2 with the script's own refusal line
    30 UNCERTAIN        everything else: no plan gate is paid

A stop or a refusal is evidence, not success, and not a reason to retry.
Python's own exit codes (1 for an uncaught exception, 2 for a usage error) are
never a verdict here.

Usage (attended; this file grants no admission):

    python3 tools/plan1853/reader.py --launcher <saved launch output> --receipt <new file>
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import importlib.util
import io
import json
import os
import re
import socket
import ssl
import stat
import sys
import threading
import time
import types
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

APP = "bainluck-heavy"
COMMAND = "python3 scripts/repair_1853_archive_grades.py"
API_HOST = "api.heroku.com"
LOG_HOST_SUFFIX = ".heroku.com"
DEADLINE_S = 30.0
CAP_BYTES = 16_384
LAUNCHER_MAX_BYTES = 4_096
LOG_LINES = 1_500
NETRC_MACHINE = "api.heroku.com"

REPO = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO / "backend" / "scripts" / "repair_1853_archive_grades.py"
KMS_PATH = REPO / "backend" / "app" / "utils" / "kalshi_market_status.py"
#: The bytes this reader's schema, digest and verdict rule come from. Heavy must
#: carry the same script blob (git dd3ece533b) for a run to be judged by it.
SCRIPT_SHA256 = "ab45ba3fa5f1ffe80ab6f14994a51520fe563454c9599aa79d65e991bfb4159c"
KMS_SHA256 = "c74d62819a155d1cfb875e52eb9a5a4b4877017e4f4f4273f4d83ca84a197940"

ADMISSIBLE, STOP, REFUSAL, UNCERTAIN = 0, 10, 20, 30
VERDICTS = {ADMISSIBLE: "ADMISSIBLE_PLAN", STOP: "STOP_RESULT",
            REFUSAL: "REFUSAL", UNCERTAIN: "UNCERTAIN"}

PLAN_KEYS = {"event_ticker", "archive_sha256", "plan_digest", "planned", "refused"}
LEG_KEYS = {"outcome_id", "ticker", "is_winner", "venue_status", "venue_result",
            "approved_before_sha256"}
REFUSED_REASONS = {"absent_from_archive", "already_graded", "no_verdict"}

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_RUN = re.compile(r"\brun\.[0-9]+\b")
_LAUNCH = re.compile(
    r"^Running (?P<cmd>.+?) on (?:⬢ )?(?P<app>[a-z0-9-]+)\.\.\. "
    r"done, (?P<run>run\.[0-9]+)(?: \([^()]+\))?$"
)
_FRAME = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)) "
    r"(?P<source>app|heroku)\[(?P<dyno>[^\]\s]+)\]: (?P<msg>.*)$"
)
_STARTING = re.compile(r"^Starting process with command `(?P<cmd>.*)`$")
_STATE = re.compile(r"^State changed from [a-z]+ to [a-z]+$")
_EXITED = re.compile(r"^Process exited with status (?P<status>[0-9]+)$")
_TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]{8,512}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX16 = re.compile(r"[0-9a-f]{16}")
_TRACEBACK = "Traceback (most recent call last):"


class Uncertain(Exception):
    """A result that pays no plan gate. ``reason`` is a fixed code; ``detail``
    never carries a credential, a bearer URL or an exception's own text."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


def _continuous() -> float:
    # CLOCK_MONOTONIC counts system sleep on macOS; time.monotonic does not.
    clock = getattr(time, "CLOCK_MONOTONIC", None)
    return time.clock_gettime(clock) if clock is not None else time.monotonic()


class Budget:
    """The one deadline and the one byte cap every stage draws on."""

    def __init__(self, deadline_s: float = DEADLINE_S, cap: int = CAP_BYTES) -> None:
        self.deadline_s, self.cap = deadline_s, cap
        self._t0 = (time.monotonic(), _continuous(), time.time())
        self.used = 0
        self.by_stage: dict[str, int] = {}

    def elapsed(self) -> float:
        a, c, w = self._t0
        return max(time.monotonic() - a, _continuous() - c, time.time() - w, 0.0)

    def remaining(self) -> float:
        left = self.deadline_s - self.elapsed()
        if left <= 0:
            raise Uncertain("DEADLINE", f"the shared {self.deadline_s:g} s deadline passed")
        return left

    def room(self) -> int:
        return self.cap - self.used

    def charge(self, n: int, stage: str) -> None:
        self.used += n
        self.by_stage[stage] = self.by_stage.get(stage, 0) + n
        if self.used > self.cap:
            raise Uncertain("OVERSIZED", f"{stage} took the reader past its {self.cap}-byte cap")


# ── inputs ────────────────────────────────────────────────────────────────────


def load_pinned():
    """The script and the verdict helper, refused unless their bytes are pinned."""
    mods = []
    for path, pin, name in ((SCRIPT_PATH, SCRIPT_SHA256, "plan1853_script"),
                            (KMS_PATH, KMS_SHA256, "plan1853_kms")):
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != pin:
            raise Uncertain("SOURCE_PIN", f"{path.name} is not the pinned source")
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mods.append(mod)
    return tuple(mods)


def parse_launcher(raw: bytes) -> str:
    """The dyno the operator's launch created — from its ``done, run.N`` line.

    Exactly one such line, naming the exact no-flag command on ``bainluck-heavy``,
    and no other dyno named anywhere in the evidence (an echoed argument can
    name an old one).
    """
    if len(raw) > LAUNCHER_MAX_BYTES:
        raise Uncertain("LAUNCHER", f"launcher evidence exceeds {LAUNCHER_MAX_BYTES} bytes")
    try:
        text = _ANSI.sub("", raw.decode("utf-8"))
    except UnicodeDecodeError:
        raise Uncertain("LAUNCHER", "launcher evidence is not UTF-8") from None
    if "\x00" in text:
        raise Uncertain("LAUNCHER", "launcher evidence holds a NUL")
    lines = [ln.rstrip("\r") for ln in text.split("\n")]
    done = [ln for ln in lines if "done, run." in ln]
    if len(done) != 1:
        raise Uncertain("LAUNCHER", f"{len(done)} 'done, run.N' lines; exactly one is required")
    m = _LAUNCH.match(done[0].strip())
    if not m:
        raise Uncertain("LAUNCHER", "the 'done, run.N' line is not a run:detached launch line")
    cmd = m["cmd"]
    if cmd.startswith("`") and cmd.endswith("`") and len(cmd) > 1:
        cmd = cmd[1:-1]
    if cmd != COMMAND:
        raise Uncertain("LAUNCHER", "the launch did not run the exact no-flag 1853 command")
    if m["app"] != APP:
        raise Uncertain("LAUNCHER", f"the launch ran on {m['app']!r}, not {APP}")
    run = m["run"]
    others = sorted(set(_RUN.findall(text)) - {run})
    if others:
        raise Uncertain("LAUNCHER", f"the evidence also names {others}; refusing to choose")
    return run


def read_netrc_token(path: Path, budget: Budget) -> str:
    """The ``api.heroku.com`` password, read once, in-process, within the budget.

    The file must be a regular file (a FIFO or device would stall the read); its
    bytes are charged to the cap.
    """
    budget.remaining()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as exc:
        raise Uncertain("CREDENTIAL", f"netrc unavailable ({type(exc).__name__})") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Uncertain("CREDENTIAL", "netrc is not a regular file")
        raw = b""
        while len(raw) <= budget.room():
            try:
                chunk = os.read(fd, budget.room() + 1 - len(raw))
            except OSError as exc:
                raise Uncertain("CREDENTIAL", f"netrc read failed ({type(exc).__name__})") from None
            if not chunk:
                break
            raw += chunk
    finally:
        os.close(fd)
    budget.charge(len(raw), "credential")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise Uncertain("CREDENTIAL", "netrc is not UTF-8") from None
    tokens = " ".join(ln for ln in lines if not ln.lstrip().startswith("#")).split()
    entries: list[tuple[Optional[str], dict]] = []
    i = 0
    while i < len(tokens):
        head = tokens[i]
        if head == "machine" and i + 1 < len(tokens):
            host, i = tokens[i + 1], i + 2
        elif head == "default":
            host, i = None, i + 1
        else:
            raise Uncertain("CREDENTIAL", "netrc has a form this reader does not parse")
        fields: dict = {}
        while i < len(tokens) and tokens[i] not in ("machine", "default", "macdef"):
            key = tokens[i]
            if key not in ("login", "password", "account") or i + 1 >= len(tokens) or key in fields:
                raise Uncertain("CREDENTIAL", "netrc has a form this reader does not parse")
            fields[key], i = tokens[i + 1], i + 2
        entries.append((host, fields))
    mine = [f for h, f in entries if h == NETRC_MACHINE]
    if len(mine) != 1 or not _TOKEN.fullmatch(mine[0].get("password", "")):
        raise Uncertain("CREDENTIAL", f"netrc holds no single usable {NETRC_MACHINE} entry")
    return mine[0]["password"]


# ── transport ─────────────────────────────────────────────────────────────────


def _resolve(host: str, port: int, budget: Budget, getaddrinfo=socket.getaddrinfo):
    """The FIRST address for ``host``, within the deadline. ``getaddrinfo`` cannot
    be interrupted, so it runs on a daemon thread the reader abandons at the
    deadline; a late answer is never used."""
    box: dict = {}

    def work():
        try:
            box["ok"] = getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except BaseException as exc:  # noqa: BLE001 - reported by type only
            box["err"] = exc

    t = threading.Thread(target=work, name="plan1853-resolve", daemon=True)
    t.start()
    t.join(budget.remaining())
    if t.is_alive():
        raise Uncertain("DEADLINE", f"resolving {host} outlived the deadline (thread abandoned)")
    if "err" in box or not box.get("ok"):
        raise Uncertain("TRANSPORT", f"resolving {host} failed ({type(box.get('err')).__name__})")
    return box["ok"][0]


def tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def connect_tls(host: str, port: int, budget: Budget):
    family, kind, proto, _, addr = _resolve(host, port, budget)
    raw = socket.socket(family, kind, proto)
    try:
        raw.settimeout(budget.remaining())
        raw.connect(addr)
        return tls_context().wrap_socket(raw, server_hostname=host)
    except BaseException:
        raw.close()
        raise


class _Metered:
    """A socket whose every received byte is charged, and whose every wait is
    bounded by what is left of the deadline. It never takes in more than one
    byte past the cap."""

    def __init__(self, sock, budget: Budget, stage: str) -> None:
        self._sock, self._budget, self._stage = sock, budget, stage

    def recv_into(self, buf, nbytes: int = 0) -> int:
        want = min(nbytes or len(buf), max(self._budget.room(), 0) + 1)
        self._sock.settimeout(self._budget.remaining())
        n = self._sock.recv_into(buf, want)
        self._budget.charge(n, self._stage)
        return n

    def sendall(self, data) -> None:
        self._sock.settimeout(self._budget.remaining())
        self._sock.sendall(data)

    def makefile(self, mode="rb", *args, **kwargs):
        return io.BufferedReader(socket.SocketIO(self, "rb"))

    def _decref_socketios(self) -> None:
        pass

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass  # cleanup never changes a verdict


class _Conn(http.client.HTTPConnection):
    default_port = 443

    def __init__(self, host, budget, stage, connector) -> None:
        super().__init__(host, 443, timeout=None)
        self._budget, self._stage, self._connector = budget, stage, connector

    def connect(self) -> None:
        self.sock = _Metered(self._connector(self.host, 443, self._budget),
                             self._budget, self._stage)


def _transport_error(stage: str, exc: BaseException) -> Uncertain:
    if isinstance(exc, Uncertain):
        return exc
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return Uncertain("DEADLINE", f"{stage} waited past the deadline")
    return Uncertain("TRANSPORT", f"{stage} failed ({type(exc).__name__})")


def open_log_session(run: str, token: str, budget: Budget, connector) -> str:
    """POST one log session for ``run`` on bainluck-heavy; return its bearer URL."""
    body = json.dumps({"dyno": run, "lines": LOG_LINES, "tail": True}).encode()
    conn = _Conn(API_HOST, budget, "api", connector)
    try:
        conn.request("POST", f"/apps/{APP}/log-sessions", body=body, headers={
            "Accept": "application/vnd.heroku+json; version=3",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "bainluck-plan1853-reader",
        })
        resp = conn.getresponse()
        payload = resp.read()
        status = resp.status
    except BaseException as exc:
        raise _transport_error("log-session request", exc) from None
    finally:
        conn.close()
    if status not in (200, 201):
        raise Uncertain("HTTP_STATUS", f"log-session request returned {status}")
    try:
        url = json.loads(payload)["logplex_url"]
    except (ValueError, KeyError, TypeError):
        raise Uncertain("HTTP_BODY", "log-session response carries no logplex_url") from None
    if not isinstance(url, str):
        raise Uncertain("HTTP_BODY", "log-session response carries no logplex_url")
    return url


def log_endpoint(url: str) -> tuple[str, str]:
    """``(host, path?query)`` of a bearer URL that is HTTPS on a .heroku.com host.
    Only the host is ever reported."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise Uncertain("UNEXPECTED_ENDPOINT", "logplex_url does not parse") from None
    host = parts.hostname or ""
    if (parts.scheme != "https" or not host.endswith(LOG_HOST_SUFFIX) or parts.username
            or parts.password or port not in (None, 443) or parts.fragment):
        raise Uncertain("UNEXPECTED_ENDPOINT", f"logplex_url is not HTTPS on a {LOG_HOST_SUFFIX} host")
    return host, (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


def stream_log(host: str, target: str, run: str, budget: Budget, connector) -> "LogRead":
    """GET the session once; read until the run's terminal evidence is complete,
    the stream ends, or the budget runs out."""
    log = LogRead(run)
    conn = _Conn(host, budget, "log", connector)
    try:
        try:
            conn.request("GET", target, headers={"User-Agent": "bainluck-plan1853-reader"})
            resp = conn.getresponse()
            if resp.status != 200:
                raise Uncertain("HTTP_STATUS", f"log stream returned {resp.status}")
            while not log.ready():
                data = resp.read1(4096)
                if not data:
                    log.end()
                    break
                log.feed(data)
        except BaseException as exc:
            log.error = _transport_error("log stream", exc)
    finally:
        conn.close()
    return log


# ── the log ───────────────────────────────────────────────────────────────────


class LogRead:
    """The raw bytes read for one dyno, framed back into lines.

    NUL bytes at either end of a line are logplex framing and are dropped; a NUL
    anywhere else, an unframed line, or a line for any other dyno is evidence the
    read cannot be trusted.
    """

    def __init__(self, run: str) -> None:
        self.run = run
        self.raw = bytearray()
        self.ended = False
        self.error: Optional[Uncertain] = None
        self.malformed: Optional[Uncertain] = None
        self.app: list[str] = []
        self.heroku: list[str] = []
        self._consumed = 0

    def feed(self, data: bytes) -> None:
        self.raw += data
        end = self.raw.rfind(b"\n") + 1
        if end > self._consumed:
            for line in bytes(self.raw[self._consumed:end]).split(b"\n")[:-1]:
                self._line(line)
            self._consumed = end

    def _line(self, line: bytes) -> None:
        if self.malformed:
            return
        line = line.rstrip(b"\r").strip(b"\x00")
        if not line:
            return
        if b"\x00" in line:
            self.malformed = Uncertain("MALFORMED_FRAME", "a NUL inside a log line")
            return
        try:
            m = _FRAME.match(line.decode("utf-8"))
        except UnicodeDecodeError:
            m = None
        if not m:
            self.malformed = Uncertain("MALFORMED_FRAME", "a line without logplex framing")
        elif m["dyno"] != self.run:
            self.malformed = Uncertain("MISMATCHED_RUN", f"a line for {m['dyno']}, not {self.run}")
        else:
            (self.app if m["source"] == "app" else self.heroku).append(m["msg"])

    def end(self) -> None:
        self.ended = True
        if self.partial and not self.malformed:
            self.malformed = Uncertain("MALFORMED_FRAME", "the stream ended inside a line")

    @property
    def partial(self) -> bool:
        return self._consumed < len(self.raw)

    def exits(self) -> list[int]:
        return [int(m["status"]) for m in map(_EXITED.match, self.heroku) if m]

    def ready(self) -> bool:
        """Everything a verdict needs has arrived (or nothing more can help)."""
        if self.malformed:
            return True
        exits = self.exits()
        if not exits:
            return False
        if len(exits) > 1 or exits[0] not in (0, 1, 2) or _TRACEBACK in self.app:
            return True
        if exits[0] == 2:
            return bool(self.app)
        return "}" in self.app


# ── the verdict ───────────────────────────────────────────────────────────────


def _no_dupes(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise Uncertain("MALFORMED_JSON", "a JSON object repeats a key")
    return dict(pairs)


def _bad_constant(name):
    raise Uncertain("MALFORMED_JSON", f"a JSON {name} constant")


def _loads(text: str):
    try:
        return json.loads(text, object_pairs_hook=_no_dupes, parse_constant=_bad_constant)
    except ValueError:
        raise Uncertain("MALFORMED_JSON", "the printed document is not JSON") from None


def script_digest(script, planned: list[dict]) -> str:
    """The script's OWN ``plan_digest`` code over the printed legs: only the
    approved-version hash it would compute from the row is supplied from the
    printed ``approved_before_sha256``."""
    scope = dict(script.plan_digest.__globals__)
    scope["approved_sha256"] = lambda g: g.approved_before_sha256
    fn = types.FunctionType(script.plan_digest.__code__, scope, "plan_digest")
    return fn([types.SimpleNamespace(**p) for p in planned])


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def judge_plan(doc, status: int, script, kms) -> int:
    """A complete exit-0/1 document, held to the script's own output contract."""
    if not isinstance(doc, dict):
        raise Uncertain("SCHEMA", "the document is not an object")
    want = PLAN_KEYS | ({"stop"} if status == 1 else set())
    if set(doc) != want:
        raise Uncertain("SCHEMA", f"keys {sorted(set(doc) ^ want)} differ from a plan-mode {status} output")
    if doc["event_ticker"] != script.EVENT_TICKER or doc["archive_sha256"] != script.ARCHIVE_SHA256:
        raise Uncertain("SCHEMA", "the document names another event or archive")
    planned, refused = doc["planned"], doc["refused"]
    if not isinstance(planned, list) or not isinstance(refused, dict):
        raise Uncertain("SCHEMA", "planned/refused have the wrong shape")
    archive = {leg["ticker"]: leg for leg in script.load_archive_legs()}
    ids, tickers = set(), set()
    for p in planned:
        if not isinstance(p, dict) or set(p) != LEG_KEYS:
            raise Uncertain("SCHEMA", "a planned leg has the wrong keys")
        if not (_is_int(p["outcome_id"]) and isinstance(p["ticker"], str)
                and isinstance(p["is_winner"], bool)
                and isinstance(p["approved_before_sha256"], str)
                and _HEX64.fullmatch(p["approved_before_sha256"])):
            raise Uncertain("SCHEMA", "a planned leg has a wrongly typed field")
        if p["outcome_id"] in ids or p["ticker"] in tickers:
            raise Uncertain("SCHEMA", "a planned leg repeats")
        ids.add(p["outcome_id"])
        tickers.add(p["ticker"])
        leg = archive.get(p["ticker"])
        if (leg is None or p["venue_status"] != leg.get("status")
                or p["venue_result"] != leg.get("result")
                or kms.gradeable_winner(leg.get("status"), leg.get("result")) is not p["is_winner"]):
            raise Uncertain("ARCHIVE_MISMATCH", f"planned leg {p['outcome_id']} is not what the retained archive grades")
    for reason, members in refused.items():
        if (reason not in REFUSED_REASONS or not isinstance(members, list) or not members
                or not all(_is_int(i) for i in members) or ids.intersection(members)):
            raise Uncertain("SCHEMA", "refused has the wrong shape")
    if not (isinstance(doc["plan_digest"], str) and _HEX16.fullmatch(doc["plan_digest"])):
        raise Uncertain("SCHEMA", "plan_digest is not a 16-hex digest")
    if script_digest(script, planned) != doc["plan_digest"]:
        raise Uncertain("DIGEST_INVALID", "plan_digest does not match the printed legs")
    n = len(planned)
    if status == 0:
        if n != script.EXPECTED_PLAN:
            raise Uncertain("SCHEMA", f"an exit-0 plan of {n} legs; the script stops unless {script.EXPECTED_PLAN}")
        return ADMISSIBLE
    stop = (f"plan holds {n} legs, expected {script.EXPECTED_PLAN}: the stored "
            "legs moved since the retained read; do not apply this plan")
    if n == script.EXPECTED_PLAN or doc["stop"] != stop:
        raise Uncertain("SCHEMA", "an exit-1 document that is not the script's own stop")
    return STOP


def judge(log: LogRead, script, kms) -> tuple[int, dict]:
    """What the run printed, or why nothing it printed can pay."""
    if log.malformed:
        raise log.malformed
    if log.error:
        raise log.error  # the read stopped before its evidence was whole
    starts = [m["cmd"] for m in map(_STARTING.match, log.heroku) if m]
    if len(starts) != 1 or starts[0] != COMMAND:
        raise Uncertain("MISMATCHED_COMMAND", f"{len(starts)} start lines; exactly one for the exact command is required")
    exits = log.exits()
    if len(exits) != 1:
        raise Uncertain("NO_TERMINAL" if not exits else "AMBIGUOUS_TERMINAL",
                        f"{len(exits)} exit lines for {log.run}")
    status = exits[0]
    known = (_STARTING, _STATE, _EXITED)
    if any(not any(p.match(msg) for p in known) for msg in log.heroku):
        raise Uncertain("UNRECOGNIZED_LIFECYCLE", "a platform line this reader does not recognize")
    if status not in (0, 1, 2):
        raise Uncertain("EXIT_UNKNOWN", f"the run exited {status}")
    if _TRACEBACK in log.app:
        raise Uncertain("TRACEBACK", f"the run exited {status} with a traceback, not a script result")
    if status == 2:
        if len(log.app) != 1:
            raise Uncertain("EXTRA_TEXT", "an exit-2 run printed other than one refusal line")
        doc = _loads(log.app[0])
        if not (isinstance(doc, dict) and set(doc) == {"refused"} and isinstance(doc["refused"], str)
                and json.dumps(doc) == log.app[0]):
            raise Uncertain("SCHEMA", "an exit-2 line that is not the script's own refusal")
        return REFUSAL, {"exit_status": 2, "refusal": doc["refused"]}
    if not log.app or log.app[0] != "{" or log.app[-1] != "}" or log.app.count("}") != 1:
        raise Uncertain("EXTRA_TEXT" if "}" in log.app else "INCOMPLETE_JSON",
                        "the app output is not exactly one complete printed document")
    text = "\n".join(log.app)
    doc = _loads(text)
    if json.dumps(doc, indent=2, default=str) != text:
        raise Uncertain("NONCANONICAL", "the document is not byte-for-byte the script's own print")
    code = judge_plan(doc, status, script, kms)
    return code, {"exit_status": status, "plan_digest": doc["plan_digest"],
                  "planned_count": len(doc["planned"]), "document": doc}


# ── the read ──────────────────────────────────────────────────────────────────


def read_plan(launcher: bytes, netrc_path: Path, *, connector: Optional[Callable] = None,
              deadline_s: float = DEADLINE_S, cap: int = CAP_BYTES) -> dict:
    """One read, end to end. Never raises; the receipt says what happened."""
    budget = Budget(deadline_s, cap)
    connector = connector or connect_tls
    receipt: dict = {
        "tool": "tools/plan1853/reader.py",
        "reader_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "script_sha256": SCRIPT_SHA256, "kms_sha256": KMS_SHA256,
        "app": APP, "command": COMMAND,
        "launcher_sha256": hashlib.sha256(launcher).hexdigest(),
        "deadline_s": deadline_s, "cap_bytes": cap,
        "apply_authorized": False,  # no verdict here authorizes a backup, apply or restore
        "pays_plan_gate": False,
        "remote_run_state": "not observed by a timeout: a reader timeout does not prove the run stopped",
    }
    log: Optional[LogRead] = None
    try:
        script, kms = load_pinned()
        run = parse_launcher(launcher)
        receipt["run"] = run
        token = read_netrc_token(netrc_path, budget)
        url = open_log_session(run, token, budget, connector)
        host, target = log_endpoint(url)
        receipt["log_host"] = host
        log = stream_log(host, target, run, budget, connector)
        code, found = judge(log, script, kms)
        budget.remaining()  # a verdict reached after the deadline is late
        receipt.update(found)
        receipt["verdict"], receipt["reason"] = VERDICTS[code], VERDICTS[code]
        receipt["pays_plan_gate"] = code == ADMISSIBLE
        if code == STOP:
            receipt["stop_population_must_never_be_applied"] = True
    except Uncertain as u:
        code = UNCERTAIN
        receipt.update(verdict=VERDICTS[UNCERTAIN], reason=u.reason, detail=u.detail)
    except Exception as exc:  # noqa: BLE001 - a harness failure is a verdict too
        code = UNCERTAIN
        receipt.update(verdict=VERDICTS[UNCERTAIN], reason="HARNESS", detail=type(exc).__name__)
    receipt["exit_code"] = code
    receipt["elapsed_s"] = round(budget.elapsed(), 3)
    receipt["bytes"] = {"used": budget.used, "by_stage": dict(budget.by_stage)}
    if log is not None:
        receipt["log"] = {
            "raw_b64": base64.b64encode(bytes(log.raw)).decode(),
            "raw_sha256": hashlib.sha256(bytes(log.raw)).hexdigest(),
            "app_lines": len(log.app), "platform_lines": list(log.heroku),
            "ended": log.ended, "partial_tail": log.partial,
        }
    return receipt


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: {message}", file=sys.stderr)
        raise SystemExit(UNCERTAIN)


def main(argv=None) -> int:
    p = _Parser(description="Read one #1853 no-flag plan run's output (read-only).")
    p.add_argument("--launcher", required=True, type=Path, help="the saved run:detached output")
    p.add_argument("--receipt", required=True, type=Path, help="a NEW file for the receipt")
    args = p.parse_args(argv)
    try:
        fd = os.open(args.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        print(f"UNCERTAIN receipt not created ({type(exc).__name__})", file=sys.stderr)
        return UNCERTAIN
    try:
        with open(args.launcher, "rb") as fh:
            launcher = fh.read(LAUNCHER_MAX_BYTES + 1)
    except OSError:
        launcher = b""
    netrc = Path(os.environ.get("HOME", "/nonexistent")) / ".netrc"
    receipt = read_plan(launcher, netrc)
    with os.fdopen(fd, "w") as fh:
        json.dump(receipt, fh, indent=2, sort_keys=True)
    print(f"{receipt['verdict']} {receipt['reason']} exit={receipt['exit_code']} receipt={args.receipt}")
    return receipt["exit_code"]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - never let Python's 1 read as STOP_RESULT
        raise SystemExit(UNCERTAIN)
