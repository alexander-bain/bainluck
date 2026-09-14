/**
 * #6085 — A FINISHED GAME'S LINK PREVIEW DOES NOT PUBLISH A FORECAST.
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION 2026-09-14 06:1xZ ═══
 *
 * `https://bainluck.com/events/15310688` (US Open semi-final) pasted anywhere
 * that unfurls, read at one instant:
 *
 *   og:title        "Ben Shelton vs Alexander Zverev: Alexander Zverev won 3-1"
 *   og:description  "Final: Alexander Zverev beat Ben Shelton 3-1."
 *   og:image        "3%"  ...  "97%"   in 74px type, and no score anywhere
 *
 * One preview, two claims. The text states a result; the picture beside it
 * publishes a forecast.
 *
 * `GET /api/events/15310688` at the same minute:
 *
 *   status                       completed
 *   completed_at                 21:53:36Z
 *   current_odds.captured_at     21:51:16Z      ← the number the card drew
 *   home_rendered_percent        97
 *   opening_odds.home_prob       0.5758         ← the honest pre-match reading
 *   home_score / away_score      3 / 1          ← the result
 *   hero_probability_source      settled
 *
 * So 97% is not a pre-match figure. It is the last in-game blend, captured two
 * minutes and twenty seconds before the final whistle and frozen there. The
 * pre-match reading (58/42) and the score were both in the same payload.
 *
 * ═══ WHY THIS SUITE ASSERTS THE RENDER, NOT THE HELPERS ═══
 *
 * Nothing in the fix is a new rule. `isFinishedForShare` already decided when a
 * forecast must be withheld, `resolveEventOutcome` already decided who won and
 * with what trust, and `prematchReading` already decided which number a settled
 * card may print — for the title beside this picture and for the three card
 * surfaces `FeedCard` serves. All three were green throughout the bug, because
 * what was untested was whether THIS CARD CALLS THEM. No test of a rule can
 * answer that, so the route is invoked for real with `next/og` stubbed, and the
 * assertions read the strings a reader sees.
 *
 * That is the same reasoning, and the same harness, as `shareCardDuelPair4963` —
 * the last time this card was caught deciding privately something four surfaces
 * share.
 */

import React from "react";

/** The element `ImageResponse` was constructed with. `mock`-prefixed for jest hoisting. */
const mockImageResponseCalls: React.ReactElement[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import OgImage from "@/app/events/[id]/opengraph-image";

/* ───────────────────────────── the specimens ───────────────────────────── */

/**
 * The production payload, field for field, trimmed to what this route reads.
 *
 * Kept as the real row rather than a minimal invention: the whole finding was
 * that a plausible-looking card can be drawn from an honest payload, and a
 * fixture built to the fix's shape could not have caught that.
 */
const ZVEREV_SHELTON = {
  id: 15310688,
  home_team: "Alexander Zverev",
  away_team: "Ben Shelton",
  status: "completed",
  sport: "tennis_atp_us_open",
  sport_name: "ATP US Open",
  home_score: 3,
  away_score: 1,
  completed_at: "2026-09-13T21:53:36.535853+00:00",
  commence_time: "2026-09-13T18:13:40+00:00",
  hero_probability_source: "settled",
  hero_settled_result: "home",
  linescore: { sets: [[6, 3], [7, 6], [5, 7], [6, 2]] as [number, number][] },
  current_odds: {
    captured_at: "2026-09-13T21:51:16.130914+00:00",
    home_probability: 0.9689,
    away_probability: 0.0311,
    home_rendered_percent: 97,
    away_rendered_percent: 3,
  },
  opening_odds: {
    home_probability: 0.5758,
    away_probability: 0.4242,
    spread: -1.5,
    over_under: 42.5,
    favorite: "home" as const,
  },
};

/** The same match while it is still being played — the control that must not move. */
const STILL_PLAYING = {
  ...ZVEREV_SHELTON,
  status: "live",
  home_score: 2,
  away_score: 1,
  completed_at: null,
  hero_probability_source: "blend",
  hero_settled_result: null,
};

/* ────────────────────────────── the harness ────────────────────────────── */

async function renderCard(body: unknown): Promise<React.ReactElement> {
  mockImageResponseCalls.length = 0;
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  }) as unknown as typeof fetch;

  await OgImage({ params: { id: "15310688" } });

  if (mockImageResponseCalls.length !== 1) {
    throw new Error(
      `expected exactly 1 ImageResponse, captured ${mockImageResponseCalls.length}`,
    );
  }
  return mockImageResponseCalls[0];
}

interface PrintedText {
  text: string;
  fontSize?: number;
  fontWeight?: number;
  color?: string;
}

/**
 * Every string the tree prints, with the style of the box it prints it in.
 *
 * The style is inherited down to the text node so a `<div style={{fontSize}}>`
 * wrapping a bare string is attributed correctly, which is how the hero slot is
 * identified without reaching for a testid the real card does not carry.
 */
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

/**
 * The two team-name boxes, away first, with the colour each is drawn in.
 *
 * `fontWeight` and not `fontSize` alone: the crest badges are also 44px, at
 * weight 900.
 */
function nameBoxes(element: React.ReactElement): PrintedText[] {
  return printed(element).filter((p) => p.fontSize === 44 && p.fontWeight === 850);
}

/** The colour a name that is neither crowned nor muted is drawn in. */
const NEUTRAL_NAME = "#111827";
/** The colour a beaten side's name recedes to. */
const MUTED_NAME = "#64748b";

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
 * The width of the away side of the split bar, as a whole percent, or `null`
 * when the card draws no bar.
 *
 * Asserted because the bar is the one place the forecast can survive as a
 * SHAPE after being removed as a number — a bar still split 97/3 under a
 * settled score says the same wrong thing without printing it, and no
 * text-reading assertion in this file would notice.
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
      style?: { width?: string | number; height?: string | number; borderRadius?: number };
      // `ReactNode` and not `unknown` here: this branch hands the children to
      // `React.Children.toArray`, which will not take an `unknown`.
      children?: React.ReactNode;
    };
    // The TRACK, identified by its own geometry — anchoring on the fill alone
    // matched the root canvas, which is also `100%` by `100%`.
    if (props?.style?.height === 30 && props?.style?.borderRadius === 999) {
      const fill = React.Children.toArray(props.children).find(React.isValidElement) as
        | React.ReactElement
        | undefined;
      const width = (fill?.props as { style?: { width?: string } } | undefined)?.style?.width;
      if (typeof width === "string" && width.endsWith("%")) {
        found = Number.parseInt(width, 10);
      }
      return;
    }
    walk(props?.children);
  };
  walk(element);
  return found;
}

/* ─────────────────────────────── the tests ─────────────────────────────── */

describe("#6085 — a finished game's share picture leads with the result", () => {
  it("REPRODUCTION: the production specimen no longer prints 97% anywhere", async () => {
    const card = await renderCard(ZVEREV_SHELTON);
    const text = allText(card);

    // The two strings a reader actually saw on production, byte for byte.
    expect(text).not.toContain("97%");
    expect(text).not.toContain("3%");
  });

  it("draws the SCORE in the hero slot, not a probability", async () => {
    expect(heroSlot(await renderCard(ZVEREV_SHELTON))).toEqual(["1", "3"]);
  });

  it("prints the pre-match reading the payload actually carries, per side", async () => {
    const text = allText(await renderCard(ZVEREV_SHELTON));
    // 0.4242 / 0.5758 rounded as a pair — Shelton's 42, Zverev's 58. These are
    // the numbers `opening_odds` holds, NOT the 3/97 the card used to draw.
    expect(text).toContain("42%");
    expect(text).toContain("58%");
  });

  it("names the rung, because an opening_odds reading is a sportsbook median", async () => {
    // Alex: "labelled when not a prediction market." `sportsbooks` and never a
    // venue name (notice 33), and never the banned words.
    const text = allText(await renderCard(ZVEREV_SHELTON));
    expect(text).toContain("Pre-match · sportsbooks");
    expect(text).not.toMatch(/\bbookmaker/i);
    expect(text).not.toMatch(/\bbooks\b/);
  });

  it("carries the same scoreline the title beside it prints", async () => {
    // `resolveEventOutcome` winner's-games-first, from the same call the
    // layout makes. The two halves of one preview cannot word it two ways.
    expect(allText(await renderCard(ZVEREV_SHELTON))).toContain(
      "Final · 6-3, 7-6, 5-7, 6-2",
    );
  });

  it("lets the winner read as what happened and the beaten side recede", async () => {
    // The other half of the settled treatment: once the probability is gone,
    // the emphasis is what carries the result. Zverev is home and won.
    expect(nameBoxes(await renderCard(ZVEREV_SHELTON)).map((n) => n.color)).toEqual([
      MUTED_NAME,
      NEUTRAL_NAME,
    ]);
  });

  it("splits the bar on the pre-match pair, not the frozen one", async () => {
    // 42, not 3. `FeedCard`'s rule: "finished events show opening odds".
    expect(barAwayWidth(await renderCard(ZVEREV_SHELTON))).toBe(42);
  });

  it("draws no bar at all when there is no pre-match reading to split it on", async () => {
    expect(
      barAwayWidth(await renderCard({ ...ZVEREV_SHELTON, opening_odds: undefined })),
    ).toBeNull();
  });

  it("CONTROL: a live game still leads with its current probability", async () => {
    const card = await renderCard(STILL_PLAYING);
    // The forecast is the story while the game is on, so nothing here moves.
    expect(heroSlot(card)).toEqual(["3%", "97%"]);
    expect(barAwayWidth(card)).toBe(3);
    const text = allText(card);
    expect(text).toContain("Live now");
    // And the pre-match pair must NOT appear as a second reading beside it.
    expect(text).not.toContain("42%");
    expect(text).not.toContain("Pre-match");
  });

  it("CONTROL: a scheduled game is untouched", async () => {
    const card = await renderCard({
      ...ZVEREV_SHELTON,
      status: "scheduled",
      home_score: null,
      away_score: null,
      completed_at: null,
      hero_probability_source: null,
    });
    expect(heroSlot(card)).toEqual(["3%", "97%"]);
    expect(allText(card)).toContain("Upcoming");
  });

  it("a CLOSED game crowns nobody from its frozen scores — and still withholds the forecast", async () => {
    // The trap `layout.tsx` documents: `closed` scores are frozen mid-game and
    // were measured to INVERT the winner in 2 of 8 sampled rows. So the score
    // rung must decline them — while `closed` is still trusted to withhold.
    const card = await renderCard({
      ...ZVEREV_SHELTON,
      status: "closed",
      hero_probability_source: "blend",
      hero_settled_result: null,
    });
    const text = allText(card);
    expect(text).not.toContain("97%");
    expect(text).not.toContain("3%");
    expect(heroSlot(card)).toEqual([]);
    expect(text).toContain("Final");
    // The pre-match reading is a different question and survives.
    expect(text).toContain("58%");

    // ⚠️ THE HALF THAT A MUTATION RUN CAUGHT THIS FILE MISSING.
    //
    // Withholding the forecast is not the whole of the `closed` rule. Feeding
    // the ladder these scores anyway crowns a winner from them — a scoreline
    // in the footer and the beaten name greyed — and every assertion above
    // this comment stays green while it happens. The frozen scores were
    // measured to point at the WRONG player in 2 of 8 sampled rows, so a crown
    // drawn from them is the same lie the forecast was, in a quieter font.
    expect(text).not.toContain("6-3");
    expect(text).not.toMatch(/Final ·/);
    expect(nameBoxes(card).map((n) => n.color)).toEqual([NEUTRAL_NAME, NEUTRAL_NAME]);
  });

  it("a finished game with no pre-match reading prints no number at all", async () => {
    // `null` from `prematchReading` is a real answer and the only one that
    // licenses the empty space — a settled card prints nothing rather than a
    // number about a different question.
    const card = await renderCard({
      ...ZVEREV_SHELTON,
      opening_odds: undefined,
    });
    const text = allText(card);
    expect(text).not.toContain("97%");
    expect(text).not.toContain("%");
    // The result is still told.
    expect(heroSlot(card)).toEqual(["1", "3"]);
  });

  it("a settled DRAW mutes neither side", async () => {
    // `resolveEventOutcome` returns null on equal scores rather than crowning
    // the home side, so "we cannot crown" must not render as "nobody won".
    const card = await renderCard({
      ...ZVEREV_SHELTON,
      home_score: 2,
      away_score: 2,
      linescore: null,
    });
    const text = allText(card);
    expect(text).not.toContain("97%");
    // Both scores are still shown; neither name is greyed as a loser.
    expect(heroSlot(card)).toEqual(["2", "2"]);
    const names = nameBoxes(card);
    expect(names.map((n) => n.text)).toEqual(["Ben Shelton", "Alexander Zverev"]);
    expect(names.map((n) => n.color)).toEqual([NEUTRAL_NAME, NEUTRAL_NAME]);
  });
});
