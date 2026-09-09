// #4118 / STANDING NOTICE 34 — the accuracy page's method notes stay out of the
// page body.
//
// Alex, 2026-09-08, on the US Open page: *"all the grey text is madness, and
// shouldn't be user-facing at all"* — coverage counts, limitations and method
// notes go *"in the PR, the artifact, or a tooltip on the source mark — never
// in the page body… A reader sees the number, the small source mark (D91), and
// at most one short caption."*
//
// `/calibration` had eight of these when the notice landed. Six were moved
// behind `<CalibrationCardNote>` (a closed `<details>`) rather than deleted,
// because half of them exist under EARLIER, more specific Alex instructions —
// UX-P075 item (a) made the cohort's proxy footnote non-optional, and the
// Queue-316 hook list calls its anchors *"a claim Alex asked to be made in
// words"*. Moving satisfies both readings; deleting would overwrite four dated
// instructions with one later general one, which is not a build lane's call.
//
// WHY A SOURCE SLICE AND NOT A RENDER. `calibrationAuditHooks.test.tsx` gives
// the reason for the page itself: it is a 2,000-line client component behind
// SWR, so "rendering it would prove less and break more". What this suite
// asserts is a STRUCTURAL relationship inside the JSX — which element encloses
// which — and that survives the reword a phrase guard would not.
//
// AND THAT IS WHY IT IS HALF OF A PAIR. A slice can only prove the notes are
// inside a `CalibrationCardNote`; it cannot prove a `CalibrationCardNote` is a
// disclosure. `calibrationCardNote.test.tsx` proves that, by rendering one and
// asserting it is a `<details>` with no `open`. Neither suite is sufficient
// alone, and a future edit that defeats the sweep has to defeat both.
//
// THE TRAP THIS SUITE IS WRITTEN AROUND (calibration/1061, #4113): a guard that
// bans an assertion cannot be a substring test. `not.toMatch(/the curve is
// current/)` red-lit the FIX, because the honest way to withhold a claim in
// English is to negate it in front of the reader. So nothing here bans a
// phrase from the file. It asserts WHERE a phrase is.

import * as fs from "fs";
import * as path from "path";

const PAGE = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const SOURCE: string = fs.readFileSync(PAGE, "utf8");

const OPEN = "<CalibrationCardNote";
const CLOSE = "</CalibrationCardNote>";

/**
 * The `[start, end)` spans of every `<CalibrationCardNote>…</CalibrationCardNote>`.
 *
 * A flat scan, deliberately: these do not nest, and a parser that silently
 * tolerated nesting would also silently tolerate an unclosed tag — which is the
 * one malformation that would make every `isInsideANote` answer true.
 */
function noteRegions(source: string): Array<[number, number]> {
  const spans: Array<[number, number]> = [];
  let from = 0;
  for (;;) {
    const open = source.indexOf(OPEN, from);
    if (open === -1) break;
    const close = source.indexOf(CLOSE, open);
    if (close === -1) throw new Error(`unclosed ${OPEN} at index ${open}`);
    spans.push([open, close + CLOSE.length]);
    from = close + CLOSE.length;
  }
  return spans;
}

const REGIONS = noteRegions(SOURCE);

function isInsideANote(needle: string): boolean {
  const at = SOURCE.indexOf(needle);
  if (at === -1) throw new Error(`not in page.tsx at all: ${JSON.stringify(needle)}`);
  return REGIONS.some(([start, end]) => at >= start && at < end);
}

/**
 * The blocks the sweep moved, by a fragment that identifies each uniquely.
 *
 * Fragments, not whole sentences, and no line numbers: a comment moving above a
 * block must not red this suite, and neither must an editorial reword of the
 * note's own wording — the claim is about location.
 */
const MOVED_BEHIND_A_DISCLOSURE: ReadonlyArray<readonly [string, string]> = [
  ["the provider note (Queue 316 item 2)", 'data-testid="calibration-provider-note"'],
  ["what ECE and MCE are", "worst-bucket sensitivity"],
  ["the traded/untraded proxy note", "receive trading volume for most of these markets"],
  ["how to read the matched-bucket table", "Error is actual minus predicted"],
  ["why a thin category is not published", "A calibration curve is only honest with enough"],
  // #4291 (calibration/1065) — the two cards #4118's sweep did not reach. They
  // are the furthest down the page, which is why calibration/1063's LOOK stopped
  // above them and why they are a second queue rather than an oversight caught
  // in review. Both photographed bare on production at 390px before this ship.
  ["how to read the By Category dots", "hollow dots with wide error bars"],
  ["which categories are excluded and why", "statistical noise, not a calibration signal"],
  ["which population the category table counts", 'data-testid="calibration-category-population-note"'],
] as const;

describe("standing notice 34 — the method notes are not in the page body", () => {
  test.each(MOVED_BEHIND_A_DISCLOSURE)(
    "%s sits inside a CalibrationCardNote",
    (_what, fragment) => {
      expect(isInsideANote(fragment)).toBe(true);
    },
  );

  // POSITIVE AND NEGATIVE CONTROL ON THE SLICE ITSELF. Every assertion above is
  // worthless if `noteRegions` returns one span covering the file (everything
  // reads as inside) or no spans at all with a truthy default (nothing would).
  // A control that can only fail alongside the ship is a duplicate of the ship;
  // these two fail on the two ways the parser can lie, and neither can be
  // satisfied by the page being correct.
  test("the slice discriminates: the hero heading is NOT inside a note", () => {
    expect(isInsideANote("Do Prediction Markets Predict Anything?")).toBe(false);
  });

  test("the slice found the disclosures at all, and more than one", () => {
    // Bounded both ways rather than pinned to a count. Fewer than two spans
    // means the parser is not finding them; more than one per moved block means
    // it is finding something that is not a note. It is legitimately not 1:1 —
    // Source Comparison folds two of the five blocks (what a row is, and what
    // ECE and MCE are) into a single note, because two disclosures stacked on
    // one card is the noise this ship exists to remove.
    expect(REGIONS.length).toBeGreaterThan(1);
    expect(REGIONS.length).toBeLessThanOrEqual(MOVED_BEHIND_A_DISCLOSURE.length);
    // No span may swallow the file: a note is a paragraph or two, not a page.
    for (const [start, end] of REGIONS) {
      expect(end - start).toBeLessThan(SOURCE.length / 4);
    }
  });

  // ═══ #4291 — THE TWO CARDS AT THE FOOT OF THE PAGE ═══
  //
  // `isInsideANote` throws on a fragment that is not in the file at all, so the
  // three rows added above already fail the DELETE mutant as loudly as they fail
  // the leave-it-in-the-body one: the claim "moved, not deleted" is carried by
  // the same assertion. What it does NOT carry is the two things that make the
  // move honest rather than a disappearance, so they are asserted here.

  test("the pooled-row counts still travel as data, not as a sentence", () => {
    // The population note is the block notice 34 objects to most (a coverage
    // count in the page body), and the cheapest way to satisfy that objection is
    // to drop it. These attributes are how the rails read the same numbers, and
    // they are what makes moving it different from losing it — the same pairing
    // the drift clause gets below.
    expect(SOURCE).toContain("data-pooled-rows={pooledRenderedRowCount}");
    expect(SOURCE).toContain("data-total-rows={categoryMetrics.length}");
  });

  test.each([
    ["By Category", "One curve per category. Select a tab to change it."],
    ["Category Breakdown", "Every published category, sorted by ECE. Lower is better."],
  ])("%s leads with a caption, and it is NOT itself folded away", (_card, caption) => {
    // Notice 34 allows "at most one short caption" and #4118 shipped one on
    // every card it swept. A card whose whole subhead went behind the disclosure
    // passes every assertion above while handing the reader a heading and a grey
    // "How to read this" — which is not what the notice asks for. Location
    // again, both ways: present, and outside.
    expect(SOURCE).toContain(caption);
    expect(isInsideANote(caption)).toBe(false);
  });

  // The one thing the sweep DELETED rather than moved: the currency banner's
  // ", and 128 of 128 units have drifted since".
  //
  // It is a coverage count in the page body — the shape notice 34 names first —
  // and "units" is undefined jargon on a reader's screen (notice 19). The
  // warning it sat in is untouched: the banner still dates the inputs and still
  // says the curve describes the market as of then.
  //
  // Asserted as ABSENCE OF THE CALL, not absence of a phrase, for the reason in
  // this file's header — and because the sentence is composed at runtime from a
  // payload, so no literal of it exists here to ban.
  //
  // The ban is on the CALL — `stalenessDriftClause(` with its paren — not on
  // the identifier: the page keeps a comment naming the function to say why it
  // is no longer called, and a ban a correct explanation cannot survive is the
  // #4113 trap again in a smaller frame.
  test("the banner does not render a drifted-units count", () => {
    expect(SOURCE).not.toContain("stalenessDriftClause(");
    expect(SOURCE).not.toContain("driftClause ?");
  });

  test("but the drift still travels, as data, where the notice sends it", () => {
    // The ban above must not be satisfiable by dropping the disclosure. This is
    // the same pairing `calibrationBannerCopy.test.tsx` makes for the staged-at
    // date: the count leaves the sentence, it does not leave the page.
    expect(SOURCE).toContain("data-units-drifted");
    expect(SOURCE).toContain("data-units-banked");
  });

  test("and the warning the count sat inside is still a warning", () => {
    expect(SOURCE).toContain("the market data behind it was last staged");
    expect(SOURCE).toContain("So it describes the market as of then, not now.");
    expect(SOURCE).toContain("staleness.stagedAgeS");
  });
});
