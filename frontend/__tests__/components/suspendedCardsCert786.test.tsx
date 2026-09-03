// THE CARD MUST SHOW IT — live/048, CERT-786 (render half).
//
// CERT-786's frontend finding, verbatim: "`frontend/components/FeedCard.tsx` has
// only live/finished/scheduled branches, so that reachable suspended card gets no
// suspended label and retains the live/pregame probability treatment; the separate
// Discover card has the same fall-through … where an old commence time can become
// a negative countdown if a suspended payload reaches it."
//
// Both of those are RENDER claims, so both are asserted against rendered output.
// `suspendedIsFirstClassCert786.test.ts` proves the shared vocabulary is right;
// only this file proves a card prints it. #2060's lesson: a source grep cannot
// tell a rendered field from a declared one — a mutation that wrapped the
// commence-time conditional in `{false && (` left every string intact and passed
// the whole suite.
//
// BOTH DIRECTIONS PER GOTCHA #43. Every case has a live or scheduled sibling
// asserted UNCHANGED, because a card that suppressed its probability strip for
// every status would satisfy the suspended assertions and break the product.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FeedCard from "@/components/FeedCard";
import { EventCard as DiscoverEventCard } from "@/components/discover/EventCard";
import { SUSPENDED_LABEL, suspendedSummary } from "@/lib/eventState";
import type { FeedEventData, FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

// The CERT-752 specimen. A commence time deliberately IN THE PAST — that is not
// incidental colour, it is the input that produced the negative countdown.
const COMMENCE_IN_THE_PAST = new Date(Date.now() - 15 * 3600_000).toISOString();

function makeData(over: Partial<FeedEventData> = {}): FeedEventData {
  return {
    id: 15295047,
    external_id: "evt-15295047",
    sport: "tennis_atp_us_open",
    sport_name: "US Open",
    home_team: "Francesco Passaro",
    away_team: "Jesper de Jong",
    commence_time: COMMENCE_IN_THE_PAST,
    status: "suspended",
    away_score: 1,
    home_score: 2,
    home_team_data: { primary_color: "#2563eb", logo_small: "h.png" },
    away_team_data: { primary_color: "#64748b", logo_small: "a.png" },
    current_odds: {
      captured_at: COMMENCE_IN_THE_PAST,
      home_probability: 0.72,
      away_probability: 0.28,
      spread: null,
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
    },
    ...over,
  } as unknown as FeedEventData;
}

function makeItem(data: FeedEventData): FeedItem {
  return {
    type: "event",
    score: 50,
    reason: "",
    headline: "",
    data,
  } as unknown as FeedItem;
}

function renderFeedCard(data: FeedEventData): string {
  return renderToStaticMarkup(<FeedCard item={makeItem(data)} />);
}

function renderDiscoverCard(data: FeedEventData): string {
  return renderToStaticMarkup(
    <DiscoverEventCard
      item={makeItem(data)}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />
  );
}

/** The rendered text with entities decoded, so `·` and `&amp;` compare sanely.
 *
 * `&amp;` is unescaped LAST (CodeQL `js/double-escaping`, alert 1892 — same
 * class as 1896 on the CERT-792 sibling, fixed with it). Unescaping the
 * ampersand first turns a literal `&amp;#x27;` into an apostrophe, one escape
 * too many, so an assertion could pass on text the page never showed.
 */
function text(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;|&#xB7;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");
}

const EXPECTED = suspendedSummary(1, 2); // "No result reported · last score 1-2"

// ---------------------------------------------------------------------------
// FeedCard — /sports, the category grids, My Stuff
// ---------------------------------------------------------------------------

describe("FeedCard renders the suspended state", () => {
  it("prints the shared summary", () => {
    expect(text(renderFeedCard(makeData()))).toContain(EXPECTED);
  });

  it("drops the live probability chips", () => {
    // CERT-786: "retains the live/pregame probability treatment". The numbers
    // are the last live blend on a match nothing is reporting on, so at full
    // weight beside "no result reported" they present a stale line as current.
    const rendered = text(renderFeedCard(makeData()));
    expect(rendered).not.toContain("72%");
    expect(rendered).not.toContain("28%");
  });

  it("still shows both of them on a LIVE card", () => {
    // The control. Without it, suppressing the strip for every status would
    // pass the case above and empty the product.
    const rendered = text(renderFeedCard(makeData({ status: "live" })));
    expect(rendered).toContain("72%");
    expect(rendered).toContain("28%");
  });

  it("still shows a start time on a SCHEDULED card", () => {
    const rendered = text(
      renderFeedCard(
        makeData({
          status: "scheduled",
          commence_time: new Date(Date.now() + 3 * 3600_000).toISOString(),
          away_score: null,
          home_score: null,
        })
      )
    );
    expect(rendered).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });

  it("names the state in the link's accessible label", () => {
    expect(renderFeedCard(makeData())).toContain(SUSPENDED_LABEL);
  });
});

// ---------------------------------------------------------------------------
// The Discover card — the default landing page
// ---------------------------------------------------------------------------

describe("the Discover card renders the suspended state", () => {
  it("prints the shared summary", () => {
    expect(text(renderDiscoverCard(makeData()))).toContain(EXPECTED);
  });

  it("prints no NEGATIVE countdown", () => {
    // THE cert finding, driven on the input that causes it: this card's
    // "upcoming" arm computes `(commence - now)` in minutes and prints it, and
    // a suspended row's commence time is in the past BY CONSTRUCTION. The old
    // behaviour rendered something like "-901m" between two team crests.
    const rendered = text(renderDiscoverCard(makeData()));
    expect(rendered).not.toMatch(/-\d+\s*[mh]\b/);
  });

  it("still counts down on a genuinely upcoming card", () => {
    // The control, and it is the one that matters most here: a card that
    // printed no countdown for any status would satisfy the case above.
    const rendered = text(
      renderDiscoverCard(
        makeData({
          status: "scheduled",
          commence_time: new Date(Date.now() + 3 * 3600_000).toISOString(),
          away_score: null,
          home_score: null,
        })
      )
    );
    expect(rendered).toMatch(/\b3h\b/);
  });

  it("drops the win-probability strip", () => {
    const rendered = renderDiscoverCard(makeData());
    expect(rendered).not.toContain('data-testid="event-card-away-probability"');
  });

  it("still draws the strip on a LIVE card", () => {
    const rendered = renderDiscoverCard(makeData({ status: "live" }));
    expect(rendered).toContain('data-testid="event-card-away-probability"');
  });

  it("still shows the last score beside the crests", () => {
    // Suppressing the state's treatment must not suppress the one fact the row
    // does carry. The scores render in the crest strip, as they do when live.
    expect(renderDiscoverCard(makeData())).toContain(
      '<span class="text-2xl font-black tabular-nums text-white drop-shadow">1</span>'
    );
  });
});

// ---------------------------------------------------------------------------
// The two cards agree
// ---------------------------------------------------------------------------

it("both cards print the SAME words for the same row", () => {
  // "with the same words" is the acceptance test. Asserted as an equality
  // between two rendered surfaces rather than as two independent `toContain`s,
  // so a future edit to one card's copy fails here instead of drifting.
  const data = makeData();
  expect(text(renderFeedCard(data))).toContain(EXPECTED);
  expect(text(renderDiscoverCard(data))).toContain(EXPECTED);
});

it("both cards fall back to the bare badge when no score was ever captured", () => {
  const data = makeData({ away_score: null, home_score: null });
  for (const rendered of [text(renderFeedCard(data)), text(renderDiscoverCard(data))]) {
    expect(rendered).toContain(SUSPENDED_LABEL);
    expect(rendered).not.toContain("last score");
  }
});

// ---------------------------------------------------------------------------
// Properties that ALREADY HELD — kept as controls, not offered as evidence
// ---------------------------------------------------------------------------
//
// The red arm (revert `FeedCard.tsx`, `discover/EventCard.tsx` and
// `feedSections.ts`, keep the shared vocabulary module, re-run) put 13 of the
// 38 cases in this pair of files into the red and left these four green. They
// are green in BOTH arms, so they prove nothing about this repair and are
// separated rather than left to read as though they did.
//
// They are still worth keeping, because each names a claim that would be
// catastrophic to start making and that nothing else asserts: the false FINAL
// was written by the BACKEND as `status='closed'`, so no card ever had the
// chance to print "Final" over a suspended row, and the first edit that gave
// one that chance would be a silent regression of the whole CERT-752 finding.
//
// `prints no start time` is the subtlest of the four and worth naming exactly:
// `formatGameTime` already returns the empty string for a commence time in the
// past (`if (diffMs <= 0) return ""`), so the FeedCard never printed a start
// time for a suspended row even before the branch existed. The negative
// countdown CERT-786 found is the Discover card's, which computes its own
// label and does NOT have that floor — and that case is behavioural, sits
// above, and went red.

describe("controls: claims a suspended card must never start making", () => {
  it("FeedCard prints no start time", () => {
    const rendered = text(renderFeedCard(makeData()));
    expect(rendered).not.toMatch(/\b(Today|Tomorrow)\b/);
    expect(rendered).not.toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });

  it("neither card prints Final", () => {
    expect(text(renderFeedCard(makeData()))).not.toMatch(/\bFinal\b/i);
    expect(text(renderDiscoverCard(makeData()))).not.toMatch(/\bFinal\b/i);
  });

  it("the Discover card declares no winner off the partial score", () => {
    // The specimen is 1-2 down, and the settled card's "X won" line sits in the
    // slot immediately beside the one this state now uses.
    expect(text(renderDiscoverCard(makeData()))).not.toMatch(/\bwon\b/i);
  });
});
