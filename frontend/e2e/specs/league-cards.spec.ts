import { test, expect, readContentRegionText } from "../fixtures/audit";
import { RSC_PREFETCH_ABORT } from "../helpers/navigationAborts";
import { leagueOwed } from "../helpers/leagueCardOracle";

/**
 * UX-P083 (#1860) — the RENDERED half of ruling 047 on the league page.
 *
 * ── WHY THIS PACK EXISTS ──
 *
 * UX-P074 shipped all three of ruling 047's league-page retrofits (`db88e530`):
 * events render through the shared `EventCard`, date ladders through the shared
 * `QuantityGroup` kernel, and every yes/no market as ONE row stating the Yes
 * side by name. The issue nonetheless stayed open, correctly, because its
 * acceptance is a RENDER COUNT — "none of the three ruled shapes renders through
 * a league-local variant" — and ruling 044 says a client render count is not
 * curl-dischargeable. INT-069's loss ledger routed it to this rail and recorded
 * that only API-level corroboration had been collected.
 *
 * So the code has been right for a merge cycle and unphotographed the whole
 * time. That is the same gap the event-page pack was built to close, and the
 * same one ruling 047 is most vulnerable to: a card system fragments back one
 * page at a time, and nothing fails when it does.
 *
 * ── THE ORACLE IS THE PAYLOAD, NOT A SECOND READING OF THE SCREEN ──
 *
 * Counting rows and then asserting the rows look right is scraping the surface
 * under test — a wrong partition and a wrong render agree and pass. So this
 * spec fetches `/api/leagues/baseball_mlb` and re-derives, from the same rules
 * the component uses, HOW MANY binaries and ladders the page owes. The DOM is
 * then checked against that independent count.
 *
 * The partition rules are deliberately restated rather than imported from
 * `lib/leagueCards`: importing the implementation would make this the
 * constant-oracle family (gotcha #121) — the test comparing production to the
 * very function production reads, asserting nothing. They now live in
 * `helpers/leagueCardOracle.js`, and `__tests__/lib/leagueCardOracleParity.test.ts`
 * runs the restatement and the component's own classifiers over the same
 * production payload and fails when they disagree. Independence is what makes
 * this an instrument; the parity test is what keeps the independent copy honest.
 *
 * ── UX-P087: WHY THE RESTATEMENT IS NOW FAITHFUL, NOT "SAFELY STRICT" ──
 *
 * This spec's first real run (32055873206) failed `16 rows for 15 binaries` and
 * was read as ruling 047 regressing. It was not: the page rendered SIXTEEN
 * binaries as SIXTEEN rows, one row each. The oracle required `length === 2` and
 * therefore could not see the one-sided `Shohei Ohtani: Cy Young and MVP Winner`
 * (`Yes 1%`) that `binaryAnswer` counts on purpose.
 *
 * The old header called the strictness safe because it made the assertions
 * "floors". Two of them were. The binary one was a CEILING, and an under-counting
 * oracle lowers a ceiling onto a correct page. **An oracle is only safely strict
 * in the direction of the assertion that consumes it** — so the rules are stated
 * faithfully and the two market assertions are exact equalities. The equality
 * also closes a hole the ceiling never could: under `rows <= owed`, a page that
 * dropped every binary row rendered zero rows and PASSED.
 *
 * ── DELIBERATE LIMITS, STATED ──
 *
 *  - `contentMode: "none"` — the shared evaluator's card check is written for
 *    the Discover feed; the blank-page check still applies and the assertions
 *    below are this spec's own.
 *  - MLB is the specimen because it is the measured one in #1860 and the only
 *    league guaranteed a full slate daily in season. Out of season the games
 *    rails legitimately empty, so the games journey asserts the CARD TYPE when
 *    games exist and does not fail an empty slate — an empty rail is honest,
 *    a bespoke row is not.
 */

/** The shared event card marks itself (added by this queue). A league-local row would not. */
const EVENT_CARD = '[data-testid="event-card"]';
/** The two ruled blocks, marked by `LeagueMarketSection`. */
const LADDERS = '[data-league-block="ladders"]';
const BINARIES = '[data-league-block="binaries"]';
/** One row per binary — the whole point of retrofit 3. */
const BINARY_ROW = `${BINARIES} a[href^="/futures/"]`;
/** The shared Quantity kernel's rungs. */
const LADDER_CARD = `${LADDERS} > *`;

const LEAGUE_PATH = "/sport/baseball/mlb";
const LEAGUE_KEY = "baseball_mlb";

const API_BASE = (process.env.AUDIT_API_BASE_URL || "https://api.bainluck.com").replace(/\/$/, "");

/**
 * What the page owes, from the payload — the independent half of the oracle.
 *
 * `sections` is a MAPPING, which is what the server sends: `{"awards": [...],
 * "props": [...], "more_markets": [...]}`, with no top-level `markets` key. It
 * was once typed as an array and read with `.flatMap`, which threw
 * `flatMap is not a function` — so this acceptance test crashed inside its own
 * payload reader and never evaluated the page at all. `leagueMarkets` THROWS on
 * a shape it cannot read rather than tolerating one, because tolerance would
 * zero every count and make the assertions below vacuously true.
 *
 * A non-OK response is reported as `-1` rather than `0`: the guards below are
 * `> 0`, so a dead API skips the retrofit assertions instead of passing them.
 */
async function leaguePayload(): Promise<{ binaries: number; ladders: number; games: number }> {
  const res = await fetch(`${API_BASE}/api/leagues/${LEAGUE_KEY}`);
  if (!res.ok) return { binaries: -1, ladders: -1, games: -1 };
  return leagueOwed(await res.json());
}

test("league page renders the SHARED card system, not three local variants", async ({ page, journey }) => {
  const owed = await leaguePayload();

  await page.goto(LEAGUE_PATH, { waitUntil: "domcontentloaded" });

  // Something from the page proper must mount before anything is counted. Any
  // one of the three ruled surfaces is enough — which of them arrives first
  // depends on the slate, and requiring a specific one would make an honest
  // out-of-season page look broken.
  await Promise.race([
    page.locator(EVENT_CARD).first().waitFor({ state: "visible", timeout: 45_000 }).catch(() => null),
    page.locator(BINARIES).first().waitFor({ state: "visible", timeout: 45_000 }).catch(() => null),
    page.locator(LADDERS).first().waitFor({ state: "visible", timeout: 45_000 }).catch(() => null),
  ]);

  const eventCards = await page.locator(EVENT_CARD).count().catch(() => 0);
  const binaryRows = await page.locator(BINARY_ROW).count().catch(() => 0);
  const ladderCards = await page.locator(LADDER_CARD).count().catch(() => 0);
  const hasBinaryBlock = (await page.locator(BINARIES).count().catch(() => 0)) > 0;

  /**
   * Retrofit 3's real claim, and the one a row count alone cannot make: each
   * binary occupies ONE row. The pre-retrofit `PropGroupCard` drew two rows per
   * binary — Yes and No — so a page with N binaries rendering 2N rows is the
   * exact regression. Reading the row count against the payload's binary count
   * is what distinguishes them.
   *
   * Also read each row's text so a row that silently reverted to leading with
   * `No` is visible in the artifact.
   */
  const rowTexts = await page
    .locator(BINARY_ROW)
    .evaluateAll((nodes) => nodes.slice(0, 40).map((n) => ((n as HTMLElement).textContent || "").trim().slice(0, 90)))
    .catch(() => [] as string[]);

  const mainText = await readContentRegionText(page);

  await journey.finish({
    allowedNavigationAborts: [RSC_PREFETCH_ABORT],
    journeyId: "league.cards.one_system",
    expectedPath: LEAGUE_PATH,
    contentMode: "none",
    realCardFound: false,
    mainRegionNonBlank: mainText.trim().length > 40,
  });

  // The page has to have rendered SOMETHING of the card system, or the run
  // collected no evidence about it — which is not a pass (the rail's rule).
  expect(
    eventCards + binaryRows + ladderCards,
    `the league page rendered none of the three ruled shapes — payload owed ` +
      `${owed.games} game(s), ${owed.binaries} binary/ies, ${owed.ladders} ladder(s)`,
  ).toBeGreaterThan(0);

  // Retrofit 1 — games render through the SHARED event card. An empty slate is
  // honest and is not failed; a populated rail that drew no shared card is the
  // league-local variant coming back.
  if (owed.games > 0) {
    expect(
      eventCards,
      `the payload carries ${owed.games} game(s) but the page rendered no ` +
        `[data-testid="event-card"] — the games rail is drawing a league-local row again`,
    ).toBeGreaterThan(0);
  }

  // Retrofit 3 — ONE row per binary, never two, and never none.
  //
  // EXACT, in both directions, because the oracle is faithful (UX-P087) and both
  // directions are real news:
  //   too many  → the two-row (Yes AND No) presentation is back, or a shape that
  //               is not a binary is leaking into the block;
  //   too few   → binaries are silently vanishing. The old `<= owed` ceiling
  //               could not see that at all — zero rows passed it.
  if (owed.binaries > 0) {
    expect(
      hasBinaryBlock,
      `the payload carries ${owed.binaries} yes/no market(s) and the page rendered no ` +
        `[data-league-block="binaries"] — binaries are routing through a card again`,
    ).toBe(true);
    expect(
      binaryRows,
      `${owed.binaries} binary/ies must occupy exactly ${owed.binaries} rows; the page ` +
        `rendered ${binaryRows}. MORE means the two-row (Yes AND No) presentation is ` +
        `back or a non-binary is leaking in; FEWER means binaries are being dropped. ` +
        `Rows: ${JSON.stringify(rowTexts.slice(0, 6))}`,
    ).toBe(owed.binaries);
  }

  // Retrofit 2 — date ladders render as the shared heatmap kernel, whole. Also
  // exact: every ladder in the section is serialised, so every one is owed a
  // QuantityGroup, and a ladder falling back to `PropGroupCard` shows up here as
  // a missing one rather than as a card nobody counted.
  if (owed.ladders > 0) {
    expect(
      ladderCards,
      `the payload carries ${owed.ladders} date ladder(s) but the page rendered ` +
        `${ladderCards} inside [data-league-block="ladders"] — a shortfall means ladders ` +
        `are routing through PropGroupCard again (probability-sorted and truncated at ` +
        `6 of 8); a surplus means something that is not a ladder is being drawn as one`,
    ).toBe(owed.ladders);
  }
});

/**
 * The other direction, per gotcha #43: a cap or a re-route must not empty an
 * adjacent surface. The shared `EventCard` carries the `data-testid` this queue
 * added, so one of its OTHER callers is checked to have kept its cards — proving
 * the shared component was not disturbed by being marked.
 *
 * #1860: this pointed at `/sports` and failed, and the failure was the TEST's.
 * `app/sports/page.tsx` does not import `EventCard` — it renders its own
 * `data-testid="sports-card"` markup — so the control asserted that a surface
 * which has never used the shared card must contain it, and read the resulting
 * `30 wrappers, 0 shared cards` as a regression in a component it had not
 * touched. Verified 2026-08-17: the importers are `app/sports/[key]`,
 * `app/search`, `app/my-stuff` and `app/preferences`. The per-league route is
 * the right control — it is a real reader path and it is populated in season.
 */
test("the shared event card still populates its original surface", async ({ page, journey }) => {
  const path = "/sports/baseball_mlb";
  await page.goto(path, { waitUntil: "domcontentloaded" });

  await page
    .locator(EVENT_CARD)
    .first()
    .waitFor({ state: "visible", timeout: 45_000 })
    .catch(() => null);

  const cards = await page.locator(EVENT_CARD).count().catch(() => 0);
  const mainText = await readContentRegionText(page);

  await journey.finish({
    allowedNavigationAborts: [RSC_PREFETCH_ABORT],
    journeyId: "league.cards.adjacent_sports_feed",
    expectedPath: path,
    contentMode: "none",
    realCardFound: false,
    mainRegionNonBlank: mainText.trim().length > 40,
  });

  // An out-of-season or empty slate is legitimate and is not failed. The claim
  // is conditional on the page having rendered its own content: a populated
  // league page that drew ZERO shared cards is the marked component having
  // stopped rendering.
  const owed = await leaguePayload();
  if (owed.games > 0) {
    expect(
      cards,
      `${path} owes ${owed.games} game(s) but rendered no [data-testid="event-card"] — ` +
        `marking the shared component must not have changed what it renders`,
    ).toBeGreaterThan(0);
  }
});
