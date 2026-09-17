/**
 * #6119 — A LINK PREVIEW STOPS INVENTING A COIN FLIP FOR A GAME NOBODY HAS
 * QUOTED.
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION 2026-09-14 09:10Z ═══
 *
 * `https://bainluck.com/events/15310840` — Frauen-Bundesliga, Bayern Munich vs
 * Bayer Leverkusen, kick-off `2026-09-14T16:00:00Z` — pasted anywhere that
 * unfurls, read at one instant:
 *
 *   og:title        "Bayern Munich vs Bayer Leverkusen Odds | Bain Luck"
 *   og:description  "Mon, Sep 14. Follow Bayern Munich vs Bayer Leverkusen with
 *                    probability-first odds on Bain Luck."
 *   og:image        "50%" ... "50%" in the hero slot, over a dead-even split bar
 *
 * The WORDS are careful. They are the non-numeric copy `buildEventShareCopy`
 * falls back to when it has no price, and they say nothing about anyone's
 * chances. The PICTURE, drawn from the same payload by a file two doors away,
 * asserts a coin flip in the largest type on the card.
 *
 * `GET /api/events/15310840` at that minute:
 *
 *   status                      scheduled
 *   current_odds                null
 *   opening_odds                null
 *   win_probability_sources     null
 *
 * There is no price, from any source, anywhere on the row. 50/50 is not a
 * rounding artefact or a stale capture — it is the literal `?? 0.5` pair at the
 * top of `opengraph-image.tsx`, rendered as a finding about the world.
 *
 * The second specimen is the same shape one state along: `/events/15312491`,
 * Saracens vs Leicester Tigers, `status='live'`, the same three nulls, the same
 * even bar, footer "Live now".
 *
 * ═══ WHY THIS IS NOT #5846 ═══
 *
 * #5846 found this exact `?? 0.5` pair drawing 50/50 with crests reading `AWA`
 * and `HOM` for a link to a game THAT DOES NOT EXIST, and closed it by narrowing
 * `lookup` so a missing event returns before the layout. Its comment then says,
 * in as many words, that the coalesce itself was left standing because on a real
 * row it is "the live card's existing, certed behaviour for a row with no price".
 *
 * Certed is not correct — it is deferred. This is the deferred case.
 *
 * ═══ REACH, AND WHY THE ISSUE'S OWN NUMBER IS NOT THE ONE USED HERE ═══
 *
 * A straight random sample (`ORDER BY md5(id::text)`) of 80 of the 2,329 rows
 * sitting `live` or `scheduled` at 09:30Z: **35 served no price at all — 44%**,
 * or roughly 1,020 previews currently drawing this card.
 *
 * 🔴 THAT IS A CORRECTED NUMBER AND THE CORRECTION IS THE LESSON. The first pass
 * read 49 of 80 — 61% — because it fetched the payloads in a tight loop, and
 * `/api/events/{id}` rate-limits at 60/minute. A throttled body is
 * `{"detail": "Rate limit exceeded: 60/minute"}`, which carries no `current_odds`
 * key, so every throttled row was scored as a row with no price. A census that
 * asks "is this field absent?" cannot tell an absent field from a response that
 * was never a row, and it always errs toward "absent". Re-measured at 1.05s
 * spacing with every response validated by `id` first: 80 of 80 resolved, 35
 * priceless.
 *
 * #6119 filed the reach as 1,097 off `win_probability_sources IS NULL`. That is a
 * proxy for the column the card draws from, and re-measured it is a GOOD proxy,
 * not the loose one the contaminated pass claimed: of 40 no-source rows 37 serve
 * no price and 3 do; of 40 with-source rows 39 are priced and 1 is not. Weighted,
 * ~45% — agreeing with the direct sample. The predicate still reads `current_odds`
 * because that is what the card draws from, but the proxy was never the thing
 * that was wrong; the fetch was.
 *
 * ═══ WHAT THE RULE IS, AND WHY IT WAS NOT WRITTEN HERE ═══
 *
 * It was already written. `buildEventShareCopy` has always asked
 * `formatProbability` for both sides and dropped to the non-numeric copy when
 * either came back null. #6119 lifts that WHOLE into `shareForecastPercents`, and
 * both halves of the preview now call it. This is the fourth consecutive ship in
 * this chain (#6085, #6105, #6113) whose fix is an adoption rather than a new
 * rule, and the reason is always the same one: the defect is never that a rule is
 * missing, it is that one of two surfaces never asked for it.
 *
 * ═══ AND WHERE THE ADOPTION STOPS ═══
 *
 * The picture's predicate is NARROWER than the words' rule, which is not what I
 * built first. The first cut was `shareForecastPercents(event) === null`, so the
 * two halves would agree on every row — and it reddened
 * `shareCardDuelPair4963.test.tsx`, correctly.
 *
 * `formatProbability` counts an exact 0 as "no number", inherited from #1495
 * where the argument was about a bare 0.5. #4963 then ruled the opposite for this
 * very card: *"a finished game's loser is 0%, and 0% is a fact, not a missing
 * value"* — the `--` it used to print there was the defect. The two surfaces have
 * disagreed about a zero ever since, and settling that is not this ship: it has
 * no measured members (0 of 87 `current_odds` objects across the throttled
 * samples), the
 * measured defect is the key being ABSENT, and flipping it would reverse a
 * shipped ruling on the authority of a fixture.
 *
 * So the zero keeps today's behaviour on both halves, and the gap is asserted in
 * BOTH directions below rather than described in a comment — every row the
 * picture calls priceless is also quiet in the words, and the rows in between are
 * exactly the zeroes. That is the trap this lane keeps re-earning: widening past
 * what you measured is a guess, and here the guess had a prior ruling under it.
 *
 * ═══ WHAT IS DELIBERATELY *NOT* DONE ═══
 *
 * Withholding only. A price can arrive on the very next poll, so `noPrice` may
 * make the card quiet and may never make it assert anything: it does not touch
 * the status word (an unquoted match is still genuinely upcoming, or genuinely
 * live), it does not crown anyone, and it does not freeze the card into an
 * unfurler's cache. The last four tests in this file are what hold that line.
 *
 * And it prints no `--`. Notice 34: leave the space empty rather than explain the
 * emptiness. The slot is dropped, not filled with a dash.
 */

import React from "react";
import {
  buildEventShareCopy,
  hasNoPriceForShare,
  shareForecastPercents,
} from "@/lib/eventShareMeta";

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

import OgImage from "@/app/events/[id]/opengraph-image";

/* ───────────────────────────── the specimens ───────────────────────────── */

/**
 * The production payload, field for field, trimmed to what these two surfaces
 * read — the real row and not a minimal invention, for the reason #6085's suite
 * gives: the finding is that a PLAUSIBLE card is drawn from an HONEST payload,
 * and a fixture built to the fix's shape cannot catch that.
 *
 * `commence_time` is an OFFSET and not the literal `2026-09-14T16:00:00Z` the row
 * carried. Four fixtures in the suites #6105 touched had already rotted from
 * future-dated into past-dated while still calling themselves `scheduled`, which
 * silently moves them into `hasNoReportedResult`'s branch and would make this
 * file pass for the wrong reason six hours from now (gotcha #44).
 *
 * Both brand colours really are near-identical reds; see the closing note.
 */
const BAYERN_LEVERKUSEN = {
  id: 15310840,
  home_team: "Bayer Leverkusen",
  away_team: "Bayern Munich",
  status: "scheduled",
  sport: "soccer_germany_bundesliga_women",
  sport_key: null,
  sport_name: "Frauen-Bundesliga",
  home_score: null,
  away_score: null,
  completed_at: null,
  commence_time: new Date(Date.now() + 6 * 60 * 60 * 1000).toISOString(),
  hero_probability_source: null,
  hero_settled_result: null,
  current_odds: null,
  opening_odds: null,
  live_probability_pinned: null,
  linescore: null,
  home_team_data: { primary_color: "#DA0308" },
  away_team_data: { primary_color: "#dc052d" },
};

/**
 * The second production specimen: the same three nulls, `status='live'`, already
 * under way. Present because the two rows exercise DIFFERENT status words, and
 * the ship must change neither of them.
 */
const SARACENS_LEICESTER = {
  ...BAYERN_LEVERKUSEN,
  id: 15312491,
  home_team: "Leicester Tigers",
  away_team: "Saracens",
  status: "live",
  sport: "rugbyleague_nrl",
  sport_name: "Rugby",
  commence_time: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
};

/**
 * ═══ THE CONTROL THAT CARRIES THE WHOLE SHIP ═══
 *
 * The same row, same status, same clock — with a real price on it.
 *
 * Without this, a mutant that withholds the forecast on EVERY scheduled row
 * passes every other assertion in this file, and that mutant is not hypothetical:
 * "scheduled games have no settled number, just draw the quiet card" is the
 * obvious over-reach. 45 of the 80 sampled rows are priced and must be untouched.
 */
/**
 * ⚠️ #6238 — EVERY PRICED FIXTURE BELOW CARRIES A TWO-WAY SPORT KEY.
 *
 * `BAYERN_LEVERKUSEN` is a soccer row, and since #6238 the share card withholds
 * the AWAY figure on a sport whose winner market prices a draw: the served away
 * value is `1 − home`, i.e. "the home team does not win" — away win OR draw —
 * and printing it under the away crest is the defect that ship closed.
 *
 * That is correct and it is not what this file is about. These fixtures exist to
 * prove the NO-PRICE rule does not over-reach onto a row that HAS a price, and
 * they assert the away half of the pair to do it. Left on the soccer key they
 * would assert #6238's behaviour instead and this file would stop testing its
 * own subject.
 *
 * The withholding arm keeps the soccer key untouched: a row with no price has no
 * away figure to withhold, so #6238 cannot reach it and the production specimen
 * stays verbatim.
 */
const PRICED_SPORT = { sport: "americanfootball_nfl", sport_name: "NFL" };

const PRICED = {
  ...BAYERN_LEVERKUSEN,
  ...PRICED_SPORT,
  current_odds: {
    captured_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    home_probability: 0.62,
    away_probability: 0.38,
    home_rendered_percent: 62,
    away_rendered_percent: 38,
  },
};

/**
 * `current_odds` present as an OBJECT, with one side missing — on a TWO-WAY
 * sport, where that is still an absent price and the whole slot goes.
 *
 * Not observed on production (0 of 87 priced objects), and pinned anyway: the
 * type permits it, the pair must be taken whole or not at all (#2279), and a
 * per-side coalesce here is exactly how `servedDuelPercents` came to exist.
 *
 * ⚠️ #6670 — this fixture carried the SOCCER key until #6238's producer half
 * landed, and it no longer may. The two rows now mean opposite things and the
 * sport key is the only thing that tells them apart, so they are two fixtures.
 */
const HALF_PRICED = {
  ...BAYERN_LEVERKUSEN,
  ...PRICED_SPORT,
  current_odds: { home_probability: 0.62, away_probability: null },
};

/**
 * ═══ #6670 — THE SAME SHAPE, ON A DRAW-PRICED SPORT, MEANING THE OPPOSITE ═══
 *
 * Home priced, away absent, soccer. Before #6238's producer half (`81c72f3e3`,
 * #6668) this shape could not occur: `routes/feed.py` derived away as `1 − home`
 * and always served it. That producer stops serving it on a sport whose winner
 * market prices a draw, because `1 − P(home)` there is *away win OR draw* and the
 * draw's mass was printing under the away crest.
 *
 * So on this row the absence is the server WITHHOLDING a figure it cannot
 * source, beside a home figure it can — not the absence of a price. It is now
 * the ORDINARY shape of a live soccer payload, where the fixture above is the
 * one never observed.
 */
const HALF_PRICED_DRAW_SPORT = {
  ...BAYERN_LEVERKUSEN,
  current_odds: { home_probability: 0.62, away_probability: null },
};

/**
 * ═══ THE ROW THIS SHIP DELIBERATELY DOES NOT TOUCH ═══
 *
 * A price of exactly 0 on one side.
 *
 * My first cut of `hasNoPriceForShare` was `shareForecastPercents(event) ===
 * null`, so the picture would withhold on exactly the rows the words go quiet
 * on. That reddened `shareCardDuelPair4963.test.tsx`, and it was right to:
 * #4963 ruled for this exact card that *"a finished game's loser is 0%, and 0%
 * is a fact, not a missing value"* — printing `--` there was the defect it
 * closed. `formatProbability`'s zero clause (from #1495, where it was about a
 * bare 0.5) says the opposite, so the two halves have disagreed about a zero
 * since #4963 landed.
 *
 * Not resolved here. It has no measured members (0 of 87 `current_odds` objects
 * across the throttled samples), the measured defect is the key being ABSENT, and flipping it
 * would reverse a shipped ruling on the strength of a fixture. The zero keeps
 * today's behaviour on both surfaces and the disagreement is pinned below rather
 * than quietly closed.
 */
const ZERO_PRICED = {
  ...BAYERN_LEVERKUSEN,
  ...PRICED_SPORT,
  current_odds: {
    home_probability: 1,
    away_probability: 0,
    home_rendered_percent: 100,
    away_rendered_percent: 0,
  },
};

/**
 * No current price, but an opening line on the row.
 *
 * Measured population TODAY is zero — `opening_odds` is withheld until the
 * pre-game consensus freezes (#3922) and is composed from the same sportsbook
 * snapshots that would have produced a current price, so the two go missing
 * together (0 of 1,097 no-source rows carry an opening). Pinned because it is the
 * one row where "withhold" must not mean "print nothing": #6105's machinery
 * already promotes the pre-match reading here, labelled, and this ship reuses
 * that rather than adding a fourth branch.
 */
const NO_CURRENT_BUT_OPENING = {
  ...BAYERN_LEVERKUSEN,
  ...PRICED_SPORT,
  status: "live",
  commence_time: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
  opening_odds: { home_probability: 0.62, away_probability: 0.38, favorite: "home" as const },
};

/**
 * No price AND finished, with a trusted score. `isFinal` must keep winning: a
 * result outranks an absence, and the settled card is a different card.
 */
const NO_PRICE_AND_FINAL = {
  ...BAYERN_LEVERKUSEN,
  status: "completed",
  hero_probability_source: "settled",
  hero_settled_result: "home",
  home_score: 3,
  away_score: 1,
  commence_time: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
  completed_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
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

  await OgImage({ params: { id: "15310840" } });

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
 * The bar is the one place a forecast survives as a SHAPE after being removed as
 * a number, and no text assertion in this file would see it. Anchored on the
 * PARENT's `borderRadius: 999` + `height: 30`, not the child's `height: "100%"`,
 * which also matches the 1200×630 root canvas (#6085's walker matched it).
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

describe("#6119 — the picture stops inventing 50/50 for an unquoted game", () => {
  it("REPRODUCES THE PRODUCTION CARD when the fix is removed, and replaces it", async () => {
    const card = await renderCard(BAYERN_LEVERKUSEN);
    const text = allText(card);

    // The exact pair production drew, in the exact slot it drew it in.
    expect(heroSlot(card)).not.toEqual(["50%", "50%"]);
    expect(text).not.toContain("50%");

    // What it draws instead: NOTHING in the hero slot. Not a dash (notice 34),
    // not a zero, not the word "unavailable" — the slot is simply not rendered.
    expect(heroSlot(card)).toEqual([]);
    expect(text).not.toContain("--");

    // The card is quiet, not blank: the reader still gets the matchup, the
    // league and the honest status. This is the assertion that stops a "fix"
    // which withholds by drawing the dead-link card instead.
    expect(text).toContain("Bayern Munich");
    expect(text).toContain("Bayer Leverkusen");
    expect(text).toContain("Frauen-Bundesliga");
  });

  it("withholds the forecast as a SHAPE too — the bar goes with the number", async () => {
    // A 50/50 bar under no numbers is the coin flip surviving as geometry, which
    // is the identical failure #6085 and #6105 each had to close separately.
    expect(barAwayWidth(await renderCard(BAYERN_LEVERKUSEN))).toBeNull();
    expect(barAwayWidth(await renderCard(SARACENS_LEICESTER))).toBeNull();
  });

  it("leaves a PRICED row of the same shape completely alone", async () => {
    const card = await renderCard(PRICED);

    expect(heroSlot(card)).toEqual(["38%", "62%"]);
    // The value and not merely `not.toBeNull()`: a mutant that keeps the bar but
    // draws it from the withheld pair would pass the weaker assertion.
    expect(barAwayWidth(card)).toBe(38);
    expect(allText(card)).toContain("Upcoming");
  });

  it("withholds when the pair is HALF served — no number is no number", async () => {
    // One side present and the other absent is still "we do not have a price",
    // and taking the pair whole is #2279's rule on the surface that never
    // adopted it. Note this row would otherwise draw 62% beside a coalesced 50%.
    const half = await renderCard(HALF_PRICED);
    expect(heroSlot(half)).toEqual([]);
    expect(barAwayWidth(half)).toBeNull();
    expect(allText(half)).not.toContain("62%");
    expect(allText(half)).not.toContain("50%");
  });

  it("#6670 — KEEPS the honest home number when the away leg is WITHHELD, not missing", async () => {
    // The same object as `HALF_PRICED` one test up, on a draw-priced sport. The
    // test above and this one are the pair: identical `current_odds`, opposite
    // answers, and the sport key is the only thing between them.
    //
    // What the reader gets: the current home figure, no away numeral, and a bar
    // whose remainder is visibly unallocated rather than handed to either side
    // (#6238's render half, already shipped — this row simply reaches it now
    // instead of being routed to the withheld path a rung above).
    const card = await renderCard(HALF_PRICED_DRAW_SPORT);

    expect(heroSlot(card)).toEqual(["62%"]);
    // The `?? 0.5` coalesce is one line above the render and is exactly what
    // this card used to draw for an unpriced side. It must not reach the page
    // through the new branch, as a numeral OR as a width.
    expect(allText(card)).not.toContain("50%");
    expect(allText(card)).not.toContain("38%");
    // `barAwayWidth` reads the track's SOLE CHILD, and on the withheld branch
    // that child is the HOME share drawn at its own width against a neutral
    // track (`drawPricedCardFamily6238` pins the colours). So 62 and not null:
    // the bar is the numeral above it at 1200px wide, and it must agree with it
    // — a `?? 0.5` reaching the geometry would read 50 here while the numeral
    // still read 62.
    expect(barAwayWidth(card)).toBe(62);

    // And NOT the pre-match treatment: the number on the card is the current
    // one, so the card must not label it as the sportsbook median it is not.
    // This is the whole difference the ship makes — before it, this row fell to
    // `prematch` and printed the opening line, or nothing where the row has no
    // opening line at all.
    expect(allText(card)).not.toContain("Pre-match");
    expect(allText(card)).toContain("Bayer Leverkusen");
  });

  it("LEAVES AN EXACT ZERO ALONE — #4963's ruling is not reversed here", async () => {
    // The guard on this ship's own over-reach. `hasNoPriceForShare` is narrower
    // than the words' rule ON PURPOSE (see its docstring): a real 0% loser is a
    // fact #4963 fought to print, and withholding it would re-introduce the
    // blank that ship removed. Unmeasured in the wild either way, so today's
    // behaviour stands and this test is what keeps it standing.
    const zero = await renderCard(ZERO_PRICED);
    expect(heroSlot(zero)).toEqual(["0%", "100%"]);
    expect(barAwayWidth(zero)).toBe(3); // clamped to [3, 97] so a sliver shows
  });

  it("promotes the OPENING line when the row has one, labelled, rather than printing nothing", async () => {
    const card = await renderCard(NO_CURRENT_BUT_OPENING);

    // #6105's machinery, reused. The pre-match pair in the hero slot, away first.
    expect(heroSlot(card)).toEqual(["38%", "62%"]);
    expect(barAwayWidth(card)).toBe(38);
    // Labelled as the sportsbook median it is — an unlabelled 62% in that slot
    // reads as a live call. `sportsbooks`, never a venue name (notice 33).
    expect(allText(card)).toContain("Pre-match");
    expect(allText(card)).not.toContain("bookmaker");
  });
});

/* ═════════════════ WHAT THE ABSENCE MAY *NOT* DO ═════════════════ */

describe("#6119 — no price withholds, and never asserts", () => {
  it("does not touch the status word: an unquoted match is still upcoming, or still live", async () => {
    // The whole defect was the picture making a claim the row does not support.
    // "No price" is not evidence about the clock, and a fix that reached
    // `eventStatus` would be the same over-reach pointing the other way — it
    // would print "No result reported" over ~1,020 games, most of which have not
    // kicked off. #6113 moved that branch to the TOP of `eventStatus` and the
    // order is load-bearing, so this is the assertion that keeps `noPrice` out.
    expect(allText(await renderCard(BAYERN_LEVERKUSEN))).toContain("Upcoming");

    const live = allText(await renderCard(SARACENS_LEICESTER));
    expect(live).toContain("Live now");
    expect(live).not.toContain("No result reported");
  });

  it("does not freeze the card into an unfurler's cache", async () => {
    // A price can arrive on the very next poll. Caching this as settled would
    // pin the quiet card over a game that has since been quoted — and the
    // unfurler, not us, decides when to look again (#6049).
    await renderCard(BAYERN_LEVERKUSEN);
    const quiet = lastCacheControl();
    await renderCard(PRICED);
    expect(quiet).toBe(lastCacheControl());

    await renderCard(NO_PRICE_AND_FINAL);
    expect(lastCacheControl()).not.toBe(quiet);
  });

  it("does not outrank a finished game: the settled card still wins", async () => {
    const card = await renderCard(NO_PRICE_AND_FINAL);

    // The SCORE in the hero slot, away first — the settled treatment, untouched.
    expect(heroSlot(card)).toEqual(["1", "3"]);
    expect(allText(card)).toContain("Final");
  });
});

/* ═══════════════════════════════ THE WORDS ════════════════════════════════ */

describe("#6119 — the two halves of the preview answer as one", () => {
  it("keeps the copy byte-identical on both sides of the refactor", async () => {
    // `shareForecastPercents` replaced two `formatProbability` locals and the
    // `&&` between them. That is a refactor on the text half and it must be
    // invisible: these are the strings production served, verbatim.
    const quiet = buildEventShareCopy(BAYERN_LEVERKUSEN);
    expect(quiet.title).toBe("Bayern Munich vs Bayer Leverkusen Odds");
    // The SUFFIX and not the whole string. The description is
    // `${statusLabel(event)}. ${copy}`, and `statusLabel` formats this row's own
    // kick-off date — production read "Mon, Sep 14. Follow ...". This fixture
    // dates itself off the clock (gotcha #44), so pinning the literal prefix
    // would pin today. My first draft of this assertion did pin it and failed;
    // the copy was right and the assertion was wrong.
    expect(quiet.description).toContain(
      "Follow Bayern Munich vs Bayer Leverkusen with probability-first odds on Bain Luck.",
    );
    // The prefix is still asserted, as a SHAPE: a date sentence, then the copy.
    expect(quiet.description).toMatch(
      /^[A-Z][a-z]{2}, [A-Z][a-z]{2} \d{1,2}\. Follow Bayern Munich vs Bayer Leverkusen/,
    );
    expect(quiet.settled).toBe(false);

    const priced = buildEventShareCopy(PRICED);
    expect(priced.title).toBe("Bayern Munich vs Bayer Leverkusen: Bayern Munich 38%, Bayer Leverkusen 62%");
    expect(priced.description).toContain(
      "Bain Luck gives Bayern Munich a 38% win probability and Bayer Leverkusen a 62% win probability.",
    );
  });

  it("agrees with the picture on every row where we simply have no number", async () => {
    // THE SHIP, stated once as a property rather than case by case: the sentence
    // and the image make the same call about whether we hold a number. This is
    // the assertion that would have caught the original defect without anyone
    // having to know which of the two halves was the wrong one.
    // #6670 — `HALF_PRICED_DRAW_SPORT` is deliberately NOT in this list. It is
    // the one row where the two halves no longer answer alike, by decision
    // rather than by accident, and it has its own assertion below saying which
    // direction the gap runs in. Adding it here would read as a regression of
    // this property; leaving it out silently would hide that it exists.
    for (const row of [BAYERN_LEVERKUSEN, SARACENS_LEICESTER, PRICED, HALF_PRICED]) {
      const wordsAreQuiet = buildEventShareCopy(row).title.endsWith(" Odds");
      const pictureIsQuiet = heroSlot(await renderCard(row)).length === 0;
      expect({ id: row.id, status: row.status, wordsAreQuiet, pictureIsQuiet }).toEqual({
        id: row.id,
        status: row.status,
        wordsAreQuiet,
        pictureIsQuiet: wordsAreQuiet,
      });
    }
  });

  it("names the ONE row where they still disagree, and both directions of the gap", async () => {
    // Written as an assertion and not a comment so the gap cannot be closed by
    // accident in either direction (my memory's rule: a guard that asserts every
    // A is a B leaves the reverse population live — so count it).
    //
    // FORWARD: every row the picture calls priceless, the words also call
    // priceless. If this ever fails, the picture has started withholding a
    // number the sentence beside it prints — the original defect, mirrored.
    const ALL = [
      BAYERN_LEVERKUSEN,
      SARACENS_LEICESTER,
      PRICED,
      HALF_PRICED,
      HALF_PRICED_DRAW_SPORT,
      ZERO_PRICED,
    ];
    for (const row of ALL) {
      if (hasNoPriceForShare(row)) expect(shareForecastPercents(row)).toBeNull();
    }

    // REVERSE: the rows in between — quiet in the words, numeric in the picture
    // — and there are now TWO classes of them, which is the #6670 amendment
    // stated as a count rather than as prose.
    //
    //   · the exact zero, #4963's standing disagreement, unchanged;
    //   · the draw-priced row whose away leg the server withholds, where the
    //     picture prints the honest home figure and the title has no one-sided
    //     spelling to print (#6670).
    //
    // Both are the picture speaking while the words stay quiet. The FORWARD
    // direction above is what must never grow a member: a picture withholding a
    // number the sentence beside it prints is the original defect, mirrored.
    const between = ALL.filter(
      (row) => shareForecastPercents(row) === null && !hasNoPriceForShare(row),
    ).map((row) => row.current_odds);
    expect(between).toEqual([HALF_PRICED_DRAW_SPORT.current_odds, ZERO_PRICED.current_odds]);
  });
});

/* ══════════════════════════════ THE PREDICATE ═════════════════════════════ */

describe("#6119 — shareForecastPercents, the one owner", () => {
  it("returns the pair WHOLE or null, never one side", () => {
    expect(shareForecastPercents(PRICED)).toEqual({ away: "38%", home: "62%" });
    expect(shareForecastPercents(BAYERN_LEVERKUSEN)).toBeNull();
    expect(shareForecastPercents(HALF_PRICED)).toBeNull();
    expect(shareForecastPercents({ current_odds: undefined })).toBeNull();
    expect(
      shareForecastPercents({ current_odds: { home_probability: Number.NaN, away_probability: 0.5 } }),
    ).toBeNull();
    // The words' inherited zero clause, pinned as the WORDS' behaviour so that
    // moving it is a deliberate act with a failing test attached.
    expect(shareForecastPercents(ZERO_PRICED)).toBeNull();
  });

  it("hasNoPriceForShare asks the narrower question, and says so", () => {
    expect(hasNoPriceForShare(BAYERN_LEVERKUSEN)).toBe(true);
    expect(hasNoPriceForShare(SARACENS_LEICESTER)).toBe(true);
    expect(hasNoPriceForShare(HALF_PRICED)).toBe(true);
    expect(hasNoPriceForShare({ current_odds: { home_probability: 0.6, away_probability: Number.NaN } })).toBe(true);

    expect(hasNoPriceForShare(PRICED)).toBe(false);
    // The divergence, at the unit level: a real zero IS a price here.
    expect(hasNoPriceForShare(ZERO_PRICED)).toBe(false);
  });

  it("#6670 — a WITHHELD away is not a missing price, and only on the sports that withhold", () => {
    // The same object shape, twice, differing only in the sport key. If these
    // two ever answer the same, the predicate has stopped reading the sport and
    // one of the two rows is wrong: the soccer card loses the honest home
    // number, or the NFL card starts drawing a 50% it was handed by a `?? 0.5`.
    expect(HALF_PRICED.current_odds).toEqual(HALF_PRICED_DRAW_SPORT.current_odds);
    expect(hasNoPriceForShare(HALF_PRICED_DRAW_SPORT)).toBe(false);
    expect(hasNoPriceForShare(HALF_PRICED)).toBe(true);

    // The home half is still the anchor. A withheld away beside NO home number
    // is not a withholding at all — there is nothing left to draw.
    expect(
      hasNoPriceForShare({ ...HALF_PRICED_DRAW_SPORT, current_odds: { home_probability: null, away_probability: null } }),
    ).toBe(true);

    // A NaN is corruption and not a declination, on either kind of sport.
    expect(
      hasNoPriceForShare({ ...HALF_PRICED_DRAW_SPORT, current_odds: { home_probability: 0.62, away_probability: Number.NaN } }),
    ).toBe(true);

    // And the sport key is read by the card's own precedence, so a row carrying
    // only `sport_key` is classified the same as one carrying only `sport`.
    const { sport: _dropped, ...noSport } = HALF_PRICED_DRAW_SPORT;
    expect(hasNoPriceForShare({ ...noSport, sport_key: "soccer_germany_bundesliga" })).toBe(false);
    expect(hasNoPriceForShare(noSport)).toBe(true);
  });

  it("reads current_odds and NOT win_probability_sources", () => {
    // The issue's reach came off `win_probability_sources`, which is a proxy and
    // errs slightly both ways (3 of 40 / 1 of 40 on production). A row with
    // no sources but a real served price must keep its number.
    expect(hasNoPriceForShare(PRICED)).toBe(false);
  });
});
