/**
 * #10340 (heading half) — before kickoff a game page said "script" twice.
 *
 * The duplicate-only slice (PR #10400) stopped THE SCRIPT repeating rows the
 * "All N props" fold already draws. What remained was two headings that both
 * said "script": the rail's "The script" and this section's own. Root's
 * decision (`10340-SUPPLEMENTAL-HEADING-DECISION.md`): the rail keeps the name;
 * the section that is left, on that pregame path only, is "More props" —
 * "Additional market questions for this game." — with no secondary "Props".
 * Every other state and every other caller keeps its heading.
 */
import { readFileSync } from "fs";
import { join } from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";

const ITEMS: PropMark[] = [
  { key: "Total Runs|Over 7.5", label: "Over 7.5 runs", pregame_mark: 0.52, current: 0.55, graded_result: null },
  { key: "First Inning|Yes", label: "Run in the 1st", pregame_mark: 0.41, current: 0.44, graded_result: null },
];

/** The header row: the eyebrow span and, if present, the secondary title span. */
function header(html: string) {
  const eyebrow = html.match(/tracking-\[0\.1em\] text-text-primary">([^<]*)<\/span>/)?.[1] ?? null;
  const title = html.match(/<span class="text-sm text-text-secondary">([^<]*)<\/span>/)?.[1] ?? null;
  const blurb = html.match(/<p class="text-xs text-text-muted mb-4">([^<]*)<\/p>/)?.[1] ?? null;
  return { eyebrow, title, blurb };
}

describe("#10340 — the pregame supplemental section is headed as what it is", () => {
  it("before kickoff, supplemental: 'More props', the neutral description, no 'Props'", () => {
    const html = renderToStaticMarkup(
      <PropsSection items={ITEMS} eventStatus="scheduled" supplemental />
    );
    expect(header(html)).toEqual({
      eyebrow: "More props",
      title: null,
      blurb: "Additional market questions for this game.",
    });
    expect(html).not.toContain("The script");
    // The rows themselves are untouched.
    expect(html).toContain("Over 7.5 runs");
    expect(html).toContain("Run in the 1st");
    expect(html).toContain("55%");
  });

  it("CONTROL — the ordinary standalone section keeps THE SCRIPT's heading", () => {
    const html = renderToStaticMarkup(<PropsSection items={ITEMS} eventStatus="scheduled" />);
    expect(header(html)).toEqual({
      eyebrow: "The script",
      title: "Props",
      blurb: "What the market expects before the event.",
    });
  });

  it("CONTROL — live ignores supplemental: still THE DIVERGENCE", () => {
    const html = renderToStaticMarkup(
      <PropsSection items={ITEMS} eventStatus="live" supplemental />
    );
    expect(header(html)).toEqual({
      eyebrow: "The divergence",
      title: "Props",
      blurb: "How far the live number has moved from the pregame script.",
    });
  });

  it("CONTROL — final ignores supplemental: still WHAT HIT, graded", () => {
    const graded: PropMark[] = ITEMS.map((i, n) => ({ ...i, graded_result: n === 0 ? "hit" : "miss" }));
    const html = renderToStaticMarkup(
      <PropsSection items={graded} eventStatus="completed" supplemental />
    );
    expect(header(html)).toEqual({
      eyebrow: "What hit",
      title: "Props",
      blurb: "The pregame script, graded.",
    });
  });

  it("CONTROL — empty content still renders nothing", () => {
    expect(
      renderToStaticMarkup(<PropsSection items={[]} eventStatus="scheduled" supplemental />)
    ).toBe("");
  });

  it("the event page asks for it only on the known-pregame path where the fold mounts", () => {
    const page = readFileSync(join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
    // Same `knownPregame` that gates the duplicate filter, and the same
    // `player_props` condition the rail and the "All N props" fold mount on.
    expect(page).toContain(
      "supplemental={knownPregame && (gameMarkets?.player_props?.length ?? 0) > 0}"
    );
    expect(page.match(/supplemental=/g)).toHaveLength(1);
  });
});
