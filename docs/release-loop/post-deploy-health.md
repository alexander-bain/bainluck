# Unattended production release health

**Pillar: TRUTH. Ship: a broken production release returns to the previous working version while every model session is asleep.**

## Preparation and activation

This branch does not merge, push master, change repository protection, change Heroku configuration, or modify the active speed tools. Alex's “master is current” is the integration hold. The exact operational tools are currently outside tracked master:

- `artifacts/g4f72-kit.txt` names `speed-10090-fastdeploy-G4F72-ee450b32-TENTHS-NOT-WHOLE-PERCENT-20261101T1915Z`, which holds `check.py` and `watch_dnpl.sh`.
- `artifacts/speed-tools/latency_guard2.py` and `latency_guard3.py` are read unchanged.
- The operational headline input conversion comes from the G4F32 `streak.py`; `health.py` preserves its exclusion of `stamp_no_reading` before invoking the original guards.

Builder A must first make `tools/speed/check.py`, `latency_guard2.py`, and `latency_guard3.py` available. Missing tools make the observer fail visibly; missing tools do not authorize a rollback. The workflow needs existing `HEROKU_API_KEY`, `VERCEL_TOKEN`, `GH_TOKEN` from the workflow token, and repository variables `VERCEL_PROJECT_ID`, optional `VERCEL_TEAM_ID`, and `NOW_ISSUE` (the numeric GitHub issue number). The NOW issue was not present in this local master snapshot and cannot be looked up with internet disabled.

## What runs

A successful master CI workflow and production `deployment_status` trigger discovery. A five-minute scheduled reconciliation also checks the current provider release, including a Heroku release created outside GitHub. Receipts are GitHub deployments in `release-health-heroku` and `release-health-vercel`; the provider's immutable release/deployment ID makes repeated observations idempotent. The observer always checks out trusted master, never PR source with deployment secrets.

The worker probe and public routes run on a 30-second cadence with bounded requests. Boot health becomes available at three minutes; the existing worker check does not establish its final A10 verdict until the later scan+180 through scan+780 window. The observer retains that distinction and the original guard requirements instead of calling a three-minute startup pass a final latency pass. Public route exceptions, malformed JSON, a missing dependency reported by `/api/health`, and an empty or malformed feed fail the release. Vercel also requires the production website to return HTML.

The original watcher calls guard2 with `5000 10` and guard3 with `12 20 30`. Guard2 stops at two consecutive sampled minutes above 5,000 ms, excluding `na_orientation`. Guard3's executable code stops at three consecutive sampled minutes above 5,000 ms once the start+2-minute boundary is reached, and applies the 20-point deterioration rule to the under-500-ms minute share. Its docstring still says two; the executable code is authoritative. No threshold is inferred from HTTP request duration. The adapter reads `headline-clock` reports from worker logs and passes the original streak text shape to both original guards.

## Rollback and limits

`python3 tools/release/rollback.py --provider heroku --candidate-sha FULL_SHA --candidate-id RELEASE_UUID --reason REASON` is shared with the full-suite watchdog. Vercel uses `--provider vercel`. An optional `--previous-id` pins an already captured baseline. Without it, the entry selects the previous successful provider release with a different source SHA. An unknown source SHA or target refuses to mutate. A stale candidate never rolls back a newer release. Rollback is confirmed by a bounded 90-second read of the target source SHA before a success is reported. Successful rollback exits 1 so the watchdog remains visibly failed; a superseded candidate exits 0; an observer or rollback harness error exits 2.

The short rollback job owns `heroku-deploy`, the existing CI writer lock, or `vercel-production`. The 25-minute observer owns only its candidate observer lock and does not block deployments. Provider identity is checked twice before the rollback POST. **Heroku and Vercel do not supply an atomic compare-and-swap rollback against the current release.** The Actions lock excludes other Actions writers, but an independent external deploy in the gap between the last read and POST can still race. All autonomous release writers must adopt these writer locks after the Delivery Speed window finishes; this PR cannot promise transactional safety against an unrelated external deployer.

The provider API currently exposes the active production release, so five-minute reconciliation checks the current release, not an intermediate release already superseded before it ran. Exact event delivery for every out-of-band Heroku release requires an authenticated Heroku webhook bridge to GitHub, which is not configured in this repository. The schedule is the unattended fallback, and this limitation must be resolved before claiming immediate checks after every external release. Vercel's production GitHub deployment event supplies the immediate trigger.

## Verification

`python3 -m unittest discover -s tools/release/tests -v` passes fourteen tests: stale release refusal, exact rollback payloads, unknown identities, partial health degradation, empty/malformed feeds, missing canonical tools, last-verdict selection, no-valid-price conversion, midnight ordering, and missing venue samples. Synthetic data passed to the original guard2 and guard3 produced their exact respective two-minute and three-minute rollback verdicts at 5,000 ms. YAML parses locally and Python compiles under local 3.12; the workflow pins 3.11. Live API calls, provider permissions, event delivery, rollback verification, and a runner on 3.11 remain unverified because internet is disabled here.
