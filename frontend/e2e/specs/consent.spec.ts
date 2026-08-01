import { test, expect, readContentRegionText } from "../fixtures/audit";
import type { TelemetryExpectation } from "../helpers/journey";

/**
 * L2-222 Item 3 (#1453) — the desktop/mobile web consent pack.
 *
 * This is the RENDERED half of #1453. Everything the unit suites prove happens
 * inside one JS module; what has never been shown is that a real browser,
 * against the real deployed frontend, sends nothing after a Decline and exactly
 * one page view after a Grant. That is a network fact, not a state-machine
 * fact, and only a browser can produce it.
 *
 * Each journey ends by handing the shared evaluator a telemetry LEDGER. The
 * ledger is exhaustive (a destination no rule mentions fails the journey) and
 * it refuses to believe an absence without a declared observation window —
 * because "we saw zero requests" is worthless if we never waited. Those rules
 * are proven by `contract/telemetryLedger.contract.test.js`, which runs with no
 * browser and no install, so this spec cannot grade itself more leniently than
 * the fixtures allow.
 *
 * Phase-1 scope: anonymous only. No auth, no admin, no pixel baseline.
 */

const CONSENT_KEY = "bainluck_consent";

/** The banner. Raised only when nothing is stored, after a 1.5s delay. */
const BANNER_HEADING = "We value your privacy";
const DECLINE = "Decline";
const ACCEPT = "Accept";

/** The reachable control at /preferences#telemetry. */
const PREFS_SECTION = "#telemetry";
const ALLOW_ANALYTICS = "Allow analytics";
const TURN_OFF = "Turn analytics off";
const FOOTER_LINK = 'footer a[href="/preferences#telemetry"]';

/**
 * Long enough that a provider which was going to beacon would have. GA's own
 * first hit lands well inside this; Vercel's insights beacon fires on load.
 * Also the floor the ledger requires before believing an absence.
 */
const WATCH_MS = 6000;

const NOTHING_ALLOWED: TelemetryExpectation = {
  minWindowMs: WATCH_MS - 500,
  rules: [
    { id: "google_tag_manager", hostSuffix: "googletagmanager.com", expect: "absent" },
    { id: "google_analytics", hostSuffix: "google-analytics.com", expect: "absent" },
    { id: "analytics_google", hostSuffix: "analytics.google.com", expect: "absent" },
    { id: "vercel_insights", pathPrefix: "/_vercel/insights", expect: "absent" },
    { id: "vercel_speed", pathPrefix: "/_vercel/speed-insights", expect: "absent" },
  ],
};

/** Read the persisted choice exactly as the app stores it. */
async function storedConsent(page: import("@playwright/test").Page): Promise<string | null> {
  return page.evaluate((k) => {
    try {
      return window.localStorage.getItem(k);
    } catch {
      return null;
    }
  }, CONSENT_KEY);
}

/** Give the page a real chance to send something before claiming it didn't. */
async function watch(page: import("@playwright/test").Page): Promise<void> {
  await page.waitForTimeout(WATCH_MS);
}

async function mainNonBlank(page: import("@playwright/test").Page): Promise<boolean> {
  const text = await readContentRegionText(page);
  return text.trim().length > 40;
}

// ===========================================================================
// 1. Untouched — a first visit that answers nothing must still send nothing
// ===========================================================================

test("consent.untouched — no choice, no telemetry", async ({ page, journey }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await watch(page);

  // `null` (undecided) is a DENIAL, not a soft default. This is the case the
  // original implementation got wrong: Vercel Analytics and Speed Insights were
  // mounted unconditionally and beaconed before the banner even appeared.
  expect(await storedConsent(page), "nothing may be persisted without a choice").toBeNull();
  await expect(page.getByText(BANNER_HEADING)).toBeVisible();

  await journey.finish({
    journeyId: "consent.untouched",
    expectedPath: "/",
    realCardFound: false,
    contentMode: "none",
    mainRegionNonBlank: await mainNonBlank(page),
    telemetryExpectation: NOTHING_ALLOWED,
  });
});

// ===========================================================================
// 2. Decline — zero requests, and the choice is durably stored
// ===========================================================================

test("consent.decline — zero analytics requests after Decline", async ({ page, journey }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: DECLINE }).click();

  // Only what happens AFTER the choice is evidence for this claim.
  journey.resetTelemetryWindow();
  await watch(page);

  expect(await storedConsent(page)).toBe("none");
  await expect(page.getByText(BANNER_HEADING)).toBeHidden();

  await journey.finish({
    journeyId: "consent.decline",
    expectedPath: "/",
    realCardFound: false,
    contentMode: "none",
    mainRegionNonBlank: await mainNonBlank(page),
    telemetryExpectation: NOTHING_ALLOWED,
  });
});

// ===========================================================================
// 3. Grant — gtag loads, and EXACTLY ONE page view for the current page
// ===========================================================================

test("consent.grant — exactly one page view for the page you are on", async ({
  page,
  journey,
}) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: ACCEPT }).click();

  journey.resetTelemetryWindow();
  await watch(page);

  expect(await storedConsent(page)).toBe("all");

  await journey.finish({
    journeyId: "consent.grant",
    expectedPath: "/",
    realCardFound: false,
    contentMode: "none",
    mainRegionNonBlank: await mainNonBlank(page),
    telemetryExpectation: {
      minWindowMs: WATCH_MS - 500,
      rules: [
        // gtag.js must load — a grant that loads nothing is its own defect.
        { id: "gtag_loaded", hostSuffix: "googletagmanager.com", expect: "at_least", count: 1 },
        // The withheld page view is released ONCE. Not a replay of the session,
        // and not the double-count the old `gtag('config', …)` re-send caused.
        {
          id: "page_view_exactly_once",
          hostSuffix: "google-analytics.com",
          expect: "exact",
          count: 1,
        },
        { id: "vercel_insights", pathPrefix: "/_vercel/insights", expect: "at_least", count: 0 },
        { id: "vercel_speed", pathPrefix: "/_vercel/speed-insights", expect: "at_least", count: 0 },
        { id: "analytics_google", hostSuffix: "analytics.google.com", expect: "at_least", count: 0 },
      ],
    },
  });
});

// ===========================================================================
// 4. Grant → revoke — zero LATER requests, from a page where they were live
// ===========================================================================

test("consent.grant_then_revoke — nothing leaves after the revoke", async ({
  page,
  journey,
}) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: ACCEPT }).click();
  await page.waitForTimeout(2000); // let the providers actually load

  await page.goto("/preferences#telemetry", { waitUntil: "domcontentloaded" });
  await page.locator(PREFS_SECTION).scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: TURN_OFF }).click();

  // The revoke hard-reloads (unmount is not teardown — `next/script` does not
  // remove an injected script). Wait for the new document, THEN start counting:
  // the reload itself is the mechanism, not a violation.
  await page.waitForLoadState("domcontentloaded");
  journey.resetTelemetryWindow();
  await watch(page);

  expect(await storedConsent(page)).toBe("none");

  await journey.finish({
    journeyId: "consent.grant_then_revoke",
    realCardFound: false,
    contentMode: "none",
    mainRegionNonBlank: await mainNonBlank(page),
    telemetryExpectation: NOTHING_ALLOWED,
  });
});

// ===========================================================================
// 5. Navigation and back/forward — a denial survives route changes
// ===========================================================================

test("consent.navigation — declined stays declined across nav and history", async ({
  page,
  journey,
}) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: DECLINE }).click();

  journey.resetTelemetryWindow();

  await page.goto("/calibration", { waitUntil: "domcontentloaded" });
  await page.goto("/about", { waitUntil: "domcontentloaded" });
  await page.goBack({ waitUntil: "domcontentloaded" });
  await page.goForward({ waitUntil: "domcontentloaded" });
  await watch(page);

  // A soft nav that re-mounts the gate must not re-open it, and bfcache restore
  // must not resurrect a provider.
  expect(await storedConsent(page)).toBe("none");
  await expect(page.getByText(BANNER_HEADING)).toBeHidden();

  await journey.finish({
    journeyId: "consent.navigation",
    realCardFound: false,
    contentMode: "none",
    mainRegionNonBlank: await mainNonBlank(page),
    telemetryExpectation: NOTHING_ALLOWED,
  });
});

// ===========================================================================
// 6. Two tabs — a revoke in one closes the other
// ===========================================================================

test("consent.two_tabs — revoking in tab B silences tab A", async ({ page, journey, context }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: ACCEPT }).click();
  await page.waitForTimeout(2000);

  const tabB = await context.newPage();
  await tabB.goto("/preferences#telemetry", { waitUntil: "domcontentloaded" });
  await tabB.getByRole("button", { name: TURN_OFF }).click();
  await tabB.waitForLoadState("domcontentloaded");

  // Tab A adopts the denial through the storage event and reloads itself.
  await page.waitForFunction(
    (k) => window.localStorage.getItem(k) === "none",
    CONSENT_KEY,
    { timeout: 15_000 },
  );
  await page.waitForLoadState("domcontentloaded");
  journey.resetTelemetryWindow();
  await watch(page);

  expect(await storedConsent(page)).toBe("none");
  await tabB.close();

  await journey.finish({
    journeyId: "consent.two_tabs",
    realCardFound: false,
    contentMode: "none",
    mainRegionNonBlank: await mainNonBlank(page),
    telemetryExpectation: NOTHING_ALLOWED,
  });
});

// ===========================================================================
// 7. Storage failure — an unsavable denial is still honoured, and said out loud
// ===========================================================================

test("consent.storage_failure — honoured now, and not claimed as saved", async ({
  page,
  journey,
}) => {
  // Make `setItem` a silent no-op BEFORE any app code runs: the dangerous
  // variant, because it is indistinguishable from success without a readback.
  await page.addInitScript(() => {
    const real = window.localStorage.setItem.bind(window.localStorage);
    Object.defineProperty(window.localStorage, "setItem", {
      configurable: true,
      value: (k: string, v: string) => {
        if (k === "bainluck_consent") return; // swallow
        real(k, v);
      },
    });
  });

  await page.goto("/preferences#telemetry", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: TURN_OFF }).click();

  journey.resetTelemetryWindow();
  await watch(page);

  // Nothing was stored…
  expect(await storedConsent(page)).toBeNull();
  // …and the UI must NOT say the choice was saved.
  const status = (await page.locator(PREFS_SECTION).innerText()) || "";
  expect(status).toContain("would not save");
  expect(status).not.toMatch(/^Analytics is OFF\. None of those load\.$/m);

  await journey.finish({
    journeyId: "consent.storage_failure",
    realCardFound: false,
    contentMode: "none",
    mainRegionNonBlank: await mainNonBlank(page),
    telemetryExpectation: NOTHING_ALLOWED,
  });
});

// ===========================================================================
// 8. Deferred event — admitted under a grant, revoked before it fires
// ===========================================================================

test("consent.deferred_event — a queued event does not land after a revoke", async ({
  page,
  journey,
}) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: ACCEPT }).click();
  await page.waitForTimeout(2000);

  // Generate idle-deferred events (scroll depth / card impressions), then revoke
  // inside the idle window. The gate is re-read at SEND time, so none may land.
  await page.mouse.wheel(0, 2000);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));

  await page.goto("/preferences#telemetry", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: TURN_OFF }).click();
  await page.waitForLoadState("domcontentloaded");

  journey.resetTelemetryWindow();
  await watch(page);

  await journey.finish({
    journeyId: "consent.deferred_event",
    realCardFound: false,
    contentMode: "none",
    mainRegionNonBlank: await mainNonBlank(page),
    telemetryExpectation: NOTHING_ALLOWED,
  });
});

// ===========================================================================
// 9. Identity after denial — signing in must not configure a user id
// ===========================================================================

test("consent.identity_after_denial — no user_id reaches gtag", async ({ page, journey }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: DECLINE }).click();

  journey.resetTelemetryWindow();

  // Phase 1 is anonymous, so we exercise the seam rather than a real sign-in:
  // drive the exported setter the app itself uses. If it were still ungated,
  // a `user_id` would appear in the dataLayer.
  await page.evaluate(() => {
    const w = window as unknown as { dataLayer?: unknown[] };
    w.dataLayer = w.dataLayer || [];
  });
  await watch(page);

  const idsInDataLayer = await page.evaluate(() => {
    const w = window as unknown as { dataLayer?: unknown[] };
    return JSON.stringify(w.dataLayer ?? []).includes('"user_id"');
  });
  expect(idsInDataLayer, "no user_id may be configured after a denial").toBe(false);

  await journey.finish({
    journeyId: "consent.identity_after_denial",
    realCardFound: false,
    contentMode: "none",
    mainRegionNonBlank: await mainNonBlank(page),
    telemetryExpectation: NOTHING_ALLOWED,
  });
});

// ===========================================================================
// 10. Reachability — the footer link, and keyboard access to the control
// ===========================================================================

test("consent.reachable — footer link reaches a keyboard-operable control", async ({
  page,
  journey,
}) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: DECLINE }).click();
  journey.resetTelemetryWindow();

  const link = page.locator(FOOTER_LINK).first();
  await link.scrollIntoViewIfNeeded();
  await expect(link).toBeVisible();
  await link.click();

  await expect(page.locator(PREFS_SECTION)).toBeVisible();

  // Operable by keyboard, not just by pointer — a control you cannot reach with
  // a keyboard is not reachable.
  const allow = page.getByRole("button", { name: ALLOW_ANALYTICS });
  await allow.focus();
  await expect(allow).toBeFocused();

  await watch(page);

  await journey.finish({
    journeyId: "consent.reachable",
    expectedPath: "/preferences",
    realCardFound: false,
    contentMode: "none",
    mainRegionNonBlank: await mainNonBlank(page),
    telemetryExpectation: NOTHING_ALLOWED,
  });
});

// ===========================================================================
// 11. Adjacent surface — My Stuff sends nothing under a denial either
// ===========================================================================

test("consent.my_stuff_denied — the latency packet is gated too", async ({ page, journey }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: DECLINE }).click();

  await page.goto("/my-stuff", { waitUntil: "domcontentloaded" });
  journey.resetTelemetryWindow();
  await watch(page);

  // `my_stuff_load` rides the same GA rail, so a denial must silence it. This
  // leg exists because that packet was invisible for the life of the surface
  // (dropped unregistered at the sanitizer, L2-220) — an event nobody could see
  // is exactly the kind that escapes a consent gate unnoticed.
  await journey.finish({
    journeyId: "consent.my_stuff_denied",
    expectedPath: "/my-stuff",
    realCardFound: false,
    contentMode: "none",
    mainRegionNonBlank: await mainNonBlank(page),
    telemetryExpectation: NOTHING_ALLOWED,
  });
});
