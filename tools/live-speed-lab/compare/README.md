# #10090: compare → improve → ship

**PILLARS: TRUTH / FORMATTING. SHIP:** fresh blended probabilities reach held web and Native headlines and charts sooner, with fewer long gaps. DNPL stays ON. This is a small entry point into the existing #10669 lab, not a new lab, dashboard or release gate.

## Use it now

From this checkout, consume the completed admission comparison **without rerunning it**:

```sh
python3 tools/live-speed-lab/compare/compare.py consume \
  tools/live-speed-lab/compare/admission-retained.json --out /tmp/admission-comparison
open /tmp/admission-comparison/index.html
python3 -m unittest discover -s tools/live-speed-lab/compare -p 'test_*.py'
```

The self-contained output contains `comparison.json`, the side-by-side HTML view, actual page screenshots and a hash manifest. The slider synchronizes recorded headline values and SVG chart paths from **real separate backend/page runs**. It is evidence playback, not a fabricated frontend performance test. The report uses no external assets, production connections or service credentials.

The existing two runs provide one completed actual-candidate comparison: released `efe320d0` versus admission fix `1c755177` (PR #11668). One selected PM input during a held Kalshi publication reaches both endpoints sooner. Its consumer-receipt-to-DOM bounds, including clock uncertainty, are approximately **1.017–1.125 s baseline versus 0.722–0.827 s candidate**. The old send-to-first-observed samples remain 1.121/0.825 s; do not mix these timing boundaries. Whole-sample gaps remain 3.994/4.200 s, including deliberately quiet input intervals. **Decision: improvement supported for that witness.** Integrator owns release; the application source remains identical on the test-only CI successors. Independent source acceptance and original failure logs remain earned evidence.

The historical inputs have identical source/value/label order, **not byte-identical timestamps**. They were rebased per arm and have up to 35.4 ms relative scheduling difference. Host layout is the same, but contemporaneous host-load readings were not retained. Those limitations are displayed. They narrow the historical decision; do not retroactively label this a strict identical-input benchmark or use it as final production acceptance.

## Six steps, used for every change

1. **Name the delay and ship.** Record the released baseline SHA and release receipt, candidate delta, exact event/source identities, and the specific eligible information that waits. A backend change requires the real backend path. Do not infer upstream silence from stored values, rounded values, or stoppages.
2. **Choose the smallest deciding case.** Predeclare the input witness, state/context, bottleneck, output identity/expected blend, full sample window, correctness controls and invalid conditions. Reserve the existing lab slot; do not disturb another owner. Cap measurement adaptation around 20% of the iteration. If the necessary faithful context is absent, identify that precise gap before buying a broad capture.
3. **Compare isolated arms.** Use the same timestamped input tape and relative schedule, equivalent starting state, same topology/dependencies and comparable compute. Keep DNPL ON in both. Pin any necessary timestamp translation as one declared epoch shift, preserve source ages and spacing, and compare canonical timestamps/payloads exactly; retain raw wire hashes and actual send jitter. If literal wire timestamps differ, say so. Never silently drop fields to manufacture equality. Each arm uses its own fresh disposable PG/Redis, real consumers, blend, SSE and page. Existing helper refuses non-local backend sockets and browser requests and holds the #10669 exclusive lock. No production DSN, subscriptions with write effects, notifications or candidate external side effects.
4. **Decide, including negative results.** `improvement_supported`, `no_improvement_demonstrated` / `no_improvement_or_regression`, or `experiment_invalid` with a specific repair. A supported 0.1 s gain can ship even if it does not reach 1 s. Preserve the worst-delay guard while reducing cumulative debt. Use AB/BA repetitions only if uncertainty, load or jitter could reverse the decision; retain each repetition, never select the fastest pair. A valid negative eliminates the approach. A setup failure does not justify unchanged retries.
5. **Review and ship.** Build owner fixes code; independent reviewer owns acceptance; Integrator carries exact source through existing CI/release. The comparison tool never deploys, restarts, toggles DNPL or changes holds. Do not bundle an independent fix behind tool work. Reuse unchanged source reviews/tests and report which evidence applies after composition.
6. **Verify deployed behavior.** Measurement owns bounded production input/stream capture and independent attribution. Native owns SwiftUI/device work. Verify exact deployed/installed source and predeclared cases; report local-only, merged, deployed and installed acceptance separately. The #10090 goal remains active until the actual production and installed-iPhone cases pass.

## Entry points and experiment modes

`consume SPEC --out NEW_DIR` is offline, repeatable analysis of retained full-path admission artifacts; original files are never modified. Existing output directories refuse rather than overwrite. Failed input artifacts write `INVALID.json` with the precise reason.

`run SPEC --out NEW_DIR` invokes the **existing** pinned `warm_helper.arm` twice with DNPL ON, fresh state and the original cleanup/lock/deadlines. Both prepared sources and the transition scorer are verified before starting either arm. It pins backend fixture, proxy, observer and fixture input bytes as well as the helper/scorer. It adds before/after host load, CPU count and wall time; the helper retains actual process exits/cleanup/source hashes. Order can be baseline/candidate or candidate/baseline. Output reserves a new directory before execution, retains completed arm pointers in `RUNS.json`, stops after a failed arm, and saves the failure in `INVALID.json`. Failed arms have their own identity/path and never count as completed. Helper stdout is retained even if cleanup raises. Successful output is under `report/`. Preparation/export/build remains the existing helper's separate step. No implicit rebuild, source fetch or production connection. This initial run adapter is specifically `controlled-admission`; it retains the historical synthetic scheduling limits above. It is **not yet the strict timestamp-tape adapter** described in step 3. Do not use it to claim that stronger contract.

`stage-recorder SPEC --out NEW_DIR` copies the existing lab and changes only its passive EventSource listener list to include `preview_open_v3`, `preview_v3`, `reconcile`, `reconnect` and `heartbeat`. It verifies all four original lab-file hashes before staging and refuses drift. It leaves the product, reducer, primary DOM recorder and previous runs unchanged. The old pair cannot supply preview-v3 receipt times; those remain null. The staged observer is for the next needed run, not a reason to repeat this one.

`stage-display-recorder SPEC --out NEW_DIR` additionally records the adopted-state DOM attributes from UX's #11673 seam, separately for headline and actual chart endpoint. It inserts `display_sample.cjs` into the existing 100 ms sample and retains the sampler's hash. Missing attributes on older source are `unsupported`, duplicate surfaces `ambiguous`, and unavailable identities stay empty. CSS visibility and viewport intersection are separate. The sample carries its own monotonic read interval; neither that interval nor the preview's receipt clock is physical paint timing. Identity is copied verbatim, never guessed from percentages or chart paths. This is a passive recording adapter, not eligibility or correctness certification.

```sh
python3 tools/live-speed-lab/compare/compare.py stage-display-recorder \
  tools/live-speed-lab/compare/admission-retained.json --out /tmp/dnpl-display-recorder
```

Use the staged `comparison-spec.json` only after pinning the next experiment's prepared sources/context. Staging does not run either arm or overwrite old evidence. This full-page recorder wraps the product's existing `EventSource`: it records the actual URL on each frame and leaves constructor arguments untouched. Today's product requests `preview_protocol=authority-v3`; verify the recorded URL and envelope on a new run. Do not confuse it with Measurement's historical independent `/stream` recorder, whose negotiation needs its own update. There is no new subscription, transport change, primary observation-clock change or backend receipt-trigger change.

Recorder controls: the ordinary Python comparison tests plus `node --test tools/live-speed-lab/compare/test_display_sample.cjs`, using the existing lab's Playwright dependency through `NODE_PATH` and installed Chrome. The latter uses local DOM fixtures with all network requests blocked. It proves passive extraction, not the product seam's attribution; UX's real-page controls and independent review own that proof. New records remain unscored until Live's input-to-published-state correspondence establishes eligibility. Do not treat absent joins as zero delay, silently map equal values, or rerun the completed admission pair just to populate these fields.

`score TRACE.json --out score.json` handles the common eligible-state/display contract, including explicit supersession, intervals, missing updates and separate surfaces. It is reusable for web or Native adapters; it is not an oracle that determines eligibility from a price.

Modes are added **when a concrete optimization needs them**, not as a new architecture program:

| Mode | Existing machinery | Current readiness / next exact adaptation |
|---|---|---|
| Controlled bottleneck | Real held-row + held-publication admission case | Working retained comparison and pinned two-arm entry point. Canonical timestamp-tape enforcement remains required before claiming strict identical-input runs. |
| Captured bad stretch | `backend_lab.recorded_sequence`, retained `wire.jsonl`, fixture graph and starting-context loader | Already present in the lab; not automatically mapped to the admission scorer. Next named gap must provide input eligibility/coverage adapter and canonical tape/epoch checks. Missing starting books, revisions, authority, membership or source context means invalid, not a simplified success. |
| Live shadow | Measurement's existing capture can supply a single read-only source stream | No new live subscriber started here. Only add a bounded tee into isolated consumers when a named replay leaves a production-relevance question. Require mapped identities, queue/drop accounting, per-arm isolated DB/Redis and blocked egress. Never mirror production writes or share candidate state. A backend replay is not a live-shadow claim. |

Unsupported modes fail explicitly. They do not silently execute the synthetic admission case. This first increment does not claim all three modes are delivered.

## Score contract and definitions

Trace times are milliseconds in **one declared comparison clock**, represented as `[earliest, latest]`. Cross-process wall/monotonic mappings must retain their measured spread, sample resolution and sleep/discontinuity checks. A source observation time is not a receipt time. DOM callbacks/samples and SwiftUI evaluation are not paint timestamps. For overlapping covering display intervals, first-display bounds are `[min earliest, min latest]`, not the interval of whichever row sorts first.

`eligible[]`: `{id, stream, at_ms:[lo,hi], evidence, supersedes?:[ids]}`. Each identity denotes a selected, admissible **blend state owed to this display**, identified by contributing input marks and authority/revision. The witness must include the actual selection/eligibility decision or a predeclared invariant verified by controls. A rejected, duplicated, unselected or unchanged raw venue tick is not automatically an obligation. An unchanged probability may still owe an observation update; the adapter must declare which state/clock is owed. Probability equality never proves supersession.

`displays[]`: `{surface:"headline"|"chart", at_ms:[lo,hi], covers:[ids]}`. A later state covers an earlier state only through explicit same-stream `supersedes` edges. Preserve all authority/revision/session/floor identities. The chart witness must prove the correct point and continuity, not merely a changed path. Unknown identity remains unscored and reduces coverage.

`coverage`, `checks`, `violations` are mandatory context; an unexecuted check is `not_measured`, not zero failures. The retained adapter reports sampled target agreement plus banked source controls, not blanket ordering/expiry acceptance.

- **Worst avoidable delay:** maximum eligible-availability → correct display interval in the attributed cohort, separately for headline and chart. It excludes upstream waiting before eligible information exists here. An unresolved obligation is right-censored at sample end; `worst_is_lower_bound` prevents treating that age as a completed latency.
- **Cumulative trailing time:** length of the union of all intervals where the display owes a newer eligible state. Overlap and explicitly superseded states are charged once; headline and chart have separate totals, with a union for both. It is elapsed stale time, not the sum of every tick's latency.
- **Under one second:** strict `<1000 ms`. Report definitely-under / denominator, definitely-over and uncertain. Explicitly coalesced predecessors are reported separately and excluded from the distinct-display denominator, but still contribute to worst/cumulative trailing time. An unresolved state older than a second fails; a younger end-censored state is uncertain.
- **Failures:** unresolved identities, explicitly detected ordering/expiry violations, and headline/chart inconsistencies. Source test coverage does not turn unmeasured runtime failures into zero.
- **Whole-sample gaps:** reuse the existing transition scorer including both edges. Keep these visible alongside eligibility debt; silence is not automatically unnecessary waiting.

An incomplete or mismatched cohort cannot receive an improvement decision; right-censored debt remains visible but the comparison is invalid until its precise missing coverage is resolved. An empty or partly mapped cohort cannot yield a global 100% claim. In the admission report, 1/1 versus 0/1 refers only to the predeclared target, not all 116 input groups. Exact admission, blend computation and old preview client-receipt times are unknown; publication call/return delimit a region, not a precise Redis publish instant.

## Native and final acceptance

Native's existing `SubsecondHeldDelivery10090Tests.swift` mounts real `EventDetailView` and feeds `PacedStream` through real transport/controller/ViewModel. Its `LiveTimingSeam` currently misses preview-v3 receipt/adoption and compares committed state in view marks. Native returned that concrete gap; its extension remains Native-owned, after current primary work. Do not score missing preview marks as missed delivery.

Reuse `(input_id, offset_ms, sse_event, data, authority_id)` records from the backend stream. Native's suggested marks are `input.sent`, `frame.received`, `preview.received`, `model.headline`, `model.chart`, `view.headline`, `view.chart`, with uptime, source-observed clock and chart-edge date separate. For backend-only changes, prefer AB/BA through the **same** SwiftUI build/simulator and report load; two simultaneous simulators can create contention. Use two only when the changed client/source and available resources make that comparison meaningful. Installed-phone marks/pixel bounds remain separate; no simulator automation dependency on backend shipping.

Before the final production/iPhone run, release owner + Measurement + Native must bind the bounded cases and exact installed/deployed source: a live multi-source Tier1/2 event with mapped upstream input, the previously reproduced gap class, unchanged-value observation and recovery/ordering behavior. Choose event eligibility before capture, with a declared replacement rule if it finishes. Every measured eligible state must reach both surfaces under one second within uncertainty, with no unexplained misses/correctness failures. Do not select only successful events afterward. Capture limits and unresolved coverage stay explicit. Finite acceptance never implies universal coverage.
