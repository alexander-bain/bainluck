/**
 * ux/1349 / #4646 — THE "BIGGER PICTURE" RAIL STOPS RE-ANSWERING THE HERO'S QUESTION.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/events/15314525` (Zhao–Ma, WTA qualifying) at 390px, 2026-09-18 11:10 PM PDT —
 * `artifacts/ux-1349/BEFORE-4646-15314525-390.png`:
 *
 *     Zhao  30%  –  70%  Ma            ← the hero, "Aggregate"
 *     …
 *     Bigger Picture · Season context
 *       GAME PROPS
 *         OTHER (1)   [Carol Zhao  30%]
 *       GAME PROPS
 *         OTHER (1)   [Yexin Ma    74%]
 *       2 related futures from multiple sources
 *
 * Ma is 70% and 74% on one screen, 30 + 74 = 104%, and the "season context" the
 * subtitle promises is this match's own market, published as two raw legs with the
 * overround left in. Alex's standing ruling is one number per question.
 *
 * ═══ WHY THE ASSERTIONS ARE ON RENDERED MARKUP, OVER A PRODUCTION CAPTURE ═══
 *
 * `isRelevantGameProp` is not exported, and the thing that matters is not whether a
 * predicate returns false — it is WHICH CARDS A READER IS LEFT WITH. Two fixtures are
 * frozen production payloads, taken minutes after the frame above:
 *
 *   `relatedFutures15314525.20260919-4646.json`  2 rows, BOTH the event's own moneyline
 *   `relatedFutures15314529.20260919-4646.json` 12 rows, 2 of them the own moneyline
 *
 * The second one is why this file is not a one-line test. A capture whose whole payload
 * is the defect can only ever assert an ABSENCE, and an absence is passed perfectly by a
 * component that renders nothing at all — so the twelve-row page is the both-directions
 * arm (gotcha #43): the same diff must delete exactly two cards there and leave the rest
 * of the rail standing.
 *
 * ═══ RED ON THE PARENT ═══
 *
 * Banked in `artifacts/ux-1349/PARENT-render-dump.txt`, same fixtures, parent build:
 *
 *   15314525  4,419 chars of markup — `Other (1) Carol Zhao 27%`, `Other (1) Yexin Ma 74%`
 *   15314529  `Other (1) Viktoria Morvayova 77%` beside the four markets that survive
 *
 * Sections B and C below are red there by heading, by card and by count.
 *
 * ═══ THE PRICES IN A FIXTURE ARE NOT THE PRICES IN THE FRAME ═══
 *
 * The capture reads 27% where the screenshot reads 30%: a scheduled match re-prices
 * between two reads minutes apart. Nothing here asserts a price for that reason — the
 * claims are about WHICH MARKET draws, which is a property of the payload's shape.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ownQuestionOnly from "../fixtures/relatedFutures15314525.20260919-4646.json";
import ownQuestionPlusRail from "../fixtures/relatedFutures15314529.20260919-4646.json";

type Payload = {
  event_id: number;
  home_team: string;
  away_team: string;
  home_team_futures: { market_name: string; display_category: string }[];
  away_team_futures: { market_name: string; display_category: string }[];
};

const ONLY = ownQuestionOnly as unknown as Payload;
const PLUS = ownQuestionPlusRail as unknown as Payload;

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: swrPayload,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedFutures = require("@/components/RelatedFutures").default;

/**
 * Render the rail for one captured payload.
 *
 * `homeStandings` / `awayStandings` / `teamProgression` are omitted for #3775's reason:
 * each opens the section on its own and would mask what section B measures.
 */
function render(payload: Payload): string {
  swrPayload = payload;
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: payload.event_id,
      homeTeam: payload.home_team,
      awayTeam: payload.away_team,
    }),
  );
}

/** Tag-stripped text, so a heading is read the way a reader meets it. */
function text(html: string): string {
  return html.replace(/<[^>]*>/g, "\n").replace(/[ \t]+\n/g, "\n").replace(/\n+/g, "\n").trim();
}

/** How many times a group heading appears in the served markup. */
function headings(html: string, label: string): number {
  return (text(html).match(new RegExp(`^${label}$`, "gm")) ?? []).length;
}

/**
 * The rows in a capture that ARE the bare matchup, derived from the fixture rather than
 * transcribed — so this file cannot drift from the payload it ships with.
 */
function bareMatchupRows(p: Payload): string[] {
  const sides = [p.home_team, p.away_team].map((s) => s.toLowerCase());
  return [...p.home_team_futures, ...p.away_team_futures]
    .filter((r) => {
      const m = r.market_name.toLowerCase().match(/^(.+?)\s+vs\.?\s+(.+)$/);
      return !!m && sides.includes(m[1].trim()) && sides.includes(m[2].trim());
    })
    .map((r) => r.market_name);
}

describe("A · CONTROL — the captures reach the component and the rail speaks", () => {
  // Arm-independent: true before and after. Without it, a green section C could mean
  // "the duplicate went away" or "the component stopped rendering cards at all".
  it("the twelve-row capture draws its rail, with the markets that are not this match", () => {
    const html = render(PLUS);

    expect(html).toContain("Bigger Picture");
    expect(headings(html, "Match o/u 22.5")).toBe(1);
    expect(headings(html, "Total sets o/u 2.5")).toBe(1);
    expect(text(html)).toContain("Viktoria morvayova (-1.5) vs nika radisic (+1.5)");
  });

  it("each capture really does carry this event's own moneyline, twice", () => {
    // The specimen check. If a later payload refresh drops these rows, sections B and C
    // start passing for free and this arm says so out loud.
    expect(bareMatchupRows(ONLY)).toEqual(["Zhao vs Ma", "Zhao vs Ma"]);
    expect(bareMatchupRows(PLUS)).toEqual(["Radisic vs Morvayova", "Radisic vs Morvayova"]);
  });
});

describe("B · a rail that is NOTHING BUT the event's own question does not open", () => {
  it("renders no section at all — no header, no cards, no caption", () => {
    const html = render(ONLY);

    // Parent: 4,419 chars carrying both cards.
    expect(html).toBe("");
    expect(html).not.toContain("Bigger Picture");
    expect(html).not.toContain("Carol Zhao");
    expect(html).not.toContain("Yexin Ma");
    expect(html).not.toMatch(/related futures from multiple sources/);
  });
});

describe("C · a rail that holds the question AND other markets loses only the question", () => {
  const html = render(PLUS);

  it("the two moneyline legs are gone — the `Other` group they made is empty", () => {
    // Every other group in this capture is named by the text after its market's colon;
    // the bare matchup has no colon, so it is the one that lands in `Other`. Parent: 1.
    expect(headings(html, "Other")).toBe(0);
  });

  it("the qualified markets that MENTION the same two players are deliberately kept", () => {
    // `Set 1 Winner: Nika Radisic vs Viktoria Morvayova` and `Singapore Open,
    // Qualification: Nika Radisic vs Viktoria Morvayova` both survive, and the second is
    // genuinely the same question under a venue's prefix. Stripping a leading qualifier
    // would catch it — and would also catch `Set 1 Winner:`, which is a DIFFERENT
    // question. That case is ux/1170's backend arm on #4646, not this diff, and this
    // assertion pins the scope so nobody "completes" the fix by widening the predicate.
    expect(headings(html, "Nika radisic vs viktoria morvayova")).toBe(2);
  });

  it("the drop is scoped to `game_prop`, which is the filter's whole contract", () => {
    // The same two captured rows, re-bucketed. `isRelevantGameProp` returns early for
    // every other `display_category`, and this diff did not move that early return —
    // hoisting the new test above it would silently reach `games`, `series`, `award` and
    // the championship paths, whose own dedupe rules are not this ship. A mutant that
    // hoists it is caught here rather than in production.
    const asGames = {
      ...ONLY,
      home_team_futures: ONLY.home_team_futures.map((r) => ({ ...r, display_category: "other" })),
      away_team_futures: ONLY.away_team_futures.map((r) => ({ ...r, display_category: "other" })),
    };

    const html = render(asGames as Payload);

    // The `games` bucket draws its own card shape — an "Upcoming games" grid keyed on the
    // opponent — so the reading is that both rows still reach a card, not that the market
    // name is printed.
    expect(html).toContain("Bigger Picture");
    expect(headings(html, "Upcoming games")).toBe(2);
    expect(html).toContain("74%");
    expect(html).toContain("27%");
  });

  it("the rail still draws both sides' surviving cards", () => {
    expect(html).toContain("Bigger Picture");
    expect(html).toContain("Nika Radisic");
    expect(html).toContain("Viktoria Morvayova");
    expect(headings(html, "Match o/u 22.5")).toBe(1);
    expect(headings(html, "Total sets o/u 2.5")).toBe(1);
  });
});
