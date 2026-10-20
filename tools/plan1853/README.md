# #1853 plan-output reader

PILLAR: TRUTH. SHIP: settled markets in the original never-graded cohort can show their venue-confirmed results instead of remaining blank.

`reader.py` reads the output of ONE operator-launched, no-flag plan run of `backend/scripts/repair_1853_archive_grades.py` on `bainluck-heavy` and writes one receipt. **Nothing in this directory authorizes running it, launching the plan or applying anything.** Operator selection, admission, the window and the launch itself are separate gates.

## What it is bound to

- **Target**: `bainluck-heavy`, the exact command `python3 scripts/repair_1853_archive_grades.py`, `POST https://api.heroku.com/apps/bainluck-heavy/log-sessions` and the HTTPS `.heroku.com` `logplex_url` that endpoint returns. No app, command, SQL, URL, proxy or provider argument exists. Proxy variables are ignored.
- **Run handle**: the one `done, run.N` line of the saved launch output. The launch file is read like the credential: a regular file only, opened non-blocking, at most 4,096 bytes, charged to the cap. That line must name the exact command on `bainluck-heavy`, and no other `run.N` may appear in the evidence.
- **Envelope** (revised under Root's 035A from the first 16,384-byte proposal):
  - **One shared 30 s deadline**, from the top of `main`. It uses the awake, sleep-counting and wall clocks; the largest wins. Every socket wait is sized from what is left. The TLS context is built before connecting, the handshake timeout is refreshed after `connect`, and a context or handshake that returns late is late.
  - **One 65,536-byte cap** over every byte taken in and every byte retained: the launcher file, the netrc file, both responses' status lines, headers, chunk framing, bodies and errors. The log is also charged at its base64 size as it arrives, plus a fixed 4,096-byte reserve for the receipt's metadata. The serialized receipt is checked against the cap before it is written. One that would not fit is replaced by a short `UNCERTAIN RECEIPT_OVERSIZED` receipt, never truncated.
  - **No read-ahead**: every log byte taken off the socket goes straight to the parser.
  - One log session and one read. No retry, no polling, no second address.
- **Credential**: the `api.heroku.com` password from `$HOME/.netrc`, read in-process. No `heroku auth:token` child, so there are no detached CLI workers. It must be a regular file, and it is never retained. The token and the bearer URL never reach argv, the environment, the terminal or the receipt.
- **Judgement**: the script (sha256 `ab45ba3f…159c`, git blob `dd3ece533b`) and `kalshi_market_status.py` (`c74d6281…7940`) are pinned. Any other bytes make the result `SOURCE_PIN`. Every judged output is held to the script's own print. The checks are: exactly one framed `Starting process` line for the exact command and exactly one `Process exited with status N`; dyno-framed lines only (NULs at line ends are framing, a NUL anywhere else is malformed); one byte-canonical `json.dumps(indent=2)` document; no partial tail (a line still incomplete when the terminal evidence arrives is read to its end inside the deadline and then judged; it is never paid on); the script's own keys, event and archive; every planned leg graded the same way by the retained archive through `gradeable_winner`; and `plan_digest` recomputed by the script's own `plan_digest` code.

| reader exit | verdict | meaning |
|---|---|---|
| 0 | `ADMISSIBLE_PLAN` | run exited 0: the complete 22-leg plan, digest verified. Pays the plan gate only. `apply_authorized` is always false |
| 10 | `STOP_RESULT` | run exited 1 with the script's own stop: that population must never be applied |
| 20 | `REFUSAL` | run exited 2 with the script's own one-line refusal |
| 30 | `UNCERTAIN` | everything else, including a timeout, an oversized read, a traceback under exit 1, any other exit, extra text, or a mismatched run or command |

A stop or a refusal is evidence, not success, and not a reason to retry. A reader timeout does not prove the remote run stopped.

## Known limits (stated, not widened)

- **The first envelope could not hold a plan.** Logplex frames each of the plan's 195 printed lines (6,671 B raw), so the read alone is 16,410 B (`run.NNNN`) or 16,609 B (`run.NNNNN`). At 16,384 bytes the reader returns `UNCERTAIN OVERSIZED` on an honest plan. That refusal is kept as a test. At 65,536 bytes, intake plus the receipt fits the 22-leg plan, the 21-leg stop and the 30-leg stop, even with 2 KiB of headers per response.
- **Waits no in-process timer can interrupt**: local file opens and reads, the trust-store load inside `ssl.create_default_context`, the receipt write, and `getaddrinfo` (on a daemon thread abandoned at the deadline). A hard wall around the whole client needs an external bounded invocation at admission.
- **Run time**: dyno boot plus the plan must finish inside whatever is left of the 30 s after the session opens.
- **Strict content rules**: any non-JSON app line (an import-time warning, for example) or any unrecognized platform line (`Error R14`, for example) is `UNCERTAIN`.
- **Unproven against real output**: the logplex line shape and the `logplex_url` host come from Heroku's documented format, not from a retained real capture. `getaddrinfo` cannot be interrupted, so it runs on an abandoned daemon thread. TLS handshake bytes are not metered.

Usage, attended only: `python3 tools/plan1853/reader.py --launcher <saved launch output> --receipt <new file>`.
