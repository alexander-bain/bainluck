import { test, expect, readContentRegionText } from "../fixtures/audit";

/**
 * L2-227 — rendered truth for the five championship grids.
 *
 * Queue 295 put an explicit per-league register behind the grid serving path,
 * so a cell now arrives carrying a typed state (live / won / eliminated /
 * missing / unavailable) instead of always arriving as a number. The web
 * renderer was cut over to honour that state; this pack is the browser-side
 * half of the proof.
 *
 * What it answers, per league, at desktop and mobile:
 *
 *   1. Did the grid render real rows, or a page of nothing?
 *   2. Does every stage cell carry a declared state (`data-cell-state`)?
 *   3. Does any NON-live cell show a percentage? That is the exact defect the
 *      register exists to kill — a settled or missing cell wearing a live
 *      number — and it fails the journey outright.
 *   4. Do cells keep stable dimensions, i.e. no zero-height/zero-width cell
 *      that collapsed the row?
 *
 * Deliberate limits, stated rather than hidden:
 *
 *   - `contentMode: "none"` — the shared evaluator's card check is written for
 *     the Discover feed. The blank-page check still applies, and the grid
 *     assertions below are this spec's own.
 *   - Non-live states are NOT organic in production yet. The 2026-08-01
 *     census of the deployed a303db18 returned `live` for 120/120 NBA,
 *     120/120 MLB and 735/735 golf cells, with no register published. So
 *     check 3 is a REGRESSION guard here (it proves the live path stayed
 *     honest) and the settled/missing/unavailable states are proved against
 *     fixed fixtures in `frontend/__tests__/components/gridRegisterRendering.test.tsx`.
 *     When Queue 296 publishes registers, this spec starts observing them
 *     without any change.
 */

/** A stage cell renders its state as a data attribute — not as copy. */
const CELL = "[data-cell-state]";
/** Any table row in the grid body. */
const ROW = "tbody tr";
/** The grid's own error surface. */
const ERROR = '[data-testid="grid-error"], [role="alert"]';

const LEAGUES = [
  { journeyId: "grid.nba", path: "/playoffs/nba" },
  { journeyId: "grid.nhl", path: "/playoffs/nhl" },
  { journeyId: "grid.mlb", path: "/playoffs/mlb" },
  { journeyId: "grid.nfl", path: "/playoffs/nfl" },
  { journeyId: "grid.golf", path: "/playoffs/golf" },
] as const;

/** States that must never be accompanied by a percentage. */
const NON_LIVE = new Set(["clinched", "eliminated", "missing", "unavailable"]);

const PERCENT = /\d+(\.\d+)?%|<0\.1%/;

for (const league of LEAGUES) {
  test(`championship grid renders honest cell states @ ${league.path}`, async ({ page, journey }) => {
    await page.goto(league.path, { waitUntil: "domcontentloaded" });

    const rowLocator = page.locator(ROW).first();
    const errorLocator = page.locator(ERROR).first();

    await Promise.race([
      rowLocator.waitFor({ state: "visible", timeout: 45_000 }).catch(() => null),
      errorLocator.waitFor({ state: "visible", timeout: 45_000 }).catch(() => null),
    ]);

    const rowCount = await page.locator(ROW).count().catch(() => 0);
    const cells = page.locator(CELL);
    const cellCount = await cells.count().catch(() => 0);

    // Read every cell's declared state alongside its rendered text in ONE
    // browser round trip — a per-cell `evaluate` on a 735-row golf grid is
    // slower than the test timeout.
    const observed = await cells.evaluateAll((nodes) =>
      nodes.map((n) => {
        const el = n as HTMLElement;
        const box = el.getBoundingClientRect();
        return {
          state: el.getAttribute("data-cell-state") || "",
          text: (el.textContent || "").trim(),
          label: el.getAttribute("aria-label") || "",
          width: box.width,
          height: box.height,
        };
      }),
    ).catch(() => [] as { state: string; text: string; label: string; width: number; height: number }[]);

    // (3) The defect the register exists to kill.
    const dishonest = observed.filter((c) => NON_LIVE.has(c.state) && PERCENT.test(c.text));
    // (4) A cell that collapsed to nothing.
    const collapsed = observed.filter((c) => c.width <= 0 || c.height <= 0);
    // Every cell must be able to say what it is.
    const unnamed = observed.filter((c) => !c.state || !c.label);

    const mainText = await readContentRegionText(page);

    await journey.finish({
      journeyId: league.journeyId,
      expectedPath: league.path,
      contentMode: "none",
      realCardFound: false,
      mainRegionNonBlank: mainText.trim().length > 40 && rowCount > 0,
    });

    expect(rowCount, "the grid must render at least one row").toBeGreaterThan(0);
    expect(cellCount, "the grid must render at least one stage cell").toBeGreaterThan(0);
    expect(
      dishonest.map((c) => `${c.state}:${c.text}`),
      "a settled/missing/unavailable cell must never show a percentage",
    ).toEqual([]);
    expect(
      collapsed.length,
      "no stage cell may collapse to zero width or height",
    ).toBe(0);
    expect(
      unnamed.length,
      "every stage cell must carry a state and an accessible name",
    ).toBe(0);
  });
}

/**
 * The adjacent journey. The grid cutover touched a shared progression
 * renderer, so a league page that embeds the same table must not regress —
 * this is the "adjacent surface stays populated" half of gotcha #43.
 */
test("adjacent league page still renders its progression table", async ({ page, journey }) => {
  const path = "/sport/basketball/nba";
  await page.goto(path, { waitUntil: "domcontentloaded" });

  await page
    .locator(ROW)
    .first()
    .waitFor({ state: "visible", timeout: 45_000 })
    .catch(() => null);

  const rowCount = await page.locator(ROW).count().catch(() => 0);
  const mainText = await readContentRegionText(page);

  await journey.finish({
    journeyId: "grid.adjacent_league_page",
    expectedPath: path,
    contentMode: "none",
    realCardFound: false,
    mainRegionNonBlank: mainText.trim().length > 40,
  });

  expect(rowCount, "the league page's progression table must stay populated").toBeGreaterThan(0);
});
