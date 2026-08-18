import { test, expect, readContentRegionText } from "../fixtures/audit";
import { RSC_PREFETCH_ABORT } from "../helpers/navigationAborts";

/**
 * UX-P086 (#1620) — the RENDERED half of "lead with the answer" on the PHONE.
 *
 * ── WHY THIS PACK EXISTS ──
 *
 * #1620 said the phone search dropdown never got #993 Slice A. That was true
 * when it was filed and it stopped being true on 2026-08-09: UX-P035 extracted
 * the row presentation into `lib/searchSuggestionDisplay.ts`, wired BOTH
 * dropdowns to it, and merged (`1e940a35`, an ancestor of master). Cycle 82
 * re-measured the premise before building anything and found the code already
 * shipped — the eighth consecutive cycle in which a staged premise was
 * falsified by running the instrument first.
 *
 * What was never produced is the PHOTOGRAPH. #1620's own acceptance names a
 * production proof — `answer_visible_typeahead` with `surface=mobile` going
 * from zero to non-zero — and that proof was never collected, which is the
 * honest reason the issue is still open eight days later. A GA4 counter is also
 * not something this lane can read, so the provider-independent substitute is
 * this: a real browser, at a real phone viewport, against the real deployed
 * frontend, photographing the answer row.
 *
 * That gap is the same one the league-cards and event-page packs were built to
 * close, and it is the specific way a shipped UX fix rots: nothing fails when a
 * rendered feature quietly stops rendering, because no gate ever looked at it.
 *
 * ── THE ORACLE IS THE PAYLOAD, NOT A SECOND READING OF THE SCREEN ──
 *
 * Counting rows and then asserting the rows look right is scraping the surface
 * under test: a wrong render and a wrong expectation agree and pass. So each
 * journey fetches `/api/events/typeahead` itself and re-derives, from the
 * payload, HOW MANY rows the dropdown OWES an answer to. The DOM is then
 * checked against that independently-derived count.
 *
 * The derivation is deliberately RESTATED here rather than imported from
 * `lib/searchSuggestionDisplay`. Importing the implementation would make this
 * the constant-oracle family (gotcha #121) — the test comparing production to
 * the very function production reads, which asserts nothing. It is kept to the
 * one rule that matters ("a futures suggestion with at least one non-null
 * probability owes an answer") so a refinement elsewhere cannot red it
 * spuriously.
 *
 * ── DELIBERATE LIMITS, STATED ──
 *
 *  - `contentMode: "none"` — the shared evaluator's card check is written for
 *    the Discover feed. The blank-page check still applies; the assertions
 *    below are this spec's own.
 *  - The query is a fixed, high-inventory term. If production returns no priced
 *    futures for it at all, the journey asserts the HONEST-EMPTY direction
 *    (rows rendered, no fabricated answers) rather than failing — an upstream
 *    inventory gap is not a render defect. The run still records what it saw,
 *    so a permanently answerless dropdown shows up as a standing zero rather
 *    than a green.
 *  - No coherence assertion. Production really does return three outcomes at
 *    100% for "Next Red Sox Manager"; that is gap-list K6 and #1620 ruled it
 *    explicitly out of scope. Suppressing it would also hide legitimate
 *    independent-binary fields (gotcha #23). The rail photographs what ships.
 */

/** Both dropdowns mark their rows identically (added by this queue). */
const ROW = '[data-testid="search-suggestion"]';
/** The #993 Slice A subtitle — the thing that was never on a phone. */
const ANSWER = '[data-testid="search-answer"]';
/** The phone entry point; absent above the `md` breakpoint. */
const MOBILE_TRIGGER = 'button[aria-label="Open search"]';
/**
 * Present on both surfaces — and, on a phone, present TWICE.
 *
 * UX-P087, from this pack's first real run (32066929779, at the ux-73 merge SHA):
 * both mobile journeys died before touching the page with
 *
 *     strict mode violation: locator('input[aria-label="Search…"]')
 *     resolved to 2 elements
 *
 * `layout.tsx` keeps the desktop `SearchBar` mounted inside a `hidden md:block`
 * container at every width, so on a phone its input is in the DOM alongside the
 * overlay's — and `SearchBar.tsx:336` and `MobileSearchOverlay.tsx:180` give them
 * the SAME accessible name. Playwright counts DOM matches, not painted ones.
 *
 * `.first()` is NOT the repair, and this is the part worth writing down: in DOM
 * order the hidden desktop input comes first, so `.first()` on a phone would
 * quietly drive the input the reader cannot see — a green run photographing the
 * wrong surface, on the pack whose entire purpose is that #993 shipped to
 * desktop and missed the phone. `:visible` picks the one a reader could actually
 * type into, which is what every assertion here means by "the input".
 */
const INPUT = 'input[aria-label="Search teams, games, and futures"]:visible';

/**
 * A term with durable inventory on both sides: a team (unpriced row, proves the
 * fallback) and several priced futures (proves the answer). Fixed rather than
 * random so a red is reproducible.
 */
const QUERY = "red sox";

/** A leader line reads `Name 67%`. This is the shape, not a specific value. */
const PERCENT = /\d{1,3}\s*%/;

interface TypeaheadOutcomeLike {
  name?: string;
  probability?: number | null;
}
interface SuggestionLike {
  type?: string;
  text?: string;
  top_outcomes?: TypeaheadOutcomeLike[] | null;
}

/**
 * What the dropdown owes, derived from the payload alone.
 *
 * Restated, not imported — see the header. One rule: a futures suggestion
 * carrying at least one non-null probability must lead with an answer.
 */
function deriveOwed(suggestions: SuggestionLike[]): {
  total: number;
  answersOwed: number;
  unpricedFutures: number;
} {
  let answersOwed = 0;
  let unpricedFutures = 0;
  for (const s of suggestions) {
    if (s.type !== "futures") continue;
    const priced = (s.top_outcomes ?? []).filter(
      (o) => o && o.probability !== null && o.probability !== undefined,
    );
    if (priced.length > 0) answersOwed += 1;
    else unpricedFutures += 1;
  }
  return { total: suggestions.length, answersOwed, unpricedFutures };
}

/** Ask production directly. The API base is the audited deployment's own. */
async function fetchOwed(page: import("@playwright/test").Page) {
  const apiBase = process.env.AUDIT_API_BASE_URL || "https://api.bainluck.com";
  const res = await page.request.get(
    `${apiBase}/api/events/typeahead?q=${encodeURIComponent(QUERY)}`,
    { timeout: 30_000 },
  );
  // A 429 here is the rail's own rate-limit budget, not a product defect, and
  // it must not be reported as "the dropdown owes nothing" (gotcha #53: an
  // empty 200 and an unavailable answer are different facts).
  expect(
    res.ok(),
    `the typeahead oracle returned HTTP ${res.status()} — the payload could not be ` +
      `read, so nothing about the DOM can be graded against it`,
  ).toBeTruthy();
  const body = (await res.json()) as unknown;
  const suggestions: SuggestionLike[] = Array.isArray(body)
    ? (body as SuggestionLike[])
    : ((body as { suggestions?: SuggestionLike[] })?.suggestions ?? []);
  return { ...deriveOwed(suggestions), suggestions };
}

/**
 * Open whichever dropdown this viewport actually mounts and type the query.
 *
 * The two are mutually exclusive by viewport — `layout.tsx` mounts
 * `MobileSearchTrigger` in a `md:hidden` container and `SearchBar` in a
 * `hidden md:block` one — which is the structural reason #993 could ship to one
 * and miss the other entirely. The pack runs on both projects so the phone is
 * graded and the desktop is the control.
 */
async function openDropdown(page: import("@playwright/test").Page): Promise<"mobile" | "desktop"> {
  const trigger = page.locator(MOBILE_TRIGGER);
  const isPhone = await trigger.isVisible().catch(() => false);

  if (isPhone) {
    await trigger.click();
    await page.locator(INPUT).waitFor({ state: "visible", timeout: 15_000 });
  } else {
    await page.locator(INPUT).click();
  }

  // No `.first()` anywhere: `INPUT` is `:visible`-scoped, so exactly one element
  // matches on either surface, and an ambiguity would be a strict-mode RED
  // rather than a silent pick. See the selector's comment — `.first()` on a
  // phone selects the hidden desktop input.
  await page.locator(INPUT).fill(QUERY);
  // The dropdown is debounced; wait for rows rather than a fixed sleep.
  await page
    .locator(ROW)
    .first()
    .waitFor({ state: "visible", timeout: 20_000 })
    .catch(() => null);

  return isPhone ? "mobile" : "desktop";
}

test("the search dropdown leads with the answer", async ({ page, journey }) => {
  const path = "/";
  await page.goto(path, { waitUntil: "domcontentloaded" });

  const owed = await fetchOwed(page);
  const surface = await openDropdown(page);

  const rows = await page.locator(ROW).count().catch(() => 0);
  const answers = await page.locator(ANSWER).count().catch(() => 0);
  const answerTexts = await page.locator(ANSWER).allInnerTexts().catch(() => [] as string[]);
  const mainText = await readContentRegionText(page);

  await journey.finish({
    allowedNavigationAborts: [RSC_PREFETCH_ABORT],
    journeyId: `search.answer_first_row.${surface}`,
    expectedPath: path,
    contentMode: "none",
    realCardFound: false,
    mainRegionNonBlank: mainText.trim().length > 40,
  });

  // The dropdown must have rendered at all. This is the #1620 precondition:
  // the phone surface exists and responds to typing.
  expect(
    rows,
    `typing "${QUERY}" on the ${surface} surface rendered ZERO suggestion rows, ` +
      `while the API returned ${owed.total} suggestion(s) — the dropdown is not ` +
      `consuming the payload at all`,
  ).toBeGreaterThan(0);

  if (owed.answersOwed > 0) {
    // THE ASSERTION #1620 EXISTS FOR. The payload carries priced futures, so
    // the dropdown must lead with the answer rather than a bare title.
    expect(
      answers,
      `the payload owes ${owed.answersOwed} answer row(s) for "${QUERY}" but the ` +
        `${surface} dropdown rendered ${answers}. On mobile this is #1620 itself: ` +
        `the row falls back to the desktop code's else-branch and shows a bare ` +
        `title where the leader's probability belongs.`,
    ).toBeGreaterThan(0);

    // Whatever it rendered must actually state a probability — a leader line
    // with no percentage is the same defect wearing the right testid.
    const withPercent = answerTexts.filter((t) => PERCENT.test(t));
    expect(
      withPercent.length,
      `${answers} answer row(s) rendered on ${surface} but none states a ` +
        `percentage. Texts: ${JSON.stringify(answerTexts.slice(0, 4))}`,
    ).toBeGreaterThan(0);
  } else {
    // HONEST-EMPTY, and recorded rather than silently passed: production had no
    // priced futures for this term. Nothing may be fabricated.
    expect(
      answers,
      `the payload carries NO priced futures for "${QUERY}", so the ${surface} ` +
        `dropdown must show no answer rows — it rendered ${answers}`,
    ).toBe(0);
  }
});

/**
 * The other direction, per gotcha #43. A cap or a fallback must not be proven
 * only in the direction that makes it look good:
 *
 *  - an UNPRICED futures suggestion must still render its row (falling back to
 *    `market_type_label`), not vanish;
 *  - a row with no subtitle must render no empty line;
 *  - and the non-futures rows (teams, games) must survive alongside the
 *    answers, which is the adjacent-surface half — the same shape that emptied
 *    the Sports tab in #1091.
 */
test("answer rows do not displace the rest of the dropdown", async ({ page, journey }) => {
  const path = "/";
  await page.goto(path, { waitUntil: "domcontentloaded" });

  const owed = await fetchOwed(page);
  const surface = await openDropdown(page);

  const rows = await page.locator(ROW).count().catch(() => 0);
  const futuresRows = await page
    .locator(`${ROW}[data-suggestion-type="futures"]`)
    .count()
    .catch(() => 0);
  const nonFuturesRows = rows - futuresRows;
  const mainText = await readContentRegionText(page);

  // An empty subtitle line is invisible to a screenshot but is a real defect:
  // it is the "renders no empty line" clause of #1620's acceptance.
  const blankSubtitles = await page
    .locator(`${ROW} div:not([data-testid]):text-matches("^\\\\s*$")`)
    .count()
    .catch(() => 0);

  await journey.finish({
    allowedNavigationAborts: [RSC_PREFETCH_ABORT],
    journeyId: `search.answer_row_adjacency.${surface}`,
    expectedPath: path,
    contentMode: "none",
    realCardFound: false,
    mainRegionNonBlank: mainText.trim().length > 40,
  });

  const expectedFutures = owed.answersOwed + owed.unpricedFutures;
  if (expectedFutures > 0) {
    expect(
      futuresRows,
      `the payload carries ${expectedFutures} futures suggestion(s) ` +
        `(${owed.answersOwed} priced, ${owed.unpricedFutures} unpriced) but the ` +
        `${surface} dropdown rendered ${futuresRows} futures row(s) — an unpriced ` +
        `suggestion must fall back to its label, never disappear`,
    ).toBeGreaterThanOrEqual(1);
  }

  // The team/game rows are the adjacent surface: leading with the answer must
  // not have cost them their place in the list.
  if (owed.total > expectedFutures) {
    expect(
      nonFuturesRows,
      `the payload carries ${owed.total - expectedFutures} non-futures ` +
        `suggestion(s) for "${QUERY}" but the ${surface} dropdown rendered ` +
        `${nonFuturesRows} — the answer rows have displaced the teams and games`,
    ).toBeGreaterThan(0);
  }

  expect(
    blankSubtitles,
    `${blankSubtitles} suggestion row(s) on ${surface} render an EMPTY subtitle ` +
      `line — a row with no subtitle must render no line at all`,
  ).toBe(0);
});
