/**
 * #6113 — A LINK PREVIEW STOPS SAYING "LIVE NOW" OVER A NUMBER THE SERVER HAS
 * ALREADY FLAGGED AS FROZEN.
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION 2026-09-14 08:26Z ═══
 *
 * `https://bainluck.com/events/15312053` — ATP, Vishal Balsekar vs Lomakin, first
 * serve `2026-09-14T06:00:00Z` — pasted anywhere that unfurls, read at one instant:
 *
 *   og:title        "Vishal Balsekar vs Lomakin: Vishal Balsekar 1%, Lomakin 99%"
 *   og:description  "Live now. Bain Luck gives Vishal Balsekar a 1% win
 *                    probability and Lomakin a 99% win probability."
 *   og:image        "1%" ... "99%" in the hero slot, a 1/99 bar, footer "Live now"
 *
 * And the page those three link to, the same minute, leads with:
 *
 *   "No result reported"   ·   a Win Probability chart that is a FLAT line at 99%
 *
 * The page is honest. The preview says the match is being played.
 *
 * ═══ WHY THE NUMBER IS NOT A FORECAST EITHER ═══
 *
 * `GET /api/events/15312053` at that minute:
 *
 *   status                              live
 *   home_score / away_score             null / null
 *   win_probability_sources.kalshi      value 0.99, updated_at 08:21:19Z  ← FRESH
 *   live_probability_pinned.pinned      true
 *   live_probability_pinned.observations  59
 *   live_probability_pinned.span_seconds  7105
 *
 * The same 0.99 came back **59 times across 7,105 seconds** — just under two hours
 * — while the stamp stayed five minutes old. This is #5077's shape exactly: the
 * polls never stopped, they simply wrote the same value back, which is why
 * `lib/types.ts` says in the field's own docstring that **no frontend age rule can
 * see this**. The server flag is the only witness there is.
 *
 * ═══ WHY IT IS NOT A TAIL CASE, AND WHY THE OTHER ARM IS NOT CARRIED ═══
 *
 * Of the **23** rows sitting `status='live'` on production at 08:26Z, **8** carried
 * `live_probability_pinned` — 35%, at one arbitrary instant, with no waiting for a
 * transient.
 *
 * The complementary arm is empty and that is structural rather than lucky: **0 of
 * 23** had a blend older than an hour (the oldest was six minutes), because
 * `odds_polling.py` moves a genuinely silent `live` row to `suspended` — which
 * `hasNoReportedResult` already catches and #6105 already taught both halves of
 * this preview to read. The pinned rows are precisely the ones that net cannot
 * see, because the polling never went quiet.
 *
 * So this ship widens the PINNED arm only. `liveClaimIsUnbacked` is still the
 * helper that decides, so the meaning of "this live claim is unbacked" keeps one
 * owner across the page (#5459), the hero caption (#2800) and this preview — but
 * it is handed `blendAgeMs: null`, because a second copy of the page's
 * `freshestSourceStamp` would be a rule with no measured members AND would reopen
 * #5885, where a 61-minute pregame blend printed "No result reported" ten hours
 * before kickoff. Gating on `status === "live"` sidesteps that entirely.
 *
 * ═══ WHY THE WORD AND THE NUMBER MOVE TOGETHER ═══
 *
 * #6079's lesson, re-earned at #6105 and again here: fixing only the label leaves
 * "No result reported" printed under a 99% blend in the largest type on the card —
 * a contradiction where there had been one consistent lie. The label, the hero
 * pair, the bar and the description are one claim on one predicate.
 *
 * ═══ WHAT IS DELIBERATELY *NOT* DONE ═══
 *
 * A pinned row can UN-PIN the moment the price moves again, so this may WITHHOLD a
 * forecast and may never crown anyone, and it must not freeze the card into an
 * unfurler's cache. Every winner rung, and the settled cache window, stay gated on
 * `isFinal` alone — the last three tests here are what hold that line.
 */

import React from "react";
import { buildEventShareCopy, hasNoReportedResultForShare } from "@/lib/eventShareMeta";
import { unfurlImageCacheControl } from "@/lib/unfurlImageCache";

/** The element `ImageResponse` was constructed with. `mock`-prefixed for jest hoisting. */
const mockImageResponseCalls: React.ReactElement[] = [];
/** The OPTIONS it was constructed with — #6105's mutation run proved nothing else reads them. */
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
 * read. The real row and not a minimal invention, for the reason #6085's suite
 * gives: the finding is that a PLAUSIBLE card is drawn from an HONEST payload, and
 * a fixture built to the fix's shape cannot catch that.
 *
 * `opening_odds` is the row's own pre-match reading, which is what the card draws
 * once the live forecast is withheld.
 */
const BALSEKAR_LOMAKIN = {
  id: 15312053,
  home_team: "Lomakin",
  away_team: "Vishal Balsekar",
  status: "live",
  sport: "tennis_atp",
  sport_name: "Tennis Atp",
  home_score: null,
  away_score: null,
  completed_at: null,
  commence_time: "2026-09-14T06:00:00+00:00",
  hero_probability_source: "blend",
  hero_settled_result: null,
  current_odds: {
    captured_at: "2026-09-14T08:21:19.355978+00:00",
    home_probability: 0.99,
    away_probability: 0.01,
    home_rendered_percent: 99,
    away_rendered_percent: 1,
  },
  opening_odds: {
    home_probability: 0.62,
    away_probability: 0.38,
    favorite: "home" as const,
  },
  live_probability_pinned: {
    pinned: true,
    probability: 0.99,
    observations: 59,
    span_seconds: 7105,
    since: "2026-09-14T06:23:14.316502+00:00",
  },
};

/**
 * THE CONTROL THAT CARRIES THE WHOLE SHIP: the same row, same status, same frozen
 * -looking 99%, with the server flag ABSENT.
 *
 * Without this, a mutant returning `true` for every `live` row passes — and that
 * mutant is not hypothetical, it is the obvious "just treat live-with-no-score as
 * unreported" shortcut. A live match legitimately sits at 99% in the third set.
 * The flag is the only thing that distinguishes the two, so the flag is the only
 * thing that may move the card.
 */
const NOT_PINNED = (() => {
  const { live_probability_pinned: _dropped, ...rest } = BALSEKAR_LOMAKIN;
  return rest;
})();

/**
 * The server serving the envelope with `pinned` explicitly false.
 *
 * The route reads `?.pinned` rather than the object's presence, and these two
 * fixtures are what makes that a decision instead of an accident.
 */
const PINNED_FALSE = {
  ...BALSEKAR_LOMAKIN,
  live_probability_pinned: { ...BALSEKAR_LOMAKIN.live_probability_pinned, pinned: false },
};

/**
 * Pinned, but NOT yet under way — the #5885 guard.
 *
 * A pregame market polled slowly can sit at one price for two hours and be flagged
 * for it, and this is the row where saying "No result reported" would be the lie
 * told in the other direction. An OFFSET and not a literal date: four fixtures in
 * the suites #6105 touched had already rotted from future-dated into past-dated
 * while still calling themselves scheduled (gotcha #44).
 */
const PINNED_BEFORE_KICKOFF = {
  ...BALSEKAR_LOMAKIN,
  status: "scheduled",
  commence_time: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
};

/** Pinned AND finished. `isFinal` must keep winning: a result outranks a freeze. */
const PINNED_AND_FINAL = {
  ...BALSEKAR_LOMAKIN,
  status: "completed",
  hero_probability_source: "settled",
  hero_settled_result: "home",
  home_score: 2,
  away_score: 0,
  completed_at: "2026-09-14T08:30:00+00:00",
};

/* ────────────────────────────── the harness ────────────────────────────── */

async function renderCard(body: unknown): Promise<React.ReactElement> {
  mockImageResponseCalls.length = 0;
  mockImageResponseOptions.length = 0;
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  }) as unknown as typeof fetch;

  await OgImage({ params: { id: "15312053" } });

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
      style?: { fontSize?: number };
      children?: unknown;
    };
    walk(props?.children, { fontSize: props?.style?.fontSize ?? style.fontSize });
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

/**
 * The width of the away side of the split bar, as a whole percent, or `null` when
 * the card draws no bar.
 *
 * The bar is the one place a forecast survives as a SHAPE after being removed as a
 * number, and no text assertion in this file would see it. Anchored on the
 * PARENT's `borderRadius: 999` + `height: 30` and not on the child's
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
      style?: { height?: string | number; borderRadius?: number };
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

describe("#6113 — the picture stops calling a frozen match Live now", () => {
  it("REPRODUCES THE PRODUCTION CARD when the fix is removed, and replaces it", async () => {
    const card = await renderCard(BALSEKAR_LOMAKIN);
    const text = allText(card);

    // The two strings production drew, side by side, gone together.
    expect(text).not.toContain("Live now");
    expect(heroSlot(card)).not.toEqual(["1%", "99%"]);

    // What it draws instead: the pre-match pair, away first, and the house badge.
    expect(heroSlot(card)).toEqual(["38%", "62%"]);
    expect(text).toContain("No result reported");
  });

  it("withholds the forecast as a SHAPE too — the bar follows the number", async () => {
    // 38 is the pre-match reading the card falls back to; asserting the VALUE and
    // not merely `not.toBe(...)` is what stops a mutant that keeps the live bar
    // and only changes the words.
    expect(barAwayWidth(await renderCard(BALSEKAR_LOMAKIN))).toBe(38);

    // The unpinned twin draws the LIVE 1% — as 3, because the bar is clamped to
    // [3, 97] so a sliver stays visible at 1200px. Written as the clamped value
    // with the reason rather than as `1`, which is what this assertion first
    // expected: the number the card draws is the contract, and a test that
    // disagreed with it would be pinning my arithmetic, not the card's.
    expect(barAwayWidth(await renderCard(NOT_PINNED))).toBe(3);
  });

  it("CONTROL: an unpinned live match at the same 99% still leads with it", async () => {
    // The strawman kill. Everything about this row is identical to the specimen
    // except the server's flag — a live match genuinely sitting at 99% in the
    // third set must be untouched.
    const card = await renderCard(NOT_PINNED);
    expect(heroSlot(card)).toEqual(["1%", "99%"]);
    expect(allText(card)).toContain("Live now");
    expect(allText(card)).not.toContain("No result reported");
  });

  it("CONTROL: `pinned: false` is read as a VALUE, not as the key being present", async () => {
    const card = await renderCard(PINNED_FALSE);
    expect(heroSlot(card)).toEqual(["1%", "99%"]);
    expect(allText(card)).toContain("Live now");
  });

  it("CONTROL: a pinned row that has NOT kicked off keeps its forecast (#5885)", async () => {
    const card = await renderCard(PINNED_BEFORE_KICKOFF);
    expect(allText(card)).not.toContain("No result reported");
    expect(heroSlot(card)).toEqual(["1%", "99%"]);
  });

  it("a pinned row is never CROWNED — it withholds, it does not settle", async () => {
    const text = allText(await renderCard(BALSEKAR_LOMAKIN));
    expect(text).not.toContain("Final");
    expect(text).not.toContain("won");
  });

  it("a finished row outranks the freeze: `isFinal` still wins", async () => {
    const text = allText(await renderCard(PINNED_AND_FINAL));
    expect(text).toContain("Final");
    expect(text).not.toContain("No result reported");
  });

  it("a pinned card stays CACHED AS MOVING — it can un-pin", async () => {
    // #6105's surviving mutant, in this ship's own shape: every string above can
    // be right while the card is frozen into an unfurler's cache as though it were
    // settled. A pinned row is the opposite of settled — the price may move again
    // one minute later — so the window must be the moving one.
    await renderCard(BALSEKAR_LOMAKIN);
    expect(lastCacheControl()).toBe(unfurlImageCacheControl("moving"));
    expect(lastCacheControl()).not.toBe(unfurlImageCacheControl("settled"));
  });
});

/* ════════════════════════════ THE WORDS BESIDE IT ═════════════════════════ */

describe("#6113 — the title and description stop promising a live forecast", () => {
  const copyFor = (event: unknown, now?: number) =>
    buildEventShareCopy(event as Parameters<typeof buildEventShareCopy>[0], null, now);

  it("REPRODUCES the production description and replaces it", () => {
    const copy = copyFor(BALSEKAR_LOMAKIN);

    // Production: "Live now. Bain Luck gives Vishal Balsekar a 1% win probability
    // and Lomakin a 99% win probability."
    expect(copy.description).not.toContain("Live now");
    expect(copy.description).not.toContain("win probability");
    expect(copy.description).toContain("No result reported");

    // The title carried the same pair and must lose it with the sentence.
    expect(copy.title).not.toContain("99%");
    expect(copy.title).toContain("No result reported");
  });

  it("BOTH HALVES OF ONE PREVIEW AGREE — the whole point of the ship", async () => {
    // #6085 and #6079 were each one half of a preview fixed while the other went
    // on lying. This asserts the pair directly rather than trusting two suites.
    const card = allText(await renderCard(BALSEKAR_LOMAKIN));
    const copy = copyFor(BALSEKAR_LOMAKIN);
    expect(card).toContain("No result reported");
    expect(copy.description).toContain("No result reported");
    expect(card).not.toContain("Live now");
    expect(copy.description).not.toContain("Live now");
  });

  it("CONTROL: an unpinned live match keeps the probability copy", () => {
    expect(copyFor(NOT_PINNED).description).toContain("win probability");
    expect(copyFor(PINNED_FALSE).description).toContain("win probability");
  });

  it("CONTROL: a pinned row before kickoff keeps the probability copy (#5885)", () => {
    expect(copyFor(PINNED_BEFORE_KICKOFF).description).toContain("win probability");
  });
});

/* ═══════════════════════════════ THE PREDICATE ════════════════════════════ */

describe("#6113 — hasNoReportedResultForShare", () => {
  it("answers true for the measured specimen and false for its twin", () => {
    expect(hasNoReportedResultForShare(BALSEKAR_LOMAKIN)).toBe(true);
    expect(hasNoReportedResultForShare(NOT_PINNED)).toBe(false);
    expect(hasNoReportedResultForShare(PINNED_FALSE)).toBe(false);
  });

  it("keeps everything `hasNoReportedResult` already decided", () => {
    // The inherited arm, unchanged: a suspended row, and a scheduled row past the
    // grace, both still answer true WITHOUT any pinned flag in the payload.
    expect(hasNoReportedResultForShare({ status: "suspended" })).toBe(true);
    expect(
      hasNoReportedResultForShare({
        status: "scheduled",
        commence_time: new Date(Date.now() - 25 * 60 * 60 * 1000).toISOString(),
      }),
    ).toBe(true);
    expect(
      hasNoReportedResultForShare({
        status: "scheduled",
        commence_time: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      }),
    ).toBe(false);
  });

  it("the pinned arm is gated on `live` and nothing else", () => {
    // A pinned flag on any non-live status must not reach the new branch. `closed`
    // and `completed` are handled by `isFinishedForShare` upstream of this; what
    // matters here is that this predicate does not claim them for itself.
    const pinned = { pinned: true };
    expect(
      hasNoReportedResultForShare({ status: "closed", live_probability_pinned: pinned }),
    ).toBe(false);
    expect(
      hasNoReportedResultForShare({ status: "completed", live_probability_pinned: pinned }),
    ).toBe(false);
  });

  it("reads `live` the way the rest of the module does — trimmed and case-folded", () => {
    // `isFinishedForShare` normalises its status; a sibling predicate that did not
    // would disagree with it on the same row, which is the class of bug this whole
    // module exists to prevent.
    expect(
      hasNoReportedResultForShare({ status: " LIVE ", live_probability_pinned: { pinned: true } }),
    ).toBe(true);
  });

  it("an absent payload field is not a freeze", () => {
    expect(hasNoReportedResultForShare({ status: "live" })).toBe(false);
    expect(hasNoReportedResultForShare({ status: "live", live_probability_pinned: null })).toBe(
      false,
    );
  });
});
