import { test, expect, readContentRegionText } from "../fixtures/audit";
import { RSC_PREFETCH_ABORT } from "../helpers/navigationAborts";

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
 * The partition rules are deliberately restated here rather than imported from
 * `lib/leagueCards`: importing the implementation would make this the
 * constant-oracle family (gotcha #121) — the test comparing production to the
 * very function production reads, asserting nothing. They are kept narrow and
 * the spec asserts a FLOOR rather than an exact equality where the restatement
 * could legitimately diverge, so a rule refinement does not red the rail
 * spuriously.
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

type Outcome = { name?: string | null; probability?: number | null };
type Market = { id?: number; name?: string; top_outcomes?: Outcome[] | null; outcome_count?: number };

/**
 * Restated partition rules (see the header on why these are not imported).
 *
 * A binary is a two-outcome market whose outcomes are Yes and No. A date ladder
 * is a market whose outcomes are all "Before <date>"-shaped. Both are
 * intentionally stricter than the component's, so this oracle UNDER-counts
 * rather than over-counts and the DOM assertions below stay floors.
 */
function isBinary(m: Market): boolean {
  const outs = m.top_outcomes ?? [];
  if (outs.length !== 2) return false;
  const names = outs.map((o) => (o.name ?? "").trim().toLowerCase());
  return names.includes("yes") && names.includes("no");
}

function isDateLadder(m: Market): boolean {
  const outs = m.top_outcomes ?? [];
  if (outs.length < 3) return false;
  return outs.every((o) => /^before\s+/i.test((o.name ?? "").trim()));
}

/**
 * #1860 — the oracle reads `sections` as a MAPPING, which is what the server
 * sends: `{"awards": Market[], "props": Market[], "more_markets": Market[]}`.
 *
 * It was previously typed `{markets?: Market[]}[]` and read with
 * `(body.sections ?? []).flatMap(...)`, which throws `flatMap is not a function`
 * on an object — so the acceptance test for this issue crashed inside its own
 * payload reader and never evaluated the page at all. Measured against
 * production 2026-08-17: `sections` is a dict of three lists and there is no
 * top-level `markets` key.
 *
 * Note what the naive repair would have cost: making the reader merely
 * *tolerant* (returning `[]` on an unexpected shape) would have zeroed
 * `owed.binaries` and `owed.ladders`, and both retrofit assertions below are
 * guarded by `if (owed.X > 0)`. The test would have gone GREEN having checked
 * nothing. So an unreadable payload throws instead — a shape this test cannot
 * read is a fact about the test, and it must say so.
 */
async function leaguePayload(): Promise<{ binaries: number; ladders: number; games: number }> {
  const res = await fetch(`${API_BASE}/api/leagues/${LEAGUE_KEY}`);
  if (!res.ok) return { binaries: -1, ladders: -1, games: -1 };
  const body = (await res.json()) as {
    sections?: Record<string, Market[]> | null;
    markets?: Market[] | null;
    upcoming_games?: unknown[];
    recent_results?: unknown[];
  };

  let markets: Market[];
  if (Array.isArray(body.markets)) {
    markets = body.markets;
  } else if (body.sections && typeof body.sections === "object" && !Array.isArray(body.sections)) {
    markets = Object.values(body.sections).flatMap((list) => (Array.isArray(list) ? list : []));
  } else {
    throw new Error(
      `GET /api/leagues/${LEAGUE_KEY} returned neither a 'markets' array nor a ` +
        `'sections' mapping — top-level keys were [${Object.keys(body).join(", ")}]. ` +
        `The oracle cannot grade the page against a payload it cannot read, and ` +
        `reading zero markets would make every assertion below vacuously true.`,
    );
  }

  return {
    binaries: markets.filter(isBinary).length,
    ladders: markets.filter(isDateLadder).length,
    games: (body.upcoming_games?.length ?? 0) + (body.recent_results?.length ?? 0),
  };
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

  // Retrofit 3 — ONE row per binary, never two.
  if (owed.binaries > 0) {
    expect(
      hasBinaryBlock,
      `the payload carries ${owed.binaries} yes/no market(s) and the page rendered no ` +
        `[data-league-block="binaries"] — binaries are routing through a card again`,
    ).toBe(true);
    expect(
      binaryRows,
      `${owed.binaries} binary/ies must occupy at most ${owed.binaries} rows; ` +
        `${binaryRows} rows means the two-row (Yes AND No) presentation is back. ` +
        `Rows: ${JSON.stringify(rowTexts.slice(0, 6))}`,
    ).toBeLessThanOrEqual(owed.binaries);
  }

  // Retrofit 2 — date ladders render as the shared heatmap kernel, whole.
  if (owed.ladders > 0) {
    expect(
      ladderCards,
      `the payload carries ${owed.ladders} date ladder(s) but the page rendered ` +
        `${ladderCards} inside [data-league-block="ladders"] — ladders are routing ` +
        `through PropGroupCard again (probability-sorted and truncated at 6 of 8)`,
    ).toBeGreaterThan(0);
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
