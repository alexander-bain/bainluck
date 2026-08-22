# UX post-deploy proof harness

Built by UX-P119 (cycle 116) so the window after the drain deploys is **minutes, not
hours**. Every "OWED: production evidence" line in READY-ux-101 … READY-ux-105 is
discharged by something in here.

```bash
tools/postdeploy/run-all.sh          # everything, read-only
```

Each proof carries its own deploy gate, so this is safe to run the moment a deploy lands:
anything not yet in reports `NOT DEPLOYED` rather than a misleading pass.

## The files

| file | proves | branch it gates on |
|---|---|---|
| `proof-2065-feed-funnel.sh` | Discover serves event cards, mixed statuses, no duplicate matchup, esports not dominant | `program/ux-103` |
| `proof-2084-duel-sum.sh` | every served duel pair sums to 100 and the favourite prints its own rounding | `program/ux-101` |
| `proof-2086-settled-markets.sh` | the settled `status` is served; **picks a specimen and hands Alex a URL** | `program/ux-102` |
| `verify-2094-backfill.sh` | the defect-route backfill's dry-run census + **cluster projection**; `--apply` commits and re-checks idempotence | `program/ux-105` |
| `compare-calibration-baseline.sh` | `/tmp/cal.json` baseline vs a fresh curl — shape held, movement reported | — |
| `lib.sh` | the deploy gate, retrying transport, verdict vocabulary | — |

## Verdicts

`PASS(0)` · `FAIL(1)` · `UNKNOWN(3)` · `NOT_DEPLOYED(4)` · `TRANSPORT(5)`

Per gotcha #54's amendment: **1 is a result; anything else is a story about the harness.**
`UNKNOWN` is used deliberately and often — an empty population, a slate too thin for a
check to fire, a specimen with nothing to render. None of those is a pass, and the whole
reason this harness exists is that they have repeatedly been recorded as one.

## Three things it deliberately does not do

1. **It does not claim to prove #2086.** That fix is client-side and the API payload is
   identical before and after, so no API check can tell a fixed deploy from an unfixed
   one. The script verifies the input and then names the rendered check as Alex's, with a
   specific event URL. A harness that "proved" it would be lying.
2. **It does not apply anything.** `verify-2094-backfill.sh --apply` is the only write in
   the set and `run-all.sh` does not call it.
3. **It does not discharge the human evidence.** Alex's 5-shot capture and the 60-second
   force-quit check (`READY-ux-105.md`) are what close #1929 / #1937. Code shipped is not
   closure.

## Baseline capture, before the deploy

```bash
tools/postdeploy/compare-calibration-baseline.sh --capture   # writes /tmp/cal.json
# … deploy …
tools/postdeploy/compare-calibration-baseline.sh             # compares
```

## Notes that cost time to learn

- **The gate measures ancestry, not handoff prose.** `require_deployed` reads
  `/api/health`'s commit and runs `merge-base --is-ancestor` against a *local* ref. UX-P119
  discovered this way that `program/ux-101` was already merged while the handoff pointer
  only tracked `ux-102..105` — which is how #2084's proof got discharged a cycle early.
- **`/api/calibration` 503s for 1–4 minutes after every release** and then self-heals.
  `api_get` retries; a release-window 503 costs a wait, not a false alarm.
- **The read rail rate-limits at 60/min and other lanes share it.** A transient 400/429 on
  an admin query is not "no rows exist"; the discovery calls retry.
- **`home_rendered_percent` lives under `data.current_odds`**, not at the top of `data`.
  The first draft of the #2084 proof read the top level and printed a confident FAIL
  against a fix that was deployed and working.
- **`other` on `game-markets` is a FLAT list** of
  `{market_name, outcome_name, probability, source}` — no nested `outcomes`, no per-row
  `status` or `is_winner`. UX-P115's grades came from the database, not this endpoint.
