/**
 * #6064 — THE BIGGEST NUMBER ON THE PAGE WAS THE ONE SURFACE THAT DID NOT CLAMP.
 *
 * ═══ WHAT THE SITE SERVED, PRODUCTION, 2026-09-14 ═══
 *
 * `/events/14637256` (Giants v Cowboys) served, on ONE row:
 *
 *   "home_probability": 0.999,  "home_rendered_percent": 100
 *   "away_probability": 0.001,  "away_rendered_percent": 0
 *
 * so the hero printed `100% – 0%` while the game was still being played. Both
 * ends of the defect in a single frame: a team that had not won reading as
 * certain, and a side the market was actively pricing at 1-in-1000 reading as
 * impossible. `*_rendered_percent` is the SERVED integer, so this is what the
 * page drew, not a local re-derivation.
 *
 * UX-P046 exists to refuse exactly that render — "rounding may never move a
 * probability across a boundary it is not on" — and every other surface on the
 * site obeys it, including the `Opened …` line in this same hero. The hero did
 * not, because `EventHeroProbabilityPair` prints the integer and the `%` as
 * two sibling spans for layout and so could not take `formatProbability`'s
 * finished string. It printed the bare `renderedPercent` instead, and the rule
 * was silently absent from the largest element of the page.
 *
 * ═══ REACH — NOT A TAIL ═══
 *
 * 517 distinct events carried a source probability at or past the boundary in
 * the 7 days to 2026-09-14 (13,124 snapshots; `win_prob_snapshots`, a
 * per-source proxy for the blend the hero draws). ~74 events a day. There is no
 * gate on this render: every game that becomes near-certain in play printed it.
 *
 * ═══ WHAT THIS FILE PINS, AND THE HALF THAT MUST NOT MOVE ═══
 *
 * Both directions (gotcha #43). Clamping everything in sight would satisfy the
 * first half and break settled events, where `100%` is the CORRECT and required
 * render: an exact 1.0 is not a rounding artefact, it is certainty, and
 * "settled means settled" says the hero shows the winner. So the arms below
 * assert the marker appears at 0.996 AND is absent at exactly 1.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import EventHeroProbabilityPair, {
  shownPair,
  sideParts,
} from "@/components/EventHeroProbabilityPair";

function render(props: Partial<React.ComponentProps<typeof EventHeroProbabilityPair>>) {
  return renderToStaticMarkup(
    <EventHeroProbabilityPair
      homeProb={0.62}
      awayProb={0.38}
      homePct={62}
      awayPct={38}
      homeColor="#111827"
      awayColor="#94A3B8"
      {...props}
    />,
  );
}

/**
 * The hero's visible text, entities resolved and whitespace removed.
 *
 * THROWS when nothing drew. Every negative arm below reads this rather than the
 * raw markup: `not.toContain("100")` over the document is satisfied by any
 * attribute holding those digits — `data-probability="1"`, a colour, a class —
 * so it would go green over a hero still printing `100%`.
 *
 * The text is COLLECTED from between the tags, not produced by stripping tags
 * out. `replace(/<[^>]*>/g, "")` is the shape of a broken HTML sanitizer and
 * CodeQL flags it high severity (`js/incomplete-multi-character-sanitization`):
 * one pass of tag removal can leave tag-shaped text behind. Matching the text
 * nodes is not a sanitizer, so there is nothing to do incompletely.
 */
function heroText(html: string): string {
  const block = html.match(/<div class="flex items-baseline"[\s\S]*<\/div>/);
  if (!block) throw new Error("the hero pair did not render");
  const text = [...block[0].matchAll(/>([^<>]*)</g)]
    .map((m) => m[1])
    .join("")
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .replace(/\s+/g, "");
  if (text === "") throw new Error("the hero rendered no text at all");
  return text;
}

/** The digits inside the two giant numerals, which is what `%` attaches to. */
function numerals(html: string): string[] {
  return [...html.matchAll(/tabular-nums"[^>]*>([^<]*)</g)].map((m) => m[1]);
}

describe("#6064 the hero clamps the ends the rest of the site clamps", () => {
  test("the production specimen: 0.999 / 0.001 stops reading as certain and impossible", () => {
    // The served pair, exactly as the API returned it, rendered integers and all.
    const html = render({
      homeProb: 0.999,
      awayProb: 0.001,
      homePct: 100,
      awayPct: 0,
    });

    expect(heroText(html)).toBe(">99%–<1%");
  });

  test("a live underdog at 0.004 is not told it cannot win", () => {
    // The low end is the half UX-P046 was written for: `0%` does not read as
    // "unlikely", it reads as "impossible", over a price the market is quoting.
    const html = render({
      homeProb: 0.004,
      awayProb: 0.996,
      homePct: 0,
      awayPct: 100,
    });

    expect(heroText(html)).toBe("<1%–>99%");
  });

  test("an ordinary pair is untouched, sign and all", () => {
    expect(heroText(render({}))).toBe("62%–38%");
  });

  // ─── the direction that must NOT move ──────────────────────────────────────

  test("a SETTLED winner still reads 100%, because 1.0 is not a rounding artefact", () => {
    // "Settled means settled": the hero shows the winner. A fix that clamped on
    // the printed integer rather than on the probability would print `>99%`
    // here and tell a reader the finished game was still in doubt.
    const html = render({
      homeProb: 1,
      awayProb: 0,
      homePct: 100,
      awayPct: 0,
    });

    expect(heroText(html)).toBe("100%–0%");
  });

  test("an exact 0 keeps its plain 0%, which is a true statement about a loser", () => {
    const html = render({
      homeProb: 0,
      awayProb: 1,
      homePct: 0,
      awayPct: 100,
    });

    expect(heroText(html)).toBe("0%–100%");
  });

  // ─── the layout constraint that made this its own issue ────────────────────

  test("the marker is NOT inside the giant numeral span", () => {
    // `>` at `text-[48px] font-black` is a ~30px glyph and the centre column has
    // a 144px budget at 320px (#5866). The numerals must stay bare digits so the
    // marker can ride at `text-lg` with the `%` it qualifies.
    const html = render({
      homeProb: 0.999,
      awayProb: 0.001,
      homePct: 100,
      awayPct: 0,
    });

    expect(numerals(html)).toEqual(["99", "1"]);
    for (const n of numerals(html)) expect(n).toMatch(/^\d+$/);
  });

  test("#5866's two sized numerals survive — the pair did not gain a third", () => {
    const html = render({
      homeProb: 0.999,
      awayProb: 0.001,
      homePct: 100,
      awayPct: 0,
    });

    expect(numerals(html)).toHaveLength(2);
  });

  // ─── the invariants this must not have broken ──────────────────────────────

  test("#2085's complement survives the clamp: the printed digits still sum to 100", () => {
    // The two clamps are symmetric, so a `>99` opposite a `<1` still reads as
    // one question with two sides. This is the arm that fails if only one end
    // is ever clamped.
    const html = render({
      homeProb: 0.996,
      awayProb: 0.004,
      homePct: 100,
      awayPct: 0,
    });

    const [home, away] = numerals(html).map(Number);
    expect(home + away).toBe(100);
  });

  test("#3459's both-null case is untouched — no marker on a withheld reading", () => {
    const html = render({
      homeProb: null,
      awayProb: null,
      homePct: null,
      awayPct: null,
    });

    // Read the TEXT, not the markup: `>` closes every tag in the document, so
    // asserting against the raw HTML is a test that can never pass and proves
    // nothing about what a reader sees.
    expect(heroText(html)).toBe("Nopriceyet");
  });

  test("one side known and the other not still prints the em dash beside a number", () => {
    // Deliberate, and older than this ship: a dash BESIDE a real number reads
    // as the comparison it is. The clamp must not turn it into a marker.
    const html = render({
      homeProb: 0.62,
      awayProb: null,
      homePct: 62,
      awayPct: null,
    });

    expect(heroText(html)).toBe("62%–—%");
  });

  // ─── mid-tween, where a naive implementation grows a marker ────────────────

  test("counting up to a clamped value shows no marker until it lands", () => {
    // No tween frame is observable through the DOM — effects never run under
    // `renderToStaticMarkup` and `useCountTo` seeds from the target — so the
    // frames are driven through the two pure functions the component itself
    // calls, `shownPair` then `sideParts`. Asking `probabilityParts` directly
    // would re-implement the composition and pass however the component wired
    // it; this fails if `sideParts` stops honouring the frame it is handed.
    const target = 100;
    const prob = 0.996;

    for (const frame of [40, 78, 97, 98, 99]) {
      const { home } = shownPair(target, 0, frame, true);
      expect(sideParts(prob, home)).toEqual({
        marker: null,
        digits: String(frame),
      });
    }

    // Landing on the served integer is the only frame that earns the marker.
    const { home: landed } = shownPair(target, 0, target, true);
    expect(sideParts(prob, landed)).toEqual({ marker: ">", digits: "99" });
  });
});
