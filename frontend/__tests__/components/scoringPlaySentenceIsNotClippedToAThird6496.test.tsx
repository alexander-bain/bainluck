/**
 * #6496 — the scoring-play sentence under the win-probability chart must not be
 * clipped to a third of itself at phone width.
 *
 * THE PRODUCTION CASE. Read at 390px on 2026-09-16 against live frontend
 * `2ede802a7`, `/events/14638896` (Chiefs 31-10 Broncos, Final) printed:
 *
 *   ● Passing Touchdown
 *   Kenneth Walker III 2 Yd pa…
 *
 * for `Kenneth Walker III 2 Yd pass from Patrick Mahomes (Harrison Butker Kick)`.
 * The type label above already says "Passing Touchdown", so the clipped half was
 * the only part carrying new information — who threw it.
 *
 * MEASURED, NOT EYEBALLED. `truncate` sets `overflow: hidden`, so the DOM answers
 * "did the reader lose text" itself via `scrollWidth` vs `clientWidth`. Four of
 * the four most-recent completed NFL games, all at `clientWidth` exactly 159px:
 *
 *   14638896 KC-DEN   159px shown / 418px needed   62% lost
 *   14637256 NYG-DAL  159px shown / 429px needed   63% lost
 *   14780148 MIN-GB   159px shown / 375px needed   58% lost
 *   14780150 PHI-WAS  159px shown / 472px needed   66% lost
 *
 * None carried a `title` attribute, so the text was unreachable by any reader.
 * The 159px is structural, not a long-string accident: the row's other two
 * children (period/clock badge, score) are `shrink-0`, so the `min-w-0` text
 * column absorbs all of the squeeze. `min-w-0` was already present and correct —
 * this was never the usual missing-`min-w-0` bug.
 *
 * WHY THE OBVIOUS ONE-WORD FIX IS NOT THE FIX, which is what ARM 2 exists to
 * pin. Swapping `truncate` for `line-clamp-2` in place leaves the sentence in the
 * 159px column: two lines is 318px, still short of the 418px specimen and well
 * short of 472px. The sentence has to leave the row. At the card's full width
 * (measured: 334px) two lines hold 668px and every measured play fits.
 *
 * And the two classes cannot be combined — `truncate` sets `white-space: nowrap`,
 * which silently defeats a clamp. That is #4342's finding on the golf list
 * (`UpcomingTournaments.tsx:96`), the identical shape, and ARM 3 pins it here so
 * a later tidy-up cannot reintroduce it.
 */

import { renderToStaticMarkup } from "react-dom/server";
import GamePlayCard from "../../components/GamePlayCard";
import type { ActiveChartPoint } from "../../lib/types";

const FULL_PLAY =
  "Kenneth Walker III 2 Yd pass from Patrick Mahomes (Harrison Butker Kick)";

function point(partial: Partial<ActiveChartPoint> = {}): ActiveChartPoint {
  return {
    timestamp: "2026-09-15T02:41:23Z",
    homeProb: 1,
    awayProb: 0,
    probKnown: true,
    homeScore: 31,
    awayScore: 10,
    period: "4",
    clock: "14:39",
    scoringPlay: {
      type: "Passing Touchdown",
      description: FULL_PLAY,
      short_text: "",
      timestamp: "2026-09-15T02:41:23Z",
      team: "Kansas City Chiefs",
      home_score: 31,
      away_score: 10,
    },
    ...partial,
  } as unknown as ActiveChartPoint;
}

function markup(pt: ActiveChartPoint | null) {
  return renderToStaticMarkup(
    <GamePlayCard
      activePoint={pt}
      homeTeam="Kansas City Chiefs"
      awayTeam="Denver Broncos"
    />,
  );
}

/**
 * The balanced `<div>` block that begins at `startTag`, by counting opens and
 * closes. A regex cannot answer a nesting question, and nesting is precisely
 * what ARM 2 is about — "is the sentence inside the squeezed column".
 */
function balancedBlockFrom(html: string, startTag: string): string {
  const start = html.indexOf(startTag);
  if (start === -1) throw new Error(`start tag not found: ${startTag}`);
  let depth = 0;
  for (let i = start; i < html.length; i++) {
    if (html.startsWith("<div", i)) depth++;
    else if (html.startsWith("</div>", i)) {
      depth--;
      if (depth === 0) return html.slice(start, i + "</div>".length);
    }
  }
  throw new Error("unbalanced markup");
}

/**
 * The `class` attribute of the description element, found by its testid. Throws
 * if the element is absent, so a fix that drops it cannot read as "no truncate".
 */
function classesOfDescription(html: string): string {
  const m = html.match(
    /<p\b[^>]*data-testid="game-play-card-description"[^>]*>/,
  );
  if (!m) throw new Error("description element not rendered");
  const cls = m[0].match(/class="([^"]*)"/);
  if (!cls) throw new Error("description element has no class attribute");
  return cls[1];
}

describe("#6496 — the play sentence reaches the reader whole", () => {
  // ARM 1 PASSES ON THE PARENT, and that is not a flaw to fix — it is the shape
  // of the defect. `truncate` clips in CSS, so the full string was always in the
  // DOM; the reader lost it at paint. A `testEnvironment: 'node'` suite has no
  // layout and can never see that directly. ARM 1 pins that the sentence is
  // present and whole; ARMs 2 and 3 are the ones that redden on the parent
  // (verified: reverting the component fails exactly those two), because the
  // only thing a markup test CAN pin about a layout bug is the structure that
  // caused it. The pixel claim is measured on production and recorded above.
  test("ARM 1: the full sentence is rendered, not a clipped prefix", () => {
    const html = markup(point());
    expect(html).toContain(FULL_PLAY);
    // The half production dropped. Named explicitly so a future clip that
    // happens to keep the scorer still reddens this.
    expect(html).toContain("pass from Patrick Mahomes");
  });

  test("ARM 2: the sentence is NOT inside the 159px squeezed column", () => {
    // The load-bearing arm. `flex-1 min-w-0` is the column the badge and score
    // squeeze to 159px; a fix that only swaps the class leaves the sentence
    // here and still clips, so this is what makes that fix fail.
    const html = markup(point());
    const row = balancedBlockFrom(html, '<div class="flex items-start gap-3"');

    expect(row).toContain("min-w-0"); // the column still exists, unchanged
    expect(row).not.toContain(FULL_PLAY);
    expect(row).not.toContain('data-testid="game-play-card-description"');

    // ...and it really is on the card, just outside that row.
    expect(html).toContain('data-testid="game-play-card-description"');
    expect(html).toContain(FULL_PLAY);
  });

  test("ARM 3: line-clamp-2, and never `truncate` on the same element", () => {
    // #4342: `truncate` sets `white-space: nowrap`, which silently defeats a
    // clamp — combining them ships the bug back while looking fixed.
    // Located by testid, not by an exact class string: this arm is about which
    // classes the element carries, so keying the LOOKUP on those same classes
    // would make it pass for the wrong reason and break on any reordering.
    const html = markup(point());
    const cls = classesOfDescription(html);
    expect(cls).toContain("line-clamp-2");
    expect(cls).not.toContain("truncate");
  });

  test("ARM 4: the type label still renders, and above the sentence", () => {
    // The sentence moved; the red-dot type label did not.
    const html = markup(point());
    expect(html).toContain("Passing Touchdown");
    expect(html.indexOf("Passing Touchdown")).toBeLessThan(html.indexOf(FULL_PLAY));
  });

  test("CONTROL: a point with no scoring play renders no description element", () => {
    // No empty chrome on the ordinary between-plays point, which is most of a
    // live game's scrub path.
    const html = markup(point({ scoringPlay: null }));
    expect(html).not.toContain('data-testid="game-play-card-description"');
    // The probability line is what that point shows instead, still present.
    expect(html).toContain('data-testid="game-play-card-probability"');
  });

  test("CONTROL: a scoring play with an empty description renders nothing", () => {
    // `description` and `short_text` both empty is a real wire shape; it must
    // not produce a bare empty paragraph under the row.
    const html = markup(
      point({
        scoringPlay: {
          type: "Field Goal Good",
          description: "",
          short_text: "",
        },
      } as unknown as Partial<ActiveChartPoint>),
    );
    expect(html).not.toContain('data-testid="game-play-card-description"');
    expect(html).toContain("Field Goal Good");
  });
});
