# Grade the probability the game page published

Pillar: TRUTH. Ship: `/calibration` can grade the probability readers see on game
pages. This tools-only PR prepares the labelled export and scoring input for
#11850's one-page analysis, after #12108 PR 1 records the served blend. It does
not change a source, a published probability, a flag, or the calibration page.

`blend_replay_export` and `blend_scorer` extend the canonical
`calibration_population_integrity` contract in `eval_registry.json` (ruling 002).
The adopted plan is #11850 comment6674713798, sections4–5; Alex's44-A stands.

## Frozen input and independent scoring

One packet contains event id, league, explicit series/doubleheader cluster id,
start time and binary home-win result, plus its odds snapshots, source snapshots
and recorded probability publications. A drawn game is a home non-win for this
target; this is not an away-win or three-way target. Unknown results refuse the
packet. Every unreadable packet/row is a failure, retained in the report.

The exporter keeps recorded `sources`, status, fallback inputs, method, revision,
clocks, payload hash and blend verbatim on `served` rows. `recorded_at` is the
pre-commit insertion clock, not a device-delivery receipt. Revision selects the
last publication at or before each of T-24h, T-6h, T-1h and start, using the
installed `publication_reader` selector. A missing horizon stays missing.

`reconstruction` rows rebuild the book median, book floor and split refusal with
the actual producer's rules. They use only observations confirmed at the chosen
instant, with no forward fill beyond `valid_until`. Ties need a unique row id.
Capture clocks do not establish the original writer's clock, source removals or
complete book population. Those limitations remain in each row. Reconstructed
numbers never acquire the `served` label. Where a recorded publication exists,
reconstruction uses that exact instant and recorded fallback inputs/status;
otherwise historical fallback inputs stay unknown.

An independent measurement owner freezes the export hash and commits the scoring
protocol **before inspecting score outputs**. The checked-in protocol's
`recording_start: null` intentionally refuses a real score until the actual
switch receipt is posted and committed. It must not be replaced by an assumed
switch time. Candidate weights, if used, are frozen by SHA-256 in that protocol;
there is no fitting or activation command here. An untracked or modified protocol
refuses even if its replacement checksum is supplied.

Train is Sep1–Oct15 (soccer Sep16 onward), tune is Oct16 up to the actual recording
switch, held-out is the first four weeks of recorded blends after the switch.
Events, series and doubleheaders cannot cross splits. Historical-bank rows and
reconstructions cannot become held-out forecasts. The tuner receives held-out
cohort counts only; the independent scorer owns the full score receipt.

## Running without a database

From `backend/`, use the existing Python environment:

```sh
python3 -m scripts.evals.blend_replay_export --input /private/tmp/packets.json \
  --recording-start '<actual posted offset-aware switch time>' \
  --output /private/tmp/frozen-replay.json
python3 -m scripts.evals.blend_scorer --input /private/tmp/frozen-replay.json \
  --sha256 '<export sha256>' \
  --protocol scripts/evals/blend_replay_protocol.json \
  --protocol-sha256 '<committed protocol sha256>' \
  --output /private/tmp/blend-score.json
```

Optional `--candidate /private/tmp/frozen-candidate.json` supplies a method id and
weights for exactly today's source feature set. Its checksum must match the
committed protocol. Candidates run through the existing aggregation cascade in
this offline process; original weights are restored even on failure. A new
method/feature/training window needs its own pre-registered version and independent
review. The first score counts; keep every attempted receipt. Output paths are
exclusive-create and cannot overwrite an earlier attempt.

## Read-only database export, when its gate is earned

No production read is needed to build or test this PR. Before an operational
export the measurement owner must name explicit event ids and series groups,
carry forward statement seconds already spent that night, and attest that the
whole off-peak slot is clear of attended folds/applies. `--database` also needs
`--manifest`, `--read-window-clear`, and `--statement-seconds-used`. Credentials
come from the existing `DATABASE_URL` environment and are never printed.

Queries are per-event/index-bounded with a10-second statement timeout; PostgreSQL
connection and transactions are read-only. The nightly statement budget is1800
seconds, including time already spent, and the current busy-hours guard is
checked before connecting and before each read. Each event/table has a20,000-row
cap; overflow fails instead of silently truncating. A read failure and consumed
statement time remain in the export receipt. The owner carries that receipt into
the next run; this tool adds no scheduler or collector. It never deletes rows.

## What the receipt proves

The scorer first reproduces each recorded blend and tier exactly through
`compute_aggregate_probability_tiered`. It separately compares reconstructed and
recorded values at the same instant; fewer than95% agreeing overlapping pairs
fails. Missing overlap is UNKNOWN, never acceptance. Real agreement and coverage
still need the independent read after PR1 is live; fixture tests are not that
acceptance.

Metrics are per league × horizon × time split × record kind: log loss, Brier,
the exact10-band ECE/signed gap from `calibration_scoring._stats`, sample counts,
and95% cluster-bootstrap intervals. The seed and1000 replicates are frozen.
Log loss clips endpoints at1e-15 and still counts endpoint errors. A singleton
cluster has unknown intervals. Candidate deltas use paired cluster resampling;
cohorts with fewer than400 held-out forecasts cannot meet the statistical bar.
The0.5-point ECE and significant log-loss-worsening guardrails, plus pooled ECE
by horizon, remain explicit. A statistical improvement is not a licence: every
licence stays HELD, activation NONE, and the live speed gate UNKNOWN here.

Each score receipts the frozen input/protocol/candidate hashes and current
implementation hashes. Neither scorer nor export changes a production table,
source weights, capture/grading policy, calibration population, or served page.
Tests1–3 and any population/de-vig changes remain their own reviewed steps.
