/**
 * #4283 — A QUIET ROW SHOWS A MARK, NOT A SENTENCE ABOUT OUR PIPELINE.
 *
 * ═══ THE STRING ═══
 *
 * `slateRowFreshnessLabel` built `Last number 20 hours ago` for a quiet match
 * row and `rowFreshnessLabel` mirrored it on the contender boards (UX-P135, on
 * purpose — one idea, one vocabulary). Standing notice 34 quotes that shape
 * verbatim in its list of what may never appear in a page body: *"method notes
 * ('last number is when we last saw…')"*. #4278 took it off the props cards by
 * switching them to the `dot` variant; these were the two surfaces left.
 *
 * ═══ WHAT MAY NOT MOVE, AND WHY IT IS HALF THIS FILE ═══
 *
 * The two functions return three different things and only one is banned:
 *
 *     "No probability yet"        an ANSWER to the reader's question   KEEP
 *     "no reading yet"            the same, when there is no age       KEEP
 *     "Last number 20 hours ago"  a method note about our pipeline     MARK
 *     "Alcaraz + Sinner 20h ago"  the same, plus which leg is old      MARK
 *
 * Burying an answer in a tooltip is not a fix for notice 34, it is ruling 027's
 * honest-empty failure wearing the fix's clothes. So every "the sentence is
 * gone" case below is paired with a case asserting the ANSWER still renders as
 * text — and the classification is `kind`, decided at the branch that built the
 * sentence, never a phrase match at the call site.
 *
 * 🔴 That "at the branch" is not a stylistic preference; it is a bug this file
 * caught. The first cut inferred `kind` from whether `age_hours` was set, and
 * the unpriced branch returns "No probability yet" for a fixture four days out
 * that carries one anyway — so the ANSWER was classified as a method note and
 * would have been buried in a tooltip. Which question a return answers is
 * knowable only where it is built.
 *
 * ═══ 🔴 THE PREFIX, ASSERTED AND NOT ASSUMED ═══
 *
 * #4278 came within an inch of shipping the CERT-411 round-2 falsehood: moving
 * the props chip to `dot` silently dropped the `Name: ` prefix, so a two-leg
 * card whose other half refreshed an hour ago would have claimed the whole card
 * was 35 days old. The issue asked for this to be asserted rather than assumed,
 * because the visible mark has no room for a name — the tooltip and the
 * `sr-only` copy are the ONLY places that fact can live.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import { matchListFromSlate } from "@/lib/matchList";
import { FreshnessDot, compactAge } from "@/components/FreshnessDot";
import { rowFreshness, type TournamentBoardData, type TournamentRow } from "@/lib/tournament";
import { slateRowFreshness, type SlateMatch } from "@/lib/slate";

/** Text a reader actually sees — attributes and sr-only copy stripped out. */
function bodyText(html: string): string {
  return html
    .replace(/<span class="sr-only">.*?<\/span>/g, " ")
    .replace(/<[^>]*>/g, " ");
}

function row(overrides: Partial<TournamentRow> = {}): TournamentRow {
  return {
    entity_key: "player-a",
    display_name: "Player A",
    seed: null,
    country: null,
    rank: 1,
    state: "live",
    probability: 0.52,
    probability_is_live: true,
    observed_at: "2026-08-25T11:00:00+00:00",
    age_hours: 1,
    price_state: "live",
    freshest_observed_at: "2026-08-25T11:00:00+00:00",
    freshest_age_hours: 1,
    stale_sources: [],
    mixed_freshness: false,
    source_count: 2,
    sources: [],
    trend: [],
    trend_delta: null,
    image: null,
    blend_rule: null,
    divergent: false,
    ...overrides,
  };
}

function board(rows: TournamentRow[]): TournamentBoardData {
  return {
    draw: "mens-singles",
    label: "Men's Singles",
    rows,
    contenders: rows.length,
    unpriced: 0,
    rows_not_live: rows.length,
    mixed_freshness_rows: 0,
    price_state: "dark",
    newest_observed_at: "2026-08-05T11:00:00+00:00",
    age_hours: 20 * 24,
  } as TournamentBoardData;
}

const QUIET_ROW = row({
  probability_is_live: false,
  price_state: "dark",
  age_hours: 20 * 24,
  observed_at: "2026-08-05T11:00:00+00:00",
  stale_sources: ["polymarket"],
  mixed_freshness: true,
});

function side(entity: string, name: string, prob: number) {
  return {
    entity_key: entity,
    display_name: name,
    seed: null,
    country: null,
    role: "player",
    probability: prob,
    opening_probability: prob,
    move: null,
    raw_probability: prob,
    raw_opening_probability: prob,
    age_hours: 20,
    price_state: "dark",
    observed_at: "2026-08-25T11:00:00+00:00",
  };
}

function slateMatch(overrides: Partial<SlateMatch> = {}): SlateMatch {
  return {
    matchup_key: "a-vs-b",
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "Round of 16",
    scheduled_date: "2026-09-09T17:00:00+00:00",
    probability_is_live: false,
    priced: true,
    coherent: true,
    price_state: "dark",
    observed_at: "2026-08-25T11:00:00+00:00",
    age_hours: 20,
    freshest_observed_at: "2026-08-25T11:00:00+00:00",
    freshest_age_hours: 20,
    mixed_freshness: false,
    stale_sides: [],
    raw_sum: 1,
    opening_raw_sum: 1,
    favourite: "alcaraz",
    has_moved: false,
    source_count: 2,
    sides: [side("alcaraz", "Alcaraz", 0.62), side("sinner", "Sinner", 0.38)],
    ...(overrides as object),
  } as SlateMatch;
}

// ---------------------------------------------------------------------------
// The classification — one rule, both surfaces
// ---------------------------------------------------------------------------

describe("an age is a method note; an answer is an answer", () => {
  it("classifies the slate's three returns", () => {
    expect(slateRowFreshness(slateMatch())).toEqual({
      label: "Last number 20 hours ago",
      kind: "age",
      ageHours: 20,
    });
    expect(slateRowFreshness(slateMatch({ priced: false }))).toEqual({
      label: "No probability yet",
      kind: "answer",
      ageHours: null,
    });
    expect(slateRowFreshness(slateMatch({ age_hours: null }))?.kind).toBe("answer");
    // A live row says nothing at all — an admission every row makes is not one.
    expect(slateRowFreshness(slateMatch({ probability_is_live: true }))).toBeNull();
  });

  it("classifies the board's returns the same way", () => {
    expect(rowFreshness(QUIET_ROW)).toEqual({
      label: "one reading 20 days ago",
      kind: "age",
      ageHours: 20 * 24,
    });
    expect(rowFreshness(row({ probability_is_live: false, age_hours: null }))?.kind).toBe(
      "answer"
    );
    expect(rowFreshness(row())).toBeNull();
  });

  it("keys on the AGE, not on the words, so a rewording cannot drift it", () => {
    // Same phrase-free contract both ways round: an age present makes it a mark
    // whatever the sentence says, and an age absent keeps it in the body.
    expect(slateRowFreshness(slateMatch({ age_hours: 1 }))?.kind).toBe("age");
    expect(slateRowFreshness(slateMatch({ age_hours: 0.5 }))?.kind).toBe("age");
    expect(slateRowFreshness(slateMatch({ age_hours: NaN }))?.kind).toBe("answer");
  });

  it("keeps the string API the 25 existing assertions read", () => {
    // `slateRowFreshnessLabel` is a thin wrapper over `slateRowFreshness`, so
    // the two can never disagree about what the row says. If this ever needs
    // deleting, the sentence has moved and every caller needs revisiting.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { slateRowFreshnessLabel } = require("@/lib/slate");
    expect(slateRowFreshnessLabel(slateMatch())).toBe("Last number 20 hours ago");
    expect(slateRowFreshnessLabel(slateMatch({ priced: false }))).toBe("No probability yet");
  });
});

// ---------------------------------------------------------------------------
// The mark
// ---------------------------------------------------------------------------

describe("the mark carries the WHOLE admission", () => {
  it("puts the full label, prefix included, in the tooltip and the sr-only copy", () => {
    const html = renderToStaticMarkup(
      <FreshnessDot label="Alcaraz + Sinner 20 hours ago" ageHours={20} testId="match-age" />
    );
    // SURVIVAL — a component returning null passes every absence below it.
    expect(html).toContain('data-testid="match-age"');
    expect(html).toContain('data-variant="dot"');

    // 🔴 CERT-411 round 2: the name survives into BOTH accessible copies.
    expect(html).toContain('title="Alcaraz + Sinner 20 hours ago"');
    expect(html).toContain(
      '<span class="sr-only">Alcaraz + Sinner 20 hours ago. </span>'
    );

    // And what the eye gets is the bounded mark, not the sentence.
    expect(bodyText(html)).toContain("20h");
    expect(bodyText(html)).not.toContain("hours ago");
    expect(bodyText(html)).not.toContain("Alcaraz");
  });

  it("compacts an age the way the props chip already did", () => {
    expect(compactAge(20)).toBe("20h");
    expect(compactAge(47.9)).toBe("47h");
    expect(compactAge(48)).toBe("2d");
    expect(compactAge(20 * 24)).toBe("20d");
    expect(compactAge(null)).toBe("—");
  });
});

// ---------------------------------------------------------------------------
// The board, rendered
// ---------------------------------------------------------------------------

describe("the contender board", () => {
  it("draws a mark for a quiet row and no sentence in the body", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={board([QUIET_ROW])} />);
    // SURVIVAL — the row rendered and still admits its state.
    expect(html).toContain('data-testid="board-row"');
    expect(html).toContain('data-testid="row-age"');
    expect(html).toContain('title="one reading 20 days ago"');

    // The banned shape is off the ROW, prefix and all. Scoped to the row and
    // not the whole render on purpose: the board's own "Updates paused / last
    // confirmed reading 20 days ago" BANNER is a different thing — UX-P146's
    // deliberate admission that the whole board is not live, which notice 34
    // does not touch and which this ship must not quietly delete.
    const rowHtml = html.slice(html.indexOf('data-testid="board-row"'));
    expect(bodyText(rowHtml)).not.toMatch(/\d+\s+(hour|day|min)s?\s+ago/);
    expect(bodyText(rowHtml)).not.toContain("one reading");
    expect(bodyText(rowHtml)).toContain("20d");
  });

  it("still says nothing at all on a live row", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={board([row()])} />);
    expect(html).toContain('data-testid="board-row"'); // survival
    expect(html).not.toContain('data-testid="row-age"');
  });

  it("keeps an ANSWER in the body rather than burying it in a tooltip", () => {
    // The honest-empty half of ruling 027. This is the case that a naive
    // "move every freshness string to a tooltip" fix would silently break.
    const noReading = row({
      probability_is_live: false,
      price_state: "dark",
      age_hours: null,
    });
    const html = renderToStaticMarkup(<TournamentBoard board={board([noReading])} />);
    expect(html).toContain('data-testid="row-age"'); // survival
    // The board's own no-age word is "never" (`stalenessLabel`), where the
    // slate says "no reading yet" — a real vocabulary split between the two
    // halves that UX-P135 would want closed, but NOT this ship's to close.
    // What matters here is that it stayed in the body rather than a tooltip.
    const rowHtml = html.slice(html.indexOf('data-testid="board-row"'));
    expect(bodyText(rowHtml)).toContain("never");
    expect(rowHtml).not.toContain('title="never"');
  });
});

// ---------------------------------------------------------------------------
// The match slate, rendered
//
// 🔴 THIS BLOCK EXISTS BECAUSE ITS ABSENCE PASSED A REVERT. With the board case
// above but no slate case, restoring `TournamentMatches` to print the sentence
// unconditionally left the whole file GREEN — the two surfaces are mirrored in
// the source and were not mirrored in the guard, so half the ship was unheld.
// #4278 hit the same class from the other side: a specimen that never reaches
// the branch is not a test.
// ---------------------------------------------------------------------------

describe("the match slate", () => {
  const renderSlate = (m: SlateMatch) =>
    renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([m])} notice={null} />
    );

  it("draws a mark for a quiet match and no sentence in the body", () => {
    const html = renderSlate(slateMatch());
    // SURVIVAL — the row rendered, with its players, and still admits its age.
    expect(html).toContain("Alcaraz");
    expect(html).toContain('data-testid="match-age"');
    expect(html).toContain('title="Last number 20 hours ago"');

    expect(bodyText(html)).not.toContain("Last number");
    expect(bodyText(html)).not.toMatch(/\d+\s+(hour|day|min)s?\s+ago/);
    expect(bodyText(html)).toContain("20h");
  });

  it("keeps the leg names in the tooltip when only one side is old", () => {
    // CERT-411 round 2 on the slate's own mixed branch, which builds its label
    // from the stale sides rather than from "Last number".
    const html = renderSlate(
      slateMatch({ mixed_freshness: true, stale_sides: ["alcaraz"] })
    );
    expect(html).toContain('data-testid="match-age"'); // survival
    expect(html).toContain('title="Alcaraz 20 hours ago"');
    expect(bodyText(html)).not.toContain("Alcaraz 20 hours ago");
  });

  it("keeps 'No probability yet' in the body, where the reader can read it", () => {
    const html = renderSlate(slateMatch({ priced: false }));
    expect(html).toContain('data-testid="match-age"'); // survival
    expect(bodyText(html)).toContain("No probability yet");
    // An answer is not a tooltip. This is the assertion that fails if someone
    // "simplifies" the split away by marking every freshness string.
    expect(html).not.toContain('title="No probability yet"');
  });
});
