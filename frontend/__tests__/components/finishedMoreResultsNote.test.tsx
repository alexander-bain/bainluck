// #5860 — THE CAPTION UNDER /sports "FINISHED" MAY NOT CLAIM AN ORDER ITS POOL
// WAS NOT SELECTED BY.
//
// ═══ THE DEFECT ═══
//
// The line read "Showing the 4 most recent — more in NCAA Football, MLS and
// MLB." On production 2026-09-13 08:55Z the four cards it described were all
// Saturday-afternoon finals, and the five games that had actually ended most
// recently — Hawaii 07:24Z, USC 06:16Z, Utah, Fresno State and Nevada 06:01Z —
// were not on the rail at all. The section's SORT is recency and is correct
// (`buildFinishedSection`, guarded in `sportsFinishedSection.test.ts`); the pool
// it sorts is the score-ranked feed window, whose most recently ended member was
// 05:44Z. So the sentence was false about the only thing it asserted.
//
// ═══ WHAT THIS FILE PINS ═══
//
// That the rendered line makes no completeness claim, and that it still leads
// somewhere. RENDERED, NOT GREPPED (#2060): the claim is about markup, so the
// note was lifted out of `app/sports/page.tsx` — which has no render harness —
// into a component that can be rendered with real props.
//
// The recency-ordered pool is the backend arm of #5860 and is not ux's file set
// (notice 41); nothing here would catch it, and this file does not pretend to.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { FinishedMoreResultsNote } from "@/components/sports/FinishedMoreResultsNote";
import type { LeagueResultsLink } from "@/lib/sports/finishedSection";

const NCAAF: LeagueResultsLink = {
  label: "NCAA Football",
  href: "/sport/football/ncaaf",
};
const MLS: LeagueResultsLink = { label: "MLS", href: "/sport/soccer/mls" };
const MLB: LeagueResultsLink = { label: "MLB", href: "/sport/baseball/mlb" };

function render(props: Parameters<typeof FinishedMoreResultsNote>[0]): string {
  return renderToStaticMarkup(<FinishedMoreResultsNote {...props} />);
}

describe("the Finished cap note does not claim to be the most recent results", () => {
  test("no ordering claim survives anywhere in the rendered line", () => {
    const markup = render({ cappedMore: true, links: [NCAAF, MLS, MLB] });

    // The exact sentence that was false, and the two weaker forms of the same
    // claim a later edit would reach for.
    expect(markup).not.toContain("most recent");
    expect(markup).not.toContain("Showing the");
    expect(markup).not.toContain("latest");
  });

  test("CONTROL: it does render, and every capped-out league is reachable", () => {
    // Without this the test above is green for a component that returns null in
    // every state — the vacuous shape an absence assertion is most prone to.
    const markup = render({ cappedMore: true, links: [NCAAF, MLS, MLB] });

    expect(markup).toContain("More results in");
    expect(markup).toContain('href="/sport/football/ncaaf"');
    expect(markup).toContain('href="/sport/soccer/mls"');
    expect(markup).toContain('href="/sport/baseball/mlb"');
    // A sentence a reader finishes: "More results in A, B and C." — commas
    // between, "and" before the last, a full stop at the end.
    //
    // Asserted as markup fragments rather than by stripping the tags: a
    // `replace(/<[^>]*>/g, "")` here reads to CodeQL as an incomplete HTML
    // sanitiser (`js/incomplete-multi-character-sanitization`, high severity)
    // and refuses the sha under notice 32. The rule is right about the shape
    // even though this one only ever sees its own render.
    expect(markup).toContain(">More results in ");
    expect(markup).toContain(">NCAA Football</a>");
    expect(markup).toContain("<span>, <a ");
    expect(markup).toContain("<span> and <a ");
    expect(markup).toContain(">MLB</a></span>.</p>");
  });

  test("one league is named without a stray comma or conjunction", () => {
    const markup = render({ cappedMore: true, links: [MLB] });

    expect(markup).toContain(">More results in ");
    expect(markup).toContain(">MLB</a></span>.</p>");
    expect(markup).not.toContain(" and ");
    expect(markup).not.toContain("<span>, ");
  });

  test("nothing was capped: no line at all", () => {
    // The section showed everything it had. A note here would be about nothing.
    expect(render({ cappedMore: false, links: [NCAAF] })).toBe("");
  });

  test("capped, but the register knows none of the leagues: no line at all", () => {
    // The pre-#5860 code rendered the bare claim with no destination in this
    // state. "More results in ." is not a sentence, and "there are more,
    // somewhere" is diagnostic prose on a reader's screen (notice 34). The
    // section's own count badge already says how many are shown.
    expect(render({ cappedMore: true, links: [] })).toBe("");
  });

  test("the probe handle the /sports LOOK reads is still on the line", () => {
    expect(render({ cappedMore: true, links: [MLB] })).toContain(
      'data-testid="finished-cap-note"',
    );
  });
});
