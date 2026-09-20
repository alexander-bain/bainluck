/**
 * #7416 — A "GAMES THIS WEEK" ROW KEEPS ITS FIXTURE, AND ITS ODDS STOP LYING.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `https://bainluck.com/futures/129037` ("Pro Football: 2027 Champion") at
 * 390px on 2026-09-20, verbatim from `artifacts/ux-1385/BEFORE-7416-nfl-390.png`:
 *
 *     Today      Tampa Bay Buccaneers 1%   Cleveland Brow…
 *     10:00 AM
 *     Today      Atlanta Falcons 0%   Carolina Panthers 0%
 *     10:00 AM
 *
 * The fixture — "Cleveland Browns at Tampa Bay Buccaneers", the row's subject
 * and the thing its link goes to — is not truncated, it is ABSENT. What is left
 * reads as the game's own price, and so read it is false: a game one of the two
 * must win, with both sides at 0%. The second percentage is clipped off the
 * right edge of the card. The same page at 1280px renders the row complete,
 * which is what makes this responsive rather than a design question.
 *
 * ═══ WHAT THIS FILE CAN AND CANNOT SEE ═══
 *
 * Jest runs in `node` here — there is no layout engine, so NO test in this
 * repository can watch a box get squeezed to zero width. Every text assertion
 * below is GREEN ON THE BUG: the fixture string was in the markup the whole
 * time; a reader never saw it because flexbox gave its box no width.
 *
 * So the layout half of this file asserts the CLASS CONTRACT that decides the
 * widths, and it asserts it by exact class TOKEN rather than by substring,
 * because the whole defect lives in the difference between `flex-shrink-0` and
 * `sm:flex-shrink-0`. A substring test cannot tell those apart and would pass on
 * the defect. Three tokens are load-bearing:
 *
 *   - the fixture and the odds STACK below `sm` (`flex-col` + `sm:flex-row`),
 *     so the fixture gets the row's full content width at phone size;
 *   - the odds block may SHRINK below `sm` (no unprefixed `flex-shrink-0`) and
 *     carries `min-w-0`, so it ellipsizes inside the card instead of
 *     overflowing it;
 *   - the per-name cap is `sm:max-w-[10rem]`, NOT `max-w-[10rem]`. Unprefixed,
 *     two names hold 2×160px on a card whose content column is ~210px, which is
 *     the overflow itself. #2553's desktop cap is preserved by the prefix.
 *
 * The percentage and ordering halves are real behaviour and are tested as such.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import GamesThisWeek, {
  RelatedEventRow,
  fixtureOrderedTeams,
} from "@/components/futures/GamesThisWeek";
import type { RelatedEvent, RelatedEventLinkedTeam } from "@/lib/types";

/**
 * Served by `GET /api/futures/129037/related-events` on 2026-09-20, copied
 * field for field. Atlanta 0.0035 / Carolina 0.0045 are the two probabilities
 * that printed `0%` in the screenshot above, and `linked_teams` really does
 * arrive `[home, away]` — the reverse of the fixture line's "Away at Home".
 */
const FALCONS_PANTHERS: RelatedEvent = {
  event_id: 14782703,
  home_team: "Atlanta Falcons",
  away_team: "Carolina Panthers",
  commence_time: "2026-09-20T17:00:00+00:00",
  status: "scheduled",
  sport: "americanfootball_nfl",
  home_score: null,
  away_score: null,
  linked_teams: [
    {
      side: "home",
      team_name: "Atlanta Falcons",
      outcome_name: "Atlanta Falcons",
      probability: 0.0035,
      american_odds: 28471,
      rank: 30,
    },
    {
      side: "away",
      team_name: "Carolina Panthers",
      outcome_name: "Carolina Panthers",
      probability: 0.0045,
      american_odds: 22122,
      rank: 26,
    },
  ],
};

/** The same section's longest fixture, and the one whose odds were clipped. */
const BROWNS_BUCS: RelatedEvent = {
  event_id: 14782150,
  home_team: "Tampa Bay Buccaneers",
  away_team: "Cleveland Browns",
  commence_time: "2026-09-20T17:00:00+00:00",
  status: "scheduled",
  sport: "americanfootball_nfl",
  home_score: null,
  away_score: null,
  linked_teams: [
    {
      side: "home",
      team_name: "Tampa Bay Buccaneers",
      outcome_name: "Tampa Bay Buccaneers",
      probability: 0.0115,
      american_odds: 8596,
      rank: 20,
    },
    {
      side: "away",
      team_name: "Cleveland Browns",
      outcome_name: "Cleveland Browns",
      probability: 0.0035,
      american_odds: 28471,
      rank: 31,
    },
  ],
};

const markup = (node: React.ReactElement): string => renderToStaticMarkup(node);

/** Every `class` attribute in the markup, in document order. */
const classAttrs = (html: string): string[] =>
  Array.from(html.matchAll(/class="([^"]*)"/g)).map((m) => m[1]);

/** Exact token membership — `sm:flex-shrink-0` must not answer for `flex-shrink-0`. */
const hasToken = (cls: string, token: string): boolean =>
  cls.split(/\s+/).includes(token);

const attrsWith = (html: string, token: string): string[] =>
  classAttrs(html).filter((c) => hasToken(c, token));

/**
 * The odds container: the one element that may not shrink from `sm` up but
 * must shrink below it. The time gutter also carries `sm:flex-shrink-0`, so the
 * `min-w-0` is what tells them apart.
 */
const oddsBlocks = (html: string): string[] =>
  attrsWith(html, "sm:flex-shrink-0").filter((c) => hasToken(c, "min-w-0"));

/** The rendered percentages, in the order they appear in the row. */
const percents = (html: string): string[] =>
  Array.from(html.matchAll(/>((?:&lt;|&gt;)?\d+%)</g)).map((m) =>
    m[1].replace("&lt;", "<").replace("&gt;", ">"),
  );

describe("#7416 layout contract — the fixture cannot be squeezed to nothing", () => {
  it("stacks the fixture above the odds below sm, and lays them out in a row from sm up", () => {
    const html = markup(<RelatedEventRow event={FALCONS_PANTHERS} />);
    // Two boxes carry `sm:flex-1` — the content wrapper and, inside it, the
    // fixture. The wrapper is the one that changes DIRECTION at the breakpoint.
    const wrappers = attrsWith(html, "sm:flex-1").filter((c) => hasToken(c, "flex-col"));

    expect(wrappers).toHaveLength(1);
    expect(hasToken(wrappers[0], "sm:flex-row")).toBe(true);
    // Able to be narrower than its own text, or `truncate` cannot fire.
    expect(hasToken(wrappers[0], "min-w-0")).toBe(true);

    // The fixture itself takes the free space from sm up and may shrink below it.
    const fixture = attrsWith(html, "sm:flex-1").filter((c) => !hasToken(c, "flex-col"));
    expect(fixture).toStrictEqual(["min-w-0 sm:flex-1"]);
  });

  it("stacks the time above the fixture below sm, because a 64px gutter is 30% of the row", () => {
    const row = attrsWith(markup(<RelatedEventRow event={FALCONS_PANTHERS} />), "rounded-lg");

    expect(row).toHaveLength(1);
    expect(hasToken(row[0], "flex-col")).toBe(true);
    expect(hasToken(row[0], "sm:flex-row")).toBe(true);

    // The gutter itself: reserved from sm up, not at phone width. Unprefixed,
    // `w-16` plus its gap takes 76px of a 294px row and the fixture pays it.
    const gutters = attrsWith(markup(<RelatedEventRow event={FALCONS_PANTHERS} />), "sm:w-16");
    expect(gutters).toHaveLength(1);
    expect(hasToken(gutters[0], "w-16")).toBe(false);
  });

  it("lets the odds block shrink below sm — an unprefixed flex-shrink-0 there IS the defect", () => {
    const blocks = oddsBlocks(markup(<RelatedEventRow event={FALCONS_PANTHERS} />));

    expect(blocks).toHaveLength(1);
    expect(hasToken(blocks[0], "flex-shrink-0")).toBe(false);
  });

  it("caps a team name at 10rem only from sm up, so two names cannot claim 320px of a 210px column", () => {
    const html = markup(<RelatedEventRow event={BROWNS_BUCS} />);

    const names = attrsWith(html, "truncate").filter((c) => hasToken(c, "font-medium"));
    expect(names).toHaveLength(2);
    for (const name of names) {
      expect(hasToken(name, "sm:max-w-[10rem]")).toBe(true);
      expect(hasToken(name, "max-w-[10rem]")).toBe(false);
      // Truncation only happens if the box is allowed to be smaller than its text.
      expect(hasToken(name, "min-w-0")).toBe(true);
    }
  });

  it("shrinks the name and never the number — a clipped percentage is the thing being read", () => {
    const html = markup(<RelatedEventRow event={BROWNS_BUCS} />);
    // `mx-1` is the score's own mono span, which belongs to the fixture line.
    const percentSpans = attrsWith(html, "font-mono").filter((c) => !hasToken(c, "mx-1"));

    expect(percentSpans).toHaveLength(2);
    for (const span of percentSpans) {
      expect(hasToken(span, "flex-shrink-0")).toBe(true);
    }
  });

  it("still renders the fixture text itself — the row's subject and its link target", () => {
    const html = markup(<RelatedEventRow event={BROWNS_BUCS} />);

    expect(html).toContain("Cleveland Browns");
    expect(html).toContain("Tampa Bay Buccaneers");
    expect(html).toContain("at</span>");
    expect(html).toContain('href="/events/14782150"');
  });
});

describe("#7416 the percentages — a priced team never reads 0%", () => {
  it("prints <1% for Atlanta 0.0035 and Carolina 0.0045, which both printed 0%", () => {
    const html = markup(<RelatedEventRow event={FALCONS_PANTHERS} />);

    expect(percents(html)).toStrictEqual(["<1%", "<1%"]);
    expect(html).not.toContain(">0%<");
  });

  it("leaves a percentage that was never on the boundary alone", () => {
    // Tampa Bay 0.0115 rounds to 1 and is printed as 1%, not marked.
    expect(percents(markup(<RelatedEventRow event={BROWNS_BUCS} />))).toStrictEqual([
      "<1%",
      "1%",
    ]);
  });

  it("prints a genuine zero as 0% — the marker is for values rounding ACROSS the boundary", () => {
    const event: RelatedEvent = {
      ...FALCONS_PANTHERS,
      linked_teams: [
        { ...FALCONS_PANTHERS.linked_teams[0], probability: 0 },
        { ...FALCONS_PANTHERS.linked_teams[1], probability: 0.0045 },
      ],
    };

    // Away first, so the genuine zero (Atlanta, home) is the second reading.
    expect(percents(markup(<RelatedEventRow event={event} />))).toStrictEqual(["<1%", "0%"]);
  });

  it("prints no percentage at all for a team the market has not priced", () => {
    const event: RelatedEvent = {
      ...FALCONS_PANTHERS,
      linked_teams: [
        { ...FALCONS_PANTHERS.linked_teams[0], probability: null },
        { ...FALCONS_PANTHERS.linked_teams[1], probability: null },
      ],
    };
    const html = markup(<RelatedEventRow event={event} />);

    expect(percents(html)).toStrictEqual([]);
    // The names are still there — the row is not blanked, only the missing number is.
    expect(html).toContain("Atlanta Falcons");
    expect(html).toContain("Carolina Panthers");
  });
});

describe("#7416 the odds read in the fixture's own order", () => {
  it("prints away then home, matching 'Carolina Panthers at Atlanta Falcons'", () => {
    const html = markup(<RelatedEventRow event={FALCONS_PANTHERS} />);

    // Served [home, away]; rendered away-first.
    expect(html.indexOf("Carolina Panthers")).toBeLessThan(html.indexOf("Atlanta Falcons"));
    expect(fixtureOrderedTeams(FALCONS_PANTHERS.linked_teams).map((t) => t.side)).toStrictEqual([
      "away",
      "home",
    ]);
  });

  it("is a reorder, not a filter — every served team still renders", () => {
    const ordered = fixtureOrderedTeams(FALCONS_PANTHERS.linked_teams);

    // Compared by name: a bare `.sort()` over objects coerces every element to
    // "[object Object]", ties them all, and passes on a comparator that dropped
    // a team and duplicated another.
    const byName = (teams: RelatedEventLinkedTeam[]) =>
      [...teams].sort((a, b) => a.team_name.localeCompare(b.team_name));

    expect(ordered).toHaveLength(FALCONS_PANTHERS.linked_teams.length);
    expect(byName(ordered)).toStrictEqual(byName(FALCONS_PANTHERS.linked_teams));
  });

  it("leaves the served order alone when the sides are not home/away", () => {
    // Both sides tie on rank, so only a STABLE sort preserves this; an
    // unstable one, or a comparator that invented an order, would move them.
    const odd = [
      { ...FALCONS_PANTHERS.linked_teams[0], side: "neutral" as unknown as RelatedEventLinkedTeam["side"], team_name: "First" },
      { ...FALCONS_PANTHERS.linked_teams[1], side: "neutral" as unknown as RelatedEventLinkedTeam["side"], team_name: "Second" },
    ];

    expect(fixtureOrderedTeams(odd).map((t) => t.team_name)).toStrictEqual(["First", "Second"]);
  });

  it("sorts a side it does not recognise AFTER the two it does", () => {
    // Mixed, not uniform: with every side unknown the ranks tie and any default
    // preserves the order, so a uniform case cannot tell `?? 2` from `?? 0`.
    const mixed = [
      { ...FALCONS_PANTHERS.linked_teams[0], side: "neutral" as unknown as RelatedEventLinkedTeam["side"], team_name: "Neutral" },
      { ...FALCONS_PANTHERS.linked_teams[1], side: "home" as const, team_name: "Home" },
    ];

    expect(fixtureOrderedTeams(mixed).map((t) => t.team_name)).toStrictEqual(["Home", "Neutral"]);
  });

  it("does not drop a single-sided row", () => {
    const solo = [FALCONS_PANTHERS.linked_teams[0]];

    expect(fixtureOrderedTeams(solo).map((t) => t.team_name)).toStrictEqual(["Atlanta Falcons"]);
  });

  it("returns a new array rather than sorting the payload in place", () => {
    const served = [...FALCONS_PANTHERS.linked_teams];
    fixtureOrderedTeams(served);

    expect(served.map((t) => t.side)).toStrictEqual(["home", "away"]);
  });
});

describe("#7416 the section", () => {
  it("names what the percentages are, so they are not read as the game's price", () => {
    const html = markup(<GamesThisWeek events={[FALCONS_PANTHERS, BROWNS_BUCS]} />);

    expect(html).toContain("Games This Week");
    expect(html).toContain("Each team&#x27;s odds in this market.");
  });

  it("renders one row per event", () => {
    const html = markup(<GamesThisWeek events={[FALCONS_PANTHERS, BROWNS_BUCS]} />);

    expect(Array.from(html.matchAll(/href="\/events\//g))).toHaveLength(2);
  });

  it("renders nothing at all when there are no related events", () => {
    const html = markup(<GamesThisWeek events={[]} />);

    // Not "an empty card with a heading and a caption over nothing".
    expect(html).toBe("");
  });

  it("renders a row whose odds are missing entirely without an empty odds box", () => {
    const event: RelatedEvent = { ...FALCONS_PANTHERS, linked_teams: [] };
    const html = markup(<RelatedEventRow event={event} />);

    expect(oddsBlocks(html)).toStrictEqual([]);
    expect(html).toContain("Carolina Panthers");
  });
});
