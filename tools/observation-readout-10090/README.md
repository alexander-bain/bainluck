# Bounded observation recorder

Pillars: TRUTH / FORMATTING. Ship: the visible observation readout can explain
how long a person waited for its next forward update, with the displayed DNPL
or committed provenance recorded alongside it.

`capture.mjs` exports `captureObservation(tab, options)` and
`analyzeObservation(capture, options)`. The caller supplies its **currently bound
CUA tab** and the route event ID. The helper never discovers tabs, navigates,
opens the disclosure, issues HTTP requests, writes a file or starts a daemon.
Do not run it through shell browser automation or ordinary Playwright.

The four read-only attributes are `data-observation-at`,
`data-observation-count`, `data-observation-delivery` and
`data-observation-event-id` on `live-connection-status`. The counter is the UI's
page-session forward high-water counter: first valid observation counts 1;
backward timestamps, repeats and restoration to the previous high-water do not
increment it. Fullscreen and inline views share that count. Provenance describes
the value currently displayed; it is **not** the rollout configuration flag.

## CUA usage

In the existing `cua_repl` Node runtime, after the owner has selected a current
`tab` using the documented CUA API, and the user/operator has opened the
“Probability observed” disclosure so its timestamp is visibly displayed:

```js
var recorder = await import('/Users/bain/.codex-personal/worktrees/observation-readout/bainluck/tools/observation-readout-10090/capture.mjs');
var observationCapture = await recorder.captureObservation(tab, {
  eventId: '15333766', // replace with the route event actually bound to tab
  durationMs: 180000,
});
nodeRepl.write(observationCapture.analysis);
```

Await the entire capture inside one tool call with a tool budget longer than the
requested recording. Default and maximum duration are 180 seconds; a shorter
positive duration is supported. Polling is 100 ms with one read in flight. The
CUA invocation is `evaluateAll(pageFunction, undefined, { timeoutMs })`, with its
timeout limited to remaining capture time. A read is always awaited: there is no
Promise.race or abandoned browser request. If the runtime exceeds its timeout,
actual elapsed time/overrun and failures remain recorded; no new read starts
after the deadline. The helper cannot enforce an external runtime's timeout.

Save **after** the awaited capture, in that same Node runtime, to an approved
local artifact directory that already exists:

```js
var captureFiles = await import('node:fs/promises');
await captureFiles.writeFile(
  '/Users/bain/.codex-personal/private-artifacts/live-10090/observation-capture.json',
  JSON.stringify(observationCapture, null, 2) + '\n', 'utf8',
);
```

Choose a new output filename for each capture. No live capture is part of the
unit tests. A stale tab handle or undeployed/missing attributes produces an
invalid capture, never a fabricated zero-second result.

## Interpret the result

The main metric is `analysis.longest`: the **whole recording's longest interval
without forward advancement**, including its beginning and unfinished ending.
The first reading establishes a baseline; it is not counted as a new arrival.
A 5-second interval ending in an update followed by 49 seconds without another
update reports a **49-second observed lower bound**, not 5 seconds.

Every read keeps monotonic begin/end times. An advancement happened somewhere
between the preceding read's beginning and the new read's end. `lowerMs` and
`upperMs` bracket the whole-window maximum using those uncertainties; the
`kind` is the interval establishing its lower bound. The leading edge begins
at capture time zero. The trailing lower bound stops at the last successful
read's beginning, not the recorder's later stop/timeout. A censored pause can
extend outside the recording, so these bounds do not bound its full lifetime.

Only `QUALIFIED` supports the whole-sample maximum. The timestamp disclosure must
be both open and visibly displayed on every sample. A closed/hidden disclosure
retains metadata but is explicitly `UNQUALIFIED` for this visible timestamp
metric; the recorder never clicks it open. Any missing/invalid read,
invalid timestamp/counter/provenance, counter reset or leap, ambiguous visible
component, read taking over 500 ms, or sampling gap over 500 ms makes it
`UNQUALIFIED`. Its interval candidates are retained for diagnosis but **must not
be reported as established user pauses**. Fewer than two usable reads spanning
positive time gives `NO_RESULT` and `longest:null`. Count leaps explicitly record
missed intermediate forward updates; a return to an old timestamp is not a new
advance. Raw timestamps are retained exactly, while ordering matches the UI's
`Date.parse` millisecond resolution. Apply local-time formatting only in a human
summary, never to the recorded strings or comparison.

Component visibility uses viewport geometry, CSS and a midpoint DOM hit-test;
this excludes a fullscreen overlay's covered inline copy. Two genuinely visible
matching components remain ambiguous and disqualify the sample. Other event IDs
are retained but never mixed into the requested event. Disclosure open/visibility
is recorded without opening it, and both are required for qualification. These are DOM observations, **not physical paint
measurements**, venue-input-to-display latency, or evidence that an update was
available upstream. Slow API/tool returns measure recorder uncertainty.

## Tests

```sh
node --test tools/observation-readout-10090/capture.test.mjs
```

Tests use fake CUA handles and captures only. No browser or network is launched.
