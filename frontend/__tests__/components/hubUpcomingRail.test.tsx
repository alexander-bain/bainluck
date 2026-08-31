/**
 * UX-P210, repairing CERT-525 — NOTHING AROUND A CARD MAY CLAIM ITS PHASE EITHER.
 *
 * CERT-519 blocked a card that said "Upcoming" about a live US Open. UX-P209
 * silenced the card. CERT-525 blocked the same sentence one level up:
 *
 *   > Unknown tennis cards lose the per-card Upcoming pill but remain directly
 *   > beneath the visible `Upcoming Tournaments` heading, so the hub still
 *   > makes the same unsupported phase claim one level up. The new render tests
 *   > exercise `StatusPill` in isolation and cannot see this surrounding claim.
 *
 * That last sentence is the brief for this file. A pill test renders a pill and
 * can only report on a pill. What Alex sees is a section, so this renders the
 * SECTION — `HubUpcomingRail`, the component the page ships — and asks the
 * question about everything visible in it, not about one element.
 *
 * ── THE ASSERTION SHAPE, WHICH IS THE OTHER HALF OF CERT-519'S LESSON ────────
 *
 * UX-P209's guard asserted `"live"` was absent, and that same assertion passed
 * for the rail that said "we cannot tell" AND for the rail that said the
 * opposite lie. An assertion about absence is half an assertion. So every case
 * here pins the whole disjunction: no affirmative phase word anywhere in the
 * rendered section, AND the exact heading that should be there — so swapping
 * the word, inventing a third one, or dropping the heading entirely all fail.
 *
 * The controls matter as much as the cases: a rail whose cards really are all
 * upcoming must KEEP "Upcoming Tournaments" (gotcha #43, both directions). A
 * guard that just deleted the word would pass every case below and destroy the
 * heading.
 *
 * ── WHY IT READS VISIBLE TEXT AND NOT THE MARKUP ─────────────────────────────
 *
 * There is no jsdom here, so this renders to static markup like its sibling.
 * The phase assertions run against `visibleText`, with tags AND attributes
 * stripped, because the section's own hooks (`data-testid="hub-upcoming-rail"`)
 * contain the word "upcoming" and a raw-markup scan would fail on a correct
 * file — UX-P205-4's over-reporting grep, in miniature. Heading PRESENCE is the
 * one thing read off the markup, since an absent element has no text to see
 * (the `visibleText`-blind-to-an-empty-element trap).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { HubUpcomingRail } from "@/components/hub/HubUpcomingRail";
import type { HubUpcoming } from "@/lib/api";

/** Visible words, with markup and attributes stripped the way a reader sees it. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&[a-z]+;|&#x?[0-9a-f]+;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const HEADING_HOOK = 'data-testid="hub-upcoming-heading"';

/** The heading's own text, or null when the section renders no heading. */
function headingText(markup: string): string | null {
  // `[\s\S]` rather than `.` with the `s` flag — the TS target here predates
  // dotAll, and the typecheck ratchet catches it (TS1501).
  const m = markup.match(/<h2[^>]*data-testid="hub-upcoming-heading"[^>]*>([\s\S]*?)<\/h2>/);
  return m ? visibleText(m[1]) : null;
}

function card(over: Partial<HubUpcoming> & { status: string }): HubUpcoming {
  return {
    key: "event:tennis:us-open",
    name: "US Open",
    domain: "tennis",
    start_date: "2026-09-13T00:00:00+00:00",
    is_major: false,
    ...over,
  } as HubUpcoming;
}

function renderRail(props: {
  cards: HubUpcoming[];
  label?: string | null;
  neutralLabel?: string | null;
}): string {
  return renderToStaticMarkup(<HubUpcomingRail {...props} />);
}

const TENNIS = { label: "Upcoming Tournaments", neutralLabel: "Tournaments" };

/** Every word the rail is forbidden to say about a phase it has not established. */
const AFFIRMATIVE_PHASE_WORDS = [/upcoming/i, /\blive\b/i, /\bfinal\b/i, /\bsettled\b/i];

describe("the rail is the thing under test, and it renders", () => {
  it("renders the real section with its cards", () => {
    // Vacuity control FIRST: an empty render would pass every "does not say"
    // assertion in this file. The card's own content must be on screen.
    const markup = renderRail({ cards: [card({ status: "unknown" })], ...TENNIS });
    expect(markup).toContain('data-testid="hub-upcoming-rail"');
    expect(visibleText(markup)).toContain("US Open");
  });

  it("can report a heading when there is one", () => {
    // The companion control: `headingText` returning null must mean absent, not
    // broken. Proved against the case that HAS a heading.
    const markup = renderRail({ cards: [card({ status: "upcoming" })], ...TENNIS });
    expect(markup).toContain(HEADING_HOOK);
    expect(headingText(markup)).toBe("Upcoming Tournaments");
  });
});

describe("a card whose phase we cannot establish is not surrounded by a phase claim", () => {
  it("prints the noun and no WHEN over an unknown card", () => {
    const markup = renderRail({ cards: [card({ status: "unknown" })], ...TENNIS });

    // Not X ...
    for (const word of AFFIRMATIVE_PHASE_WORDS) {
      expect(visibleText(markup)).not.toMatch(word);
    }
    // ... and not not-X: the heading is present and is exactly the neutral noun,
    // so removing it, or reaching for a third invented word, fails here.
    expect(headingText(markup)).toBe("Tournaments");
  });

  it("stays neutral when one unknown card sits among genuine upcoming ones", () => {
    /**
     * The mixed rail is the production shape and the easy thing to get wrong: a
     * heading covers everything under it, so one card it cannot describe is
     * enough to cost the claim. A rule reading only the FIRST card, or a
     * majority, would pass the case above and fail here.
     *
     * ⚠️ NOTE THE ASSERTION IS NOT THE ONE ABOVE, AND THE DIFFERENCE IS THE
     * POINT. The first draft swept the whole section for "upcoming" here too
     * and went red on correct code: the Laver Cup card IS upcoming, its lister
     * asserted so, and its pill is entitled to say it. Banning that would be
     * this ship's own bug in a mirror — silencing a supported claim instead of
     * an unsupported one. So what is counted is how many times the section says
     * it: once, by the one card that may.
     */
    const markup = renderRail({
      cards: [
        card({ key: "event:tennis:laver-cup", name: "Laver Cup", status: "upcoming" }),
        card({ status: "unknown" }),
      ],
      ...TENNIS,
    });
    const said = visibleText(markup).match(/upcoming/gi) || [];
    expect(said).toHaveLength(1); // the Laver Cup pill, and nothing else
    expect(headingText(markup)).toBe("Tournaments");
  });
});

describe("a live card is not filed under Upcoming either", () => {
  it("drops the affirmative heading when the rail holds a live card", () => {
    /**
     * Broader than the `unknown` case the cert names, deliberately — see the
     * helper's header. All four listers admit `live` by default, so "Upcoming
     * Cards" over a live UFC card is the identical false claim, reachable today
     * without any tennis involved. The card's own pill still says Live, which
     * is a claim the lister CAN support; what goes is the section asserting the
     * opposite around it.
     */
    const markup = renderRail({
      cards: [card({ key: "event:ufc:ufc-320", name: "UFC 320", status: "live" })],
      label: "Upcoming Cards",
      neutralLabel: "Cards",
    });
    expect(visibleText(markup)).not.toMatch(/upcoming/i);
    expect(headingText(markup)).toBe("Cards");
    // The pill keeps its supported claim — this fix removes an unsupported
    // statement, it does not blind the rail.
    expect(visibleText(markup)).toMatch(/\bLive\b/);
  });
});

describe("the control: a rail that IS upcoming keeps saying so", () => {
  it("prints the affirmative heading when every card is upcoming", () => {
    const markup = renderRail({
      cards: [
        card({ status: "upcoming" }),
        card({ key: "event:tennis:laver-cup", name: "Laver Cup", status: "upcoming" }),
      ],
      ...TENNIS,
    });
    expect(headingText(markup)).toBe("Upcoming Tournaments");
  });
});

describe("no usable neutral word lands on a true one, never the affirmative one", () => {
  it("falls back to a phase-free noun when a stale payload carries no neutral twin", () => {
    /**
     * The hub mirror lives up to 24h, so for a day after deploy some payloads
     * have `upcoming_label` and no neutral. Falling back to the affirmative
     * label would reinstate the exact defect for the one population a deploy
     * cannot reach; falling back to "Events" keeps a heading that is true of
     * every rail. Both halves are asserted, because "not Upcoming" alone is
     * satisfied by dropping the heading altogether.
     */
    const markup = renderRail({
      cards: [card({ status: "unknown" })],
      label: "Upcoming Tournaments",
      neutralLabel: undefined,
    });
    expect(visibleText(markup)).not.toMatch(/upcoming/i);
    expect(headingText(markup)).toBe("Events");
    expect(visibleText(markup)).toContain("US Open");
  });

  it("refuses a neutral label that smuggles a phase word back in", () => {
    /**
     * A config typo or a copy-pasted new hub. The backend refuses this too
     * (`TestHubNeutralUpcomingLabel`); the two checks are independent on
     * purpose, so a mistake at either end is absorbed rather than rendered.
     */
    const markup = renderRail({
      cards: [card({ status: "unknown" })],
      label: "Upcoming Tournaments",
      neutralLabel: "Upcoming Tournaments",
    });
    expect(visibleText(markup)).not.toMatch(/upcoming/i);
    expect(headingText(markup)).toBe("Events");
  });
});
