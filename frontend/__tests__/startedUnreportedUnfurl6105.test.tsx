/**
 * #6105 — A MATCH THAT STARTED AND WAS NEVER REPORTED ON DOES NOT UNFURL AS
 * "UPCOMING" OVER A FROZEN MID-GAME FORECAST.
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION 2026-09-14 07:3xZ ═══
 *
 * `https://bainluck.com/events/15291351` — NPB, Yomiuri Giants at Tokyo Yakult
 * Swallows, first pitch `2026-08-25T09:00:00Z`, **twenty days earlier** — pasted
 * anywhere that unfurls, read at one instant:
 *
 *   og:title        "Yomiuri Giants vs Tokyo Yakult Swallows:
 *                    Yomiuri Giants 93%, Tokyo Yakult Swallows 7%"
 *   og:description  "Tue, Aug 25. Bain Luck GIVES Yomiuri Giants a 93% win
 *                    probability and Tokyo Yakult Swallows a 7% win probability."
 *   og:image        "93%" ... "7%" in the hero slot, a 93/7 bar, footer "Upcoming"
 *
 * And the page those three link to, the same minute:
 *
 *   "19d ago"  ·  "No result reported"  ·  "Aug 25, 2026 · 2:00 AM PDT"
 *
 * The page is honest. The preview says the game has not been played yet.
 *
 * `GET /api/events/15291351` at that minute:
 *
 *   status                       suspended
 *   completed_at                 null
 *   current_odds.captured_at     2026-08-25T12:58:07Z   ← the number the card drew
 *   away_rendered_percent        93
 *   opening_odds.away_prob       0.5408                 ← the honest pre-match reading
 *   home_score / away_score      null / null
 *
 * So 93% was never the forecast either. It is `current_odds` captured about four
 * hours into the match and frozen there ever since; the pre-match reading on the
 * same row is 54/46, a near coin-flip. The card was thirty-nine points from the
 * honest number AND calling the game upcoming.
 *
 * ═══ WHY IT IS NOT A TAIL CASE ═══
 *
 * Measured the same morning: **2,739** `suspended` rows, **2,739** of them already
 * past their own start and **zero** with a future one, plus **821** `scheduled`
 * rows past the two-hour grace. 3,560 previews and not one row where the word
 * "Upcoming" was true.
 *
 * ═══ WHY THIS IS AN ADOPTION AND NOT A DESIGN ═══
 *
 * `lib/eventState.ts` was written for this exact failure and its own docstring
 * names it: an unrecognised status "buckets into the 'upcoming' branch by falling
 * through, and the upcoming branch renders a START TIME — so a match suspended
 * for rain would have advertised itself as about to begin. That is a quieter lie
 * than 'Final', not a smaller one."
 *
 * `EventCard`, `FeedCard`, the event-page hero and every grid section already call
 * `hasNoReportedResult()` and print `SUSPENDED_LABEL`. Both halves of the unfurl
 * were the surfaces that never called the owner — the same shape as #6085, where
 * the text half had been fixed and the picture had not, and #6079, where the
 * picture was right and the words were not.
 *
 * ═══ AND WHY THE WORD AND THE NUMBER MOVE TOGETHER ═══
 *
 * #6079's lesson, one surface over: the narrow fix is worse than the defect.
 * Changing only the label leaves "No result reported" printed under a 93% live
 * blend in the largest type on the card — a contradiction where there had been a
 * single consistent lie. So the label, the hero pair, the bar and the footnote are
 * one claim and are gated on one predicate.
 *
 * ═══ WHAT IS DELIBERATELY *NOT* DONE ═══
 *
 * `suspended` is non-terminal (live/048, EVENT-GRAPH-DOCTRINE §R) and CERT-752 is
 * the cost of forgetting it: six US Open matches, one 1-2 down in sets, nearly
 * settled and graded off a partial score. So this ship may WITHHOLD a forecast and
 * may never crown anyone — every score and winner rung stays gated on `isFinal`
 * alone, and the last two tests in the picture block are what hold that line.
 */

import React from "react";
import { buildEventShareCopy } from "@/lib/eventShareMeta";
import { UPCOMING_GRACE_MS } from "@/lib/eventState";
import { unfurlImageCacheControl } from "@/lib/unfurlImageCache";

/** The element `ImageResponse` was constructed with. `mock`-prefixed for jest hoisting. */
const mockImageResponseCalls: React.ReactElement[] = [];
/**
 * The OPTIONS it was constructed with, captured alongside the element.
 *
 * Added because a mutant that caches a no-result card as `settled` survived the
 * first full mutation run: every string on the card was right and nothing read
 * the header. That is not a cosmetic gap — the cache window is the difference
 * between a badge that corrects itself when a source finally reports and one
 * frozen into every unfurler that saw it first.
 */
const mockImageResponseOptions: Array<{ headers?: Record<string, string> }> = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(
    element: React.ReactElement,
    options: { headers?: Record<string, string> },
  ) {
    mockImageResponseCalls.push(element);
    mockImageResponseOptions.push(options);
    return { __stub: "ImageResponse" };
  },
}));

import OgImage from "@/app/events/[id]/opengraph-image";

/* ───────────────────────────── the specimens ───────────────────────────── */

/**
 * The production payload, field for field, trimmed to what these two surfaces
 * read. Kept as the real row rather than a minimal invention for the reason
 * #6085's suite gives: the finding was that a plausible card is drawn from an
 * honest payload, and a fixture built to the fix's shape could not catch that.
 */
const GIANTS_SWALLOWS = {
  id: 15291351,
  home_team: "Tokyo Yakult Swallows",
  away_team: "Yomiuri Giants",
  status: "suspended",
  sport: "baseball_npb",
  sport_name: "NPB",
  home_score: null,
  away_score: null,
  completed_at: null,
  commence_time: "2026-08-25T09:00:00+00:00",
  hero_probability_source: "blend",
  hero_settled_result: null,
  current_odds: {
    captured_at: "2026-08-25T12:58:07.829249+00:00",
    home_probability: 0.0723,
    away_probability: 0.9277,
    home_rendered_percent: 7,
    away_rendered_percent: 93,
  },
  opening_odds: {
    home_probability: 0.4592,
    away_probability: 0.5408,
    spread: 1.5,
    over_under: 8.5,
    favorite: "away" as const,
  },
};

/**
 * The SAME row an hour before its own first pitch — the control that must not
 * move, and the one that kills a mutant returning `true` unconditionally.
 *
 * An offset from the anchor and not a literal date: "upcoming" is a relation to
 * the clock, and three fixtures in the two suites this ship touched had already
 * rotted from future-dated into past-dated while still calling themselves
 * scheduled (gotcha #44).
 */
const NOT_YET_STARTED = {
  ...GIANTS_SWALLOWS,
  status: "scheduled",
  commence_time: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
};

/**
 * Being played right now, and carrying no `live_probability_pinned`.
 *
 * #6113 moved the `live` test BELOW the no-result test, so this fixture no longer
 * passes because `live` short-circuits — it passes because a live row the server
 * has not flagged as frozen is genuinely live. That is the stronger reason, and
 * the two controls below are what hold #6113 to its measured population.
 */
const IN_PROGRESS = { ...GIANTS_SWALLOWS, status: "live" };

/* ────────────────────────────── the harness ────────────────────────────── */

async function renderCard(body: unknown): Promise<React.ReactElement> {
  mockImageResponseCalls.length = 0;
  mockImageResponseOptions.length = 0;
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  }) as unknown as typeof fetch;

  await OgImage({ params: { id: "15291351" } });

  if (mockImageResponseCalls.length !== 1) {
    throw new Error(
      `expected exactly 1 ImageResponse, captured ${mockImageResponseCalls.length}`,
    );
  }
  return mockImageResponseCalls[0];
}

/** The `cache-control` the route asked for on the render just taken. */
function lastCacheControl(): string | undefined {
  return mockImageResponseOptions.at(-1)?.headers?.["cache-control"];
}

interface PrintedText {
  text: string;
  fontSize?: number;
  fontWeight?: number;
  color?: string;
}

function printed(element: React.ReactElement): PrintedText[] {
  const found: PrintedText[] = [];
  const walk = (node: unknown, style: Omit<PrintedText, "text">): void => {
    if (Array.isArray(node)) {
      node.forEach((child) => walk(child, style));
      return;
    }
    if (typeof node === "string" && node.trim() !== "") {
      found.push({ text: node, ...style });
      return;
    }
    if (typeof node === "number") {
      found.push({ text: String(node), ...style });
      return;
    }
    if (!React.isValidElement(node)) return;
    const props = node.props as {
      style?: { fontSize?: number; fontWeight?: number; color?: string };
      children?: unknown;
    };
    walk(props?.children, {
      fontSize: props?.style?.fontSize ?? style.fontSize,
      fontWeight: props?.style?.fontWeight ?? style.fontWeight,
      color: props?.style?.color ?? style.color,
    });
  };
  walk(element, {});
  return found;
}

/** The whole card as one string, for "this must appear NOWHERE" assertions. */
function allText(element: React.ReactElement): string {
  return printed(element)
    .map((p) => p.text)
    .join(" ");
}

/** What the card draws in the hero slot, away side first. */
function heroSlot(element: React.ReactElement): string[] {
  return printed(element)
    .filter((p) => p.fontSize === 74)
    .map((p) => p.text);
}

/** The two team-name boxes, away first, with the colour each is drawn in. */
function nameBoxes(element: React.ReactElement): PrintedText[] {
  return printed(element).filter((p) => p.fontSize === 44 && p.fontWeight === 850);
}

const NEUTRAL_NAME = "#111827";

/**
 * The width of the away side of the split bar, as a whole percent, or `null`
 * when the card draws no bar.
 *
 * The bar is the one place a forecast survives as a SHAPE after being removed as
 * a number, and no text assertion in this file would see it.
 *
 * Anchored on the PARENT's `borderRadius: 999` and not on the child's
 * `height: "100%"` alone — that geometry also matches the 1200×630 root canvas,
 * which is how the same walker in #6085 first matched the wrong element.
 */
function barAwayWidth(element: React.ReactElement): number | null {
  let found: number | null = null;
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (!React.isValidElement(node)) return;
    const props = node.props as {
      style?: { height?: string | number; borderRadius?: number; width?: string | number };
      children?: React.ReactNode;
    };
    if (props?.style?.borderRadius === 999 && props?.style?.height === 30) {
      React.Children.toArray(props.children).forEach((child) => {
        if (!React.isValidElement(child)) return;
        const w = (child.props as { style?: { width?: string | number } })?.style?.width;
        if (typeof w === "string" && w.endsWith("%")) {
          found = Number.parseFloat(w);
        }
      });
      return;
    }
    walk(props?.children);
  };
  walk(element);
  return found;
}

/* ═══════════════════════════════ THE PICTURE ══════════════════════════════ */

describe("#6105 — the picture stops calling a started match Upcoming", () => {
  it("REPRODUCES THE PRODUCTION CARD when the fix is removed, and replaces it", async () => {
    const card = await renderCard(GIANTS_SWALLOWS);
    const text = allText(card);

    // The two strings production drew, side by side, gone together.
    expect(text).not.toContain("Upcoming");
    expect(heroSlot(card)).not.toEqual(["93%", "7%"]);

    // What it draws instead: the pre-match pair, away first, and the house badge.
    expect(heroSlot(card)).toEqual(["54%", "46%"]);
    expect(text).toContain("No result reported");
    expect(text).toContain("Pre-match · sportsbooks");
  });

  it("prints the frozen in-game blend NOWHERE on the card", async () => {
    // Not "leads with something else" — the 93% must not survive as a footnote,
    // a caption or a second reading anywhere in the tree.
    const text = allText(await renderCard(GIANTS_SWALLOWS));
    expect(text).not.toContain("93%");
    expect(text).not.toContain("7%");
  });

  it("splits the bar on the pre-match pair, not on the frozen blend", async () => {
    // The forecast surviving as a SHAPE is the same claim told without printing.
    expect(barAwayWidth(await renderCard(GIANTS_SWALLOWS))).toBe(54);
  });

  it("draws no bar and no number when the row holds no opening line", async () => {
    // 2,054 of the 2,739 suspended rows. The card states the names, the league
    // and the badge, and says the rest by saying nothing — it must NOT fall back
    // to the live blend to fill the space.
    const card = await renderCard({ ...GIANTS_SWALLOWS, opening_odds: undefined });
    expect(heroSlot(card)).toEqual([]);
    expect(barAwayWidth(card)).toBeNull();
    expect(allText(card)).toContain("No result reported");
    expect(allText(card)).not.toContain("93%");
  });

  it("carries the last score when the row holds one", async () => {
    // The badge says what is not known; the score says what is. Away-first,
    // because this card paints the away side in the left column.
    const card = await renderCard({
      ...GIANTS_SWALLOWS,
      away_score: 4,
      home_score: 2,
    });
    expect(allText(card)).toContain("No result reported · last score 4-2");
  });

  it("treats a scheduled row past the grace the same way", async () => {
    // #6105's second arm — 821 rows. Nothing ever reported on these at all, and
    // to a reader that is the same sentence as a suspension.
    const card = await renderCard({
      ...GIANTS_SWALLOWS,
      status: "scheduled",
      commence_time: new Date(Date.now() - UPCOMING_GRACE_MS - 60_000).toISOString(),
    });
    expect(allText(card)).toContain("No result reported");
    expect(allText(card)).not.toContain("Upcoming");
    expect(heroSlot(card)).toEqual(["54%", "46%"]);
  });

  it("CROWNS NOBODY — withholding is not the same as deciding", async () => {
    // CERT-752's line. A suspended row must not pick up the settled card's
    // emphasis: no name recedes, because "we do not know who won" must never
    // render as "this side lost".
    const card = await renderCard({
      ...GIANTS_SWALLOWS,
      away_score: 4,
      home_score: 2,
    });
    const names = nameBoxes(card);
    expect(names).toHaveLength(2);
    for (const n of names) expect(n.color).toBe(NEUTRAL_NAME);
    expect(allText(card)).not.toContain("Final");
  });

  it("keeps the SHORT cache window — a withheld forecast is not a settled card", async () => {
    // The one place `forecastWithheld` and `isFinal` must NOT be collapsed, and
    // the mutant that proved this needed asserting: swapping the cache read to
    // `forecastWithheld` left every string on the card correct and survived the
    // whole suite.
    //
    // The NUMBER on a no-result card is fixed (the pre-match pair), but the STATE
    // is the most movable one we hold — `suspended` is non-terminal and the row
    // can still go `live` or be graded by something that finally watched. A
    // settled window would freeze "No result reported" into every unfurler that
    // saw it first.
    await renderCard(GIANTS_SWALLOWS);
    expect(lastCacheControl()).toBe(unfurlImageCacheControl("moving"));
    expect(lastCacheControl()).not.toBe(unfurlImageCacheControl("settled"));

    // And the finished card still takes the long one, so this is a statement
    // about the new state rather than a blanket downgrade.
    await renderCard({
      ...GIANTS_SWALLOWS,
      status: "completed",
      hero_probability_source: "settled",
      away_score: 6,
      home_score: 3,
    });
    expect(lastCacheControl()).toBe(unfurlImageCacheControl("settled"));
  });

  it("CONTROL: a live game still leads with its current probability", async () => {
    const card = await renderCard(IN_PROGRESS);
    expect(heroSlot(card)).toEqual(["93%", "7%"]);
    expect(barAwayWidth(card)).toBe(93);
    const text = allText(card);
    expect(text).toContain("Live now");
    expect(text).not.toContain("No result reported");
    expect(text).not.toContain("Pre-match");
  });

  it("CONTROL: a genuinely upcoming game still says Upcoming and keeps its forecast", async () => {
    // THE STRAWMAN KILL (gotcha #43). A `hasNoReportedResult` stubbed to `true`
    // satisfies every negative assertion above; only this test and the live one
    // above notice, because they are the two rows the ship must not touch.
    const card = await renderCard(NOT_YET_STARTED);
    expect(heroSlot(card)).toEqual(["93%", "7%"]);
    expect(barAwayWidth(card)).toBe(93);
    const text = allText(card);
    expect(text).toContain("Upcoming");
    expect(text).not.toContain("No result reported");
  });

  it("CONTROL: #6085's finished treatment is untouched", async () => {
    // A `completed` row still leads with the SCORE and still labels its
    // pre-match footnote — this ship widened the withholding, not the crowning.
    const card = await renderCard({
      ...GIANTS_SWALLOWS,
      status: "completed",
      completed_at: "2026-08-25T12:59:00+00:00",
      hero_probability_source: "settled",
      hero_settled_result: "away",
      away_score: 6,
      home_score: 3,
    });
    expect(heroSlot(card)).toEqual(["6", "3"]);
    const text = allText(card);
    expect(text).toContain("Final");
    expect(text).toContain("Pre-match · sportsbooks");
    expect(text).not.toContain("No result reported");
    expect(text).not.toContain("93%");
  });
});

/* ════════════════════════════════ THE WORDS ═══════════════════════════════ */

describe("#6105 — the title and description stop publishing a present-tense forecast", () => {
  /** What `layout.tsx` passes: the payload, and `null` because rung 2 is only
   *  fetched for a finished row. */
  const copyFor = (event: Parameters<typeof buildEventShareCopy>[0], now?: number) =>
    buildEventShareCopy(event, null, now);

  it("REPLACES the production strings", () => {
    const copy = copyFor(GIANTS_SWALLOWS);

    // Served on production, verbatim, both gone.
    expect(copy.title).not.toBe(
      "Yomiuri Giants vs Tokyo Yakult Swallows: Yomiuri Giants 93%, Tokyo Yakult Swallows 7%",
    );
    expect(copy.description).not.toContain("Bain Luck gives");

    expect(copy.title).toBe(
      "Yomiuri Giants vs Tokyo Yakult Swallows: No result reported",
    );
    expect(copy.description).toBe(
      "No result reported. This match left the live board and no source has reported a result.",
    );
    expect(copy.settled).toBe(false);
  });

  it("leaks no percentage behind the removed sentence", () => {
    // #6079's finding, one surface over: gating the WORD alone dropped a market
    // into a branch that published the frozen prices instead. The no-result
    // branch is terminal for exactly that reason.
    const copy = copyFor(GIANTS_SWALLOWS);
    expect(copy.title).not.toMatch(/\d+%/);
    expect(copy.description).not.toMatch(/\d+%/);
    expect(copy.description).not.toContain("win probability");
  });

  it("carries the last score when the row holds one", () => {
    const copy = copyFor({ ...GIANTS_SWALLOWS, away_score: 4, home_score: 2 });
    expect(copy.title).toContain("No result reported · last score 4-2");
  });

  it("says nothing about a future update", () => {
    // The shipped-copy ban rejects will-populate language, and this state's job
    // is to describe what is and is not known right now.
    const copy = copyFor(GIANTS_SWALLOWS);
    expect(copy.description).not.toMatch(/will|soon|shortly|check back|yet\./i);
  });

  it("pins the two-hour grace boundary off an injected clock", () => {
    // gotcha #44 — offset from an anchor, never branch on the real clock. The
    // boundary is the whole reason `now` is a parameter.
    const tip = Date.parse("2026-09-02T23:00:00Z");
    const scheduled = {
      ...GIANTS_SWALLOWS,
      status: "scheduled",
      commence_time: "2026-09-02T23:00:00Z",
    };

    // One minute INSIDE the grace: still plausibly about to start.
    const inside = copyFor(scheduled, tip + UPCOMING_GRACE_MS - 60_000);
    expect(inside.description).toContain("win probability");
    expect(inside.description).not.toContain("No result reported");

    // One minute OUTSIDE it: the clock has run out and nothing has spoken.
    const outside = copyFor(scheduled, tip + UPCOMING_GRACE_MS + 60_000);
    expect(outside.description).toContain("No result reported");
    expect(outside.description).not.toContain("win probability");
  });

  it("CONTROL: a live game keeps the probability copy", () => {
    expect(copyFor(IN_PROGRESS).description).toContain("win probability");
  });

  it("CONTROL: a genuinely upcoming game keeps the probability copy", () => {
    // The second half of the strawman kill.
    const copy = copyFor(NOT_YET_STARTED);
    expect(copy.description).toContain("win probability");
    expect(copy.title).toContain("93%");
  });

  it("CONTROL: a row we cannot place on the clock is left on the schedule", () => {
    // `hasNoReportedResult` answers FALSE on an absent or unparseable
    // `commence_time` on purpose — a row we cannot date is one we have no
    // standing to move. This is a documented edge, not an oversight, so it is
    // pinned rather than left for someone to "fix".
    for (const commence_time of [null, "", "not a date"]) {
      const copy = copyFor({
        ...GIANTS_SWALLOWS,
        status: "scheduled",
        commence_time,
      });
      expect(copy.description).toContain("win probability");
      expect(copy.description).toContain("Upcoming");
    }
  });

  it("CONTROL: #6085's settled ladder still answers first", () => {
    // Placement matters: the no-result branch sits BELOW every settled rung, so
    // a row something DID grade still gets its result.
    const copy = copyFor({
      ...GIANTS_SWALLOWS,
      status: "completed",
      hero_probability_source: "settled",
      hero_settled_result: "away",
      away_score: 6,
      home_score: 3,
    });
    expect(copy.title).toBe(
      "Yomiuri Giants vs Tokyo Yakult Swallows: Yomiuri Giants won 6-3",
    );
    expect(copy.settled).toBe(true);
  });
});
