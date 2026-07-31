# Browser audit rail (L2-221 / L2-223, phase 1)

Repo-owned, locally replayable Playwright. This is the replacement for the
retired third-party browser-QA provider (#1497), built to C96's design.

Deliberately kept **out of** the main `frontend/` dependency tree (its own
`package.json` + `tsconfig.json`, and `frontend/tsconfig.json` excludes `e2e`)
so it never enters Vercel/CI installs, `next build`, or the main `tsc --noEmit`
gate. GitHub Actions is orchestration, not the test API — every command below
runs identically on a laptop.

## Phase 1 boundary

**In:** anonymous journeys, manual dispatch only, structural assertions,
evidence artifacts.

**Explicitly out** (later phases, per C96's migration plan): any `schedule:`,
any issue filer, authenticated/seeded state, admin mutation, product/taste or
pixel baselines, and anything that touches the retired provider's history.

Rollback is disabling or deleting `.github/workflows/browser-audit.yml`.
Rollback does **not** mean restoring the retired provider.

## Run it

```bash
cd frontend/e2e

# 1. Contract fixtures. `node --test` — no install, no browser, no network.
#    Proves the false-green cases fail. Runs anywhere Node runs, which is the
#    point: a gate that only works once a package install succeeds is a gate
#    that gets skipped on the day it matters.
npm run contract

npm ci                                   # lockfile-gated; never `npm install`
npx playwright install --with-deps chromium

# 2. Confirm WHICH build is deployed before believing anything it renders.
AUDIT_REQUESTED_SHA=<full-40-hex> \
TRACE_BASE_URL=https://www.bainluck.com \
  npm run wait-for-sha

# 3. The anonymous Discover smoke, desktop + mobile.
AUDIT_REQUESTED_SHA=<full-40-hex> \
AUDIT_OBSERVED_FRONTEND_SHA=<full-40-hex> \
AUDIT_CHECKOUT_SHA=$(git rev-parse HEAD) \
TRACE_BASE_URL=https://www.bainluck.com \
  npm run smoke

# 4. The gate. Exit 0 only on a structurally valid, `pass` manifest whose
#    every claimed artifact re-hashes to the bytes on disk.
npm run validate -- audit-out/manifest.json --verify-bytes
```

In CI: **Actions → Browser audit (manual) → Run workflow**, with
`frontend_sha` set to the full 40-hex commit the deployed frontend must report.

## Why each piece exists

### `helpers/journey.js` — the verdict, as a pure function

The old `discover-latency.spec.ts` wrapped its first-card wait in
`.catch(() => {})` with a comment claiming the result would be null, then
recorded `Date.now() - t0` unconditionally. **A blank Discover render produced
a plausible latency number and passed.** That is the same false-green shape the
dead provider's rail had.

The evaluator now fails a journey unless it saw a real card **or** a *named*
empty state that was *proven visible*, and separately fails any journey that
carries a duration for a card that never appeared. Because it is a pure
function, `contract/journey.contract.test.js` drives the exact same code path
with fixtures — so a case proven to fail there cannot pass in production.

### `helpers/buildAuthority.js` — which build did we actually test?

Vercel deploys independently of Heroku **and** of the GitHub SHA that triggered
CI. A run that reads neither can exercise the previous or the next deployment
and still be attached as proof for the requested commit.

So the frontend publishes its own marker — `GET /api/frontend-build` plus a
`<meta name="bainluck-frontend-commit">` on every page
(`frontend/lib/buildInfo.ts`) — and the rail polls it, boundedly, before
running. Abbreviated SHAs are rejected: 7 chars are ambiguous, and "close
enough" is how a run gets attached to the wrong deployment.

Backend `/health` is recorded in a **separately named field**
(`observed_backend_sha`) and can never satisfy the frontend check.

### `helpers/manifest.js` — the invariant

A manifest validates only when: the schema matches, `selected_count > 0`, the
requested SHA equals the **observed frontend** SHA, every journey has a
terminal result (`pass|fail|infra_error|superseded`) with at least one hashed
artifact, the run result agrees with its journeys, and nothing survived
redaction. `schema/audit-manifest.schema.json` publishes the same contract; a
contract test asserts the two agree on required fields so they cannot drift.

`deriveRunResult([])` is `infra_error`, never `pass` — a rail that collects
nothing must never conclude success.

### What L2-223 added: evidence that is *bound*

L2-221 made it impossible to report green with **no** evidence. It was still
possible to report green with **unbound** evidence — evidence that looked
complete but was not tied to anything checkable. Each of these was a real hole
in the shipped rail, and each now has a dependency-free fixture in
`contract/integrity.contract.test.js`:

| Hole | What it allowed | Now |
|---|---|---|
| No checkout binding | A dispatch from any ref graded production with **that ref's** evaluator and filed the green against the deployed commit | `checkout_sha` is required; if it differs from the audited commit the workflow must have PROVEN ancestry with `git merge-base --is-ancestor` |
| `journeys <= selected` | Selecting 2 journeys and completing 1 validated — one record is not "more than" two | `selected_count == completed_count == journeys.length` |
| No runner status | A runner that failed, timed out, or was interrupted still produced a green manifest from the journeys that *had* finished | `runner_status` is recorded from Playwright's own `FullResult`; a non-`passed` runner can never accompany `result: pass` |
| Free-text `base_url` | A preview deployment or a lookalike host could be audited and filed as production | Exact-origin allowlist on `base_url`, `api_base_url` and the **final** origin the browser landed on, plus a bounded redirect chain |
| Origin-only failure grading | `api.bainluck.com` is a *different origin*, so **every backend 500 behind a blank feed was discarded as third-party noise** | First-party means "ours", not "same origin": the API's 4xx/5xx fail the journey |
| `{name, sha256}` artifacts | A plausible 64-hex digest with no file anywhere validated. A fictional artifact is worse than none — it reads as evidence in every summary | Normalized relative `path` under `artifacts/`, positive byte count, unique across the run, and `--verify-bytes` re-hashes the actual bytes in CI |
| Shell-interpolated input | `$(( ${{ inputs.sha_timeout_seconds }} * 1000 ))` evaluated arbitrary shell arithmetic chosen by the dispatcher — and `${{ }}` expands before the shell sees the line, so quoting would not have helped | Every dispatch input travels through the job env and is pattern-checked before use |

### Trace policy — phase 1 captures none

L2-221 set `trace: "on"` directly beneath a comment explaining that an
authenticated trace retains cookies and tokens. The reasoning was right and the
setting contradicted it.

A Playwright trace is a zip of the whole session: request and response bodies,
storage, and every cookie and authorization header the page sent. The
manifest's redaction pass scrubs **JSON fields**; it cannot touch those bytes.
Uploading one for 90 days and calling the run redacted was not true.

So phase 1 has three locks, not one: `trace: "off"` in the config, the workflow
no longer uploads `test-results/` or `playwright-report/`, and the validator
**rejects** a manifest that declares a trace artifact. Turning tracing back on
requires a reviewed containment policy — short retention, restricted download,
or a scrubber that operates on the trace zip itself — not an edit to the config.

### Stable Discover hooks

The smoke and latency specs used to select a card with
`main div.break-inside-avoid`. That is a Tailwind **layout** class, and
`DiscoverSkeletonGrid` carries it too — so a Discover stuck on skeletons
satisfied "a real card was visible", recorded a first-card latency, and the run
went green. The C96 [P1] false green, reintroduced through the selector rather
than the `.catch()`.

The empty state was matched by the copy string `"You're all caught up"`, so an
editorial reword would have converted a proven empty state into an unproven
blank page.

Both now bind to semantic hooks the components render deliberately:
`data-testid="discover-card"`, `data-testid="discover-empty-state"` with a
machine-readable `data-empty-state-name`, `data-testid="discover-feed-error"`,
and `data-testid="discover-skeleton"` — which the smoke journey now asserts is
**gone**. `frontend/__tests__/components/discoverAuditHooks.test.tsx` fails CI
if a hook is dropped, renamed, or leaks onto the skeleton.

### `helpers/redaction.js` — what may leave the browser

No raw cookies, auth headers, or storage state. URLs keep their origin, path
and query **keys**; query **values** are replaced, because that is where user
text lives. Emails, JWTs, bearer tokens and long hex tokens are scrubbed from
free text.

Phone redaction requires **≥ 7 real digits**, not a phone-ish shape — the
L2-219/L2-220 trap where the build tag `1.4.2 (231)` was rewritten to
`[redacted-phone])`. A scrubber that mangles build tags cannot attest build
identity, so this rail must not inherit it.
`contract/redaction.contract.test.js` pins that case — and its sibling fixture
caught the same class one layer down: ISO timestamps clear the 7-digit bar too,
so they are masked out before phone redaction and restored after.

## Reproducibility

`package.json` pins `@playwright/test` to an exact version and
`package-lock.json` is **committed** (it used to be gitignored). `npm ci` is the
enforcing gate — it exits non-zero when the lock is missing or disagrees with
`package.json`, so a run cannot produce evidence from an unpinned install.
`contract/packaging.contract.test.js` additionally fails if a future edit
reintroduces a range specifier, un-isolates the tree, or loosens the workflow's
permissions / `npm ci` / no-schedule guarantees. It reads the workflow with
comment lines stripped (and asserts the stripped text is non-vacuous), because
a prose mention of `npm install` or `issues: write` is not a configured
behaviour — the first version of those assertions tripped on the workflow's own
explanatory comments.

## What a green run does and does not prove

A green run proves: the named commit was the one deployed, the grading code
came from that commit or a descendant of it, the browser stayed on a canonical
origin, every selected journey produced a record, the runner itself terminated
cleanly, the audited pages rendered a real card or a named empty state, no
console/page errors or first-party (site **or** API) request failures occurred,
and every artifact named in the manifest re-hashes to bytes inside the uploaded
evidence tree.

It does **not** prove anything about signed-in surfaces, consent/telemetry
behaviour (that is the phase-3 consent pack for #1453), or whether the design
is *good*. Structural correctness only.
