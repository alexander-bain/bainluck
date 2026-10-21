#!/usr/bin/env python3
"""#1089 — read ONE archived Kalshi contract, once, and nothing else.

PILLAR: TRUTH. SHIP: settled NHL player questions use the correct game's
pregame forecast and result.

WHAT IT DOES. It makes at most one public GET to exactly

    https://api.elections.kalshi.com/trade-api/v2/historical/markets/KXNHLGOAL-26JUN11VGKCAR-VGKWKARLSSON71-2

and writes what came back: the complete raw response, its status, observation
time, byte count and digest, and the returned contract's own labels and rules,
verbatim. That is Measurement 022's exact contract (Root, 2026-10-20). The URL,
host, ticker, request bytes, deadline and cap are constants below; no argument
changes them.

WHAT IT NEVER DOES. No redirect is followed, no request is retried, no second
address, page, sibling, search, candle or follow-on request exists. No
credential is read: no netrc, no key, no Authorization header, and the network
child runs with an empty environment (two trust-store variables excepted). No
proxy is used: the child opens its own socket, so proxy variables are ignored
and an operator whose only egress is an HTTP proxy cannot use it. It never
derives an event identity by splitting the ticker, never selects a game by name
or time, and never decides occurrence: that is the semantic review's.

THE ATTEMPT FENCE. Before anything is sent, the reader creates
``ATTEMPT-STARTED`` exclusively in the one contract directory, writes and
fsyncs it and its directory. It never removes or overwrites it. If the marker
already exists, nothing is sent and nothing is written: exit 40,
ATTEMPT_SPENT. If it cannot be established, nothing is sent: exit 20, HOLD.
The network child refuses to run unless it inherits the open marker from the
parent that created it, so the child cannot be run alone to bypass the fence.

THE ENVELOPE. One 15 s deadline from the top of ``main``, read on the awake,
sleep-counting and wall clocks (the largest wins). The network work (trust
store, name resolution, connect, TLS, request, response) runs in a child
process in its own session; at 14 s the parent SIGKILLs that session, so no
network wait, including ``getaddrinfo``, can outlive the deadline. The last
second is reserved for the parent's local writes. The clock is read again after
the raw write and after each receipt step; a result whose step returns at or
past 15 s is rewritten NO_RESULT LATE_FINALIZATION, so whenever control returns
the exit code and the receipt agree. One 262,144-byte cap covers every byte of
the response taken in (status line, headers, chunk framing, body). Each read
asks for at most one byte past what is left, so an oversized response is
detected without being taken in whole.

WHAT THE SOURCE CANNOT BOUND. The parent's own local waits: creating and
fsyncing the marker, creating the receipt and raw files, spawning the child,
reaping it after SIGKILL, and the final writes. A local wait no timer can
interrupt is why the exact-response gate is paid only by exit 0 TOGETHER with
a receipt that says ``pays_exact_response_gate: true`` — never by the receipt
alone. The deadline starts at the top of ``main``; interpreter start-up and
imports precede it. A hard wall around the whole client still needs an
external bounded invocation at admission; this file does not prove the
operator has one.

WHAT PAYS. Exit 0 OBSERVED requires all of: the child's response complete by
its own HTTP framing (Content-Length or a terminated chunked body; a body
delimited only by the connection closing must close cleanly), at most 262,144
bytes, HTTP 200 with no content encoding, a strict JSON object holding one
``market`` object whose ``ticker`` is exactly the requested ticker, a
non-empty ``rules_primary``, and every step inside the deadline. It pays only
"one complete exact response was observed". It never pays occurrence, a
cutoff, a relink or a grade. Exit codes:

    0  OBSERVED       one complete exact response; semantic review still owed
    20 HOLD           nothing was sent (bad directory, fence not established)
    30 NO_RESULT      everything else, including 404, timeout, truncation,
                      overflow, identity mismatch and missing rules. A 404 or
                      an empty body never proves the contract does not exist
    40 ATTEMPT_SPENT  the marker already existed; nothing was sent or written

Python's own exit codes (1 for an uncaught exception, 2 for a usage error) are
never a verdict here.

Usage (attended; this file grants no admission):

    python3 tools/contract1089/reader.py --contract-dir <.../calibration-1089-plan-admission-20261018/ONE-ARCHIVED-CONTRACT> --check
    python3 tools/contract1089/reader.py --contract-dir <same> --send-the-one-request

``--check`` sends nothing and writes nothing; it reports whether a send would
be admitted by the local fence.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
import os
import re
import select
import signal
import socket
import ssl
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

HOST = "api.elections.kalshi.com"
PORT = 443
TICKER = "KXNHLGOAL-26JUN11VGKCAR-VGKWKARLSSON71-2"
PATH = f"/trade-api/v2/historical/markets/{TICKER}"
URL = f"https://{HOST}{PATH}"
REQUEST = (
    f"GET {PATH} HTTP/1.1\r\n"
    f"Host: {HOST}\r\n"
    "User-Agent: bainluck-contract1089-reader\r\n"
    "Accept: application/json\r\n"
    "Accept-Encoding: identity\r\n"
    "Connection: close\r\n"
    "\r\n"
).encode("ascii")

DEADLINE_S = 15.0
FINALIZE_RESERVE_S = 1.0  # the parent's local writes; the network child dies at 14 s
CAP_BYTES = 262_144
MARKER_MAX_BYTES = 4_096

CONTRACT_DIR_TAIL = ("calibration-1089-plan-admission-20261018", "ONE-ARCHIVED-CONTRACT")
MARKER_NAME = "ATTEMPT-STARTED"
RAW_NAME = "RAW-RESPONSE.bin"
RECEIPT_NAME = "READER-RECEIPT.json"
TRUST_ENV = ("SSL_CERT_FILE", "SSL_CERT_DIR")

OBSERVED, HOLD, NO_RESULT, ATTEMPT_SPENT = 0, 20, 30, 40
VERDICTS = {OBSERVED: "OBSERVED", HOLD: "HOLD", NO_RESULT: "NO_RESULT",
            ATTEMPT_SPENT: "ATTEMPT_SPENT"}

# The network child's exit codes. Hints for the receipt; the parent's own
# framing, byte and clock checks decide.
PUMP_CLEAN_EOF, PUMP_RAGGED_EOF, PUMP_TIMEOUT = 0, 3, 4
PUMP_RESOLVE, PUMP_CONNECT, PUMP_TLS, PUMP_SEND, PUMP_RECV = 5, 6, 7, 8, 9
PUMP_OVERSIZED, PUMP_FENCE, PUMP_HARNESS = 10, 11, 12
PUMP_CODES = {
    PUMP_CLEAN_EOF: "clean_eof", PUMP_RAGGED_EOF: "eof_without_tls_close",
    PUMP_TIMEOUT: "timeout", PUMP_RESOLVE: "resolve_failed",
    PUMP_CONNECT: "connect_failed", PUMP_TLS: "tls_failed", PUMP_SEND: "send_failed",
    PUMP_RECV: "recv_failed", PUMP_OVERSIZED: "oversized", PUMP_FENCE: "fence_refused",
    PUMP_HARNESS: "harness",
}

#: The returned contract's own labels and rules, reported verbatim when supplied.
NAMED_FIELDS = ("ticker", "event_ticker", "title", "subtitle", "yes_sub_title",
                "no_sub_title", "rules_primary", "rules_secondary")
#: Any other market field whose NAME looks like a time, date, timezone,
#: occurrence, postponement or fixture reference: reported verbatim, judged by
#: nobody here.
_TIME_OR_FIXTURE_KEY = re.compile(
    r"(_time|_ts|_date|occurr|postpon|timezone|tz|fixture|game|start|schedul)", re.I)
TIMESTAMP_NOTE = ("trading open/close and expiration timestamps are not actual puck-drop "
                  "evidence; occurrence is decided by the semantic review, never by this reader")
_DIGITS = re.compile(r"[0-9]+")


class Refusal(Exception):
    """A result that pays nothing. ``reason`` is a fixed code; ``detail`` never
    carries an exception's own text."""

    def __init__(self, reason: str, detail: str = "", code: int = NO_RESULT) -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail, self.code = reason, detail, code


class Incomplete(Exception):
    """The response's own framing says more bytes are owed."""


def _continuous() -> float:
    # CLOCK_MONOTONIC counts system sleep on macOS; time.monotonic does not.
    clock = getattr(time, "CLOCK_MONOTONIC", None)
    return time.clock_gettime(clock) if clock is not None else time.monotonic()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class Clock:
    """The one deadline every stage draws on."""

    def __init__(self, deadline_s: float = DEADLINE_S) -> None:
        self.deadline_s = deadline_s
        self._t0 = (time.monotonic(), _continuous(), time.time())

    def elapsed(self) -> float:
        a, c, w = self._t0
        return max(time.monotonic() - a, _continuous() - c, time.time() - w, 0.0)

    def late(self) -> bool:
        return self.elapsed() >= self.deadline_s

    def network_left(self) -> float:
        return self.deadline_s - FINALIZE_RESERVE_S - self.elapsed()


# ── the contract directory and the fence ─────────────────────────────────────


def contract_dir_ok(path: Path) -> Optional[str]:
    """``None`` when ``path`` is the one contract directory, else why not."""
    if not path.is_absolute() or os.path.realpath(path) != str(path):
        return "the contract directory must be an absolute path with no symlink or '..' in it"
    if tuple(path.parts[-2:]) != CONTRACT_DIR_TAIL:
        return f"the contract directory must end in {'/'.join(CONTRACT_DIR_TAIL)}"
    try:
        st = os.lstat(path)
    except OSError as exc:
        return f"the contract directory is unavailable ({type(exc).__name__})"
    if not stat.S_ISDIR(st.st_mode):
        return "the contract directory is not a directory (a symlink is refused)"
    if st.st_uid != os.getuid():
        return "the contract directory is not owned by this user"
    if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return "the contract directory is writable by others"
    return None


def fence_state(cdir: Path) -> dict:
    return {name: os.path.lexists(cdir / name) for name in (MARKER_NAME, RAW_NAME, RECEIPT_NAME)}


def _fsync_dir(cdir: Path) -> None:
    fd = os.open(cdir, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def establish_marker(cdir: Path, reader_sha: str) -> Path:
    """Create ATTEMPT-STARTED exclusively and make it durable, or say why not.

    An existing marker is ATTEMPT_SPENT. A marker created but not made durable
    stays where it is (it is never removed) and the result is HOLD: the attempt
    is then spent with no request sent, which is the safe side."""
    path = cdir / MARKER_NAME
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise Refusal("ATTEMPT_SPENT", "ATTEMPT-STARTED already exists; no request is sent",
                      ATTEMPT_SPENT) from None
    except OSError as exc:
        raise Refusal("FENCE_NOT_ESTABLISHED",
                      f"ATTEMPT-STARTED could not be created ({type(exc).__name__})", HOLD) from None
    body = json.dumps({
        "attempt": "#1089 one archived contract, Measurement 022 exact contract",
        "url": URL, "method": "GET", "created_at": _utc(), "pid": os.getpid(),
        "reader_sha256": reader_sha,
        "rule": "never removed or overwritten; its presence prohibits another attempt",
    }, sort_keys=True).encode()
    try:
        view = memoryview(body)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    except OSError as exc:
        raise Refusal("FENCE_NOT_ESTABLISHED",
                      f"ATTEMPT-STARTED was created but not made durable ({type(exc).__name__}); "
                      "it stays, and no request is sent", HOLD) from None
    finally:
        os.close(fd)
    try:
        _fsync_dir(cdir)
    except OSError as exc:
        raise Refusal("FENCE_NOT_ESTABLISHED",
                      f"the contract directory could not be synced ({type(exc).__name__}); "
                      "ATTEMPT-STARTED stays, and no request is sent", HOLD) from None
    return path


def _create_exclusive(path: Path) -> int:
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)


# ── the network child ────────────────────────────────────────────────────────


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def _check_inherited_marker(fd: int, path: Path) -> bool:
    """The child runs only under the parent that holds the marker it created."""
    try:
        if path.name != MARKER_NAME or contract_dir_ok(path.parent) is not None:
            return False
        held, named = os.fstat(fd), os.lstat(path)
        if not stat.S_ISREG(held.st_mode) or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
            return False
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, MARKER_MAX_BYTES + 1)
        if len(raw) > MARKER_MAX_BYTES:
            return False
        doc = json.loads(raw)
        return isinstance(doc, dict) and doc.get("pid") == os.getppid() and doc.get("url") == URL
    except (OSError, ValueError):
        return False


def open_tls(seconds: float, *, getaddrinfo=socket.getaddrinfo, context=None):
    """Trust store, FIRST address, connect, handshake — every wait sized from the
    child's own share of the deadline. Returns ``(socket, left)`` or raises
    ``_PumpExit``."""
    end = _continuous() + seconds

    def left() -> float:
        rem = end - _continuous()
        if rem <= 0:
            raise _PumpExit(PUMP_TIMEOUT)
        return rem

    try:
        ctx = context or ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    except Exception:  # noqa: BLE001 - reported by code only
        raise _PumpExit(PUMP_TLS) from None
    left()
    try:
        infos = getaddrinfo(HOST, PORT, type=socket.SOCK_STREAM)
        family, kind, proto, _, addr = infos[0]
    except Exception:  # noqa: BLE001
        raise _PumpExit(PUMP_RESOLVE) from None
    raw = socket.socket(family, kind, proto)
    try:
        try:
            raw.settimeout(left())
            raw.connect(addr)
        except (TimeoutError, socket.timeout):
            raise _PumpExit(PUMP_TIMEOUT) from None
        except OSError:
            raise _PumpExit(PUMP_CONNECT) from None
        try:
            raw.settimeout(left())
            tls = ctx.wrap_socket(raw, server_hostname=HOST, suppress_ragged_eofs=False)
        except (TimeoutError, socket.timeout):
            raise _PumpExit(PUMP_TIMEOUT) from None
        except (ssl.SSLError, ssl.CertificateError, OSError):
            raise _PumpExit(PUMP_TLS) from None
    except BaseException:
        raw.close()
        raise
    return tls, left


class _PumpExit(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def pump(seconds: float, out_fd: int, *, opener: Callable = open_tls) -> int:
    """Send REQUEST once on one connection and copy every received byte to
    ``out_fd`` as it arrives, never asking for more than one byte past the cap.
    Returns the child's exit code."""
    try:
        tls, left = opener(seconds)
    except _PumpExit as e:
        return e.code
    try:
        try:
            tls.settimeout(left())
            tls.sendall(REQUEST)
        except _PumpExit as e:
            return e.code
        except (TimeoutError, socket.timeout):
            return PUMP_TIMEOUT
        except OSError:
            return PUMP_SEND
        got = 0
        while True:
            try:
                tls.settimeout(left())
                chunk = tls.recv(min(65_536, CAP_BYTES + 1 - got))
            except _PumpExit as e:
                return e.code
            except ssl.SSLEOFError:
                return PUMP_RAGGED_EOF
            except (TimeoutError, socket.timeout):
                return PUMP_TIMEOUT
            except OSError:
                return PUMP_RECV
            if not chunk:
                return PUMP_CLEAN_EOF
            _write_all(out_fd, chunk)
            got += len(chunk)
            if got > CAP_BYTES:
                return PUMP_OVERSIZED
    finally:
        try:
            tls.close()
        except OSError:
            pass


def pump_main(argv: list[str]) -> int:
    """The child's entry. Refuses unless it inherits the parent's marker."""
    try:
        fd, path, seconds = int(argv[0]), Path(argv[1]), float(argv[2])
    except (IndexError, ValueError):
        return PUMP_FENCE
    if len(argv) != 3 or not (0 < seconds <= DEADLINE_S) or not _check_inherited_marker(fd, path):
        return PUMP_FENCE
    os.close(fd)
    return pump(seconds, 1)


# ── the parent's read of the child ───────────────────────────────────────────


def child_env() -> dict:
    """An empty environment, except the interpreter's trust-store variables."""
    return {k: os.environ[k] for k in TRUST_ENV if k in os.environ}


def spawn_pump(marker_fd: int, marker_path: Path, seconds: float):
    argv = [sys.executable, "-I", str(Path(__file__).resolve()), "--pump",
            str(marker_fd), str(marker_path), f"{seconds:.3f}"]
    return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, close_fds=True, pass_fds=(marker_fd,),
                            start_new_session=True, env=child_env())


class Transfer:
    """What the parent took from the child, and how the transfer ended."""

    def __init__(self) -> None:
        self.raw = bytearray()
        self.eof = False
        self.ended_by: Optional[str] = None
        self.pump_exit: Optional[int] = None
        self.observed_at: Optional[str] = None
        self.reaped = False


def _kill_and_reap(proc, clock: Clock, transfer: Transfer) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    # Reaping a SIGKILLed child is a local wait; it gets what is left of the
    # whole deadline and no more.
    try:
        proc.wait(timeout=max(clock.deadline_s - clock.elapsed(), 0.05))
        transfer.reaped = True
    except subprocess.TimeoutExpired:
        transfer.reaped = False
    rc = proc.returncode
    if rc is not None and transfer.pump_exit is None:
        transfer.pump_exit = rc


def transfer_from(proc, clock: Clock) -> Transfer:
    """Read the child's stdout until the response is complete by its own
    framing, the stream ends, the cap is passed, or the network share of the
    deadline is gone. The child's whole session is SIGKILLed on the way out."""
    t = Transfer()
    fd = proc.stdout.fileno()
    os.set_blocking(fd, False)
    try:
        while True:
            left = clock.network_left()
            if left <= 0:
                t.ended_by = "deadline"
                break
            ready, _, _ = select.select([fd], [], [], left)
            if not ready:
                continue
            try:
                chunk = os.read(fd, CAP_BYTES + 1 - len(t.raw))
            except BlockingIOError:
                continue
            if not chunk:
                t.eof, t.ended_by = True, "eof"
                t.observed_at = _utc()
                break
            t.raw += chunk
            t.observed_at = _utc()
            if len(t.raw) > CAP_BYTES:
                t.ended_by = "oversized"
                break
            try:
                parse_response(bytes(t.raw), clean_close=False)
            except Incomplete:
                continue
            except Refusal:
                pass  # malformed is final; it is judged below
            t.ended_by = "framing"
            break
    finally:
        if t.eof:
            # The child closed its stdout; let it exit on its own, within the
            # network share, so its exit code (clean or ragged close) is read.
            try:
                proc.wait(timeout=max(clock.network_left(), 0.0))
                t.pump_exit, t.reaped = proc.returncode, True
            except subprocess.TimeoutExpired:
                pass
        if not t.reaped:
            _kill_and_reap(proc, clock, t)
        try:
            proc.stdout.close()
        except OSError:
            pass
    return t


# ── the response ─────────────────────────────────────────────────────────────


class _Kept(io.BytesIO):
    def close(self) -> None:  # http.client closes its file; the offset must survive
        pass


class _Replay:
    def __init__(self, f: io.BytesIO) -> None:
        self._f = f

    def makefile(self, *a, **k):
        return self._f


def parse_response(raw: bytes, *, clean_close: bool):
    """``(status, headers, body)`` of one complete HTTP/1.x response in ``raw``.

    Raises ``Incomplete`` while the response's own framing says bytes are owed,
    and ``Refusal`` for anything malformed, ambiguous or extra. A body framed
    only by the connection closing is complete only on a clean close."""
    if b"\r\n\r\n" not in raw:
        raise Incomplete()
    f = _Kept(raw)
    resp = http.client.HTTPResponse(_Replay(f))
    try:
        resp.begin()
    except http.client.IncompleteRead:
        raise Incomplete() from None
    except (http.client.HTTPException, ValueError):
        raise Refusal("MALFORMED_HTTP", "the status line or headers do not parse") from None
    if resp.version not in (10, 11):
        raise Refusal("MALFORMED_HTTP", "not an HTTP/1.x response")
    te = resp.msg.get_all("Transfer-Encoding") or []
    cl = resp.msg.get_all("Content-Length") or []
    ce = resp.msg.get_all("Content-Encoding") or []
    if len(te) > 1 or len(cl) > 1 or (te and cl):
        raise Refusal("MALFORMED_HTTP", "ambiguous framing headers")
    if te and te[0].strip().lower() != "chunked":
        raise Refusal("MALFORMED_HTTP", "a transfer coding other than chunked")
    if cl and not _DIGITS.fullmatch(cl[0].strip()):
        raise Refusal("MALFORMED_HTTP", "a Content-Length that is not a number")
    if any(v.strip().lower() not in ("", "identity") for v in ce):
        raise Refusal("UNEXPECTED_ENCODING", "a content encoding was applied")
    try:
        body = resp.read()
    except http.client.IncompleteRead:
        raise Incomplete() from None
    except (http.client.HTTPException, ValueError):
        raise Refusal("MALFORMED_HTTP", "the body framing does not parse") from None
    consumed = f.tell()
    if te:
        if not raw[:consumed].endswith(b"\r\n\r\n"):
            raise Incomplete()  # the trailer section is not yet terminated
    elif not cl and resp.status not in (204, 304) and not (100 <= resp.status < 200):
        if not clean_close:
            raise Incomplete()  # framed only by close: wait for it, and it must be clean
    if consumed != len(raw):
        raise Refusal("EXTRA_BYTES", f"{len(raw) - consumed} bytes follow the complete response")
    headers = [[k, v] for k, v in resp.msg.items()]
    return resp.status, headers, body


def _no_dupes(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise Refusal("MALFORMED_JSON", "a JSON object repeats a key")
    return dict(pairs)


def _bad_constant(name):
    raise Refusal("MALFORMED_JSON", f"a JSON {name} constant")


def judge_body(body: bytes) -> dict:
    """The returned contract, held to the exact-ticker and rules checks. Fields
    are reported verbatim; nothing here interprets them."""
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise Refusal("MALFORMED_JSON", "the body is not UTF-8") from None
    try:
        doc = json.loads(text, object_pairs_hook=_no_dupes, parse_constant=_bad_constant)
    except ValueError:
        raise Refusal("MALFORMED_JSON", "the body is not one complete JSON document") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("market"), dict):
        raise Refusal("SCHEMA", "the body is not an object holding one market object")
    market = doc["market"]
    returned = {}
    for name in NAMED_FIELDS:
        if name in market:
            value = market[name]
            if value is not None and not isinstance(value, str):
                raise Refusal("SCHEMA", f"market.{name} is neither a string nor null")
            returned[name] = value
    if returned.get("ticker") != TICKER:
        raise Refusal("IDENTITY_MISMATCH", "the returned ticker is not exactly the requested ticker")
    if not (isinstance(returned.get("rules_primary"), str) and returned["rules_primary"].strip()):
        raise Refusal("RULES_MISSING", "the returned contract carries no rules_primary")
    others = {k: market[k] for k in sorted(market)
              if k not in NAMED_FIELDS and _TIME_OR_FIXTURE_KEY.search(k)}
    return {"returned": returned, "time_and_fixture_fields": others,
            "top_level_keys": sorted(doc), "market_keys": sorted(market)}


def judge(t: Transfer, clock: Clock) -> dict:
    """What came back, or why nothing that came back can pay."""
    raw = bytes(t.raw)
    if t.ended_by == "oversized" or len(raw) > CAP_BYTES:
        raise Refusal("OVERSIZED", f"the response passed the {CAP_BYTES}-byte cap")
    if t.ended_by == "deadline":
        raise Refusal("DEADLINE", "the network share of the 15 s deadline passed; "
                      "the child was killed")
    if not raw:
        raise Refusal("NO_RESPONSE_BYTES",
                      f"the child returned no bytes ({PUMP_CODES.get(t.pump_exit, t.pump_exit)}); "
                      "this is not an empty provider response")
    clean = t.eof and t.pump_exit == PUMP_CLEAN_EOF
    try:
        status, headers, body = parse_response(raw, clean_close=clean)
    except Incomplete:
        raise Refusal("TRUNCATED", "the response ended before its own framing was complete "
                      f"({PUMP_CODES.get(t.pump_exit, t.pump_exit)})") from None
    found = {"http_status": status, "headers": headers, "body_bytes": len(body),
             "body_sha256": hashlib.sha256(body).hexdigest()}
    if status != 200:
        detail = f"HTTP {status}"
        if status == 404:
            detail += "; a 404 does not prove the contract never existed"
        elif 300 <= status < 400:
            detail += "; redirects are never followed"
        raise Refusal("HTTP_STATUS", detail, NO_RESULT) from _Found(found)
    try:
        found.update(judge_body(body))
    except Refusal as r:
        raise r from _Found(found)
    if clock.late():
        raise Refusal("DEADLINE", "the response was judged after the deadline") from _Found(found)
    return found


class _Found(Exception):
    """Carries what was established before a refusal, for the receipt."""

    def __init__(self, found: dict) -> None:
        super().__init__("found")
        self.found = found


# ── the read ─────────────────────────────────────────────────────────────────


def reader_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def base_receipt(clock: Clock, sha: str) -> dict:
    return {
        "tool": "tools/contract1089/reader.py", "reader_sha256": sha,
        "method": "GET", "url": URL, "requested_ticker": TICKER,
        "deadline_s": clock.deadline_s, "cap_bytes": CAP_BYTES,
        "pays_exact_response_gate": False,
        "occurrence_evidence": "NOT DECIDED BY THIS READER: semantic review owed",
        "derived_identity": None,  # the ticker is never split into an event identity
        "timestamp_note": TIMESTAMP_NOTE,
    }


def read_once(marker_path: Path, clock: Clock, sha: str, *,
              spawn: Callable = spawn_pump) -> tuple[dict, bytes]:
    """The one request, end to end. Never raises an ordinary error; the receipt
    says what happened. The marker is already durable when this is called."""
    receipt = base_receipt(clock, sha)
    receipt["marker"] = str(marker_path)
    receipt["request_sent"] = "no"
    t: Optional[Transfer] = None
    marker_fd = -1
    try:
        marker_fd = os.open(marker_path, os.O_RDONLY | os.O_NOFOLLOW)
        receipt["marker_sha256"] = hashlib.sha256(os.read(marker_fd, MARKER_MAX_BYTES + 1)).hexdigest()
        if clock.network_left() <= 0:
            raise Refusal("DEADLINE", "the deadline passed before the request", HOLD)
        receipt["request_started_at"] = _utc()
        proc = spawn(marker_fd, marker_path, clock.network_left())
        receipt["request_sent"] = "possible: the network child was started"
        os.close(marker_fd)
        marker_fd = -1
        t = transfer_from(proc, clock)
        found = judge(t, clock)
        receipt.update(found)
        code = OBSERVED
        receipt.update(verdict=VERDICTS[code], reason=VERDICTS[code])
    except Refusal as r:
        code = r.code
        cause = r.__cause__
        if isinstance(cause, _Found):
            receipt.update(cause.found)
        receipt.update(verdict=VERDICTS[code], reason=r.reason, detail=r.detail)
    except Exception as exc:  # noqa: BLE001 - a harness failure is a verdict too
        code = NO_RESULT
        receipt.update(verdict=VERDICTS[code], reason="HARNESS", detail=type(exc).__name__)
    finally:
        if marker_fd >= 0:
            os.close(marker_fd)
    if code == HOLD:
        receipt["request_sent"] = "no"
    receipt["exit_code"] = code
    if t is not None:
        receipt.update(
            response_observed_at=t.observed_at, transfer_ended_by=t.ended_by,
            child_exit=PUMP_CODES.get(t.pump_exit, t.pump_exit), child_reaped=t.reaped,
            raw_name=RAW_NAME, raw_bytes=len(t.raw),
            raw_sha256=hashlib.sha256(bytes(t.raw)).hexdigest(),
        )
        if not t.reaped and code == OBSERVED:
            code = NO_RESULT
            receipt.update(verdict=VERDICTS[code], reason="CHILD_NOT_REAPED",
                           detail="the network child was not reaped inside the deadline",
                           exit_code=code)
    return receipt, (bytes(t.raw) if t is not None else b"")


# ── finalization ─────────────────────────────────────────────────────────────


def _rewrite(fd: int, body: bytes) -> None:
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    _write_all(fd, body)


def _serialize(receipt: dict) -> bytes:
    return json.dumps(receipt, indent=2, sort_keys=True).encode()


def _unpaid(receipt: dict, stage: str, clock: Clock, reason: str = "LATE_FINALIZATION") -> dict:
    elapsed = clock.elapsed()
    out = dict(receipt)
    out.update(verdict=VERDICTS[NO_RESULT], reason=reason, exit_code=NO_RESULT,
               pays_exact_response_gate=False, original_verdict=receipt.get("verdict"),
               finalize_stage=stage, finalized_elapsed_s=round(elapsed, 3),
               detail=(f"{stage} returned at {elapsed:.3f} s, past the {clock.deadline_s:g} s deadline"
                       if reason == "LATE_FINALIZATION" else f"{stage} did not complete"))
    return out


def _report(receipt: dict, path: Path) -> None:
    print(f"{receipt['verdict']} {receipt['reason']} exit={receipt['exit_code']} "
          f"raw_bytes={receipt.get('raw_bytes', 0)} elapsed_s={receipt.get('elapsed_s')} "
          f"receipt={path}", flush=True)


def finalize(raw_fd: int, receipt_fd: int, receipt_path: Path, receipt: dict, raw: bytes,
             clock: Clock) -> int:
    """Write the raw bytes and the receipt; report; close. An OBSERVED result
    stands only if every step returns inside the deadline: the clock is read
    after each, and a late or failed step rewrites the receipt NO_RESULT in the
    same file, so whenever control returns the exit code and the receipt agree."""
    stands = receipt["exit_code"] == OBSERVED
    try:
        _write_all(raw_fd, raw)
        os.fsync(raw_fd)
    except OSError:
        receipt = _unpaid(receipt, "raw_write", clock, "FINALIZATION_FAILED") if stands else dict(
            receipt, raw_write="failed")
        stands = False
    finally:
        try:
            os.close(raw_fd)
        except OSError:
            pass
    if stands and clock.late():
        receipt, stands = _unpaid(receipt, "raw_write", clock), False
    receipt = dict(receipt, elapsed_s=round(clock.elapsed(), 3),
                   pays_exact_response_gate=stands)
    try:
        _rewrite(receipt_fd, _serialize(receipt))
        if stands and clock.late():
            receipt, stands = _unpaid(receipt, "receipt_write", clock), False
            _rewrite(receipt_fd, _serialize(receipt))
        os.fsync(receipt_fd)
        if stands and clock.late():
            receipt, stands = _unpaid(receipt, "receipt_sync", clock), False
            _rewrite(receipt_fd, _serialize(receipt))
        _report(receipt, receipt_path)
        if stands and clock.late():
            receipt, stands = _unpaid(receipt, "report", clock), False
            _rewrite(receipt_fd, _serialize(receipt))
            _report(receipt, receipt_path)
    except BaseException:
        if stands:
            try:
                _rewrite(receipt_fd, _serialize(_unpaid(receipt, "finalize", clock, "FINALIZATION_FAILED")))
            except OSError:
                pass
        os.close(receipt_fd)
        raise
    ident = os.fstat(receipt_fd)
    try:
        os.close(receipt_fd)
        closed = True
    except OSError:
        closed = False
    if stands and (not closed or clock.late()):
        receipt = _unpaid(receipt, "close", clock,
                          "LATE_FINALIZATION" if closed else "FINALIZATION_FAILED")
        if not _rewrite_closed(receipt_path, ident, _serialize(receipt)):
            print(f"NO_RESULT {receipt['reason']} the receipt at {receipt_path} could not be "
                  "rewritten: it pays nothing without exit 0", file=sys.stderr, flush=True)
            return NO_RESULT
        _report(receipt, receipt_path)
    return receipt["exit_code"]


def _rewrite_closed(path: Path, ident: os.stat_result, body: bytes) -> bool:
    """Rewrite the receipt after its descriptor closed, only if the path still
    names the very file this run created."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        now = os.fstat(fd)
        if (now.st_dev, now.st_ino) != (ident.st_dev, ident.st_ino):
            return False
        _rewrite(fd, body)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


# ── entry ────────────────────────────────────────────────────────────────────


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: {message}", file=sys.stderr)
        raise SystemExit(HOLD)  # nothing was sent


def _say(code: int, reason: str, detail: str) -> int:
    print(f"{VERDICTS[code]} {reason} exit={code} {detail}", file=sys.stderr, flush=True)
    return code


def main(argv=None, *, spawn: Callable = spawn_pump, clock: Optional[Clock] = None) -> int:
    clock = clock or Clock()  # the ONE deadline starts before anything is created or read
    p = _Parser(description="Read the one #1089 archived Kalshi contract, once.")
    p.add_argument("--contract-dir", required=True, type=Path,
                   help=f"the existing .../{'/'.join(CONTRACT_DIR_TAIL)} directory")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="send nothing, write nothing")
    mode.add_argument("--send-the-one-request", action="store_true",
                      help="spend the one attempt: create ATTEMPT-STARTED, then send")
    args = p.parse_args(argv)
    cdir: Path = args.contract_dir
    why = contract_dir_ok(cdir)
    if why:
        return _say(HOLD, "CONTRACT_DIR", why)
    state = fence_state(cdir)
    if args.check:
        sha = reader_sha256()
        print(json.dumps({"check": "no request sent, nothing written", "url": URL,
                          "deadline_s": DEADLINE_S, "cap_bytes": CAP_BYTES,
                          "reader_sha256": sha, "present": state}, sort_keys=True), flush=True)
        if state[MARKER_NAME]:
            return _say(ATTEMPT_SPENT, "ATTEMPT_SPENT", "ATTEMPT-STARTED exists; a send would refuse")
        if state[RAW_NAME] or state[RECEIPT_NAME]:
            return _say(HOLD, "LEFTOVER_OUTPUT", "an output file exists without the marker")
        print("CHECK_ADMISSIBLE no request sent; a send would be admitted by the local fence",
              file=sys.stderr, flush=True)
        return 0
    if state[MARKER_NAME]:
        return _say(ATTEMPT_SPENT, "ATTEMPT_SPENT", "ATTEMPT-STARTED exists; no request is sent")
    if state[RAW_NAME] or state[RECEIPT_NAME]:
        return _say(HOLD, "LEFTOVER_OUTPUT", "an output file exists without the marker; no request is sent")
    sha = reader_sha256()
    try:
        marker = establish_marker(cdir, sha)
    except Refusal as r:
        return _say(r.code, r.reason, r.detail)
    try:
        receipt_fd = _create_exclusive(cdir / RECEIPT_NAME)
    except OSError as exc:
        return _say(HOLD, "RECEIPT_NOT_CREATED",
                    f"({type(exc).__name__}); ATTEMPT-STARTED stays, and no request is sent")
    try:
        raw_fd = _create_exclusive(cdir / RAW_NAME)
    except OSError as exc:
        receipt = base_receipt(clock, sha)
        receipt.update(verdict=VERDICTS[HOLD], reason="RAW_NOT_CREATED", exit_code=HOLD,
                       request_sent="no", detail=f"({type(exc).__name__}); no request is sent",
                       elapsed_s=round(clock.elapsed(), 3))
        _rewrite(receipt_fd, _serialize(receipt))
        os.close(receipt_fd)
        return _say(HOLD, "RAW_NOT_CREATED", "no request is sent")
    receipt, raw = read_once(marker, clock, sha, spawn=spawn)
    return finalize(raw_fd, receipt_fd, cdir / RECEIPT_NAME, receipt, raw, clock)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--pump"]:
        try:
            raise SystemExit(pump_main(sys.argv[2:]))
        except SystemExit:
            raise
        except BaseException:  # noqa: BLE001
            raise SystemExit(PUMP_HARNESS)
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - never let Python's 1 read as a verdict
        raise SystemExit(NO_RESULT)
