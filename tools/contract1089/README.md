# #1089 one-archived-contract reader

PILLAR: TRUTH. SHIP: settled NHL player questions use the correct game's pregame forecast and result.

`reader.py` is the fixed-purpose reader Measurement 022 found missing (HOLD, 2026-10-20, `artifacts/calibration-1089-plan-admission-20261018/ONE-ARCHIVED-CONTRACT/RECEIPT-HOLD-20261020.md`). It makes at most one public GET to one fixed URL and writes what came back. **Nothing in this directory authorizes running it.** Admission, the no-overlap and window clearance, and the launch itself are separate gates.

## What it is bound to

- **The request**: `GET https://api.elections.kalshi.com/trade-api/v2/historical/markets/KXNHLGOAL-26JUN11VGKCAR-VGKWKARLSSON71-2`, HTTP/1.1, `Connection: close`, `Accept-Encoding: identity`. There's no URL, ticker, host or proxy argument. One connection to the first resolved address. No redirect is followed, and there's no retry, pagination, sibling, search, candle or follow-on request.
- **No credential**: no netrc, no key, no `Authorization` header. The network child gets an empty environment, except `SSL_CERT_FILE`/`SSL_CERT_DIR`. Proxy variables are ignored, so an operator whose only egress is an HTTP proxy can't use it.
- **The attempt fence**: before sending, the reader creates `ATTEMPT-STARTED` with `O_EXCL` in the one contract directory, writes it, and fsyncs both the file and the directory. It never removes or overwrites that file. If the marker already exists, the reader sends nothing, writes nothing and exits 40. If the marker can't be made durable, the reader sends nothing and exits 20, and the marker stays, so the attempt is spent without a request. The network child refuses to run unless it inherited the open marker from the parent that created it (same inode, the parent's pid, the fixed URL).
- **The contract directory**: an absolute path with no symlink or `..`, ending in `calibration-1089-plan-admission-20261018/ONE-ARCHIVED-CONTRACT`, owned by the caller and not writable by group or other. Outputs go only there, as `RAW-RESPONSE.bin` and `READER-RECEIPT.json`, both created with `O_EXCL` and mode 0600.
- **The envelope**:
  - **One 15 s deadline** from the top of `main`. It uses the awake, sleep-counting and wall clocks, and the largest wins.
  - **The network runs in a child process.** That covers the trust store, `getaddrinfo`, connect, TLS (1.2+, hostname-verified, a ragged EOF is reported), request and response. At 14 s the parent SIGKILLs that child by its pid and reaps it. So no network wait can outlive the deadline, `getaddrinfo` included, which the #1853 reader could only abandon on a thread. The child starts no process of its own.
  - **The child stays in the reader's process group** (no new session). A whole-command timer that signals the group, such as `timeout --kill-after=1s 15s` (not `--foreground`), ends the child together with the reader, even when the reader is killed before its own cleanup runs. The internal kill signals only the child, never the group, so the invoking shell and anything else in its group are left alone.
  - **One 262,144-byte cap** on every response byte taken in: status line, headers, chunk framing and body. Both the child and the parent ask for at most one byte past what is left. An oversized response is refused after cap+1 bytes and is never taken in whole.
  - **Completeness comes from the response's own framing**, not from a socket close. That means an exact `Content-Length`, or a chunked body with its terminal chunk and a terminated trailer section. A body framed only by the close must close cleanly (TLS close_notify). Once framing completes, the child is killed, so a server that holds the connection open can't stall the read. Ambiguous framing (two lengths, length plus chunked, a coding other than chunked), any content encoding, or bytes after the response all refuse.
  - **Finalization is inside the deadline.** The clock is read again after the raw write and after each receipt step: write, fsync, report and close. An OBSERVED result whose step returns at or past 15 s is rewritten `NO_RESULT LATE_FINALIZATION` in the same file. Whenever control returns, the exit code and the receipt agree.
- **Judgement**: HTTP 200, a strict JSON object (no repeated keys, no NaN) holding one `market` object, `market.ticker` exactly the requested ticker, and a non-empty `rules_primary`. The receipt reports `ticker`, `event_ticker`, `title`, `subtitle`, `yes_sub_title`, `no_sub_title`, `rules_primary` and `rules_secondary` verbatim. It also reports, verbatim, any other market field whose name looks like a time, date, timezone, occurrence, postponement, start, schedule, game or fixture reference. **It never decides occurrence.** Trading open/close and expiration times are not puck-drop evidence. The ticker is never split into an event identity (`derived_identity: null`), and no game is chosen by name or time.

| reader exit | verdict | meaning |
|---|---|---|
| 0 | `OBSERVED` | one complete exact response, retained whole. Pays only the exact-response gate, `pays_exact_response_gate: true`. The semantic review is still owed |
| 20 | `HOLD` | nothing was sent: wrong directory, leftover output, a fence that couldn't be established, or a deadline gone before the request |
| 30 | `NO_RESULT` | everything else: 404/3xx/429/5xx, timeout, truncation, overflow, malformed HTTP or JSON, identity mismatch, missing rules, late finalization. **A 404 or no bytes is never an empty provider response and never proves the contract did not exist** |
| 40 | `ATTEMPT_SPENT` | `ATTEMPT-STARTED` already existed. Nothing was sent or written |

Python's own exit codes (1, 2) are never a verdict. A crash maps to 30.

## Known limits (stated, not widened)

- **Local waits no timer can interrupt** happen in the parent: creating and fsyncing the marker, creating the outputs, spawning the child, reaping it after SIGKILL, and the final writes. That's why the gate is paid by exit 0 **together with** a receipt that says so, never by the receipt alone. If a write never returns, there's no exit code.
- **The deadline starts at the top of `main`.** Interpreter start-up and imports come before it. A hard wall around the whole client still needs an external bounded invocation at admission (for example `timeout --kill-after=1s 15s`). This file doesn't prove the operator has one.
- **A timer that signals only the reader's pid** (not its group) does not reach the child. The child then runs until its own waits expire or its next write finds the pipe closed, and `getaddrinfo` has no wait of its own. Use a group-signalling timer.
- **Unproven against the live venue.** Offline by mandate: no test opens a socket. The child's TLS path is driven through a fake socket, and the parent's whole path runs against real subprocesses that serve canned bytes. The response shape (`{"market": {...}}`) comes from the codebase's existing `get_market` reader, not from a retained capture of this endpoint.
- **TLS trust** is the interpreter's default store, or `SSL_CERT_FILE`/`SSL_CERT_DIR` if set. If the trust store is missing, the result is `NO_RESULT` (`tls_failed`), never a fallback.
- **One address only.** If the first resolved address doesn't answer, the result is NO_RESULT. There's no second try.
- **`request_sent` is `possible` once the child starts.** The parent doesn't observe whether bytes left the host before a failure.

Usage, attended only:

```
python3 tools/contract1089/reader.py --contract-dir <abs>/calibration-1089-plan-admission-20261018/ONE-ARCHIVED-CONTRACT --check
python3 tools/contract1089/reader.py --contract-dir <same> --send-the-one-request
```

`--check` sends nothing and writes nothing. It exits 0 when the local fence would admit a send, 40 when the marker exists, and 20 on a bad directory or leftover output.
