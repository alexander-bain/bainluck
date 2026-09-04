// ux/1036 Tier A — A FINISHED CARD GIVES EACH TEAM ITS OWN PRE-MATCH NUMBER.
//
// Alex, on /sports "Just Happened" at phone width, 2026-09-02: *"How come none
// of these show pre-event probability?"*
//
// He was reading a column of FINAL cards on which the only pre-match figure was
// a grey `Opened 40/60` footnote. That string fails at the one job the number
// has — it never says WHICH TEAM is the 40 — and the live card three rows up
// gives each team its own. His instruction: keep the live-card layout on FINAL
// cards, score bold in the right column, the pre-match probability greyed beside
// each name, winner bold, and drop `Opened x/y` once the per-team numbers exist.
//
// ## Why this file renders instead of grepping
//
// #2060's lesson, and `discoverEventCardDuelInvariant`'s: a source grep cannot
// tell a rendered field from a declared one. `lib/prematchReading.ts` has its own
// contract tests; only this file proves the two CARDS show what it decides.
//
// Both directions per gotcha #43: the number appears on a FINAL card AND the
// live card is asserted unchanged — it keeps `Opened X/Y`, because there the
// opening is a second comparative fact beside a per-team current split rather
// than the only pre-match figure on the card.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FeedCard from "@/components/FeedCard";
import { EventCard as DiscoverEventCard } from "@/components/discover/EventCard";
import type { FeedEventData, FeedItem } from "@/lib/types";
import { PREMATCH_NUMBER_CLASS } from "@/lib/prematchReading";
import { visibleTextFromHtml } from "@/lib/copyBans";

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

// The pairing Alex named. Padres won at 40%, which is also why "Won as 40%
// underdog" has to survive — it is the story, and it is a different sentence
// from the two numbers.
function makeData(over: Partial<FeedEventData> = {}): FeedEventData {
  return {
    id: 15299725,
    external_id: "evt-15299725",
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: "Cincinnati Reds",
    away_team: "San Diego Padres",
    commence_time: "2026-09-02T23:10:00.000Z",
    status: "completed",
    home_score: 3,
    away_score: 5,
    ...over,
  } as FeedEventData;
}

function makeItem(data: FeedEventData, over: Partial<FeedItem> = {}): FeedItem {
  return {
    type: "event",
    score: 50,
    reason: "",
    headline: "",
    data,
    ...over,
  } as unknown as FeedItem;
}

function renderFeedCard(data: FeedEventData, item?: Partial<FeedItem>): string {
  return renderToStaticMarkup(<FeedCard item={makeItem(data, item)} />);
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

/** The percent printed in a `data-testid` cell, or `null` when the cell is absent. */
function printedPercent(html: string, testid: string): number | null {
  const cell = new RegExp(
    `<span[^>]*data-testid="${testid}"[^>]*>([\\s\\S]*?)</span>\\s*(?:</div>|<span|</span>)`
  ).exec(html);
  if (!cell) return null;
  const match = /(\d+)%/.exec(cell[1].replace(/<[^>]*>/g, " "));
  return match ? Number(match[1]) : null;
}

/**
 * WHAT A SIGHTED READER GETS — `visibleTextFromHtml` minus the `sr-only` spans.
 *
 * The D57-corrected symmetry guard needs this because the two rungs are
 * deliberately NOT identical to a screen reader: the spoken clause still names
 * its rung ("sportsbooks opened" vs "the market gave"), which is CERT-812's
 * repair and survives the correction. What Alex struck is the caveat a sighted
 * reader can see. Comparing raw visible text would fail on the one difference
 * that is supposed to be there, so the guard strips exactly that and compares
 * the rest — the pixels.
 */
function sightedText(html: string): string {
  return visibleTextFromHtml(html.replace(/<span class="sr-only">[\s\S]*?<\/span>/g, " "));
}

// CARRIES BOTH RUNGS ON PURPOSE. `opening_odds` is present on most settled
// events (36 of the 40 most recent finals, production 2026-09-03), so a fixture
// without it would make the "drops the Opened footnote" assertion vacuous — the
// old code had nothing to print either. With it, the pre-fix card prints
// `Opened 55/45` and the post-fix card must not; and the ladder is under test
// too, because Kalshi's 60 has to beat the books' 55.
const KALSHI_FINAL = makeData({
  opening_odds: { home_probability: 0.55, away_probability: 0.45, favorite: "home" },
  prematch_odds: {
    home_probability: 0.6,
    away_probability: 0.4,
    home_rendered_percent: 60,
    away_rendered_percent: 40,
    source: "kalshi",
  },
});

// ── /sports and every other FeedCard list ───────────────────────────────────

describe("the /sports FINAL card", () => {
  it("prints a pre-match percent beside EACH team, off the winning rung", () => {
    // 60/40 is Kalshi's; 55/45 is the books' `opening_odds` on the same payload.
    // The ladder is ordered, so the books number must not reach the card.
    const html = renderFeedCard(KALSHI_FINAL);

    expect(printedPercent(html, "feed-card-prematch-away")).toBe(40);
    expect(printedPercent(html, "feed-card-prematch-home")).toBe(60);
  });

  it("names the team each number is about, for a reader who cannot see the layout", () => {
    // The whole defect in one assertion: `Opened 40/60` could not do this.
    const html = renderFeedCard(KALSHI_FINAL);

    expect(html).toContain("Before the game, the market gave San Diego Padres");
    expect(html).toContain("Before the game, the market gave Cincinnati Reds");
  });

  it("drops the Opened footnote now that the per-team numbers exist", () => {
    expect(renderFeedCard(KALSHI_FINAL)).not.toContain("Opened");
  });

  it("still shows the score, in its own right-hand column", () => {
    const html = renderFeedCard(KALSHI_FINAL);

    expect(html).toContain('data-testid="feed-card-final-score"');
    expect(html).toContain(">5</div>");
    expect(html).toContain(">3</div>");
  });

  it("keeps the underdog story, which the numbers do not replace", () => {
    // Alex: "'Won as 40% underdog' stays (it is the story)."
    const html = renderFeedCard(KALSHI_FINAL, { reason: "Won as 40% underdog" });

    expect(html).toContain("Won as 40% underdog");
  });

  it("prints a sportsbook reading EXACTLY as it prints a market one", () => {
    // ═══ D57 AS CORRECTED (Alex, 2026-09-03 4:15pm) ═══
    //
    // This assertion has been three different things in one day. It asserted
    // the literal string "Pre-match · books"; then, when Alex read that on the
    // hub, it asserted a `†` and a "from sportsbooks" tooltip. Alex on round
    // two: *"We don't need to say anything about sportsbooks … just show the
    // %."* So the caveat is struck, not re-worded, and the guard inverts: the
    // two rungs must be INDISTINGUISHABLE to a reader.
    //
    // SYMMETRY IS THE ASSERTION, and it is why both fixtures carry 60/40. A
    // pair of one-sided `not.toContain`s would pass against a card that had
    // simply lost the mark on both rungs for an unrelated reason; comparing the
    // two renders' visible text catches any future per-rung branch whatever
    // costume it arrives in — a word, a glyph, a colour word, a caption.
    const booksRung = renderFeedCard(
      makeData({
        opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
      })
    );
    const marketRung = renderFeedCard(
      makeData({
        prematch_odds: {
          home_probability: 0.6,
          away_probability: 0.4,
          home_rendered_percent: 60,
          away_rendered_percent: 40,
          source: "kalshi",
        },
      } as Partial<FeedEventData>)
    );

    expect(printedPercent(booksRung, "feed-card-prematch-home")).toBe(60);
    expect(printedPercent(marketRung, "feed-card-prematch-home")).toBe(60);
    expect(sightedText(booksRung)).toBe(sightedText(marketRung));

    // And named individually, because "identical" would also be satisfied by
    // both arms carrying the mark. These are the three things D57 round one
    // shipped, each asserted gone.
    expect(booksRung).not.toContain("†");
    expect(booksRung).not.toContain("from sportsbooks");
    expect(sightedText(booksRung)).not.toMatch(/\bPre-match\b/);
    // The word itself, on the rendered text rather than on a constant —
    // `visibleTextFromHtml` strips attributes, so the payload's own
    // `data-prematch-source="books"` is exempt exactly as the copy gate has it.
    expect(visibleTextFromHtml(booksRung)).not.toMatch(/\bbooks\b/i);

    // THE DATA CONTRACT SURVIVES THE COPY. A cert still has to be able to ask
    // which rung a figure came from; what it may not do is read the answer off
    // the pixels. Deleting the attribute with the caption would have made this
    // correction unverifiable.
    expect(booksRung).toContain('data-prematch-source="books"');
    expect(marketRung).toContain('data-prematch-source="kalshi"');
  });

  it("draws the number in the ONE shared treatment, on both rungs", () => {
    // Alex: *"we've solved that problem on event cards elsewhere … find it,
    // reuse it, do not invent a third."* The treatment is the whole of what
    // makes a pre-match figure legible as one, now that no word does it, so
    // the class list is asserted rather than assumed — and asserted from the
    // exported constant, so a surface cannot drift by editing its own copy.
    for (const html of [
      renderFeedCard(KALSHI_FINAL),
      renderFeedCard(
        makeData({
          opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
        })
      ),
    ]) {
      expect(html).toContain(PREMATCH_NUMBER_CLASS);
    }
  });

  it("says which rung the spoken sentence is quoting, not just the visible label", () => {
    // The mark beside "Pre-match" is the caveat a SIGHTED reader gets (D57;
    // it was the word "books" until Alex read it on the hub). The
    // sentence beside the number is what everyone else gets, and it used to say
    // "the market gave" on every card — including the books rung, which is a
    // sportsbook median and not a market at all. Measured on the served /sports
    // payload 2026-09-03: 13 of 13 finished cards were the books rung, so the
    // unlabelled sentence was what a screen-reader user heard every time.
    //
    // BOTH ARMS. The books arm alone would pass against a card that said
    // "sportsbooks opened" unconditionally, which is the same defect mirrored.
    const books = renderFeedCard(
      makeData({
        opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
      })
    );

    expect(books).toContain("Before the game, sportsbooks opened San Diego Padres");
    expect(books).not.toContain("the market gave");

    expect(renderFeedCard(KALSHI_FINAL)).toContain(
      "Before the game, the market gave San Diego Padres"
    );
    expect(renderFeedCard(KALSHI_FINAL)).not.toContain("sportsbooks opened");
  });

  it("prints nothing at all when we hold no pre-match reading", () => {
    // The empty space is a real answer. It is what the tennis hub's finished
    // list has always done, and what stops a card inventing a prior.
    const html = renderFeedCard(makeData());

    expect(html).not.toContain('data-testid="feed-card-prematch-home"');
    expect(html).not.toContain("Pre-match");
  });

  it("leaves the LIVE card exactly as it was — Opened X/Y and no per-team prior", () => {
    // The regression arm. A live card shows the CURRENT split per team, so the
    // opening is a comparative second fact there rather than the only one.
    const html = renderFeedCard(
      makeData({
        status: "live",
        current_odds: { home_probability: 0.52, away_probability: 0.48 },
        opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
      } as Partial<FeedEventData>)
    );

    // ux/1041 (#2689) — WAS `"Opened 60/40"`. This assertion's subject is that
    // the live card KEEPS the footer, and it still does; the pair is the same
    // pair. What moved is the side order: the footer printed home-first on a
    // card that lists the away team above the home team, which inverted the
    // favourite on 10 of 10 measured rows. Home is 60 here, away 40, so the
    // away-first footer reads 40/60. Updated rather than loosened to a regex,
    // because the specific digits are what make this a regression arm.
    expect(html).toContain("Opened 40/60");
    expect(html).not.toContain('data-testid="feed-card-prematch-home"');
  });
});

// ── Discover ────────────────────────────────────────────────────────────────

describe("the Discover FINAL card", () => {
  it("prints the pre-match pair in the live strip's three slots", () => {
    const html = renderDiscoverCard(KALSHI_FINAL);

    expect(printedPercent(html, "event-card-prematch-away")).toBe(40);
    expect(printedPercent(html, "event-card-prematch-home")).toBe(60);
    expect(html).toContain("Pre-match");
  });

  it("keeps the winner line the pre-match numbers sit under", () => {
    const html = renderDiscoverCard(KALSHI_FINAL);

    expect(html).toContain("Padres won");
  });

  it("prints both rungs identically here too (D57 corrected)", () => {
    const books = renderDiscoverCard(
      makeData({
        opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
      })
    );
    const market = renderDiscoverCard(
      makeData({
        prematch_odds: {
          home_probability: 0.6,
          away_probability: 0.4,
          home_rendered_percent: 60,
          away_rendered_percent: 40,
          source: "kalshi",
        },
      } as Partial<FeedEventData>)
    );

    expect(sightedText(books)).toBe(sightedText(market));
    expect(books).not.toContain("†");
    expect(books).not.toContain("from sportsbooks");
    expect(visibleTextFromHtml(books)).not.toMatch(/\bbooks\b/i);
    expect(books).toContain('data-prematch-source="books"');

    // THE CAPTION STAYS, AND IS THE SAME CAPTION ON BOTH ARMS. This card has no
    // score column for the grey figures to contrast against, so the word
    // "Pre-match" is carrying the tense here — Alex's ask was that the tense be
    // clear. What it may not do is vary by rung, which is what the conditional
    // tooltip made it do.
    expect(books).toContain("Pre-match");
    expect(market).toContain("Pre-match");
    expect(books).toContain(PREMATCH_NUMBER_CLASS);
  });

  it("and says so in the spoken sentence too, not only the label", () => {
    const books = renderDiscoverCard(
      makeData({
        opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
      })
    );

    expect(books).toContain("Before the game, sportsbooks opened San Diego Padres");
    expect(books).not.toContain("the market gave");

    expect(renderDiscoverCard(KALSHI_FINAL)).toContain(
      "Before the game, the market gave San Diego Padres"
    );
    expect(renderDiscoverCard(KALSHI_FINAL)).not.toContain("sportsbooks opened");
  });

  it("shows no strip on a card we hold no reading for", () => {
    expect(renderDiscoverCard(makeData())).not.toContain('data-testid="event-card-prematch"');
  });

  it("leaves the LIVE win-probability strip untouched", () => {
    const html = renderDiscoverCard(
      makeData({
        status: "live",
        current_odds: { home_probability: 0.52, away_probability: 0.48 },
      } as Partial<FeedEventData>)
    );

    expect(html).toContain("Win Probability");
    expect(html).not.toContain('data-testid="event-card-prematch"');
  });
});
