/**
 * #5072 — the scheduler is only worth anything if it is CONNECTED, and only
 * NEEDED while the dependency still has the latch.
 *
 * `pollRecovery5072.test.ts` proves the scheduler behaves. It would pass just
 * as happily if `SWRProvider` never called it — a fix that is inert in
 * production and green in CI. These two guards close that gap from both ends:
 * the wiring exists, and the reason for the wiring still exists.
 *
 * A source scan is the right instrument here and a render test is not: the
 * repo has no jsdom rig (`testEnvironment: 'node'`, no `@testing-library/react`,
 * no `jest-environment-jsdom`), and what has to be true is a fact about the
 * config object handed to `SWRConfig`, not about anything on a screen.
 */
import { readFileSync } from "fs";
import { join } from "path";

const providerSource = readFileSync(
  join(__dirname, "..", "..", "components", "SWRProvider.tsx"),
  "utf8",
);

describe("#5072 — the recovery is wired into the provider", () => {
  it("arms recovery from SWR's global onError", () => {
    expect(providerSource).toMatch(/onError:/);
    expect(providerSource).toMatch(/pollRecovery\.recordError\(/);
  });

  it("passes the key's own refreshInterval, not a pinned constant", () => {
    // The load invariant is stated in terms of the key's poll cadence. A
    // hard-coded delay here would make a 5-minute key recover every 30 seconds
    // and the whole safety argument would be false while every unit test still
    // passed, because the unit tests are handed the interval directly.
    expect(providerSource).toMatch(/config\?\.refreshInterval/);
  });

  it("does NOT install a global onSuccess", () => {
    // Four pages define a hook-level `onSuccess` (`app/events/[id]/page.tsx`,
    // `app/categories/[slug]/page.tsx`, `app/event/[domain]/[slug]/page.tsx`,
    // `components/CategoryBrowser.tsx`) and a hook-level callback SHADOWS the
    // global one. A global `onSuccess` would therefore be silently dead on the
    // live event page — the exact page this issue was filed against — so the
    // design deliberately depends on `onError` alone. Someone "completing the
    // pair" later would reintroduce that trap.
    expect(providerSource).not.toMatch(/^\s*onSuccess:/m);
  });

  it("still leaves SWR's own retry ladder off", () => {
    // #L2-137. This ship restores POLLING recovery precisely so that nobody
    // has to reach for `shouldRetryOnError`, which stacks a second retry loop
    // on top of `apiFetch`'s own.
    expect(providerSource).toMatch(/shouldRetryOnError:\s*false/);
  });
});

describe("#5072 — the defect this works around is still in the pinned dependency", () => {
  const swrPkg = JSON.parse(
    readFileSync(
      join(__dirname, "..", "..", "node_modules", "swr", "package.json"),
      "utf8",
    ),
  ) as { version: string };

  const swrDist = readFileSync(
    join(__dirname, "..", "..", "node_modules", "swr", "dist", "index", "index.js"),
    "utf8",
  );

  it("swr's polling effect still refuses to fetch while the key is errored", () => {
    // THIS IS THE PREMISE OF THE WHOLE SHIP. If a future bump makes the poll
    // recover on its own, `lib/pollRecovery.ts` becomes a second poller racing
    // swr's own rather than a fix — harmless but pointless, and worth deleting.
    //
    // Read as: "does the guard that latches the key still exist?" Failing here
    // is not a regression; it is an instruction to re-read #5072 against
    // whatever version is now installed and decide whether to keep this module.
    expect(swrDist).toContain("!getCache().error");
    expect(swrPkg.version).toBe("2.4.1");
  });
});
