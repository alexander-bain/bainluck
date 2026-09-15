/**
 * #2586 (p1) — `/preferences` STOPS PRINTING A REJECTION THE READER NEVER MADE.
 *
 * ═══ THE DEFECT, PHOTOGRAPHED ON PRODUCTION 2026-09-14 20:11 PT ═══
 *
 * `https://bainluck.com/preferences` at 390px in a clean browser, signed out —
 * `artifacts/ux-1268/before-prefs.png`. Under the heading
 *
 *   YOUR INTERESTS
 *   Controls what shows up in your feed. Tap to change.
 *
 * every one of the 24 rows reads `Nah ›`: NFL, College Football, NBA, College
 * Basketball, Baseball, Hockey, Soccer, Golf, Tennis, MMA, Boxing, Motorsports,
 * Cricket, Rugby, Politics, Entertainment, Economics, Tech, Weather,
 * Geopolitics, Culture, Esports, Lacrosse, Chess. A first-time visitor reads
 * that as "I have declined all 24 categories" while the Discover feed one tap
 * away is cheerfully showing cycling, UFC, MLB, politics and tennis. Alex's
 * shopper pass filed it as reading broken, and it is: the page is stating a
 * choice as fact on a control whose entire subject is the reader's choices.
 *
 * ═══ THE CAUSE IS A COERCION, NOT A DEFAULT ═══
 *
 * The issue body asks whether the unset state is being rendered with the reject
 * label or whether the default genuinely IS reject. It is the first, in one
 * character:
 *
 *   page.tsx:212          value={interests[cat.key] ?? 0}
 *   useCategoryInterests  getLevelLabel(0) === "Nah"     — its only floor
 *   categoryInterests.ts  parseInterests(null) === {}    — an untouched device
 *
 * So absence is coerced to `0`, and `0` has exactly one label, which is the
 * reject label. There is no value in the selector for "no opinion" — `0` is
 * both "unset" and "actively rejected", and the page prints the second whenever
 * it means the first. The fix gives absence its own label and passes the raw
 * lookup, so the two stop sharing a rendering.
 *
 * ═══ 🔴 WHAT THIS DOES NOT FIX, AND WHY THAT IS DELIBERATE ═══
 *
 * live/250's comment on #2586 found a second, worse half, and it is NOT closed
 * by this ship. Verified in `backend/app/utils/personalization.py` at both
 * sites on master this session (lines 262-266 and 427-435):
 *
 *   if sport_key and ctx.sport_affinities:           # block 1, events
 *   if ctx.sport_affinities and _is_sports_candidate(...):   # block 2, futures
 *       ...
 *       if matched_affinity is None:
 *           matched_affinity = 0.0   # "implicit Nah" → NAH_AFFINITY_PENALTY -0.6
 *
 * Both blocks are gated on the map being TRUTHY. An untouched reader stores
 * `{}`, which is falsy, so no penalty is applied at all — the feed is neutral
 * and the page was the only thing lying. But a reader who sets ONE interest
 * flips the map from `{}` to `{nfl: 1.0}`, and that single write switches the
 * gate from falsy to truthy: every sports category they never touched goes from
 * no-op to a real -0.6 in the same instant, the strongest per-sport penalty in
 * the module.
 *
 * That is a ranking-semantics defect (reviewed class under 49(d), routed to
 * discover) and the decision behind it is Alex's: should implicit-Nah apply to
 * a map built by `/preferences` at all, or only to one built by a completed
 * `/onboarding` pass? It must be fixed at its source. This file deliberately
 * does NOT compensate for it by keeping the wrong label on the screen:
 *
 *   - the population it touches is the SPORTS rows only. `_is_sports_candidate`
 *     (personalization.py:39) exempts politics, entertainment, economics, tech,
 *     weather, geopolitics and culture, so a flat "Nah" after the first tap
 *     would be false for seven of the 24 rows in exactly the same way it is
 *     false for all 24 today;
 *   - and reproducing that gate in the page would put backend ranking semantics
 *     in a layout file, where it would drift the first time either side moved.
 *
 * So the residual is named in #2586 and stays open, rather than being masked by
 * a label. `an explicit Nah still reads Nah` below is what stops this file from
 * being satisfiable by deleting the reject label altogether.
 *
 * ═══ THE THREE STATES ═══
 *
 * Rendered, not source-scanned — the anchor kind UX-P223 established for these
 * pages after three certs defeated source oracles in a row. Each row drives the
 * real page through `renderToStaticMarkup` and reads the markup a person reads.
 *
 *   {}                       24 rows, every one "Not set", zero "Nah"
 *   {nfl: 1.0}               NFL "Love it", the other 23 "Not set", zero "Nah"
 *   {tennis: 0}              Tennis "Nah" — a CHOSEN rejection still says so
 *
 * The third is the control. A "fix" that renamed the label inside
 * `getLevelLabel` passes the first two and fails this one.
 *
 *   TZ=UTC npx jest --testPathPatterns=unsetInterestIsNotAChoice2586
 */

import React from "react";

/** The three GA4 hooks every page calls before any conditional return. */
const ANALYTICS_HOOKS = {
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
};

const settled = (data: unknown) => ({
  data,
  error: undefined,
  isLoading: false,
  mutate: () => {},
});

/**
 * Register `/preferences`'s module graph.
 *
 * `useCategoryInterests` is the ONLY export of its module that is replaced, via
 * `requireActual`. `getInterestLabel` — the thing under test — runs for real,
 * and so does the page's own lookup. Mocking the whole module would leave this
 * file asserting against its own fixture, which is the shape of a vacuous
 * guard: the label would come from the mock and the page could go on coercing
 * absence to `0` forever.
 *
 * The map is injected rather than driven through `browserStore` because the
 * storage path is not what #2586 is about, and `parseInterests(null) === {}`
 * is already the established behaviour this file's first row depends on.
 */
function registerPreferencesMocks(interests: Record<string, number>) {
  jest.doMock("@/hooks/useCategoryInterests", () => ({
    ...jest.requireActual("@/hooks/useCategoryInterests"),
    useCategoryInterests: () => ({
      interests,
      setInterest: () => {},
      isLoading: false,
    }),
  }));
  jest.doMock("@/hooks", () => ({
    ...ANALYTICS_HOOKS,
    usePinnedEvents: () => ({
      pinnedIds: [],
      isPinned: () => false,
      togglePin: () => {},
      isMaxReached: false,
    }),
    usePinnedFutures: () => ({
      pinnedIds: [],
      isPinned: () => false,
      togglePin: () => {},
      isMaxReached: false,
    }),
  }));
  jest.doMock("next/navigation", () => ({
    useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
    useParams: () => ({}),
  }));
  jest.doMock("@/components/AuthProvider", () => ({
    useAuthContext: () => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      signOut: () => {},
    }),
  }));
  jest.doMock("@/lib/api", () => ({
    fetchUserPreferences: () => Promise.resolve({ favorites: [] }),
    removeFavorite: () => Promise.resolve(),
    fetchEventsByIds: () => Promise.resolve([]),
    fetchFuturesByIds: () => Promise.resolve([]),
  }));
  jest.doMock("swr", () => ({
    __esModule: true,
    default: () => settled(undefined),
  }));
}

/** Strip tags so the assertion reads what a PERSON reads. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/[“”]/g, '"')
    .replace(/[’]/g, "'")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Render the page inside its own module registry.
 *
 * `react-dom/server` is required INSIDE the isolated registry: `isolateModules`
 * hands the page a fresh `react`, and a renderer bound to the outer copy reads
 * a null hook dispatcher, so the page dies on its first `useState`.
 */
function renderPreferences(interests: Record<string, number>): string {
  let markup = "";
  jest.isolateModules(() => {
    registerPreferencesMocks(interests);
    /* eslint-disable @typescript-eslint/no-var-requires */
    const render = require("react-dom/server").renderToStaticMarkup;
    const Page = require("@/app/preferences/page").default;
    /* eslint-enable @typescript-eslint/no-var-requires */
    markup = render(React.createElement(Page));
  });
  return markup;
}

/** The label sitting to the right of one category row, e.g. "Nah" for Tennis. */
function labelFor(text: string, category: string): string | null {
  const match = text.match(
    new RegExp(`${category}\\s+(Not set|Love it|Big moments|If wild|Nah)\\s*›`)
  );
  return match ? match[1] : null;
}

function countOf(text: string, label: string): number {
  return text.split(new RegExp(`(?<![A-Za-z])${label}\\s*›`)).length - 1;
}

/** Every row the page lists, transcribed from `ALL_CATEGORIES` in page.tsx. */
const ALL_ROWS = [
  "NFL",
  "College Football",
  "NBA",
  "College Basketball",
  "Baseball",
  "Hockey",
  "Soccer",
  "Golf",
  "Tennis",
  "MMA",
  "Boxing",
  "Motorsports",
  "Cricket",
  "Rugby",
  "Politics",
  "Entertainment",
  "Economics",
  "Tech",
  "Weather",
  "Geopolitics",
  "Culture",
  "Esports",
  "Lacrosse",
  "Chess",
];

describe("#2586 — an untouched interest is not a rejection", () => {
  it("renders the interests control at all", () => {
    const text = visibleText(renderPreferences({}));
    // If this row ever fails, every assertion below is vacuous — they all read
    // a control that is not on the screen.
    expect(text).toContain("Your Interests");
    expect(text).toContain("Controls what shows up in your feed");
    for (const row of ALL_ROWS) expect(text).toContain(row);
  });

  it("a clean browser shows no rejection at all", () => {
    const text = visibleText(renderPreferences({}));

    // The photographed defect: 24 × "Nah ›" on a device that has chosen nothing.
    expect(countOf(text, "Nah")).toBe(0);
    expect(countOf(text, "Not set")).toBe(ALL_ROWS.length);
    for (const row of ALL_ROWS) {
      expect(labelFor(text, row)).toBe("Not set");
    }
  });

  it("one stored interest does not silently reject the other 23", () => {
    const text = visibleText(renderPreferences({ nfl: 1.0 }));

    expect(labelFor(text, "NFL")).toBe("Love it");
    expect(countOf(text, "Nah")).toBe(0);
    expect(countOf(text, "Not set")).toBe(ALL_ROWS.length - 1);
    for (const row of ALL_ROWS.filter((r) => r !== "NFL")) {
      expect(labelFor(text, row)).toBe("Not set");
    }
  });

  it("an explicit Nah still reads Nah", () => {
    // The anti-strawman control. `0` reaching this page from storage is a
    // reader who OPENED the selector and picked the reject option; that is a
    // choice and the page must keep reporting it. A repair that renamed the
    // label inside `getLevelLabel`, or dropped the reject option from
    // `LEVEL_OPTIONS`, satisfies every row above and fails here.
    const text = visibleText(renderPreferences({ tennis: 0, golf: 0.1 }));

    expect(labelFor(text, "Tennis")).toBe("Nah");
    expect(labelFor(text, "Golf")).toBe("If wild");
    expect(countOf(text, "Nah")).toBe(1);
    expect(countOf(text, "Not set")).toBe(ALL_ROWS.length - 2);
  });

  it("the selector highlights nothing for a category never chosen", () => {
    // `Math.abs(undefined - 0) < 0.05` is NaN < 0.05, which is false — the same
    // branch, reached by accident. The page states it, so this pins the reason
    // as well as the result: an unset row has no selected option, and a chosen
    // one does.
    /* eslint-disable @typescript-eslint/no-var-requires */
    const { getInterestLabel, UNSET_INTEREST_LABEL, getLevelLabel } =
      require("@/hooks/useCategoryInterests");
    /* eslint-enable @typescript-eslint/no-var-requires */

    expect(getInterestLabel(undefined)).toBe(UNSET_INTEREST_LABEL);
    expect(getInterestLabel(0)).toBe("Nah");
    expect(getInterestLabel(0.1)).toBe("If wild");
    expect(getInterestLabel(0.3)).toBe("Big moments");
    expect(getInterestLabel(1.0)).toBe("Love it");

    // The unset label must not collide with any of the four choosable ones, or
    // the page is back to two states sharing a rendering.
    for (const value of [0, 0.1, 0.3, 1.0]) {
      expect(getLevelLabel(value)).not.toBe(UNSET_INTEREST_LABEL);
    }
  });
});
