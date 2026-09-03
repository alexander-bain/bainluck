/**
 * #2693 step 2 — THE FINISHED LIST STOPS DEAD-ENDING FOR THE ROWS THE MARKET
 * CHANNEL STRUCTURALLY CANNOT REACH.
 *
 * #2568 gave the Finished list the server's `event_links.by_matchup` map and
 * the section went from one link to twenty-eight. It could never have gone
 * further, and the reason is not coverage:
 *
 *   `build_slate` retires a matchup THE MOMENT ITS MATCH STARTS.
 *
 * So a finished match usually has no register matchup left, `build_results`
 * mints it a synthetic `espn:{competition_id}` key, and `matchupEventId`
 * refuses every key with that prefix — correctly, for Q503's reason. Measured
 * on the live payload 2026-09-02, `/api/tournaments/us-open`:
 *
 *     235 finished rows      118 carry only an `espn:` key
 *      86 linked              0 of those 118 among them
 *
 * ═══ WHAT CHANGED, AND WHY IT IS NOT A RELAXED REFUSAL ═══
 *
 * lane1/057 put an `espn_id` on 196 of the 200 US Open `events` rows. The
 * server now publishes a SECOND map, `event_links.by_espn`, built by
 * dereferencing the authority's competition id through `events.espn_id`. The
 * `espn:` prefix refusal is untouched: that refusal is about reaching the
 * REGISTER's event for a matchup whose pairing the authority contradicts, and
 * this channel does not go there — it goes to the row ESPN's own id names,
 * which lane1/057's anchor join only stamps when ESPN confirms both players.
 *
 * ═══ THE ARMS ═══
 *
 *  1. RED-FIRST: with no `by_espn` map the `espn:`-keyed rows are dead text —
 *     the shipped defect reproduced, not remembered.
 *  2. An `espn:`-keyed row with a `by_espn` entry links.
 *  3. A REGISTER-keyed row the market channel could not resolve links too
 *     (28 of the 34 `MARKET_UNLINKED` rows have a competition id).
 *  4. The market channel WINS when both could answer — the reviewed pin is
 *     never overruled by the fallback.
 *  5. An ambiguous or absent competition id still refuses. The server drops
 *     an id worn by two events; the client must not reinstate it.
 *  6. The grid survives (`display: contents`), the same trap #2568 names.
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
import {
  espnCompetitionEventId,
  matchEventHref,
} from "@/lib/tournamentEventLink";

function result(
  matchupKey: string,
  espnCompetitionId: string | null,
  winner: string,
  loser: string
): TournamentResult {
  const key = (name: string) => name.toLowerCase().replace(/ /g, "-");
  return {
    matchup_key: matchupKey,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R128",
    players: [
      {
        entity_key: key(winner),
        display_name: winner,
        seed: null,
        is_winner: true,
        image: null,
        prematch_probability: null,
      },
      {
        entity_key: key(loser),
        display_name: loser,
        seed: null,
        is_winner: false,
        image: null,
        prematch_probability: null,
      },
    ],
    winner_entity_key: key(winner),
    score: "6-4, 6-4, 6-4",
    completion: "final",
    completed_at: "2026-08-30T18:25Z",
    source_round: "Round 1",
    source: "espn",
    espn_competition_id: espnCompetitionId,
  };
}

/* Four rows, four states, from the live payload's own vocabulary. */
const PINNED = "mens-singles:daniel-merida-vs-marton-fucsovics:2026-08-30";
const UNLINKED = "mens-singles:arthur-fery-vs-lorenzo-musetti:2026-08-30";
const ESPN_ONLY = "espn:184739";
const ESPN_ONLY_UNCOVERED = "espn:184657";

const MATCHES: TournamentResult[] = [
  result(PINNED, "182565", "Marton Fucsovics", "Daniel Merida"),
  result(UNLINKED, "182545", "Lorenzo Musetti", "Arthur Fery"),
  result(ESPN_ONLY, "184739", "Martyna Kubka", "Annika Penickova"),
  // A qualifying match: ESPN played it, we hold no `events` row for it. The
  // server publishes NO_EVENT_FOR_ESPN_ID and the row stays text.
  result(ESPN_ONLY_UNCOVERED, "184657", "Maks Kasnikowski", "Nicolai Budkov Kjaer"),
];

const RESULTS: ResultsModel = {
  matches: MATCHES,
  count: MATCHES.length,
  unregistered_pairs: 0,
  winner_not_registered: 0,
  source_competitions: 4,
  source_scored: 4,
  source_errors: [],
};

const BY_MATCHUP: Record<string, number> = { [PINNED]: 15293827 };
const BY_ESPN: Record<string, number> = {
  // The pinned row's competition id ALSO resolves — to a different row, so the
  // precedence arm has something real to prove.
  "182565": 99999999,
  "182545": 15301138,
  "184739": 15299378,
};

function markup(
  eventIds?: Record<string, number> | null,
  espnEventIds?: Record<string, number> | null
): string {
  return renderToStaticMarkup(
    <TournamentResults
      results={RESULTS}
      draw="mens-singles"
      eventIds={eventIds}
      espnEventIds={espnEventIds}
      initialExpanded
    />
  );
}

function hrefs(html: string): string[] {
  return Array.from(html.matchAll(/\shref="([^"]+)"/g)).map((m) => m[1]);
}

describe("espnCompetitionEventId — the authority channel, on its own", () => {
  it("resolves a competition id the server published", () => {
    expect(espnCompetitionEventId("184739", BY_ESPN)).toBe(15299378);
  });

  it("accepts a numeric id, because JSON keys are strings and rows may not be", () => {
    expect(espnCompetitionEventId(184739, BY_ESPN)).toBe(15299378);
  });

  it("refuses an id the server did not publish — no name join, ever", () => {
    // The server counted this one: NO_EVENT_FOR_ESPN_ID (a qualifying match).
    expect(espnCompetitionEventId("184657", BY_ESPN)).toBeNull();
  });

  it("refuses when the map is absent entirely", () => {
    expect(espnCompetitionEventId("184739", null)).toBeNull();
    expect(espnCompetitionEventId("184739", undefined)).toBeNull();
  });

  it("refuses a null, empty or unusable id rather than building /events/0", () => {
    expect(espnCompetitionEventId(null, BY_ESPN)).toBeNull();
    expect(espnCompetitionEventId(undefined, BY_ESPN)).toBeNull();
    expect(espnCompetitionEventId("", BY_ESPN)).toBeNull();
    expect(espnCompetitionEventId("x", { x: 0 })).toBeNull();
    expect(espnCompetitionEventId("x", { x: -3 })).toBeNull();
    expect(
      espnCompetitionEventId("x", { x: Number.NaN } as Record<string, number>)
    ).toBeNull();
  });
});

describe("matchEventHref — the market channel is never overruled", () => {
  it("prefers the pinned market link when BOTH channels can answer", () => {
    // 182565 is in `by_espn` and would resolve to 99999999. The reviewed pin
    // wins; a fallback that outranked it would silently re-address every row.
    expect(matchEventHref(PINNED, "182565", BY_MATCHUP, BY_ESPN)).toBe(
      "/events/15293827"
    );
  });

  it("falls back to the authority when the market channel declines", () => {
    expect(matchEventHref(UNLINKED, "182545", BY_MATCHUP, BY_ESPN)).toBe(
      "/events/15301138"
    );
  });

  it("routes an espn:-keyed row, which the prefix refusal alone never could", () => {
    expect(matchEventHref(ESPN_ONLY, "184739", BY_MATCHUP, BY_ESPN)).toBe(
      "/events/15299378"
    );
  });

  it("still refuses an espn: KEY against the matchup map", () => {
    // Q503's guard, unchanged: even with the synthetic key present in
    // `by_matchup`, the register's event must not be reached this way.
    expect(
      matchEventHref(ESPN_ONLY, null, { [ESPN_ONLY]: 15293827 }, null)
    ).toBeNull();
  });

  it("returns null when neither channel answers", () => {
    expect(matchEventHref(UNLINKED, "184657", BY_MATCHUP, BY_ESPN)).toBeNull();
  });

  it("behaves exactly as before when no authority map is supplied", () => {
    expect(matchEventHref(PINNED, "182565", BY_MATCHUP)).toBe("/events/15293827");
    expect(matchEventHref(ESPN_ONLY, "184739", BY_MATCHUP)).toBeNull();
  });
});

describe("the rendered finished list", () => {
  it("RED-FIRST: without the authority map the espn:-keyed rows are dead text", () => {
    const before = hrefs(markup(BY_MATCHUP));
    expect(before).toEqual(["/events/15293827"]);
    expect(before).toHaveLength(1);
  });

  it("links the rows the authority can address, and no others", () => {
    const after = hrefs(markup(BY_MATCHUP, BY_ESPN));
    expect(after).toEqual([
      "/events/15293827", // pinned — market channel, unchanged
      "/events/15301138", // MARKET_UNLINKED — rescued by the authority
      "/events/15299378", // espn:-keyed — rescued by the authority
    ]);
    // The qualifying match has no events row and must stay text.
    expect(after).toHaveLength(3);
  });

  it("keeps the anchor out of the grid tracks (display: contents)", () => {
    // #2568's trap: an anchor that is not `contents` becomes a grid item and
    // collapses three columns into one. The fix would "work" and the list
    // would be unreadable.
    const html = markup(BY_MATCHUP, BY_ESPN);
    const anchors = Array.from(html.matchAll(/<a\s[^>]*>/g)).map((m) => m[0]);
    expect(anchors).toHaveLength(3);
    for (const anchor of anchors) {
      expect(anchor).toContain("contents");
    }
  });

  it("counts the note over the rows it can actually route", () => {
    const html = markup(BY_MATCHUP, BY_ESPN);
    expect(html).toContain('data-linked="3"');
    expect(html).toContain('data-total="4"');
  });

  it("still names the gap — a list that routes some rows must say which", () => {
    expect(markup(BY_MATCHUP, BY_ESPN)).toContain(
      "open a match page. We cannot link the rest to one yet."
    );
  });
});

describe("resultLinkCoverage — counted over the rendered draw", () => {
  it("rises with the authority map and never above the row count", () => {
    expect(resultLinkCoverage(MATCHES, BY_MATCHUP)).toEqual({
      linked: 1,
      total: 4,
    });
    expect(resultLinkCoverage(MATCHES, BY_MATCHUP, BY_ESPN)).toEqual({
      linked: 3,
      total: 4,
    });
  });

  it("is zero with neither map, which is what the section did before #2568", () => {
    expect(resultLinkCoverage(MATCHES, null, null)).toEqual({
      linked: 0,
      total: 4,
    });
  });
});

describe("a payload that predates the field", () => {
  it("renders, and degrades to the market channel alone", () => {
    // A cached hub payload written before `espn_competition_id` existed. The
    // section must not throw, and must not invent an address of its own.
    const legacy = MATCHES.map(({ espn_competition_id, ...rest }) => rest);
    const html = renderToStaticMarkup(
      <TournamentResults
        results={{ ...RESULTS, matches: legacy as TournamentResult[] }}
        draw="mens-singles"
        eventIds={BY_MATCHUP}
        espnEventIds={BY_ESPN}
        initialExpanded
      />
    );
    expect(hrefs(html)).toEqual(["/events/15293827"]);
  });

  it("resultEventHref reads the row's own competition id", () => {
    expect(resultEventHref(MATCHES[2], BY_MATCHUP, BY_ESPN)).toBe(
      "/events/15299378"
    );
  });
});
