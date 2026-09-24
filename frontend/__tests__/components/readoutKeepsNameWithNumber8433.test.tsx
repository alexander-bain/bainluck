/**
 * #8433 — the readout under the win-probability chart keeps each team's name on
 * the same line as its number at phone width.
 *
 * THE PRODUCTION CASE. `/events/14781697` (Cowboys 37–20 Commanders) at 390px,
 * holding the chart at 2:51 PM, printed:
 *
 *   Cowboys 66%
 *   —
 *   Commanders
 *   34%
 *
 * The period badge and the score are both `shrink-0`, so the `flex-1 min-w-0`
 * probability column was left ~80px and the pair broke mid-side.
 *
 * WHY NOT `whitespace-nowrap` PER SIDE (tried in ux/1486): "— Commanders 34%" is
 * wider than an 80px column, so nowrap clipped it to `— Commanders 3`. The
 * column has to get the room, not just the wrap points.
 *
 * THE FIX, and what each arm pins. The row wraps (`flex-wrap`); the pair column
 * asks for `basis-48` (192px) instead of `flex-1` (basis 0, which never wraps),
 * so a row that cannot give it 192px puts the pair on its own full-width line;
 * and each side is one `inline-block`, so the line can only break BETWEEN sides.
 *
 * A node-environment markup test has no layout, so it cannot see the break
 * itself. It pins the three structural choices that cause it; the pixel claim
 * is photographed at 390px in `artifacts/ux-1487/`. Verified: reverting any one
 * of the three choices reddens its arm.
 */

import { renderToStaticMarkup } from "react-dom/server";
import GamePlayCard from "../../components/GamePlayCard";
import type { ActiveChartPoint } from "../../lib/types";

function point(partial: Partial<ActiveChartPoint> = {}): ActiveChartPoint {
  return {
    timestamp: "2026-09-21T21:51:00Z",
    homeProb: 0.66,
    awayProb: 0.34,
    probKnown: true,
    homeScore: 17,
    awayScore: 13,
    period: "3",
    clock: "4:12",
    scoringPlay: null,
    ...partial,
  } as unknown as ActiveChartPoint;
}

function markup(pt: ActiveChartPoint, awayWithheld = false) {
  return renderToStaticMarkup(
    <GamePlayCard
      activePoint={pt}
      homeTeam="Dallas Cowboys"
      awayTeam="Washington Commanders"
      awayWithheld={awayWithheld}
    />,
  );
}

/**
 * Tags stripped, whitespace collapsed — what a reader reads. A character scan,
 * not a `.replace` over `<...>`: that shape earns a HIGH CodeQL alert even in a
 * test (same helper as `matchedGapCellIsUnsigned7587.test.tsx`). React emits the
 * em-dash as the character, so no entity decode is needed.
 */
function text(fragment: string): string {
  let out = "";
  let inTag = false;
  for (const ch of fragment) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out.split(/\s+/).filter(Boolean).join(" ");
}

/** The opening tag of the first element carrying `attr`, or throw. */
function openingTag(html: string, attr: string): string {
  const at = html.indexOf(attr);
  if (at < 0) throw new Error(`not rendered: ${attr}`);
  const start = html.lastIndexOf("<", at);
  return html.slice(start, html.indexOf(">", at) + 1);
}

function classOf(tag: string): string[] {
  const m = tag.match(/class="([^"]*)"/);
  if (!m) throw new Error(`no class attribute on ${tag}`);
  return m[1].split(/\s+/);
}

/** The pair column: the `<div>` that directly wraps the probability line. */
function pairColumnClasses(html: string): string[] {
  const at = html.indexOf('data-testid="game-play-card-probability"');
  if (at < 0) throw new Error("probability line not rendered");
  const divStart = html.lastIndexOf("<div", at);
  return classOf(html.slice(divStart, html.indexOf(">", divStart) + 1));
}

/**
 * Each side's unit, by counting nested spans from its testid. The side holds
 * a nested number span, so a lazy regex would stop at the inner `</span>`.
 */
function sides(html: string): string[] {
  const out: string[] = [];
  const marker = 'data-testid="game-play-card-side"';
  let from = 0;
  for (;;) {
    const at = html.indexOf(marker, from);
    if (at < 0) return out;
    const start = html.lastIndexOf("<span", at);
    let depth = 0;
    let i = start;
    for (; i < html.length; i++) {
      if (html.startsWith("<span", i)) depth++;
      else if (html.startsWith("</span>", i)) {
        depth--;
        if (depth === 0) break;
      }
    }
    out.push(html.slice(start, i + "</span>".length));
    from = i;
  }
}

describe("#8433 — a team's name stays with its number in the chart readout", () => {
  test("the row wraps, so the pair can take its own line", () => {
    const row = openingTag(markup(point()), 'class="flex items-start');
    expect(classOf(row)).toContain("flex-wrap");
  });

  test("the pair column asks for 192px, not flex-1's zero basis", () => {
    // `flex-1` is `flex: 1 1 0%`. A zero basis always fits, so the row never
    // wraps and the column is squeezed to whatever is left. That is the bug.
    const cls = pairColumnClasses(markup(point()));
    expect(cls).toContain("basis-48");
    expect(cls).toContain("grow");
    expect(cls).toContain("min-w-0");
    expect(cls).not.toContain("flex-1");
  });

  test("each side is one inline-block holding its own name and number", () => {
    const units = sides(markup(point()));
    expect(units).toHaveLength(2);
    for (const u of units) expect(classOf(openingTag(u, "<span"))).toContain("inline-block");
    // The separator goes with the away side, so it can never end a line alone
    // (the specimen printed a bare `—` on a line of its own).
    expect(text(units[0])).toBe("Cowboys 66%");
    expect(text(units[1])).toBe("— Commanders 34%");
  });

  test("the sentence a reader reads is unchanged", () => {
    const html = markup(point());
    const at = html.indexOf('data-testid="game-play-card-probability"');
    const body = html.slice(html.indexOf(">", at) + 1, html.indexOf("</p>", at));
    expect(text(body)).toBe("Cowboys 66% — Commanders 34%");
  });

  test("a withheld away side leaves one unit and no separator (#6238)", () => {
    const units = sides(markup(point(), true));
    expect(units).toHaveLength(1);
    expect(text(units[0])).toBe("Cowboys 66%");
    expect(markup(point(), true)).not.toContain("—");
  });

  test("CONTROL: the short-label branches keep flex-1 and do not move", () => {
    // "No price yet" and a scoring-play type label fit beside the score; giving
    // them a 192px basis would push them under it for nothing.
    const noPrice = markup(point({ probKnown: false }));
    const at = noPrice.indexOf('data-testid="game-play-card-no-probability"');
    const div = noPrice.lastIndexOf("<div", at);
    const cls = classOf(noPrice.slice(div, noPrice.indexOf(">", div) + 1));
    expect(cls).toContain("flex-1");
    expect(cls).not.toContain("basis-48");

    const play = markup(
      point({
        scoringPlay: { type: "Field Goal Good", description: "", short_text: "" },
      } as unknown as Partial<ActiveChartPoint>),
    );
    expect(play).not.toContain("basis-48");
    expect(play).not.toContain('data-testid="game-play-card-side"');
  });
});
