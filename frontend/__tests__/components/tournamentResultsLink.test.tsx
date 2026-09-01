/**
 * #2568 — THE US OPEN HUB STOPS BEING A DEAD END FOR ITS FINISHED MATCHES.
 *
 * Measured on production, 2026-09-01, `/tournaments/us-open` Men's / Tournament:
 * the page rendered **100 match rows** — 11 upcoming from the slate, 89 finished
 * from `TournamentResults` — and an anchor inventory of the rendered DOM found
 * exactly **one** of them was a link:
 *
 *     /events/15293823  ::  "1:20 PM · MEN'S SINGLES Casper Ruud …"
 *
 * A click harness confirmed it with a control in the same run: the Ruud row
 * navigated, Musetti's row and a finished R128 row did not move the URL.
 *
 * ═══ IT WAS NOT A DATA GAP. THE ADDRESS WAS ALREADY ON THE PAYLOAD ═══
 *
 * `event_links.by_matchup` — the server's id-anchored `matchup_key -> events.id`
 * map, resolved once in `tournament_event_link.py` and published beside the
 * results — carried **63 of the 192** finished rows on that same payload (28 of
 * the 89 men's). The slate row type reads it as `event_id`; the results row type
 * did not have the field at all, so the entire finished half of the page was
 * inert by construction rather than by coverage.
 *
 * ═══ WHY THE COUNTS IN THIS FILE ARE SMALL AND THE ARMS ARE NOT ═══
 *
 * Four things have to hold at once, and three of them are the ways a fix like
 * this passes a test while shipping broken:
 *
 *  1. **A resolvable row is a link** — the fix.
 *  2. **An unresolvable row is NOT** — a page that linked every row would pass
 *     arm 1 and send readers to 404s or, worse, to the wrong match. The map is
 *     the only authority; there is no name join.
 *  3. **A synthetic `espn:` key never links**, even if something puts one in the
 *     map. 90 of the 192 rows are finished matches the register does not carry.
 *  4. **The grid survives.** These rows are `display: contents` cells landing in
 *     the parent `<ul>`'s tracks (see `RESULT_GRID`). An anchor that is not also
 *     `contents` becomes a grid item itself and collapses three columns into
 *     one — the fix would "work" and the list would be unreadable. Asserted on
 *     the rendered markup, not on the source.
 *
 * Plus a RED-FIRST arm: with no map, the markup contains zero `/events/` hrefs,
 * which is the shipped defect reproduced rather than remembered.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentResults from "@/components/tournament/TournamentResults";
import {
  resultEventHref,
  resultLinkCoverage,
  type TournamentResult,
  type TournamentResults as ResultsModel,
} from "@/lib/tournamentResults";

function result(
  matchupKey: string,
  winner: string,
  loser: string
): TournamentResult {
  return {
    matchup_key: matchupKey,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R128",
    players: [
      {
        entity_key: winner.toLowerCase().replace(/ /g, "-"),
        display_name: winner,
        seed: null,
        is_winner: true,
        image: null,
        prematch_probability: null,
      },
      {
        entity_key: loser.toLowerCase().replace(/ /g, "-"),
        display_name: loser,
        seed: null,
        is_winner: false,
        image: null,
        prematch_probability: null,
      },
    ],
    winner_entity_key: winner.toLowerCase().replace(/ /g, "-"),
    score: "6-4, 6-4, 6-4",
    completion: "final",
    completed_at: "2026-08-30T18:25Z",
    source_round: "Round 1",
    source: "espn",
  };
}

/* Three rows, three states, from the live payload's own vocabulary:
   a registered matchup the server resolved, a registered matchup it could not
   (`MARKET_UNLINKED`, 52 of them that day), and an ESPN-only finished match. */
const RESOLVED = "mens-singles:daniel-merida-vs-marton-fucsovics:2026-08-30";
const UNRESOLVED = "mens-singles:arthur-fery-vs-lorenzo-musetti:2026-08-30";
const ESPN_ONLY = "espn:184739";

const MATCHES: TournamentResult[] = [
  result(RESOLVED, "Marton Fucsovics", "Daniel Merida"),
  result(UNRESOLVED, "Lorenzo Musetti", "Arthur Fery"),
  result(ESPN_ONLY, "Martyna Kubka", "Annika Penickova"),
];

const RESULTS: ResultsModel = {
  matches: MATCHES,
  count: MATCHES.length,
  unregistered_pairs: 0,
  winner_not_registered: 0,
  source_competitions: 3,
  source_scored: 3,
  source_errors: [],
};

/** The real shape of `event_links.by_matchup`, with the real event id. */
const BY_MATCHUP: Record<string, number> = { [RESOLVED]: 15293827 };

function markup(eventIds?: Record<string, number> | null): string {
  return renderToStaticMarkup(
    <TournamentResults
      results={RESULTS}
      draw="mens-singles"
      eventIds={eventIds}
      initialExpanded
    />
  );
}

function hrefs(html: string): string[] {
  // `\shref=` and not `href=` — `data-event-href="…"` is on every row and a
  // loose match counts it, which would make one linked row look like two.
  return Array.from(html.matchAll(/\shref="([^"]+)"/g)).map((m) => m[1]);
}

describe("resultEventHref — the map is the only authority", () => {
  it("routes a resolved matchup to the standard event page", () => {
    expect(resultEventHref(MATCHES[0], BY_MATCHUP)).toBe("/events/15293827");
  });

  it("returns null for a matchup the server did not resolve", () => {
    expect(resultEventHref(MATCHES[1], BY_MATCHUP)).toBeNull();
  });

  it("never routes a synthetic espn: key, even when the map carries one", () => {
    // The poison control. If an overlay ever starts writing these, the row must
    // stay text until somebody deliberately deletes the guard.
    expect(resultEventHref(MATCHES[2], { [ESPN_ONLY]: 999 })).toBeNull();
  });

  it("refuses a non-numeric or non-positive id rather than building /events/0", () => {
    expect(
      resultEventHref(MATCHES[0], { [RESOLVED]: 0 } as Record<string, number>)
    ).toBeNull();
    expect(
      resultEventHref(MATCHES[0], {
        [RESOLVED]: "15293827",
      } as unknown as Record<string, number>)
    ).toBeNull();
  });

  it("degrades to text when the payload carries no map at all", () => {
    expect(resultEventHref(MATCHES[0], undefined)).toBeNull();
    expect(resultEventHref(MATCHES[0], null)).toBeNull();
  });

  it("counts coverage over the rows it was given, not over the payload", () => {
    expect(resultLinkCoverage(MATCHES, BY_MATCHUP)).toEqual({
      linked: 1,
      total: 3,
    });
  });
});

describe("the rendered finished list", () => {
  it("RED-FIRST: with no map the list contains no event link at all", () => {
    // This is the shipped defect, executed. If this arm ever goes green the
    // green arm below stops being evidence of anything.
    const html = markup(undefined);
    expect(hrefs(html).filter((h) => h.startsWith("/events/"))).toEqual([]);
    expect(html).toContain("Fucsovics");
  });

  it("links the resolved row and only the resolved row", () => {
    const html = markup(BY_MATCHUP);
    expect(hrefs(html).filter((h) => h.startsWith("/events/"))).toEqual([
      "/events/15293827",
    ]);
    // CONTROL, same render: the two unroutable rows are still on the page. A
    // component that dropped them would satisfy the assertion above.
    expect(html).toContain("Musetti");
    expect(html).toContain("Kubka");
  });

  it("keeps the anchor out of the grid tracks (display: contents)", () => {
    const html = markup(BY_MATCHUP);
    const anchor = html.match(/<a[^>]*href="\/events\/15293827"[^>]*>/);
    expect(anchor).not.toBeNull();
    // `contents` on the anchor is what keeps the row's three cells as direct
    // children of the `<ul>`'s grid. Without it the name, the prior and the
    // score collapse into one column.
    expect(anchor![0]).toMatch(/class="[^"]*\bcontents\b/);
  });

  it("names the gap rather than leaving dead rows unexplained", () => {
    const html = markup(BY_MATCHUP);
    expect(html).toContain('data-testid="results-link-note"');
    expect(html).toContain("1 of 3");
  });

  it("says nothing about links when it can route none of them", () => {
    // A note reading "0 of 3 open a match page" is worse than silence: it
    // advertises a feature the reader cannot use anywhere on the list.
    expect(markup({})).not.toContain('data-testid="results-link-note"');
  });

  it("counts LINKED rows in the note, not rendered rows", () => {
    const both = Object.fromEntries(
      MATCHES.filter((m) => !m.matchup_key.startsWith("espn:")).map((m, i) => [
        m.matchup_key,
        15293827 + i,
      ])
    );
    const html = markup(both);
    expect(hrefs(html).filter((h) => h.startsWith("/events/"))).toHaveLength(2);
    expect(html).toContain("2 of 3");
  });

  it("says nothing about links when every row on the list routes", () => {
    // The note is about a GAP. With no gap it is noise, and a reader who can
    // click everything does not need to be told how many things they can click.
    const registered = MATCHES.filter((m) => !m.matchup_key.startsWith("espn:"));
    const html = renderToStaticMarkup(
      <TournamentResults
        results={{ ...RESULTS, matches: registered, count: registered.length }}
        draw="mens-singles"
        eventIds={Object.fromEntries(
          registered.map((m, i) => [m.matchup_key, 15293827 + i])
        )}
        initialExpanded
      />
    );
    expect(hrefs(html).filter((h) => h.startsWith("/events/"))).toHaveLength(2);
    expect(html).not.toContain('data-testid="results-link-note"');
  });

  it("marks every row with what it resolved to, link or not", () => {
    // The queryable fact a screenshot cannot carry: a shopper checking this
    // page again should be able to read the state off the DOM.
    const html = markup(BY_MATCHUP);
    expect(html).toContain('data-event-href="/events/15293827"');
    expect(html.match(/data-testid="result-row"/g)).toHaveLength(3);
    expect(html.match(/data-testid="result-link"/g)).toHaveLength(1);
  });
});
