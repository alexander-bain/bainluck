// ux/1189 (#5069) — A THREE-HOUR-OLD NUMBER IS NOT CAPTIONED "Live".
//
// ═══ WHAT WAS ON THE SCREEN ═══
//
// Sabalenka–Pegula (US Open semi-final, event 15308340), 2026-09-10 8:42pm PT,
// production, phone width, on a tab opened once and never reloaded:
//
//     ● 189m ago            <- header badge, grey, honest
//       94% – 6%
//       Live · Bain Luck blend   <- two lines below, same card, same number
//
// `/api/events/15308340` carried exactly one probability source, `polymarket`,
// written at 00:33:31Z — three hours before the shot, on a match that was still
// live. The badge and the caption describe THE SAME NUMBER and contradict each
// other inside one viewport, and the caption is the one that is wrong.
//
// ═══ WHY IT IS A SEPARATE DEFECT FROM #4861 ═══
//
// #4861 (shipped at `dc51e5db`) stops the HEADER promising "Next update: N"
// into a feed that has stopped delivering. It reaches a reader through the POLL
// branch. This one reaches a reader through the PUSHED branch, where the age
// badge is already honest and already grey — and the caption underneath it
// still says "Live". Fixing either one leaves the other on the screen.
//
// ═══ WHAT "Live" MEANS TO THE PERSON READING IT ═══
//
// In the source it distinguishes WHICH number was picked (the blend, rather
// than the opening line or the sportsbook cross-check). On the screen it reads
// as WHEN — "this is current". Those two meanings are indistinguishable to a
// reader, and on a stale page only the second one is being read. Standing
// notice 34: the fix is removing a word, not adding a sentence explaining it.

import { resolveProbability } from "../../lib/eventKeyStats";
import { heroFactIsStale, heroStampIsStale } from "../../components/event/LiveAgeStamp";
import { STALE_MS } from "../../components/event/FreshnessChip";
import type {
  EventHistoryResponse,
  EventDetailResponse,
} from "../../lib/types";

function hist(partial: Partial<EventHistoryResponse>): EventHistoryResponse {
  return { event_id: 1, history: [], ...partial } as unknown as EventHistoryResponse;
}

function evt(partial: Partial<EventDetailResponse>): EventDetailResponse {
  return {
    id: 1,
    home_team: "Home",
    away_team: "Away",
    status: "live",
    commence_time: "2026-07-23T00:00:00Z",
    ...partial,
  } as unknown as EventDetailResponse;
}

/** A live event whose hero number is a genuine blend — the branch under test. */
const LIVE_BLEND = evt({
  status: "live",
  hero_probability: 0.94,
  hero_probability_away: 0.06,
  hero_probability_source: "blend",
} as Partial<EventDetailResponse>);

/** `resolveProbability(event, history, lastChartPoint, isLive, isFinished, noReportedResult, blendIsStale)`. */
function label(blendIsStale?: boolean): string | null {
  // The `undefined` arm calls the function with the OLD arity on purpose: that
  // is what proves a pre-existing caller is untouched, and a spread of an empty
  // array would not.
  return blendIsStale === undefined
    ? resolveProbability(LIVE_BLEND, hist({}), null, true, false, false)
        .probSourceLabel
    : resolveProbability(LIVE_BLEND, hist({}), null, true, false, false, blendIsStale)
        .probSourceLabel;
}

describe("#5069 the hero caption does not claim a stale blend is live", () => {
  test("THE BUG: a blend past its boundary is not captioned 'Live'", () => {
    // This is the assertion that fails before the fix: the label was the
    // literal "Live · Bain Luck blend" with no reference to the number's age.
    expect(label(true)).not.toMatch(/Live/);
  });

  test("the number itself still shows — only the claim about its currency goes", () => {
    // Notice 34 again: an empty hero would be a worse answer than an old one.
    // The reader keeps the probability and the grey age badge above it.
    expect(label(true)).toBe("Bain Luck blend");
    const r = resolveProbability(LIVE_BLEND, hist({}), null, true, false, false, true);
    expect(r.homeProb).toBeCloseTo(0.94);
    expect(r.awayProb).toBeCloseTo(0.06);
  });

  test("a fresh blend is unchanged — this must not cost the live case its word", () => {
    expect(label(false)).toBe("Live · Bain Luck blend");
  });

  test("omitting the argument preserves every pre-existing caller exactly", () => {
    // #4015's `noReportedResult` precedent: default false, so the shared
    // `EventHeroProbabilityPair` path and every test that predates this keep
    // their behaviour without being touched.
    expect(label()).toBe("Live · Bain Luck blend");
  });
});

describe("#5069 the caption and the badge cross one boundary, at one instant", () => {
  // The reason this is worth pinning: two thresholds for one fact is how a dot
  // and its caption end up disagreeing — which is the bug this file is named
  // for. `heroStampIsStale` is the badge's own predicate, so there is exactly
  // one comparison in the codebase, not two that drift.

  test("the price boundary is 120s, and the caption flips on the same second", () => {
    expect(heroFactIsStale(120, "price")).toBe(false);
    expect(heroFactIsStale(121, "price")).toBe(true);
    // The caption is a pure function of that same boolean.
    expect(label(heroFactIsStale(120, "price"))).toBe("Live · Bain Luck blend");
    expect(label(heroFactIsStale(121, "price"))).toBe("Bain Luck blend");
  });

  test("the score keeps the chip's own five minutes, not a third invented number", () => {
    const scoreBoundaryS = STALE_MS / 1000;
    expect(scoreBoundaryS).toBe(300);
    expect(heroFactIsStale(scoreBoundaryS, "score")).toBe(false);
    expect(heroFactIsStale(scoreBoundaryS + 1, "score")).toBe(true);
  });

  test("an unstamped number is not stale — 'unknown age' is not 'old'", () => {
    // Only a measured age earns the removal of a word. A missing stamp must not
    // silently strip "Live" off a perfectly current hero.
    expect(heroStampIsStale(null, "price")).toBe(false);
    expect(heroStampIsStale(undefined, "price")).toBe(false);
    expect(heroStampIsStale("not a date", "price")).toBe(false);
  });

  test("the specimen reproduces: a 189-minute-old price is stale", () => {
    const stamp = new Date(Date.now() - 189 * 60 * 1000).toISOString();
    expect(heroStampIsStale(stamp, "price")).toBe(true);
    expect(label(heroStampIsStale(stamp, "price"))).toBe("Bain Luck blend");
  });

  test("a seconds-old price is live", () => {
    const stamp = new Date(Date.now() - 8 * 1000).toISOString();
    expect(heroStampIsStale(stamp, "price")).toBe(false);
    expect(label(heroStampIsStale(stamp, "price"))).toBe("Live · Bain Luck blend");
  });
});

describe("#5069 resolveProbability stays a pure function of its arguments", () => {
  test("the staleness decision is passed in, never read from the clock here", () => {
    // `probabilityInvariant.test.ts` and the twelve-clock sweep both lean on
    // this purity, and #4015's parameter exists for the same reason. Deriving
    // the age inside `resolveProbability` would also create a SECOND answer to
    // "how old is this number" on a page that already has exactly one
    // (`freshestSourceStamp`) — which is what #4469 exists to prevent.
    const src = require("fs").readFileSync(
      require("path").resolve(__dirname, "../../lib/eventKeyStats.ts"),
      "utf8",
    );
    const executable = src
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .split("\n")
      .map((line: string) => line.replace(/(^|\s)\/\/.*$/, "$1"))
      .join("\n");
    expect(executable).not.toMatch(/Date\.now\(\)/);

    // Same arguments, same answer, twice — no hidden clock read.
    expect(label(true)).toBe(label(true));
    expect(label(false)).toBe(label(false));
  });
});
