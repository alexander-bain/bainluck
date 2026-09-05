/**
 * THE LIVE ROW PRINTS THE SET LINE (live/063, #2746).
 *
 * Measured on production 2026-09-05T21:2xZ: `/tournaments/us-open` carried 18
 * rows and the one match on court read `● 1ST SET` over `Arthur Gea 56% /
 * Michael Zheng 44%` and nothing else, while the FINISHED panel beside it
 * printed `6-3, 6-2, 6-4` against every match that had ended. The page could
 * say what a match finished at and not what one is at.
 *
 * This is the rendered half, through the real `matchListFromSlate` →
 * `TournamentMatches` path a reader actually gets. The backend half is
 * `backend/tests/test_slate_row_in_play_line_live063.py`, and the orientation
 * rule is `frontend/__tests__/lib/slateRowLinescoreOrientation.test.ts`.
 *
 * BOTH DIRECTIONS ARE PINNED (gotcha #43). The live row gains the score AND
 * every other row stays exactly as quiet as it was — a card that started
 * printing `0-0` under every scheduled match would be this ship's own
 * regression.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { matchListFromSlate } from "@/lib/matchList";

const GEA = "espn:athlete:5001";
const ZHENG = "espn:athlete:5002";

/** Everything a reader can actually see. */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function side(
  entityKey: string,
  displayName: string,
  probability: number,
) {
  return {
    entity_key: entityKey,
    display_name: displayName,
    seed: null,
    country: null,
    image: null,
    role: "participant",
    probability,
    opening_probability: probability,
    move: null,
    raw_probability: probability,
    raw_opening_probability: probability,
    observed_at: "2026-09-05T21:25:00Z",
    age_hours: 0.05,
    price_state: "live",
  };
}

/** The scoreboard row for competition 182775, as the hub receives it. */
function liveRow(overrides: Record<string, unknown> = {}) {
  return {
    priced: true,
    pairing_source: "scoreboard",
    matchup_key: "espn:182775",
    event_id: null,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R32",
    scheduled_date: "2026-09-05T20:00:00Z",
    live_state: "in_progress",
    status_detail: "1st Set",
    coherent: true,
    decided: false,
    linescore: {
      sets: [
        [6, 4],
        [2, 1],
      ],
      home_games: 8,
      away_games: 5,
      home_entity_key: GEA,
      away_entity_key: ZHENG,
      source: "espn",
    },
    sides: [side(GEA, "Arthur Gea", 0.56), side(ZHENG, "Michael Zheng", 0.44)],
    ...overrides,
  };
}

function render(row: Record<string, unknown>): string {
  return renderToStaticMarkup(
    <TournamentMatches
      entries={matchListFromSlate([row] as never, {})}
      initialExpanded
    />,
  );
}

describe("a match on court shows the games it is being played to", () => {
  it("THE SHIP: the live row prints the set line beside its set label", () => {
    const text = visibleText(render(liveRow()));

    expect(text).toContain("6-4, 2-1");
    // Beside the badge that says WHICH set, not instead of it — the two are
    // halves of one sentence about the same moment. (The badge is uppercased
    // in CSS, so the TEXT is ESPN's own "1st Set".)
    expect(text).toContain("1st Set 6-4, 2-1");
    expect(text).toContain("Arthur Gea");
  });

  it("the line follows the DISPLAYED order, not the served one", () => {
    // Zheng priced as favourite, so the hub sorts him first while the backend's
    // line still leads with Gea. Printing `6-4, 2-1` here would attribute four
    // games' lead to the man who is behind.
    const text = visibleText(
      render(
        liveRow({
          sides: [side(GEA, "Arthur Gea", 0.44), side(ZHENG, "Michael Zheng", 0.56)],
        }),
      ),
    );

    expect(text).toContain("4-6, 1-2");
    expect(text).not.toContain("6-4, 2-1");
  });

  it("an upcoming row is as quiet as it was before this shipped", () => {
    const html = render(
      liveRow({
        live_state: "upcoming",
        status_detail: "Sat, September 5th at 5:30 PM EDT",
        linescore: undefined,
      }),
    );

    expect(html).not.toContain("match-linescore");
    expect(visibleText(html)).not.toMatch(/\d-\d/);
  });

  it("a five-set line never breaks in the middle of a set", () => {
    // MEASURED, then pinned. At 390px the meta row's flex items shrink and
    // their text wraps INSIDE them, so `6-4, 4-6, 7-6, 6-7, 6-6` broke after
    // `6-` and left a lone `6` on the next line. Nothing clipped — the row's
    // scrollWidth equalled its clientWidth — so an overflow check called it a
    // fit and only the screenshot showed the split score.
    //
    // The repair is two classes and jsdom has no layout to re-measure them
    // with, so this asserts they are still there: `whitespace-nowrap` keeps a
    // score whole, and the row's `flex-wrap` gives it somewhere to go.
    const html = render(
      liveRow({
        status_detail: "5th Set",
        linescore: {
          sets: [
            [6, 4],
            [4, 6],
            [7, 6],
            [6, 7],
            [6, 6],
          ],
          home_games: 29,
          away_games: 29,
          home_entity_key: GEA,
          away_entity_key: ZHENG,
          source: "espn",
        },
      }),
    );

    expect(visibleText(html)).toContain("6-4, 4-6, 7-6, 6-7, 6-6");
    const span = html.match(/<span[^>]*data-testid="match-linescore"[^>]*>/)?.[0] ?? "";
    expect(span).toContain("whitespace-nowrap");
    expect(html).toMatch(/class="[^"]*\bflex-wrap\b[^"]*"/);
  });

  it("a line this row cannot own is not drawn at all", () => {
    // The safe direction: a gap is visibly missing; a mis-attributed score is
    // confidently wrong and nothing on the card contradicts it.
    const html = render(
      liveRow({
        linescore: {
          sets: [[6, 4]],
          home_games: 6,
          away_games: 4,
          home_entity_key: "espn:athlete:9999",
          away_entity_key: ZHENG,
          source: "espn",
        },
      }),
    );

    expect(html).not.toContain("match-linescore");
    expect(visibleText(html)).not.toContain("6-4");
  });
});
