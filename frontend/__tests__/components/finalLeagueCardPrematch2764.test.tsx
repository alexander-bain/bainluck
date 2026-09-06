// #2764 — A FINAL CARD ON A LEAGUE, TEAM OR SEARCH PAGE SHOWS WHAT THE MARKET
// GAVE EACH SIDE BEFORE THE MATCH.
//
// ═══ THE DEFECT ═══
//
// Alex, reading /sports "Just Happened" at phone width (ux/1036, 2026-09-02):
// *"How come none of these show pre-event probability?"* ux/1036 answered that
// for the three surfaces he named — `FeedCard`, Discover's
// `components/discover/EventCard.tsx`, and the tennis hub's Finished list.
//
// `components/EventCard.tsx` is a FOURTH surface and a different file: the
// shared card on `/sport/[sport]/[league]`, team pages and search results. It
// reached the same gap from the opposite direction. It DOES compute the
// numbers for a settled event —
//
//     if (isFinishedStatus(event.status) && opening) {
//       homeProb = opening.home_probability;   <- computed
//       awayProb = opening.away_probability;
//
// — and then renders neither, because both probability chips are gated
// `!isFinished` (L2-112 Item 2) and the `Opened X/Y` footer is gated
// `!isFinished` too. So the numbers were derived and dropped on the floor, and
// a FINAL card there printed a centred score block and no pre-match figure at
// all.
//
// ═══ WHY THE BOOKS RUNG, AND WHY IT IS LABELLED ═══
//
// The Scope section of #2764 offers two routes: widen `Event` + the
// `/api/events/*` serializers so this surface gets the server-resolved ladder,
// or ship the books rung and say so. This takes the second. `Event` has no
// `prematch_odds` key — only `/api/feed` resolves Alex's Kalshi → Polymarket →
// books ladder server-side — so the card takes `lib/prematchReading.ts`'s
// documented `opening_odds` fallback, which labels itself `books`. That is
// honest rather than lossy: the sole writer of `Event.opening_*` is
// `_maybe_set_opening_odds`, a median across whichever sportsbooks were still
// quoting (#1841). An UNLABELLED books number is the old `Opened 40/60`
// footnote with a new shape, which is the thing ux/1036 removed.
//
// Reading through `prematchReading` rather than off `opening_odds` directly is
// what keeps this from becoming a fourth copy of one decision: the rounding
// (`servedDuelPercents`, so the pair rounds ONCE and cannot print 101 —
// UX-P114), the `0 < p < 1` usability rejection and the label all come from the
// module. `servedDuelPercents(a, h, null, null)` delegates to
// `renderedDuelPercents`, which is exactly what this card's own `Opened X/Y`
// already used, so the pair is bit-identical to what the live footer printed.
//
// ═══ THE ARM THAT IS NOT ABOUT THE NUMBERS ═══
//
// `homeFavorite` drives which team NAME is emphasised. On a settled card it
// reads `homeProb`/`awayProb`, which the branch quoted above has already
// swapped to the OPENING line — so a FINAL card emphasised the PRE-MATCH
// FAVOURITE's name while the score block three lines above it bolded the
// WINNER's. On any upset the card disagreed with itself. That was survivable
// while the card printed no prior; printing one beside each name makes it
// loud, so this fixes it: names say what happened, grey numbers say what was
// thought. `winnerKnown` keeps the honest third case — a draw, or a finished
// row with no score — at equal weight rather than muting both sides, which
// would read as "they both lost".
//
// ═══ RED-FIRST, AND IT IS NOT DEGENERATE ═══
//
// Every arm below was run against the parent commit before the fix existed.
// `components/EventCard.tsx` is imported by this file and exists on BOTH sides,
// so a failure here is a real behavioural difference and not a missing module
// — the degenerate "pass" live/077 caught itself on and said so.
//
// Measured at the parent (`origin/master` 8e041ab4): **6 failed, 7 passed.**
// The 6 failures are the ship. Of the 7 passes, 5 are the CONTROL block —
// the live card, the pregame card, the score block, the absent footer and the
// "No price yet" rule — and they are what proves the change is confined to
// FINAL. The other 2 are the "prints nothing" arms (no reading, and a leaked
// settled price), which pass at the parent for the uninteresting reason that
// the parent prints nothing in EVERY case. They are stated as guards against
// over-rendering, not as evidence of the ship, and they earn their place only
// once the other 6 are green.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const Mock = ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
    React.createElement("a", { href, ...props }, children);
  return { __esModule: true, default: Mock };
});
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";
import { BOOKS_SOURCE, PREMATCH_SAID } from "@/lib/prematchReading";
import type { Event } from "@/lib/types";

const IN_THE_PAST = "2026-09-01T18:00:00Z";
const LONG_PAST = "2026-08-30T18:00:00Z";

function makeEvent(over: Partial<Event> = {}): Event {
  return {
    id: 15301400,
    external_id: "evt-15301400",
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: "Boston Red Sox",
    away_team: "New York Yankees",
    commence_time: LONG_PAST,
    status: "completed",
    home_score: 2,
    away_score: 7,
    home_team_data: { primary_color: "#2563eb", logo_small: "h.png" },
    away_team_data: { primary_color: "#64748b", logo_small: "a.png" },
    // The home side opened the favourite at 62/38 and LOST. The upset is
    // deliberate: it is the only shape in which "bold the winner" and "bold the
    // favourite" give different answers, so it is the only shape that can catch
    // the name-emphasis arm.
    opening_odds: {
      home_probability: 0.62,
      away_probability: 0.38,
      spread: null,
      over_under: null,
      favorite: "home",
    },
    ...over,
  } as unknown as Event;
}

const render = (event: Event): string => renderToStaticMarkup(<EventCard event={event} />);

/**
 * The class list of the anchor that renders `team`'s NAME.
 *
 * Deliberately not `html.indexOf(team)`: the card's outermost `<a>` carries an
 * `aria-label` of "Away at Home - Final", so the first occurrence of either
 * name is that label and the emphasis assertions would read the wrapper's
 * classes instead of the name link's. Matching the `/team/` href is what pins
 * this to `TeamNameLink`.
 */
function nameLinkClass(html: string, team: string): string {
  const re = new RegExp(`<a href="[^"]*/team/[^"]*" class="([^"]*)">${team}</a>`);
  const m = html.match(re);
  if (!m) throw new Error(`no team-name link found for ${team}`);
  return m[1];
}

/**
 * The visible text of an HTML fragment.
 *
 * A character walk rather than `.replace(/<[^>]*>/g, "")`, and not for style:
 * CodeQL flags that regex as `js/incomplete-multi-character-sanitization` at
 * HIGH severity, and it is right about the shape even though nothing here is
 * sanitizing anything — a single pass that deletes `<...>` spans can leave a
 * `<script` behind when the input is adversarial, so the pattern is worth not
 * having in the codebase at all. This is exact for the markup we control and
 * carries no such claim.
 */
function visibleText(fragment: string): string {
  let out = "";
  let inTag = false;
  for (const ch of fragment) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out;
}

/** The rendered text of the element carrying `data-testid`, tags stripped. */
function testid(html: string, id: string): string | null {
  const at = html.indexOf(`data-testid="${id}"`);
  if (at === -1) return null;
  const open = html.lastIndexOf("<", at);
  // Walk the tag stack from the opening tag so a nested <span> (the sr-only
  // prefix) does not end the slice early.
  let depth = 0;
  let i = open;
  while (i < html.length) {
    if (html.startsWith("</", i)) {
      depth -= 1;
      if (depth === 0) {
        const end = html.indexOf(">", i) + 1;
        return visibleText(html.slice(open, end)).replace(/\s+/g, " ").trim();
      }
      i = html.indexOf(">", i) + 1;
      continue;
    }
    if (html[i] === "<") {
      depth += 1;
      i = html.indexOf(">", i) + 1;
      continue;
    }
    i += 1;
  }
  return null;
}

describe("#2764 — the league/team/search FINAL card", () => {
  it("prints a pre-match percent beside EACH team", () => {
    const html = render(makeEvent());
    expect(testid(html, "event-card-prematch-home")).toContain("62%");
    expect(testid(html, "event-card-prematch-away")).toContain("38%");
  });

  it("names the team each number is about, for a reader who cannot see the layout", () => {
    const html = render(makeEvent());
    // A bare "62%" beside a name is paired by LAYOUT alone. The whole point of
    // the sr-only prefix is that a screen reader has no layout.
    expect(testid(html, "event-card-prematch-home")).toBe(
      `${PREMATCH_SAID} Boston Red Sox 62%`,
    );
    expect(testid(html, "event-card-prematch-away")).toBe(
      `${PREMATCH_SAID} New York Yankees 38%`,
    );
  });

  it("labels the reading as the sportsbook median it is, exactly once", () => {
    const html = render(makeEvent());
    expect(testid(html, "event-card-prematch-label")).toBe(`Pre-match · ${BOOKS_SOURCE}`);
    // ONE label for the pair, not one per row.
    expect(html.split('data-testid="event-card-prematch-label"')).toHaveLength(2);
  });

  it("carries the rung where a measurement can read it, on both sides", () => {
    const html = render(makeEvent());
    expect(html).toContain(`data-prematch-source="${BOOKS_SOURCE}"`);
    expect(html).toContain('data-prematch="0.62"');
    expect(html).toContain('data-prematch="0.38"');
  });

  it("bolds the team that WON, not the team that was favoured", () => {
    // The home side opened 62% and lost 2-7. Before the fix the emphasis read
    // `homeFavorite`, which on FINAL is computed off the OPENING line, so the
    // losing favourite was bold and the winner was not.
    const html = render(makeEvent());
    expect(nameLinkClass(html, "New York Yankees")).toContain("font-semibold");
    expect(nameLinkClass(html, "Boston Red Sox")).not.toContain("font-semibold");
    expect(nameLinkClass(html, "Boston Red Sox")).toContain("text-text-muted");
  });

  it("emphasises NEITHER side when the result names no winner", () => {
    // A draw, and the finished-with-no-score row, are the same question. Muting
    // both would say "they both lost".
    const drawn = render(makeEvent({ home_score: 3, away_score: 3 }));
    expect(nameLinkClass(drawn, "Boston Red Sox")).not.toContain("font-semibold");
    expect(nameLinkClass(drawn, "Boston Red Sox")).not.toContain("text-text-muted");
    expect(nameLinkClass(drawn, "New York Yankees")).not.toContain("font-semibold");
    // ...and the numbers are still there: no winner is not no reading.
    expect(testid(drawn, "event-card-prematch-home")).toContain("62%");
  });

  it("prints nothing at all when we hold no pre-match reading", () => {
    const html = render(makeEvent({ opening_odds: undefined }));
    expect(testid(html, "event-card-prematch-home")).toBeNull();
    expect(testid(html, "event-card-prematch-away")).toBeNull();
    expect(testid(html, "event-card-prematch-label")).toBeNull();
  });

  it("prints nothing for a settled price that leaked backwards past the clock filter", () => {
    // `prematchReading` rejects the endpoints: an opening of exactly 1 is not a
    // prior, it is a result, and it would print as the loudest claim on the card.
    const html = render(
      makeEvent({
        opening_odds: {
          home_probability: 1,
          away_probability: 0,
          spread: null,
          over_under: null,
          favorite: "home",
        },
      } as Partial<Event>),
    );
    expect(testid(html, "event-card-prematch-home")).toBeNull();
    expect(testid(html, "event-card-prematch-label")).toBeNull();
  });
});

describe("#2764 CONTROLS — every other state of this card is untouched", () => {
  it("leaves the LIVE card exactly as it was: Opened X/Y, and no per-team prior", () => {
    const html = render(
      makeEvent({
        status: "live",
        commence_time: IN_THE_PAST,
        current_odds: {
          captured_at: IN_THE_PAST,
          home_probability: 0.44,
          away_probability: 0.56,
          spread: null,
          over_under: null,
          projected_home_score: null,
          projected_away_score: null,
        },
      } as Partial<Event>),
    );
    expect(testid(html, "event-card-prematch-home")).toBeNull();
    expect(testid(html, "event-card-prematch-label")).toBeNull();
    // The footnote this issue is NOT about still stands on the live card.
    expect(html).toContain("Opened");
    expect(html).toContain("62/38");
  });

  it("leaves the PREGAME card's chips and emphasis alone", () => {
    const html = render(
      makeEvent({
        status: "scheduled",
        commence_time: "2099-01-01T00:00:00Z",
        home_score: null,
        away_score: null,
        current_odds: {
          captured_at: IN_THE_PAST,
          home_probability: 0.815,
          away_probability: 0.185,
          spread: null,
          over_under: null,
          projected_home_score: null,
          projected_away_score: null,
        },
      } as Partial<Event>),
    );
    expect(testid(html, "event-card-prematch-home")).toBeNull();
    // The pregame favourite is still emphasised off the LIVE blend, and still
    // via text-text-primary rather than the settled card's font-semibold.
    expect(nameLinkClass(html, "Boston Red Sox")).toContain("text-text-primary");
    expect(nameLinkClass(html, "Boston Red Sox")).not.toContain("font-semibold");
    expect(nameLinkClass(html, "New York Yankees")).toContain("text-text-secondary");
  });

  it("still shows the settled score block, bolding the winning score", () => {
    const html = render(makeEvent());
    expect(html).toContain("Final");
    expect(html).toContain(">7<");
    expect(html).toContain(">2<");
  });

  it("does not resurrect Proj or Opened on a settled card", () => {
    const html = render(makeEvent());
    expect(html).not.toContain("Opened");
    expect(html).not.toContain("Proj");
  });

  it("says 'No price yet' on an unpriced pregame card, and not on a settled one", () => {
    // #2882's rule is a pregame statement. A settled card carries its own whole
    // statement (the score block), and must not also claim an absence.
    const pregame = render(
      makeEvent({
        status: "scheduled",
        commence_time: "2099-01-01T00:00:00Z",
        home_score: null,
        away_score: null,
        opening_odds: undefined,
        current_odds: undefined,
      } as Partial<Event>),
    );
    expect(pregame).toContain("No price yet");

    const settled = render(makeEvent({ opening_odds: undefined }));
    expect(settled).not.toContain("No price yet");
  });
});
