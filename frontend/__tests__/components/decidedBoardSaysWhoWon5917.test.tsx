/**
 * #5917 — THE BOARD ANSWERED A DECIDED QUESTION WITH A PROBABILITY.
 *
 * `bainluck.com/tournaments/us-open` → Women's, production, 2026-09-13 12:59Z at
 * 390px. Under a column headed TO WIN THE TITLE:
 *
 *   ⚠ Updates paused. Last confirmed reading 7 hours ago. These are the last
 *     probabilities we saw, not live ones.
 *   1  Elena Rybakina   99%
 *   2  Aryna Sabalenka   1%
 *
 * Rybakina won the title at 20:15Z the night before, and the SAME payload says
 * so in `results.matches[]` (`winner_entity_key: elena-rybakina`, `is_winner`,
 * `6-4, 5-7, 6-2`). Two inches down the same screen a settled prop reads
 * "Yes · Settled · last reading 100%" — one question closed properly, one not.
 *
 * The board was not silently wrong: the honesty rail fired. But STALENESS IS THE
 * WRONG APOLOGY. The numbers are not paused because a feed went quiet, they are
 * paused because the question is over, and "not live ones" invites the reader to
 * wait for a fresher one that does not exist.
 *
 * TWO LANES, ONE SHIP (standing notice 46). live/200 owns the payload half — PR
 * #5920 settles every row (`won` / `eliminated`, `probability: null`), moves the
 * champion to rank 1 and adds `board.decided`, deliberately PRESERVING the
 * board's freshness summary so this banner never flips to "No numbers yet" while
 * the two merges are apart. This file is the render half: `decided` is read
 * before any freshness branch, and the notice stops being a warning.
 *
 * The contract is `decided: { winner_entity_key }` and nothing else — the score
 * and the completion time live on the result row in the `results` fragment, and
 * copying them here would duplicate a fact across two readers (live/200's 13:52Z
 * correction to its own 13:25Z contract).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentBoard from "@/components/tournament/TournamentBoard";
import {
  boardNotice,
  type TournamentBoardData,
  type TournamentRow,
} from "@/lib/tournament";

function row(overrides: Partial<TournamentRow> = {}): TournamentRow {
  return {
    entity_key: "elena-rybakina",
    display_name: "Elena Rybakina",
    seed: 4,
    country: "KAZ",
    rank: 1,
    state: "won",
    probability: null,
    probability_is_live: false,
    observed_at: "2026-09-13T05:00:00+00:00",
    age_hours: 7,
    price_state: "dark",
    freshest_observed_at: "2026-09-13T05:00:00+00:00",
    freshest_age_hours: 7,
    stale_sources: ["kalshi"],
    mixed_freshness: false,
    source_count: 1,
    sources: [],
    blend_rule: null,
    divergent: false,
    trend: [],
    trend_delta: null,
    ...overrides,
  };
}

/**
 * The women's board as live/200's half leaves it: rows settled, champion at rank
 * 1, and the freshness summary PRESERVED — which is exactly the shape that used
 * to produce the wrong apology, so it is the shape this file tests.
 */
function decidedBoard(overrides: Partial<TournamentBoardData> = {}): TournamentBoardData {
  return {
    draw: "womens-singles",
    label: "Women's Singles",
    rows: [
      row(),
      row({
        entity_key: "aryna-sabalenka",
        display_name: "Aryna Sabalenka",
        rank: 2,
        state: "eliminated",
      }),
    ],
    contenders: 2,
    unpriced: 0,
    rows_not_live: 2,
    mixed_freshness_rows: 0,
    price_state: "dark",
    newest_observed_at: "2026-09-13T05:00:00+00:00",
    age_hours: 7,
    decided: { winner_entity_key: "elena-rybakina" },
    ...overrides,
  };
}

/** The same board before the final was graded — the purity control. */
const UNDECIDED = decidedBoard({
  decided: undefined,
  rows: [row({ state: "live", probability: 0.99 })],
});

describe("🔴 a decided draw is answered with a name, not a probability", () => {
  it("names the champion instead of apologising for the age of the numbers", () => {
    const notice = boardNotice(decidedBoard())!;
    expect(notice.tone).toBe("decided");
    expect(notice.headline).toBe("Settled");
    expect(notice.detail).toBe("Elena Rybakina won the title.");
  });

  it("the staleness sentence is GONE, not merely joined", () => {
    // A remedy-as-regression guard: a notice that appended the result to the
    // warning would satisfy "names the champion" and still tell the reader a
    // fresher number is coming.
    const detail = JSON.stringify(boardNotice(decidedBoard()));
    expect(detail).not.toContain("Updates paused");
    expect(detail).not.toContain("not live ones");
    expect(detail).not.toContain("hours ago");
  });

  it("beats the freshness branches even when the board is fully dark", () => {
    // `decided` is read FIRST because a decided board is stale by construction.
    // The dark branch is the one live/200 went out of its way to keep us out of;
    // this pins that neither of us is relying on the other's merge landing first.
    const notice = boardNotice(
      decidedBoard({ price_state: "dark", newest_observed_at: null, age_hours: null }),
    )!;
    expect(notice.tone).toBe("decided");
    expect(notice.detail).not.toContain("No market has put a probability");
  });

  it("says nothing it cannot source when the winner is not on the board", () => {
    // An entity key that does not resolve is a board we cannot narrate. The
    // general sentence is honest; printing the raw key as prose is not.
    const notice = boardNotice(
      decidedBoard({ decided: { winner_entity_key: "someone-else" } }),
    )!;
    expect(notice.tone).toBe("decided");
    expect(notice.detail).toBe("This draw is decided.");
    expect(notice.detail).not.toContain("someone-else");
  });
});

describe("🟢 an undecided board keeps the honesty rail exactly as it was", () => {
  it("still says updates are paused and how old the reading is", () => {
    const notice = boardNotice(UNDECIDED)!;
    // `tone` is the board's own `price_state` — "dark" at 7 hours, which is the
    // production board's state and the reason the warning fired at all.
    expect(notice.tone).toBe("dark");
    expect(notice.headline).toBe("Updates paused");
    expect(notice.detail).toContain("7 hours ago");
    expect(notice.detail).toContain("not live ones");
  });

  it("a genuinely live board still shows no notice at all", () => {
    expect(boardNotice(decidedBoard({ decided: undefined, price_state: "live" }))).toBeNull();
  });
});

describe("the rendered board — a result does not wear a warning", () => {
  it("drops the ⚠ and the amber tint on a decided board", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={decidedBoard()} />);
    expect(html).toContain('data-tone="decided"');
    expect(html).toContain("Elena Rybakina won the title.");
    // The literal character, NOT the `&#9888;` entity the source is written
    // with: React emits the glyph itself, so an entity assertion passes while
    // the triangle is on screen. (A mutant that always renders it survived this
    // arm until the assertion was taken off the source and put on the output.)
    expect(html).not.toContain("\u26a0");
    expect(html).not.toContain("bg-accent-warning/10");
  });

  it("keeps both on a board whose numbers really are just old", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={UNDECIDED} />);
    expect(html).toContain('data-tone="dark"');
    expect(html).toContain("bg-accent-warning/10");
    expect(html).toContain("\u26a0");
    expect(html).toContain("Updates paused");
  });
});
