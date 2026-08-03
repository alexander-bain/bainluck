import { test, expect, readContentRegionText } from "../fixtures/audit";

/**
 * L2-235 — the Daily and shared-challenge journeys.
 *
 * Both surfaces ship a Share control and neither had any browser coverage.
 * The bug this pack was written alongside is exactly the kind that a unit test
 * cannot see and a screenshot can: `navigator.share ? "native" : "clipboard"`
 * was re-read AFTER the branch had already run, so the reported method was a
 * guess rather than a record, and a browser with neither capability reported a
 * share it never performed.
 *
 * Headless Chromium is precisely that browser for one half of it — it has NO
 * `navigator.share`. So the clipboard branch is the one the rail can actually
 * drive, and it drives it end to end: answer the daily set, click Share, and
 * require the page to say it copied. Under the old code the label was derived
 * from `navigator` a second time; under the fix it is the value the share
 * returned. The visible difference the rail can hold onto is that the toast and
 * the reported method now come from the same decision.
 *
 * ## What this pack deliberately does NOT do
 *
 * **It does not write predictions.** `/api/predictions` is fulfilled locally
 * (see `BLOCKED_WRITE`). Answering five questions is how you reach the Share
 * control, and a rail that leaves five anonymous prediction rows behind on
 * every dispatch is a rail that edits the numbers on `/discover/stats`.
 * Blocking it keeps the journey read-only against production while still
 * exercising the whole client flow.
 *
 * **It does not seed a challenge.** Phase 1 is anonymous-only (see
 * `e2e/README.md`), so there is no real challenge code to visit and the share
 * control on `/challenge/[id]` is behind the loaded state. What IS gradeable
 * anonymously — and is the failure users actually hit from a stale link — is
 * that an unknown code renders a NAMED not-found state rather than a blank
 * page or a loader that never unmounts. Reaching the challenge share button
 * needs seeded state and belongs to a later phase.
 */

/** The declared budget for either page to reach a terminal state. */
const PAGE_BUDGET_MS = 45_000;

/**
 * The prediction write. Fulfilled with a 200 so it is neither a production
 * mutation nor a failed first-party request — the journey grades the client
 * flow, not this endpoint.
 */
const BLOCKED_WRITE = "**/api/predictions";

/** A code that cannot exist. Deterministic, so the 404 below is declarable. */
const UNKNOWN_CHALLENGE_CODE = "l2235-audit-no-such-challenge";

/**
 * The two answer buttons, alternated. Named as literals so
 * `__tests__/components/dailyChallengeAuditHooks.test.ts` can prove the page
 * still renders both.
 */
const GUESS_HOOKS = ["daily-guess-higher", "daily-guess-lower"] as const;

test("daily reports only a share that actually happened", async ({ page, journey }) => {
  const path = "/daily";

  await page.route(BLOCKED_WRITE, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" })
  );

  // The clipboard branch is the one this browser can take. Without the grant
  // `writeText` rejects, the handler swallows it, and the page correctly
  // reports nothing — which would be a true negative about the browser rather
  // than a finding about the page.
  await page
    .context()
    .grantPermissions(["clipboard-read", "clipboard-write"])
    .catch(() => {});

  await page.goto(path, { waitUntil: "domcontentloaded" });

  const pageRoot = page.locator('[data-testid="daily-page"]').first();
  const emptyState = page.locator('[data-testid="daily-empty-state"]').first();

  // Race the two terminal states. A daily set needs five guessable markets in
  // the feed; not having them is a legitimate, NAMED outcome, not a failure.
  await Promise.race([
    pageRoot.waitFor({ state: "visible", timeout: PAGE_BUDGET_MS }).catch(() => null),
    emptyState.waitFor({ state: "visible", timeout: PAGE_BUDGET_MS }).catch(() => null),
  ]);

  const emptyVisible = await emptyState.isVisible().catch(() => false);
  const emptyName = emptyVisible
    ? await emptyState.getAttribute("data-empty-state-name", { timeout: 2_000 }).catch(() => null)
    : null;
  const rootVisible = await pageRoot.isVisible().catch(() => false);

  // Answering the set is what reveals the Share control. Bounded by the goal
  // (5) plus slack rather than looping on the button's presence forever.
  //
  // Alternating the two buttons is deliberate: a loop that only ever clicks
  // Higher cannot notice that Lower stopped answering.
  let answered = 0;
  if (rootVisible && !emptyVisible) {
    for (let i = 0; i < 8; i += 1) {
      const hook = GUESS_HOOKS[i % GUESS_HOOKS.length];
      const guess = page.locator(`[data-testid="${hook}"]`).first();
      if (!(await guess.isVisible().catch(() => false))) break;
      await guess.click({ timeout: 5_000 }).catch(() => {});
      answered += 1;
    }
  }

  const shareButton = page.locator('[data-testid="daily-share"]').first();
  const shareVisible = await shareButton.isVisible().catch(() => false);

  // The observable the fix owns: the copied state and the reported method now
  // come from the same returned value instead of two separate reads.
  let copiedAfterShare: string | null = null;
  if (shareVisible) {
    await shareButton.click({ timeout: 5_000 }).catch(() => {});
    copiedAfterShare = await shareButton
      .getAttribute("data-share-copied", { timeout: 5_000 })
      .catch(() => null);
  }

  const mainText = await readContentRegionText(page);

  await journey.finish({
    journeyId: "daily.anonymous.share",
    expectedPath: path,
    // The subject is the daily flow, not the Discover feed, so the shared
    // card check does not apply. The blank-region check below still does.
    contentMode: "none",
    realCardFound: false,
    emptyState: emptyVisible ? { name: emptyName ?? "unnamed", visible: true } : null,
    mainRegionNonBlank: mainText.trim().length > 120,
  });

  // An empty daily set is a terminal, honest outcome — but it must be NAMED.
  // An unnamed empty state is indistinguishable from a blank render.
  if (emptyVisible) {
    expect(emptyName, "the empty daily state must name itself").not.toBeNull();
    expect(emptyName, "the empty daily state must name itself").not.toBe("");
    return;
  }

  // Ordered most-diagnostic first.
  expect(rootVisible, "the daily page root hook must render").toBe(true);
  expect(answered, "the daily set must present at least one question to answer").toBeGreaterThan(0);
  expect(shareVisible, `the share control must appear after answering (answered ${answered})`).toBe(
    true
  );
  expect(
    copiedAfterShare,
    "clicking Share must put the page in its copied state — the clipboard branch " +
      "ran, so the page must report that it ran",
  ).toBe("true");
});

test("an unknown shared challenge renders a named not-found state", async ({ page, journey }) => {
  const path = `/challenge/${UNKNOWN_CHALLENGE_CODE}`;

  // The 404 is the POINT of this journey, so it is declared rather than
  // discovered. The evaluator fails any first-party 4xx that is not named
  // here, which is what keeps this from being a blanket exemption.
  const apiBase = (process.env.AUDIT_API_BASE_URL || "https://api.bainluck.com").replace(/\/$/, "");
  const expected404 = `${apiBase}/api/challenges/${UNKNOWN_CHALLENGE_CODE}`;

  await page.goto(path, { waitUntil: "domcontentloaded" });

  const errorState = page.locator('[data-testid="challenge-error"]').first();
  const loadedPage = page.locator('[data-testid="challenge-page"]').first();

  await Promise.race([
    errorState.waitFor({ state: "visible", timeout: PAGE_BUDGET_MS }).catch(() => null),
    loadedPage.waitFor({ state: "visible", timeout: PAGE_BUDGET_MS }).catch(() => null),
  ]);

  const errorVisible = await errorState.isVisible().catch(() => false);
  const errorName = errorVisible
    ? await errorState.getAttribute("data-error-state-name", { timeout: 2_000 }).catch(() => null)
    : null;
  // The loader is what a hung fetch leaves mounted. Its own aria-label is the
  // hook, because it renders before any page root does.
  const loaderVisible = await page
    .getByLabel("Loading challenge")
    .first()
    .isVisible()
    .catch(() => false);

  const mainText = await readContentRegionText(page);

  await journey.finish({
    journeyId: "challenge.anonymous.unknown_code",
    expectedPath: path,
    contentMode: "none",
    realCardFound: false,
    emptyState: errorVisible ? { name: errorName ?? "unnamed", visible: true } : null,
    mainRegionNonBlank: mainText.trim().length > 80,
    allowedFailures: [expected404],
  });

  expect(errorVisible, "an unknown code must render the named error state").toBe(true);
  expect(
    errorName,
    "the error state must say WHICH failure it is, so a copy edit cannot change the verdict",
  ).toBe("challenge-not-found");
  expect(loaderVisible, "the loading state must not still be mounted").toBe(false);
});
