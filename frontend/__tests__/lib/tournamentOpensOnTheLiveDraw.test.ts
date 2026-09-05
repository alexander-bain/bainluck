/**
 * THE HUB OPENS ON THE DRAW BEING PLAYED (live/077 item 2).
 *
 * The defect this guards, measured on production 2026-09-05 at 15:04-15:22Z:
 * Potapova-Anisimova and Keys-Zheng were both `STATUS_IN_PROGRESS` on ESPN and
 * both priced and moving on our own slate, and the phone-width Round of 32
 * list showed NEITHER — it opened on the 11:30 men's match. Nothing was
 * dropped and nothing was mis-sorted. The two live matches are women's, the
 * page opened on `"mens-singles"` because a `useState` said so, and a
 * collapsed list shows five rows of whichever draw it opened on.
 *
 * So the assertions below are about the CHOICE, not about the list: the list
 * was always right about the draw it was given.
 */

import fs from "fs";
import path from "path";

import { defaultDraw } from "@/lib/matchList";
import { DRAWS, OPENING_DRAW_FALLBACK } from "@/components/tournament/DrawToggle";
import type { SlateMatch } from "@/lib/slate";

const ROOT = path.join(__dirname, "..", "..");

function readSource(relative: string): string {
  const source = fs.readFileSync(path.join(ROOT, relative), "utf8");
  // A source scan that cannot find its subject must RAISE, never quietly pass.
  if (source.trim().length === 0) throw new Error(`source scan target is empty: ${relative}`);
  return source;
}

const MENS = "mens-singles";
const WOMENS = "womens-singles";

function match(overrides: Partial<SlateMatch> = {}): SlateMatch {
  return {
    matchup_key: "womens-singles:keys-vs-zheng:2026-09-05",
    draw: WOMENS,
    draw_label: "Women's Singles",
    round: "R32",
    scheduled_date: "2026-09-05T15:05:00+00:00",
    sides: [],
    coherent: true,
    raw_sum: 1.0,
    opening_raw_sum: 1.0,
    probability_is_live: true,
    price_state: "live",
    observed_at: "2026-09-05T15:22:00+00:00",
    age_hours: 0.01,
    freshest_observed_at: "2026-09-05T15:22:00+00:00",
    freshest_age_hours: 0.01,
    stale_sides: [],
    mixed_freshness: false,
    favourite: "madison-keys",
    has_moved: true,
    source_count: 2,
    ...overrides,
  };
}

/**
 * The production Round of 32 as it stood at 16:00Z on 2026-09-05, in the
 * order the payload delivered it. Eight men's rows and seven women's; the two
 * `in_progress` rows are women's and men's respectively, so this fixture is
 * also the tie-break case and not only the regression.
 */
function productionRoundOf32(): SlateMatch[] {
  return [
    match({ draw: WOMENS, scheduled_date: "2026-09-05T15:05:00+00:00", live_state: "in_progress" }),
    match({ draw: MENS, scheduled_date: "2026-09-05T15:40:00+00:00", live_state: "in_progress" }),
    match({ draw: WOMENS, scheduled_date: "2026-09-05T16:55:00+00:00", live_state: "upcoming" }),
    match({ draw: MENS, scheduled_date: "2026-09-05T17:00:00+00:00", live_state: "upcoming" }),
    match({ draw: WOMENS, scheduled_date: "2026-09-05T17:20:00+00:00", live_state: "upcoming" }),
    match({ draw: WOMENS, scheduled_date: "2026-09-05T17:30:00+00:00", live_state: "upcoming" }),
    match({ draw: MENS, scheduled_date: "2026-09-05T18:00:00+00:00", live_state: "upcoming" }),
    match({ draw: MENS, scheduled_date: "2026-09-05T18:00:00+00:00", live_state: "upcoming" }),
  ];
}

describe("the hub opens on the draw being played", () => {
  it("opens on the women's draw when the only live matches are women's", () => {
    // The 15:04-15:22Z sample, exactly: two women's matches on court, the
    // men's day not yet started. This returned "mens-singles" before.
    const slate = [
      match({ draw: WOMENS, scheduled_date: "2026-09-05T15:05:00+00:00", live_state: "in_progress" }),
      match({ draw: WOMENS, scheduled_date: "2026-09-05T15:05:00+00:00", live_state: "in_progress" }),
      match({ draw: MENS, scheduled_date: "2026-09-05T15:30:00+00:00", live_state: "upcoming" }),
    ];
    expect(defaultDraw(slate, DRAWS)).toBe(WOMENS);
  });

  it("opens on the men's draw when the only live matches are men's", () => {
    // The mirror. A rule that just said "women's" would pass the test above.
    const slate = [
      match({ draw: MENS, scheduled_date: "2026-09-05T15:05:00+00:00", live_state: "in_progress" }),
      match({ draw: WOMENS, scheduled_date: "2026-09-05T15:30:00+00:00", live_state: "upcoming" }),
    ];
    expect(defaultDraw(slate, DRAWS)).toBe(MENS);
  });

  it("prefers the earliest-started match when both draws are on court", () => {
    expect(defaultDraw(productionRoundOf32(), DRAWS)).toBe(WOMENS);
  });

  it("still prefers the earliest-started match when the later one is men's first in the payload", () => {
    // Payload order must not decide it. Same two matches, reversed.
    const slate = [
      match({ draw: MENS, scheduled_date: "2026-09-05T15:40:00+00:00", live_state: "in_progress" }),
      match({ draw: WOMENS, scheduled_date: "2026-09-05T15:05:00+00:00", live_state: "in_progress" }),
    ];
    expect(defaultDraw(slate, DRAWS)).toBe(WOMENS);
  });

  it("breaks an exact start-time tie by the toggle's own order", () => {
    // 6 of the 15 Round-of-32 rows shared a start time on the day this was
    // written, so the tie is real and the answer must not depend on payload
    // order. Asserted from BOTH payload orders: a rule that returned "the
    // first one seen" passes one of these and fails the other.
    const womensFirst = [
      match({ draw: WOMENS, scheduled_date: "2026-09-05T18:00:00+00:00", live_state: "in_progress" }),
      match({ draw: MENS, scheduled_date: "2026-09-05T18:00:00+00:00", live_state: "in_progress" }),
    ];
    const mensFirst = [womensFirst[1], womensFirst[0]];
    expect(defaultDraw(womensFirst, DRAWS)).toBe(MENS);
    expect(defaultDraw(mensFirst, DRAWS)).toBe(MENS);
  });

  it("answers null when nothing is on court, so the caller keeps its own opening draw", () => {
    // Between sessions there is no draw to prefer, and that is NOT the same
    // as preferring the men's. The function must not invent one — the caller
    // owns the fallback.
    const slate = [
      match({ draw: WOMENS, live_state: "upcoming" }),
      match({ draw: MENS, live_state: "upcoming" }),
    ];
    expect(defaultDraw(slate, DRAWS)).toBeNull();
    expect(defaultDraw([], DRAWS)).toBeNull();
  });

  it("ignores a live match in a draw the toggle does not offer", () => {
    // Doubles and mixed ride the same slate. Selecting one would open a tab
    // that does not exist and render an empty page, which is strictly worse
    // than the bug being fixed.
    const slate = [
      match({ draw: "mixed-doubles", scheduled_date: "2026-09-05T14:00:00+00:00", live_state: "in_progress" }),
      match({ draw: MENS, scheduled_date: "2026-09-05T15:40:00+00:00", live_state: "in_progress" }),
    ];
    expect(defaultDraw(slate, DRAWS)).toBe(MENS);

    // …and when the unoffered draw is the ONLY thing live, that is a null, not
    // a selection of it.
    expect(defaultDraw([slate[0]], DRAWS)).toBeNull();
  });

  it("reads live_state and never the clock against scheduled_date", () => {
    // A five-setter outlives any elapsed-time window, and "started three hours
    // ago" is not evidence a match is over. A rule that inferred liveness from
    // the timestamp would pick the women's row here — it is older — and would
    // be opening on a draw whose matches have all finished.
    const slate = [
      match({ draw: WOMENS, scheduled_date: "2026-09-05T12:00:00+00:00", live_state: null }),
      match({ draw: MENS, scheduled_date: "2026-09-05T15:40:00+00:00", live_state: "in_progress" }),
    ];
    expect(defaultDraw(slate, DRAWS)).toBe(MENS);
  });

  it("keeps the fallback pointing at a draw the toggle actually offers", () => {
    // The fallback is only reached when nothing is live, but it is still a tab
    // that has to exist.
    expect(DRAWS.some((entry) => entry.id === OPENING_DRAW_FALLBACK)).toBe(true);
  });
});

/**
 * ═══ AND THE PAGE HAS TO ACTUALLY ASK ═══
 *
 * Every assertion above passes against a `page.tsx` that still opens on a
 * hardcoded `useState("mens-singles")` and never calls the rule — a correct
 * producer wired to nothing, which is precisely the shape the original bug
 * had. The page cannot be rendered in jest (three GA4 hooks, `useParams` and
 * a chained fetch), so this is a source scan, the same instrument
 * `hubBoot.test.ts` uses on this file for the same reason.
 */
describe("the page asks the rule, and asks it once", () => {
  const source = readSource("app/tournaments/[slug]/page.tsx");

  it("resolves the opening draw from the slate rather than a hardcoded literal", () => {
    expect(source).toContain("defaultDraw(payload.slate?.matches ?? [], DRAWS)");
    // The literal is gone from the state initialiser. It survives only as
    // `OPENING_DRAW_FALLBACK`, declared beside `DRAWS`.
    expect(source).not.toContain('useState<string>("mens-singles")');
  });

  it("resolves it in the first payload's continuation, not in an effect on data", () => {
    // An effect keyed on `data` renders the fallback draw once and replaces
    // it — a visible flash of the wrong draw on a phone, which is this bug
    // shown briefly instead of permanently. It must land in the same commit
    // as `setData`.
    const setData = source.indexOf("setData(payload)");
    const resolve = source.indexOf("setDrawChoice(");
    const loaded = source.indexOf("setLoading(false)", setData);
    expect(setData).toBeGreaterThan(-1);
    expect(resolve).toBeGreaterThan(setData);
    expect(resolve).toBeLessThan(loaded);
  });

  it("never overrides a reader who already chose", () => {
    // Two ways this must hold: the resolve is a functional update that keeps
    // an existing choice, and the toggle writes the same state.
    expect(source).toMatch(/setDrawChoice\(\s*\(current\)\s*=>\s*\n?\s*current \?\?/);
    expect(source).toContain("setDrawChoice(id)");
  });
});
