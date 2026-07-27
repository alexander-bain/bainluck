# Discover latency traces (L2-189)

Isolated, repeatable Playwright harness for measuring perceived Discover
latency. Deliberately kept **out of** the main `frontend/` dependency tree
(its own `package.json` + `tsconfig.json`) so it never enters Vercel/CI
installs or `next build`, and is excluded from the main `tsc --noEmit` gate.

## Run

```bash
cd frontend/e2e
npm install
npx playwright install chromium
# Defaults to https://www.bainluck.com; point at any environment:
TRACE_BASE_URL=https://www.bainluck.com npm run trace:discover
```

## What it records (per navigation, separated)

For `/` and `/discover`, at **desktop (1280×800)** and **375px (Pixel 5)**,
for a **cold** load and a **warm** reload:

- **shell** — `responseStart` (TTFB), `domContentLoadedEventEnd`, `loadEventEnd`
  from the Navigation Timing API (pre-hydration server structure).
- **feed** — the `/api/feed` round-trip: HTTP status, Playwright request
  timing (`responseEnd − requestStart`), plus the backend-attested
  `X-Feed-Elapsed-Ms` compute time and `X-Feed-Cache` disposition — readable
  because L2-189 added both to CORS `expose_headers`.
- **first card** — wall-clock to the first real (non-skeleton) card link.

Each run prints a `[discover-latency]` JSON blob and attaches
`discover-latency.json` to the Playwright report. A Playwright trace
(`trace: "on"`) is captured so the hydration/render/image slice between the
feed response and first card can be inspected frame-by-frame in
`npx playwright show-report`.

## Invariants (not targets)

The spec asserts only shape/ordering — it records latency, it does **not**
assert any latency budget (those are product decisions):

- a `/api/feed` response is observable, and
- backend compute (`X-Feed-Elapsed-Ms`) ≤ full client round-trip (+slack).
