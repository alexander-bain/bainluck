/**
 * LAT-P171 — the browser SDK is loaded ONLY when a DSN exists to send to.
 *
 * Measured 2026-08-31 against the deployed bundle: `@sentry/nextjs` was 102 kB
 * of the 160 kB "shared by all" chunk — 42% of Discover's 243 kB First Load JS,
 * on EVERY route — and `NEXT_PUBLIC_SENTRY_DSN` is not set on Vercel, so no DSN
 * appears anywhere in the served JS. The SDK initialized, instrumented fetch /
 * history / web-vitals, and sent nothing: over 14 days the org's only reporting
 * SDK was `sentry.python.fastapi` (2,396 events), with ZERO events and ZERO
 * transactions from the JavaScript SDK.
 *
 * That weight is on the cold critical path. All 20 entry chunks must download,
 * parse and execute before React hydrates, and the `/api/feed` request that
 * gates the first card is not issued until hydration runs — so a monitoring SDK
 * wired to nowhere delays the cards.
 *
 * 🔴 THIS DOES NOT REMOVE THE CAPABILITY, IT STOPS SHIPPING A DISCONNECTED COPY
 * OF IT. `process.env.NEXT_PUBLIC_SENTRY_DSN` is inlined at build time, so with
 * no DSN webpack eliminates the branch and never bundles the SDK; set the var on
 * Vercel and the next build reinstates it, initialized from the same options.
 * The one behavioural difference when a DSN IS set is that init happens in a
 * microtask after the entry module rather than inside it — errors thrown in that
 * window are missed, which is the price of not blocking every cold load on it.
 */
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  void import("@sentry/nextjs").then((Sentry) => {
    Sentry.init({
      dsn,

      // Only enable in production
      enabled: process.env.NODE_ENV === "production",

      // Sample 10% of transactions for performance monitoring
      tracesSampleRate: 0.1,

      // Disable session replay (not needed, saves bandwidth)
      replaysSessionSampleRate: 0,
      replaysOnErrorSampleRate: 0,
    });
  });
}

export {};
