# Visible Live iteration — #10669 / #10090

PILLARS: TRUTH / FORMATTING.
SHIP: the next changed probability reaches the held headline and chart while older history is waiting.

This is a scoped reuse of the existing full-path replay from lab commit
`9a347cbe3b`, not a new service. It runs actual archived application source,
private PostgreSQL/Redis, the decorated Kalshi consumer, SSE and the actual web
EventPage/OddsChart in Chromium at 390px. Dependencies and fixture contract paths
remain host-local as in the original lab. It uses synthetic quotes and small
Next/auth shell adapters; it does not run SwiftUI or production traffic.

The root-owned #10669 claim was read back on October 11. This checkout is isolated
from Live/Native/Integrator source ownership. There are no application changes.

## One current decision

```sh
python3 tools/live-speed-lab/full-path-replay-10669/run.py --application-ref 2c2bcefa6958b4574150a700cd70462dd3519f4d --history-hold --trials 1 --output /tmp/live-history-parent-UNIQUE
python3 tools/live-speed-lab/full-path-replay-10669/run.py --application-ref 8e9e8d29e36a540a517a605d56e48ca7c45a67e3 --history-hold --trials 1 --output /tmp/live-history-current-UNIQUE
```

Use fresh output directories. Runs are serial and acquire the existing benchmark
lock. Each invocation removes its own processes and private database. Failed
attempts remain failures; inspect lifecycle.json and worker cleanup, not only PASS.

`--history-hold` sets the existing Kalshi cadence to 250ms in **both local arms**.
This is a controlled experiment setting, not a read or change of production config.
The seed is .68; the actual protocol delivers .71, then .74. The first .71 history
helper is held for four seconds and then forwarded to real SQL. No other work is
sped up or replaced. The unchanged omission control commits .59 with both event
and market publications deliberately omitted: the page must remain .74.

The added browser acknowledgement posts the actual rendered view back to the same
Python observer that sent the quote. Its monotonic elapsed interval is an upper
bound to the observed DOM/rAF result, including return and coordination overhead;
it is not display scanout timing. Existing cross-process wall deltas remain in raw
receipts but are not used as accurate latency. Publication means call entry, not
Redis ACK; the DB read follows a 25ms revision poll.

October 11 comparison: parent 4017ms versus current 233ms input-to-render-ack;
only current rendered before history release. Identical input frames, initial
fixture, three resulting committed price/revision states, frontend tree and
runner hash were checked. Both controls and cleanup passed. The two complete
invocations totaled 52.75 seconds. One preceding attempt failed because the new
callback had an unresolved FastAPI Request annotation; it is retained, not counted
as a product failure or silently replaced.

Decision: keep accepted #10869. Its backend application tree is identical to the
tested current source. No further history scheduling or cadence source change is
justified by this case. Worker-ws carriage and production/installed-phone speed
remain unpaid; this result does not explain the separate 10.58s production gap.

Evidence: `/Users/bain/bainluck/artifacts/live-iteration-goal-20261011/RESULT.md`.
Existing six pure qualification controls passed. Full correctness, recovery and
multi-source coverage are still supplied by the existing integration gates; this
single-source case is not a replacement. The historical quiet-debt mode remains
present but was not run or newly qualified here.
