/**
 * #6127 — A PASTED MARKET LINK STOPS DRAWING A DASH IN 96px AND CROWNING AN
 * ARBITRARY LEADER.
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION 2026-09-14 10:05Z ═══
 *
 * `https://bainluck.com/futures/59698973` — *2027 Men's College Basketball
 * National Champion*, `status='open'`, `outcome_count: 2`, both outcomes served
 * with `probability: null` — pasted anywhere that unfurls, read at one instant:
 *
 *   og:title        "2027 Men's College Basketball National Champion | Bain Luck"
 *   og:description  "2027 Men's College Basketball National Champion. See this
 *                    market translated into intuitive probabilities on Bain
 *                    Luck."                                                 ✅
 *   og:image        "- -" in 96px type · "Ohio State" in 40px beneath it ·
 *                    a 3%-wide orange bar stub under that                   ❌
 *
 * The WORDS are careful, and have been since L2-55: `layout.tsx` gates the board
 * sentence on `leader && probability` and otherwise names the market and stops.
 * The PICTURE, drawn from the same payload one file away, made three claims the
 * row does not contain.
 *
 * ═══ 🔴 THE CROWNED NAME IS THE WORSE HALF, AND IT IS NOT A RANKING ═══
 *
 * `topOutcome` sorts on `(b.probability ?? -1) - (a.probability ?? -1)`. When
 * every probability is null that comparator returns 0 for every pair, so the
 * "leader" is whatever the API serialised first — ARRAY ORDER. "Ohio State" was
 * printed as the favourite for a 2027 national title on no evidence whatsoever,
 * and the bar stub beside it reads as a real long-shot price rather than as an
 * absence. A dash at least looks like a rendering fault; a name looks like a
 * finding. `crowns nobody from array order` below is the assertion for this, and
 * it is the one a fix that only deleted the dash would fail.
 *
 * ═══ REACH ═══
 *
 * 12,099 of 35,777 `open` markets (33.8%) carry no outcome with a non-null,
 * non-zero `current_probability` — one db-query, 2026-09-14 10:19Z, no fetch
 * loop, so this figure is not exposed to the rate-limit contamination that made
 * #6119 publish a wrong one. (Two fixture fetches in this session DID get
 * throttled; they were caught because every response is validated by `id` before
 * it is read, which is the rule #6119 bought.)
 *
 * The 72,143 `resolved` rows with the same emptiness are NOT this defect: they
 * take the `isResolved` branch, which draws the winner and deliberately prints no
 * percentage at all. `a resolved market is untouched` pins that.
 *
 * ═══ THE RULE IS AN ADOPTION — THE SIXTH IN A ROW ═══
 *
 * `futuresBoardPrice` is the words' own test, lifted into
 * `futuresDetailDisplay.ts` and called by both surfaces. Nothing new was decided:
 * #6061, #6079, #6085, #6105, #6113 and #6119 were all the same shape, and so is
 * this one — the defect is never that a rule is missing, it is that one of two
 * surfaces never asked for it.
 *
 * ═══ WHERE #6119's EXACT-ZERO GAP DOES *NOT* FOLLOW ═══
 *
 * On `/events/[id]` the picture's predicate had to be kept NARROWER than the
 * words', because `formatProbability` treats an exact 0 as "no number" while
 * #4963 ruled for that card that "a finished game's loser is 0%, and 0% is a
 * fact". There is no such collision here: a settled futures market takes the
 * `isResolved` branch on BOTH surfaces and prints no percentage either way, so a
 * graded zero never reaches this rule. The only rows it can see are unresolved
 * boards, where the words have always been quiet about a zero too. So this is the
 * words' rule WHOLE, and `the two halves agree on every specimen` asserts the
 * equivalence in both directions rather than leaving it to the comment.
 *
 * ═══ WHAT IS DELIBERATELY *NOT* DONE ═══
 *
 * Withholding only. A price can arrive on the next poll, so this may make the
 * card quiet and may never make it assert anything: the category pill, the market
 * name and the outcome count are facts and stay; the settled branch is untouched;
 * the cache window is untouched. And no dash — notice 34 / D102: leave the space
 * empty, do not explain the emptiness.
 */

import React from "react";
import { futuresBoardPrice } from "@/lib/futuresDetailDisplay";

/** The element `ImageResponse` was constructed with. `mock`-prefixed for jest hoisting. */
const mockImageResponseCalls: React.ReactElement[] = [];
/** The OPTIONS it was constructed with — the cache window lives here. */
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

import OgImage from "@/app/futures/[id]/opengraph-image";

/* ───────────────────────────── the specimens ───────────────────────────── */

/**
 * The slice of `GET /api/futures/{id}` these two surfaces actually read.
 *
 * Declared rather than inferred from the first fixture: every probability on the
 * measured specimen is `null`, so `typeof CBB_2027` would type the field as
 * `null` and the PRICED control — the one fixture that proves the ship did not
 * over-reach — would not typecheck against it.
 */
interface Board {
  id: number;
  name: string;
  status: string;
  llm_sport_category: string;
  sport_name: string | null;
  outcome_count: number;
  hook_description: string | null;
  outcomes: Array<{
    name: string;
    probability: number | null;
    probability_change_24h: number | null;
    is_winner: boolean | null;
  }>;
}

/**
 * The production payload, field for field, trimmed to what this route reads —
 * the real row and not a minimal invention, for the reason #6085's suite gives:
 * the finding is that a PLAUSIBLE card is drawn from an HONEST payload, and a
 * fixture built to the fix's shape cannot catch that.
 *
 * `Ohio State` leads only because it is first in the array. That is the point.
 */
const CBB_2027: Board = {
  id: 59698973,
  name: "2027 Men's College Basketball National Champion",
  status: "open",
  llm_sport_category: "basketball",
  sport_name: null,
  outcome_count: 2,
  hook_description: null,
  outcomes: [
    { name: "Ohio State", probability: null, probability_change_24h: null, is_winner: false },
    { name: "BYU", probability: null, probability_change_24h: null, is_winner: false },
  ],
};

/**
 * The second production specimen — `/futures/59164829`, Thai League 1 Champion,
 * SIXTEEN outcomes, every one null. Present because the defect's shape does not
 * depend on the board being small, and because a 16-name board makes the
 * array-order crowning even less defensible.
 */
const THAI_LEAGUE: Board = {
  id: 59164829,
  name: "Thai League 1 Champion",
  status: "open",
  llm_sport_category: "soccer",
  sport_name: null,
  outcome_count: 16,
  hook_description: null,
  outcomes: [
    { name: "Ayutthaya Utd", probability: null, probability_change_24h: null, is_winner: null },
    { name: "Pattani FC", probability: null, probability_change_24h: null, is_winner: null },
    { name: "Bangkok Utd", probability: null, probability_change_24h: null, is_winner: null },
    { name: "Buriram", probability: null, probability_change_24h: null, is_winner: null },
  ],
};

/**
 * ═══ THE CONTROL THAT CARRIES THE WHOLE SHIP ═══
 *
 * `/futures/60966073` as production served it — a priced, open, 11-outcome
 * board. Without this, a mutant that withholds the number on EVERY open market
 * passes every other assertion in this file, and that mutant is not
 * hypothetical: 23,678 of the 35,777 open markets ARE priced and must be
 * untouched.
 */
const HOUSTON_TEMP: Board = {
  id: 60966073,
  name: "Highest temperature in Houston on September 15?",
  status: "open",
  llm_sport_category: "weather",
  sport_name: null,
  outcome_count: 11,
  hook_description: null,
  outcomes: [
    { name: "94-95°F", probability: 0.408, probability_change_24h: null, is_winner: null },
    { name: "92-93°F", probability: 0.359, probability_change_24h: null, is_winner: null },
    { name: "96-97°F", probability: 0.08, probability_change_24h: -0.005, is_winner: null },
    { name: "90-91°F", probability: 0.062, probability_change_24h: 0.005, is_winner: null },
  ],
};

/**
 * ═══ THE ROW THAT SEPARATES "NO PRICE" FROM "A SMALL PRICE" ═══
 *
 * A board where the LEADER is priced and the chasers are not. The withholding is
 * a property of the leader only, and it has to be: `topOutcome` sorts unpriced
 * rows to the bottom, so a null further down says nothing about the top. If this
 * card goes quiet the fix has over-reached and thousands of thinly-quoted but
 * perfectly honest boards lose their number.
 */
const LEADER_ONLY_PRICED: Board = {
  ...THAI_LEAGUE,
  outcomes: [
    { name: "Buriram", probability: 0.71, probability_change_24h: null, is_winner: null },
    { name: "Bangkok Utd", probability: null, probability_change_24h: null, is_winner: null },
    { name: "Pattani FC", probability: null, probability_change_24h: null, is_winner: null },
  ],
};

/**
 * Every outcome priced at exactly 0 on an UNRESOLVED board.
 *
 * On the game card this shape is a live disagreement between two shipped rulings
 * (#4963 vs #1495) and #6119 deliberately left it alone. Here it is not: a graded
 * zero belongs to a resolved market, which prints no percentage on either
 * surface, so the only zeroes this rule can see are these — and the words have
 * always been quiet about them. Pinned so the two routes' different answers to
 * "what is a zero" stay a deliberate difference and not an accident.
 */
const ZERO_PRICED: Board = {
  ...CBB_2027,
  outcomes: [
    { name: "Ohio State", probability: 0, probability_change_24h: null, is_winner: false },
    { name: "BYU", probability: 0, probability_change_24h: null, is_winner: false },
  ],
};

/** A resolved market with a graded winner — the settled branch, which must not move. */
const RESOLVED_GRADED: Board = {
  ...CBB_2027,
  status: "resolved",
  outcomes: [
    { name: "Ohio State", probability: null, probability_change_24h: null, is_winner: true },
    { name: "BYU", probability: null, probability_change_24h: null, is_winner: false },
  ],
};

/**
 * A resolved market with nothing graded AND no prices — #6079's third shape. It
 * must keep taking the settled branch (grey RESOLVED pill, no percentage) rather
 * than falling into this ship's quiet branch, which would drop the pill and lose
 * the one thing the card still knows.
 */
const RESOLVED_UNGRADED: Board = {
  ...CBB_2027,
  status: "resolved",
};

/** No outcomes at all on a live row — the `leader === null` arm. */
const NO_OUTCOMES: Board = {
  ...CBB_2027,
  outcome_count: 0,
  outcomes: [],
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

  await OgImage({ params: { id: "59698973" } });

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

/**
 * The same text with the walker's fragment gaps closed.
 *
 * The footer is `{n} outcome{n !== 1 ? "s" : ""} tracked`, i.e. four sibling
 * nodes, and `allText`'s space join renders it "2  outcome s  tracked". That is
 * an artefact of the walker and not of the card, so footer assertions read this.
 */
function joinedText(element: React.ReactElement): string {
  return printed(element)
    .map((p) => p.text)
    .join("");
}

/** What the card draws in the 96px hero slot — the live probability. */
function heroNumber(element: React.ReactElement): string[] {
  return printed(element)
    .filter((p) => p.fontSize === 96)
    .map((p) => p.text);
}

/** The 40px line under the number — the leader's name. */
function leaderLine(element: React.ReactElement): string[] {
  return printed(element)
    .filter((p) => p.fontSize === 40)
    .map((p) => p.text);
}

/**
 * The width of the probability bar as a whole percent, or `null` when the card
 * draws no bar.
 *
 * The bar is the one place a price survives as a SHAPE after being removed as a
 * number, and no text assertion in this file would see it. Anchored on the
 * PARENT's `height: 24` + `borderRadius: 999`, then read off the child's `width`,
 * because the child's own `height: "100%"` is shared with nothing useful.
 */
function barWidth(element: React.ReactElement): number | null {
  let found: number | null = null;
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (!React.isValidElement(node)) return;
    const props = node.props as {
      style?: { height?: string | number; borderRadius?: number };
      children?: unknown;
    };
    if (props?.style?.height === 24 && props?.style?.borderRadius === 999) {
      const children = React.Children.toArray(props.children as React.ReactNode);
      const fill = children.find((c) => React.isValidElement(c)) as
        | React.ReactElement
        | undefined;
      const width = (fill?.props as { style?: { width?: string } } | undefined)?.style?.width;
      if (typeof width === "string" && width.endsWith("%")) {
        found = Number.parseFloat(width);
      }
      return;
    }
    walk(props?.children);
  };
  walk(element);
  return found;
}

/* ──────────────────────────────── the tests ─────────────────────────────── */

describe("#6127 — an unpriced market's link preview draws no number, no leader, no bar", () => {
  it("draws no dash, no crowned name and no bar for the measured specimen", async () => {
    const card = await renderCard(CBB_2027);
    const text = allText(card);

    // The three claims the row does not contain.
    expect(text).not.toContain("--");
    expect(text).not.toContain("Ohio State");
    expect(heroNumber(card)).toEqual([]);
    expect(leaderLine(card)).toEqual([]);
    expect(barWidth(card)).toBeNull();
    // And no percentage arrived by another route.
    expect(text).not.toMatch(/\d+%/);
  });

  it("still draws everything the row DOES contain", async () => {
    const card = await renderCard(CBB_2027);
    const text = allText(card);

    // Notice 34 is "leave the space empty", not "draw the quiet card": the market
    // name, its category and the outcome count are facts and the reader wants
    // them. Falling through to `UnfurlCard`'s empty shape would throw them away.
    expect(text).toContain("2027 Men's College Basketball National Champion");
    // #8290: the category arrives through `categoryKeyLabel`, so the key
    // `basketball` is drawn as its name. Case-sensitive so a raw key cannot pass.
    expect(text).toContain("Bain Luck Basketball");
    expect(joinedText(card)).toContain("2 outcomes tracked");
    expect(text).toContain("Bain Luck");
  });

  it("crowns nobody from array order — reversing the board changes nothing", async () => {
    // THE ASSERTION THIS SHIP EXISTS FOR. With every probability null the
    // comparator in `topOutcome` returns 0 for every pair, so before the fix this
    // card named whichever outcome the API happened to serialise first. A repair
    // that deleted only the dash would still print "Ohio State" here, and would
    // still print "BYU" for the same market on a day the API ordered it the other
    // way. Both renders must be identical.
    const forward = allText(await renderCard(CBB_2027));
    const reversed = allText(
      await renderCard({ ...CBB_2027, outcomes: [...CBB_2027.outcomes].reverse() }),
    );

    expect(forward).toEqual(reversed);
    expect(forward).not.toContain("Ohio State");
    expect(forward).not.toContain("BYU");
  });

  it("goes quiet on the 16-name board too, and names none of them", async () => {
    const card = await renderCard(THAI_LEAGUE);
    const text = allText(card);

    expect(text).toContain("Thai League 1 Champion");
    expect(joinedText(card)).toContain("16 outcomes tracked");
    expect(heroNumber(card)).toEqual([]);
    expect(barWidth(card)).toBeNull();
    THAI_LEAGUE.outcomes.forEach((o) => expect(text).not.toContain(o.name));
  });

  it("goes quiet when the market has no outcomes at all", async () => {
    const card = await renderCard(NO_OUTCOMES);

    expect(allText(card)).not.toContain("--");
    expect(heroNumber(card)).toEqual([]);
    expect(barWidth(card)).toBeNull();
  });
});

describe("#6127 — the rows this ship must NOT touch", () => {
  it("leaves a priced open market exactly as it was", async () => {
    const card = await renderCard(HOUSTON_TEMP);
    const text = allText(card);

    expect(heroNumber(card)).toEqual(["41%"]);
    expect(leaderLine(card)).toEqual(["94-95°F"]);
    expect(barWidth(card)).toBe(41);
    expect(text).toContain("Highest temperature in Houston on September 15?");
    expect(joinedText(card)).toContain("11 outcomes tracked");
  });

  it("keeps the number when only the LEADER is priced", async () => {
    // The withholding is a property of the leader, because `topOutcome` sorts
    // unpriced rows to the bottom. Over-reaching to "any null on the board" would
    // silence every thinly-quoted market that is telling the truth.
    const card = await renderCard(LEADER_ONLY_PRICED);

    expect(heroNumber(card)).toEqual(["71%"]);
    expect(leaderLine(card)).toEqual(["Buriram"]);
    expect(barWidth(card)).toBe(71);
  });

  it("keeps a resolved market on the settled branch, winner and all", async () => {
    const card = await renderCard(RESOLVED_GRADED);
    const text = allText(card);

    expect(text).toContain("Ohio State");
    expect(text).toContain("WON");
    // Settled means settled (#883 L2-53): the winner is the number, and there is
    // no percentage and no bar. That was already true and this ship is not what
    // makes it true.
    expect(heroNumber(card)).toEqual([]);
    expect(barWidth(card)).toBeNull();
  });

  it("keeps an ungraded resolved market on the settled branch, not this one", async () => {
    // #6079's third shape. It has no prices AND no grade, so it satisfies this
    // ship's predicate too — and it must still take `isResolved`, because the
    // grey RESOLVED pill is the one thing the card still honestly knows.
    const text = allText(await renderCard(RESOLVED_UNGRADED));

    expect(text).toContain("RESOLVED");
    expect(text).not.toContain("WON");
    expect(text).not.toContain("--");
  });

  it("does not change the cache window — this withholds, it does not settle", async () => {
    // A price can arrive on the next poll, so an unpriced card must stay as
    // retractable as a priced one (#6049). If withholding froze the picture into
    // an unfurler's cache, the first quote on the market would be invisible until
    // a deploy.
    await renderCard(HOUSTON_TEMP);
    const priced = lastCacheControl();
    await renderCard(CBB_2027);
    const unpriced = lastCacheControl();

    expect(unpriced).toBe(priced);
    await renderCard(RESOLVED_GRADED);
    expect(lastCacheControl()).not.toBe(priced);
  });
});

describe("#6127 — the words and the picture ask ONE question", () => {
  /**
   * The equivalence, in both directions, over every specimen above.
   *
   * `layout.tsx` gates its board sentence on `leader && probability`, where
   * `probability` is this same call; the picture now withholds on
   * `futuresBoardPrice(leader) === null`. Stated as a table rather than a comment
   * so an edit to either surface reddens here.
   *
   * Unlike #6119's game card there is no deliberate gap to protect: the exact
   * zero is quiet on BOTH halves here, because a graded zero belongs to a
   * resolved market and neither surface prints a percentage on one.
   */
  const BOARDS: Array<{ label: string; body: Board; priced: boolean }> = [
    { label: "CBB_2027 (all null)", body: CBB_2027, priced: false },
    { label: "THAI_LEAGUE (all null, 16)", body: THAI_LEAGUE, priced: false },
    { label: "NO_OUTCOMES", body: NO_OUTCOMES, priced: false },
    { label: "ZERO_PRICED (exact 0)", body: ZERO_PRICED, priced: false },
    { label: "HOUSTON_TEMP (priced)", body: HOUSTON_TEMP, priced: true },
    { label: "LEADER_ONLY_PRICED", body: LEADER_ONLY_PRICED, priced: true },
  ];

  /** `layout.tsx`'s own condition, transcribed. */
  function wordsQuoteAPrice(body: Board): boolean {
    const outcomes = body.outcomes ?? [];
    const leader = [...outcomes].sort(
      (a, b) => (b.probability ?? -1) - (a.probability ?? -1),
    )[0];
    return Boolean(leader && futuresBoardPrice(leader));
  }

  it.each(BOARDS)("$label — both halves agree", async ({ body, priced }) => {
    expect(wordsQuoteAPrice(body)).toBe(priced);

    const card = await renderCard(body);
    expect(heroNumber(card).length > 0).toBe(priced);
    expect(barWidth(card) !== null).toBe(priced);
  });

  it("an exact zero is quiet on this route, deliberately unlike the game card", async () => {
    // #4963 ruled that a finished GAME's loser at 0% is a fact, so #6119 kept its
    // picture-side predicate narrower than its words. That collision cannot occur
    // here: a graded outcome lives on a resolved market, which prints no
    // percentage on either surface. So the futures halves agree about a zero, and
    // the two routes differ ON PURPOSE.
    expect(futuresBoardPrice({ name: "Ohio State", probability: 0 })).toBeNull();

    const card = await renderCard(ZERO_PRICED);
    expect(allText(card)).not.toContain("0%");
    expect(allText(card)).not.toContain("--");
    expect(barWidth(card)).toBeNull();
  });

  it("futuresBoardPrice returns the label, never a dash", async () => {
    expect(futuresBoardPrice({ name: "x", probability: 0.408 })).toBe("41%");
    expect(futuresBoardPrice({ name: "x", probability: null })).toBeNull();
    expect(futuresBoardPrice(null)).toBeNull();
    expect(futuresBoardPrice(undefined)).toBeNull();
  });
});
