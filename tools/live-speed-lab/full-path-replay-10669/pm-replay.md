# PM probability delivery: 2039 ms to 68 ms in controlled prop churn

PILLARS: TRUTH / FORMATTING.
SHIP: a changed WIN probability reaches the held headline and chart while unrelated prop books keep arriving.

Keep the accepted PR10896 fix. The faithful local PM path confirms its causal effect beyond the fake-DB reproduction: parent6c5f827e waited until prop churn ended; candidatee4302ac250 rendered74% while churn continued.

| Observation | Parent6c5f827e | Candidatee4302ac250 |
|---|---:|---:|
| Input to publication call entry | 2023ms | 31ms |
| Input to actual headline/chart render acknowledgement | 2039ms | 68ms |
| Rendered during two-second prop churn | No | Yes |
| Whole run including build/setup/cleanup |24.65s|23.15s|

Prepared full pair:47.80s. PM adaptation took approximately5minutes after bounded inspection, reusing the existing source archive, private PostgreSQL/Redis lifecycle, SSE routes, actual EventPage/OddsChart, browser observer and omission control. No production application source changed in this fork. This is one local causal example, not a production percentile or general speed multiplier.

Identical frontend treeb7cf5a39fd61f2b9708e9634818011f62eb46506 and runner SHA2562d47c5e05d1ec712ab33155dbca1d37d73f7886132c7f60f278bfe4263e0088e. Same initial event1/revision1/.68, two named winner outcomes, and venue-labelled non-speaking totals prop. Both arms received13frames with identical payloads except per-run venue timestamps:9wide prop books plus two eligible winner pairs (.74/.26 then .59/.41). Eight prop replacements were received during actual withdrawal transactions. The wrapper forwards real SQL and deliberately ensures a newer wide-book arrival before each transaction completes for2seconds; it does not fake storage, blend computation or publication. Relative timing is coordinated against each transaction, not asserted to be identical wall timing.

Both arms store .74/revision2 and .59/revision3 with only the correct Polymarket source. One target delivers and renders74% in hero and chart; the second is deliberately committed but both publication routes withheld, and page stays74%. Zero unexpected missing target, no coalesced eligible state. Screenshots for both normal results and candidate omission were opened and inspected at390px. Source eligibility, revision and rendered frame identity agree. PM no-churn baseline also passed,66.95ms render-ack in21.93s total; it is not the parent/candidate comparison.

Timings use one Python monotonic clock from websocket send to browser POST after actual DOM/rAF observation; acknowledgement adds return/coordination overhead, not exact screen scanout. Publication means call entry, not Redis acknowledgement. The old receipt field `input_to_observed_storage_ms` is an event-revision follow-up read after polling, not quote-commit latency; it is not used as exact storage timing. Uncalibrated wall-clock deltas remain raw only.

All three new PM invocations PASS, removed their private processes/database, lifecycle stopped=true and zero cleanup errors. Each browser retained one auxiliary404; no page-script error. Shutdown's clean socket-close/reconnect log is retained, not counted as recovery testing. Actual SwiftUI, venue input transport, production load/tails, mixed-source competition and installed-device timing are not established here. Earlier phone headline/chart agreement, Live Activity and return/history acceptance remain paid; do not repeat them.

The newer next-flush-tail fix is a separate current author task. Its WIP passed the fork's three causal cases and28existing guards; this PM pair qualifies the already acceptede430fix only, not that uncommitted successor. Integrator retains delivery. Goal#10090 stays ACTIVE until actual worker carriage, bounded production changed-input timing and installed-iPhone timing are established.

Run the retained pair serially with `python3 tools/live-speed-lab/full-path-replay-10669/pm-run.py --application-ref <exact SHA> --prop-churn --trials 1 --output <fresh absolute directory>`. Omit --prop-churn for the no-churn control. Existing Kalshi-only --history-hold and --quiet-debt-comparison are refused by this PM adapter.
