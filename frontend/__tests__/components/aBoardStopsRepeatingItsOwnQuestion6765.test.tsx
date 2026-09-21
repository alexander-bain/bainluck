/**
 * #6765 — A BOARD STOPS REPEATING ITS OWN QUESTION ON EVERY LINE.
 *
 * ## What a reader met on production
 *
 * `https://bainluck.com/futures/61645756` at 390px, anonymous, 2026-09-21 13:5xZ
 * (`artifacts/ux-1415/before-6765-PROD-390-61645756-top.png`). The `<h1>` asks the
 * question and then the page asks it again, six more times:
 *
 *   | where                | printed                                                        |
 *   |----------------------|----------------------------------------------------------------|
 *   | `<h1>`               | `Korea Open: Alevtina Ibragimova vs Yeon-Woo Ku`                |
 *   | hero, under the 70%  | `Korea Open: Alevtina Ibragimova vs Yeon-Woo Ku Set 1 O/U 9.5`  |
 *   | chart caption        | `Korea Open: … Set 1 O/U 9.5 up 22.0 pts from opening.`         |
 *   | All Outcomes row 1   | `Korea Open: Alevtina Ibragimova vs Yeon…`                      |
 *   | All Outcomes row 3   | `Korea Open: Alevtina Ibragimova vs Yeon-…`                     |
 *   | All Outcomes row 4   | `Korea Open: Alevtina Ibragimova vs Yeon-W…`                    |
 *
 * The hero wastes a line. **The rows lose the information**: three different
 * sub-markets — Set 1 O/U 9.5, Set 1 Winner, Set 2 Winner — render as three rows a
 * reader cannot tell apart, because the name span is `truncate` and the first 40
 * characters of all three are the same 40 characters. Row 2 of the same board is
 * `Alevtina Ibragimova`, which is what a row is supposed to look like.
 *
 * ## The population, measured rather than asserted
 *
 * Production 2026-09-21, every open futures market, counted on the served hero
 * (`pickHeroOutcome`'s own rule, not a max-probability proxy):
 *
 *   outcome rows whose name has their board's name as a strict prefix   194
 *   boards carrying at least one                                         66
 *   boards whose HERO is one of them                                     45   (tennis 27 · table tennis 16 · 2 untagged)
 *   ...of those, rows breaking at a NON-separator character               0
 *   ...of those, rows whose remainder is empty once separators go         0
 *   shortest surviving remainder                                    12 chars   (`Set 1 Winner`)
 *   median prefix removed from a line                               43 chars
 *
 * The issue's own table said "246 leading outcomes over 45 characters". That is a
 * LENGTH proxy for this shape and it is not the same set — a 60-character player
 * name is long and is not this defect. Re-measured on the real predicate before
 * building, per the standing rule that an issue's table can invert.
 *
 * ## What this file proves, and what it deliberately does not
 *
 * PROVES, at the render level, on the real component: the painted row text loses
 * the repeat while `title` and `data-outcome-name` keep the full served name.
 * PROVES, at the rule level: every refusal, including the two hostile ones a
 * "startsWith" one-liner gets wrong (a non-separator boundary, an empty remainder).
 * PROVES, as a population diff: over the real served names of four boards, exactly
 * the prefix-shaped rows move and every other name is byte-identical.
 *
 * DOES NOT PROVE that `app/futures/[id]/page.tsx` passes `market.name` into the
 * hero and the caption — a substring scan of a page file cannot tell a correct
 * argument from a misspelled one, and this project's jest has no jsdom to mount the
 * page in. That wiring is proved by the production AFTER frame at the same URL and
 * the same offset as the BEFORE above, which is in the PR.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FuturesOutcome } from "@/lib/types";

jest.mock("@/components/EntityImage", () => ({
  __esModule: true,
  default: ({ name }: { name: string }) => <img alt={name} />,
}));

import OutcomeRow from "../../components/futures/OutcomeRow";
import {
  boardOutcomeLabel,
  movementExplanation,
  withoutBoardNamePrefix,
} from "@/lib/futuresDetailDisplay";

/** `/futures/61645756` exactly as the API served it, 2026-09-21. Four of the five
 *  rows carry the board's name; row 2 does not, and is the in-fixture control. */
const KOREA_OPEN = "Korea Open: Alevtina Ibragimova vs Yeon-Woo Ku";
const KOREA_OPEN_ROWS: Array<[string, number]> = [
  [`${KOREA_OPEN} Set 1 O/U 9.5`, 0.7],
  ["Alevtina Ibragimova", 0.57],
  [`${KOREA_OPEN} Set 1 Winner`, 0.555],
  [`${KOREA_OPEN} Set 2 Winner`, 0.54],
  [`${KOREA_OPEN} Match O/U 21.5`, 0.495],
];

/** `/futures/61294085`, the colon-separated arm — and `Italy`, a served outcome
 *  SHORTER than its own board, which must survive untouched. */
const VOLLEY = "Italy vs. Slovenia";
const VOLLEY_ROWS: Array<[string, number]> = [
  ["Italy", 0.99],
  [`${VOLLEY}: Total Sets O/U 3.5`, 0.99],
];

/** Two boards of the ordinary kind — `/futures/61308736` and `/futures/109403`.
 *  Nothing here may move, and one of them is a date ladder, which is the family
 *  #7256's measurement table says a label rule is most likely to damage. */
const US_OPEN = "2027 US Open Men's Singles Winner";
const US_OPEN_ROWS = [
  "Jakub Mensik",
  "Jannik Sinner",
  "Carlos Alcaraz",
  "Casper Ruud",
  "Alexander Zverev",
];
const DHS = "When will DHS be funded again?";
const DHS_ROWS = [
  "Before Jan 1, 2027",
  "Before Jul 1, 2026",
  "Before Jun 1, 2026",
  "Before May 22, 2026",
  "Before May 15, 2026",
];

function outcome(
  name: string,
  probability: number,
  over: Partial<FuturesOutcome> = {},
): FuturesOutcome {
  return {
    id: name.length + Math.round(probability * 1000),
    name,
    probability,
    opening_probability: 0.48,
    probability_change_24h: null,
    rank_change_24h: null,
    is_winner: null,
    last_updated: "2026-09-21T12:51:00Z",
    ...over,
  } as unknown as FuturesOutcome;
}

function row(name: string, probability: number, marketName?: string): string {
  return renderToStaticMarkup(
    <OutcomeRow
      outcome={outcome(name, probability)}
      rank={1}
      isLeader={false}
      isSelected={false}
      onToggleSelect={() => {}}
      hasHistory={false}
      marketCategory="tennis"
      marketName={marketName}
      isResolved={false}
      rendered={null}
      renderedOpening={null}
      showLastMove={false}
      showEntityImage={false}
    />,
  );
}

const ENTITY: Record<string, string> = {
  quot: '"',
  "#x27": "'",
  "#39": "'",
  lt: "<",
  gt: ">",
  amp: "&",
};

/** The text of the row's name span — what a reader actually sees in that column.
 *
 *  Two deliberate shapes, both of which a tidier-looking helper gets wrong:
 *
 *  - the span's inner HTML is ASSERTED to be text rather than stripped with a
 *    `replace(/<[^>]*>/g, "")`. Stripping is the weaker check (it would quietly
 *    pass if this ship ever wrapped the name in another element and changed what
 *    the column means) and CodeQL reads it as a sanitizer —
 *    `js/incomplete-multi-character-sanitization`, high, which is a notice-32
 *    refuse on the whole sha. It cost this PR one round trip.
 *  - the entities are decoded in ONE pass. A `.replace(&quot;).replace(&#x27;)
 *    .replace(&amp;)` chain double-decodes whatever an earlier link produced
 *    (`js/double-escaping`), and ordering it defensively is a rule the next
 *    person has to keep. A single regex cannot have the bug at all. */
function paintedName(html: string): string {
  const at = html.indexOf('data-testid="outcome-name"');
  if (at === -1) return "";
  const open = html.indexOf(">", at);
  const close = html.indexOf("</span>", open);
  const inner = html.slice(open + 1, close);
  expect(inner).not.toContain("<");
  return inner.replace(/&(quot|#x27|#39|lt|gt|amp);/g, (m, name: string) => ENTITY[name] ?? m).trim();
}

describe("#6765 — the rule only ever removes a repeat", () => {
  it("strips the board's own name off the specimen hero", () => {
    expect(boardOutcomeLabel(`${KOREA_OPEN} Set 1 O/U 9.5`, KOREA_OPEN)).toBe("Set 1 O/U 9.5");
  });

  it("strips a colon-separated prefix, the other separator the venues use", () => {
    expect(boardOutcomeLabel(`${VOLLEY}: Total Sets O/U 3.5`, VOLLEY)).toBe("Total Sets O/U 3.5");
  });

  it("does nothing at all without a board name — every other surface", () => {
    // A Discover card and a search result print this same string with no question
    // above it, so the prefix there is the only thing naming the match.
    expect(boardOutcomeLabel(`${KOREA_OPEN} Set 1 O/U 9.5`)).toBe(`${KOREA_OPEN} Set 1 O/U 9.5`);
    expect(boardOutcomeLabel(`${KOREA_OPEN} Set 1 O/U 9.5`, null)).toBe(
      `${KOREA_OPEN} Set 1 O/U 9.5`,
    );
    expect(boardOutcomeLabel(`${KOREA_OPEN} Set 1 O/U 9.5`, "   ")).toBe(
      `${KOREA_OPEN} Set 1 O/U 9.5`,
    );
  });

  it("refuses a name that IS the board name, rather than printing nothing", () => {
    expect(boardOutcomeLabel(KOREA_OPEN, KOREA_OPEN)).toBe(KOREA_OPEN);
  });

  it("refuses a name shorter than the board — `Italy` on `Italy vs. Slovenia`", () => {
    expect(boardOutcomeLabel("Italy", VOLLEY)).toBe("Italy");
  });

  it("refuses to cut mid-word: a board called `Italy` does not eat `Italymania`", () => {
    // The hostile case a bare `startsWith` gets wrong. 0 of the 194 measured rows
    // break at a non-separator, so this costs the fix nothing and is what makes it
    // safe for a short board name to exist at all.
    expect(boardOutcomeLabel("Italymania", "Italy")).toBe("Italymania");
    expect(boardOutcomeLabel("Italy2026", "Italy")).toBe("Italy2026");
  });

  it("refuses when the remainder is only punctuation", () => {
    expect(boardOutcomeLabel(`${VOLLEY}: `, VOLLEY)).toBe(`${VOLLEY}:`);
    expect(boardOutcomeLabel(`${VOLLEY} —`, VOLLEY)).toBe(`${VOLLEY} —`);
  });

  it("ignores case when matching and preserves it in what survives", () => {
    expect(boardOutcomeLabel("KOREA OPEN: ALEVTINA IBRAGIMOVA VS YEON-WOO KU Set 1 O/U 9.5", KOREA_OPEN)).toBe(
      "Set 1 O/U 9.5",
    );
    expect(boardOutcomeLabel(`${KOREA_OPEN} SET 1 O/U 9.5`, KOREA_OPEN)).toBe("SET 1 O/U 9.5");
  });

  it("only matches a PREFIX, never the board name appearing later in the name", () => {
    expect(boardOutcomeLabel(`Winner of ${KOREA_OPEN}`, KOREA_OPEN)).toBe(
      `Winner of ${KOREA_OPEN}`,
    );
  });

  it("trims the board name it is given, so a padded payload still matches", () => {
    expect(withoutBoardNamePrefix(`${VOLLEY}: Total Sets O/U 3.5`, `  ${VOLLEY}  `)).toBe(
      "Total Sets O/U 3.5",
    );
  });
});

describe("#6765 — the population diff: only the repeats move", () => {
  it("moves exactly the four prefix rows of the specimen board and leaves the fifth", () => {
    const before = KOREA_OPEN_ROWS.map(([n]) => n);
    const after = KOREA_OPEN_ROWS.map(([n]) => boardOutcomeLabel(n, KOREA_OPEN));
    expect(after).toEqual([
      "Set 1 O/U 9.5",
      "Alevtina Ibragimova",
      "Set 1 Winner",
      "Set 2 Winner",
      "Match O/U 21.5",
    ]);
    // The distinction the truncated rows had destroyed is back: four rows, four
    // different strings, none of them a prefix of another.
    expect(new Set(after).size).toBe(after.length);
    expect(before.filter((n, i) => n === after[i])).toEqual(["Alevtina Ibragimova"]);
  });

  it("leaves every name on two ordinary boards byte-identical", () => {
    for (const name of US_OPEN_ROWS) {
      expect(boardOutcomeLabel(name, US_OPEN)).toBe(name);
    }
    // The date ladder: `Before May 15, 2026` shares no prefix with its question and
    // must survive whole — a label rule that eats a date is #7256's exact warning.
    for (const name of DHS_ROWS) {
      expect(boardOutcomeLabel(name, DHS)).toBe(name);
    }
  });

  it("leaves the volleyball board's plain row and shortens only its long one", () => {
    expect(VOLLEY_ROWS.map(([n]) => boardOutcomeLabel(n, VOLLEY))).toEqual([
      "Italy",
      "Total Sets O/U 3.5",
    ]);
  });
});

describe("#6765 — the All Outcomes row, rendered", () => {
  it("paints the remainder while `title` keeps the whole served name", () => {
    const html = row(`${KOREA_OPEN} Set 1 O/U 9.5`, 0.7, KOREA_OPEN);
    expect(paintedName(html)).toBe("Set 1 O/U 9.5");
    // The reader's way back to the full string, and the reason nothing is lost.
    expect(html).toContain(`title="${KOREA_OPEN} Set 1 O/U 9.5"`);
  });

  it("keeps `data-outcome-name` on the full served name, so the order guards still read", () => {
    // `futuresDetailOutcomeOrder` and `settledBoardRankBadge6325` read this attribute
    // to assert WHICH rows rendered and in what order. It is an identity key, not a
    // picture of the row, and this ship must not quietly redefine it.
    const html = row(`${KOREA_OPEN} Set 1 Winner`, 0.555, KOREA_OPEN);
    expect(html).toContain(`data-outcome-name="${KOREA_OPEN} Set 1 Winner"`);
    expect(paintedName(html)).toBe("Set 1 Winner");
  });

  it("renders the three indistinguishable rows as three distinct ones", () => {
    const painted = [
      `${KOREA_OPEN} Set 1 O/U 9.5`,
      `${KOREA_OPEN} Set 1 Winner`,
      `${KOREA_OPEN} Set 2 Winner`,
    ].map((n) => paintedName(row(n, 0.5, KOREA_OPEN)));
    expect(painted).toEqual(["Set 1 O/U 9.5", "Set 1 Winner", "Set 2 Winner"]);
    // The defect, stated as the thing that is now false: no two of them share the
    // first 40 characters, which is roughly what survives `truncate` at 390px.
    const heads = painted.map((p) => p.slice(0, 40));
    expect(new Set(heads).size).toBe(3);
  });

  it("paints an ordinary name unchanged, with and without a board name", () => {
    expect(paintedName(row("Alevtina Ibragimova", 0.57, KOREA_OPEN))).toBe("Alevtina Ibragimova");
    expect(paintedName(row("Jakub Mensik", 0.74, US_OPEN))).toBe("Jakub Mensik");
    // A surface that does not pass `marketName` gets exactly today's behaviour.
    expect(paintedName(row(`${KOREA_OPEN} Set 1 Winner`, 0.5))).toBe(
      `${KOREA_OPEN} Set 1 Winner`,
    );
  });

  it("still truncates on its own span, so a name that IS long enough still cuts", () => {
    // #3358/#4592's contract, asserted here because this ship touches the same span.
    const html = row(`${KOREA_OPEN} Set 1 O/U 9.5`, 0.7, KOREA_OPEN);
    const at = html.indexOf('data-testid="outcome-name"');
    expect(html.slice(at - 200, at + 200)).toContain("truncate");
  });
});

describe("#6765 — the movement caption", () => {
  const leader = {
    name: `${KOREA_OPEN} Set 1 O/U 9.5`,
    probability: 0.7,
    opening_probability: 0.48,
    probability_change_24h: null,
  };

  it("drops the board name from the caption's subject", () => {
    expect(movementExplanation(leader, KOREA_OPEN)).toBe(
      "Set 1 O/U 9.5 up 22.0 pts from opening.",
    );
  });

  it("is unchanged where there is no board name to drop", () => {
    expect(movementExplanation(leader)).toBe(
      `${KOREA_OPEN} Set 1 O/U 9.5 up 22.0 pts from opening.`,
    );
    expect(movementExplanation({ ...leader, name: "Jakub Mensik" }, US_OPEN)).toBe(
      "Jakub Mensik up 22.0 pts from opening.",
    );
  });

  it("leaves #5997's Yes/No rule exactly where it was", () => {
    // `leaderLabel` answers first; a label it resolved to "Yes" carries no board
    // prefix, so the two rules cannot interact whatever the board is called.
    expect(movementExplanation({ ...leader, name: "Yes" }, "Yes or No")).toBe(
      "Yes up 22.0 pts from opening.",
    );
  });

  it("still says nothing when there is nothing to say", () => {
    expect(movementExplanation(null, KOREA_OPEN)).toBeNull();
    expect(
      movementExplanation(
        { name: "X", probability: null, opening_probability: null, probability_change_24h: null },
        KOREA_OPEN,
      ),
    ).toBeNull();
  });
});
