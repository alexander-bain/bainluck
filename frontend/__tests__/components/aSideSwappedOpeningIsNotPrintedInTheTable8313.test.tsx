/**
 * #8313 — A SIDE-SWAPPED OPENING IS NOT PRINTED IN THE TABLE EITHER.
 *
 * PR #11173 stopped the Probability Trend caption on `/futures/13795456` measuring
 * "No up 57.5 pts from opening." from an opening whose own odds say it is the
 * other side's price. The integrator's 390px look after that went live
 * (2026-10-17 09:39Z) found the same number still on the page, one card lower:
 *
 *     All Outcomes   No   OPEN 31%   LATEST 89%
 *                    Yes  OPEN 31%   LATEST 11%
 *
 * Two sides of one question that both opened at 31%. No's 31% is the same stored
 * value the caption now withholds (0.31 beside −223, which is 0.69). The table
 * read `opening_probability` raw, so the page withheld the opening in the caption
 * and printed it in the row.
 *
 * Now the caption, the OPEN cell and the opening pair all read it through
 * `readableOpeningProbability`. No's cell is absent, exactly as for a leg with no
 * opening. Nothing is substituted: not 69% (the odds converted), not 1 − 0.31,
 * not the first retained history point.
 *
 * Controls: Yes on the same payload (0.31 / +223, coherent) keeps OPEN 31%; the
 * same-session `/futures/61318328` keeps OPEN 73% / 27%; and the specimen's No leg
 * with its odds removed keeps OPEN 31%, because the odds are the only signal.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import type { FuturesOutcome } from "@/lib/types";
import { readableOpeningProbability } from "@/lib/futuresDetailDisplay";
import { renderedOutcomeRowPercents } from "@/lib/renderedPercent";
import SPECIMEN from "../fixtures/futuresDetail13795456-8313.json";
import CONTROL from "../fixtures/futuresDetail61318328-8313.json";

jest.mock("@/components/EntityImage", () => ({
  __esModule: true,
  default: ({ name }: { name: string }) => <img alt={name} />,
}));

import OutcomeRow from "../../components/futures/OutcomeRow";

const NO = 125650217;
const YES = 125650216;

const outcomesOf = (market: { outcomes: unknown[] }) =>
  market.outcomes as unknown as FuturesOutcome[];

/** The page's own pair: `renderedById` in `app/futures/[id]/page.tsx`. */
function openingPair(outs: FuturesOutcome[]): Map<number, number | null> {
  const pair = renderedOutcomeRowPercents(outs.map((o) => readableOpeningProbability(o)));
  return new Map(outs.map((o, i) => [o.id, pair[i] ?? null]));
}

/** The OPEN cell's text, or null when the row prints no OPEN cell. */
function openCell(outs: FuturesOutcome[], id: number, override?: Partial<FuturesOutcome>) {
  const base = outs.find((o) => o.id === id);
  if (!base) throw new Error(`fixture lost outcome ${id}`);
  const outcome = { ...base, ...override } as FuturesOutcome;
  const html = renderToStaticMarkup(
    <OutcomeRow
      outcome={outcome}
      rank={1}
      isLeader={false}
      isSelected={false}
      onToggleSelect={() => {}}
      hasHistory
      rendered={null}
      renderedOpening={openingPair(outs.map((o) => (o.id === id ? outcome : o))).get(id) ?? null}
      showLastMove={false}
      showEntityImage={false}
    />,
  );
  const m = html.match(/data-testid="outcome-open"[^>]*>([^<]*)</);
  return { html, open: m ? m[1] : null };
}

describe("#8313 the specimen's table: No's side-swapped opening is not printed", () => {
  test("the fixture is the served pair: both legs 0.31, odds -223 / +223", () => {
    const outs = outcomesOf(SPECIMEN);
    const no = outs.find((o) => o.id === NO)!;
    const yes = outs.find((o) => o.id === YES)!;
    expect([no.name, no.opening_probability, no.opening_american_odds]).toEqual(["No", 0.31, -223]);
    expect([yes.name, yes.opening_probability, yes.opening_american_odds]).toEqual(["Yes", 0.31, 223]);
  });

  test("No prints no OPEN cell at all: no label, no number, no substitute", () => {
    const { html, open } = openCell(outcomesOf(SPECIMEN), NO);
    expect(open).toBeNull();
    expect(html).not.toMatch(/>Open</);
    for (const wrong of ["31%", "69%", "84%"]) expect(html).not.toContain(wrong);
  });

  test("Yes on the same payload (0.31 / +223, coherent) keeps OPEN 31%", () => {
    expect(openCell(outcomesOf(SPECIMEN), YES).open).toBe("31%");
  });

  test("the page's opening pair withholds No and does not pair Yes with it", () => {
    const pair = openingPair(outcomesOf(SPECIMEN));
    expect(pair.get(NO)).toBeNull();
    expect(pair.get(YES)).toBe(31);
  });

  test("No with its odds removed keeps OPEN 31% (the odds are the only signal)", () => {
    expect(openCell(outcomesOf(SPECIMEN), NO, { opening_american_odds: null }).open).toBe("31%");
  });
});

describe("#8313 control: a coherent pair keeps both OPEN cells", () => {
  test("/futures/61318328 still prints OPEN 73% / 27%", () => {
    const outs = outcomesOf(CONTROL);
    const byName = new Map(outs.map((o) => [o.name, o.id]));
    expect(openCell(outs, byName.get("Yes")!).open).toBe("73%");
    expect(openCell(outs, byName.get("No")!).open).toBe("27%");
  });
});

describe("#8313 one reader of the opening on the page", () => {
  // A second raw read is how the caption and the row came to disagree; this pins
  // both table readers to the shared accessor.
  const src = (p: string) => readFileSync(join(__dirname, "../..", p), "utf8");
  const code = (s: string) =>
    s
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .split("\n")
      .filter((l) => !l.trim().startsWith("//"))
      .join("\n");

  test("OutcomeRow reads no raw opening_probability", () => {
    expect(code(src("components/futures/OutcomeRow.tsx"))).not.toMatch(/\.opening_probability\b/);
  });

  test("the futures page pairs openings only through readableOpeningProbability", () => {
    const page = code(src("app/futures/[id]/page.tsx"));
    expect(page).not.toMatch(/\.opening_probability\b/);
    expect(page).toMatch(/renderedOutcomeRowPercents\(outs\.map\(\(o\) => readableOpeningProbability\(o\)\)\)/);
  });
});
