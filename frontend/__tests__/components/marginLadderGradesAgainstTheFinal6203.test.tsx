/**
 * #6203 — A SETTLED MARGIN LADDER GRADES INSTEAD OF QUOTING.
 *
 * One settled card, two grammars. `/events/14637256` (New York Giants 28 ·
 * Dallas Cowboys 20, SNF, Final), the two rails side by side:
 *
 *   Total: expected vs final     EACH LINE VS THE FINAL      Over 44.5    cleared
 *   Margin: expected vs final    LAST QUOTE FOR WINNING BY   NYG by 1.5+  100%
 *
 * "Last quote" is not what those prices are. `probability` is read live and
 * collapses to the RESOLVED price the moment a market settles — production
 * served `1.0` for every rung above — so the margin rail was presenting
 * settlement values as if they were the last thing anyone quoted, with a
 * probability bar drawn for a question that already had an answer, one tap from
 * a totals rail on the same card that grades.
 *
 * ═══ THIS IS #3769'S DOCTRINE WITH THE MARGIN RAIL LEFT OUT OF IT ═══
 *
 * #3769 ruled it for the full-game TOTALS card and #6169 carried it to the half
 * TOTALS cards. Neither touched a margin rail, so `MarketMapSection` pushed
 * `{label, probability, side}` and no `outcome`, `ladderGraded()` was false for
 * every margin card that has ever rendered, and the whole card fell to the
 * quoting arm. The machinery was already waiting: `ladderHeading`'s graded arm
 * and `LadderRows`' `cleared` / `not cleared` are variant-agnostic and have been
 * since #3769.
 *
 * The same relationship as #6199 → #3788: a rule the codebase already held,
 * with one surface never built.
 *
 * ═══ WHY THE GRADE IS THE SCORE AND NEVER THE PRICE ═══
 *
 * `gradeMarginRung` never consults `probability`, `is_winner` or
 * `resolution_source`. It reads the final margin, gated on the same scoreboard
 * test the FINAL marker is gated on — #3769's rule that the ladder grades
 * exactly when the card draws the number it grades against. So the card reads
 * correctly whatever the venue's settled prices happen to be, which is what the
 * two production arms below are for: 14637256's full-game rungs are ALL served
 * at `1.0`, and four of them are for margins the Giants never reached on the
 * half rail beside them.
 *
 * ═══ BOTH MARGIN RAILS, BECAUSE HALF-FIXING IS THE DEFECT ═══
 *
 * The half TOTALS card already grades (#6169). Leaving the half MARGIN card
 * quoting would reproduce, one card lower on the same page, exactly the
 * two-tenses defect this ship closes on the full-game pair.
 *
 * ═══ WHAT MAKES THIS SUITE NON-VACUOUS ═══
 *
 * "No percentage" is also what a card that never rendered looks like, so every
 * arm renders the REAL `MarketMapSection`, asserts the card is STILL THERE by
 * title, and names every rung it expects. The controls each differ from a
 * defect arm in ONE input: the event status (kills a fix that grades everything),
 * the scoreboard (kills a fix that grades without the number it grades
 * against), and a synthetic rung sitting exactly ON the final (kills the
 * `>` / `>=` mutant, which no production fixture can distinguish — every real
 * cover line is quoted at `.5`).
 *
 * Every number below is production's, read from
 * `/api/events/14637256/game-markets` at 2026-09-14 19:4xZ, except the two
 * blocks labelled SYNTHETIC.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;|&#39;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * ONE card's ONE ladder.
 *
 * Two bounds, and this suite needed both before it could see the half rail at
 * all. A page can hold several margin cards, so the slice starts at the named
 * card's title — without that, the half arm below read the FULL-GAME card's
 * rungs and scored them as the half's. And `MarketMap` renders its ladder
 * TWICE, inline and in the tap popover, so the slice ends at the second copy of
 * the heading — without that, the last rung's cell swallowed the whole popover.
 */
function ladderOf(text: string, cardTitle: string): string {
  const card = text.slice(text.indexOf(cardTitle));
  const from = card.indexOf("Each line vs the final");
  if (from < 0) return "";
  const body = card.slice(from + "Each line vs the final".length);
  const second = body.indexOf("Each line vs the final");
  return second < 0 ? body : body.slice(0, second);
}

/**
 * Each rung's verdict, bounded by the NEXT rung's label rather than by a
 * character count — #6169's lesson, and it matters more here because
 * `toContain("cleared")` is satisfied by `"not cleared"`, so a fixed window and
 * a substring test make a wrong grade score as a pass. Exact strings, exact
 * bounds.
 */
function verdictsOf(ladder: string, labels: string[]): string[] {
  return labels.map((label, i) => {
    const at = ladder.indexOf(`${label} `);
    if (at < 0) return `${label}:absent`;
    const next = i + 1 < labels.length ? ladder.indexOf(`${labels[i + 1]} `, at) : -1;
    const cell = ladder.slice(at + label.length + 1, next < 0 ? undefined : next).trim();
    return `${label}:${cell}`;
  });
}

const HOME = "New York Giants";
const AWAY = "Dallas Cowboys";

/** Production's own history rows: halftime 14-7, final 28-20. */
const ESPN_HISTORY = [
  { period: "1st Quarter", home_score: 0, away_score: 0, timestamp: "2026-09-14T00:20:00+00:00" },
  { period: "Halftime", home_score: 14, away_score: 7, timestamp: "2026-09-14T01:30:00+00:00" },
  { period: "Final", home_score: 28, away_score: 20, timestamp: "2026-09-14T03:28:00+00:00" },
];

type Spread = { name: string; probability: number | null };

/**
 * `/events/14637256`'s full-game cover ladder **exactly as production serves
 * it** — six rungs, every one at `1.0`, which is the photograph: `NYG by 1.5+
 * 100%` under "LAST QUOTE FOR WINNING BY".
 *
 * The `…: Winning Margin` band row production also files here is deliberately
 * ABSENT. It is #6199's subject, not this ship's, and a fixture that carried it
 * would couple this suite to whether that sha has landed.
 */
const SNF_FULL_GAME: Spread[] = [
  { name: "New York G wins by over 1.5 points", probability: 1.0 },
  { name: "New York G wins by over 2.5 points", probability: 1.0 },
  { name: "New York G wins by over 3.5 points", probability: 1.0 },
  { name: "New York G wins by over 4.5 points", probability: 1.0 },
  { name: "New York G wins by over 5.5 points", probability: 1.0 },
  { name: "New York G wins by over 6.5 points", probability: 1.0 },
  { name: "New York G wins by over 7.5 points", probability: 1.0 },
];

/**
 * `/events/14637256`'s 1st-half cover ladder as production serves it — both
 * sides, and the mixed case the full-game ladder cannot show. 1H was 14-7, so
 * the Giants' 6.5 cleared and their 7.5 did not: the boundary straddles the
 * real number without a synthetic.
 */
const SNF_1H: Spread[] = [
  { name: "NY Giants wins 1H by over 2.5 points", probability: 1.0 },
  { name: "NY Giants wins 1H by over 3.5 points", probability: 1.0 },
  { name: "NY Giants wins 1H by over 4.5 points", probability: 1.0 },
  { name: "NY Giants wins 1H by over 6.5 points", probability: 1.0 },
  { name: "NY Giants wins 1H by over 7.5 points", probability: null },
  { name: "NY Giants wins 1H by over 9.5 points", probability: null },
  { name: "NY Giants wins 1H by over 10.5 points", probability: null },
  { name: "DAL Cowboys wins 1H by over 2.5 points", probability: null },
  { name: "DAL Cowboys wins 1H by over 3.5 points", probability: null },
  { name: "DAL Cowboys wins 1H by over 4.5 points", probability: null },
  { name: "DAL Cowboys wins 1H by over 6.5 points", probability: null },
];

/**
 * SYNTHETIC. A rung sitting EXACTLY on the 8-point final margin.
 *
 * Venues quote cover lines at `.5` precisely so this cannot occur, so this is
 * not claimed as a production ladder — it exists because without it `>` and
 * `>=` grade every real fixture in this file identically and the comparison is
 * untested.
 *
 * `NYG by 8+` is TRUE of an 8-point win, and the rail draws `FINAL NYG by 8`
 * two inches above it, so the inclusive reading is the one the card must not
 * contradict. The two spellings that reach this rail agree: "wins by 15 or more
 * points" is `>= 15` outright, and a `.5` cover line cannot tell the two apart.
 */
const ON_THE_NUMBER: Spread[] = [
  { name: "New York G wins by over 7 points", probability: 1.0 },
  { name: "New York G wins by over 8 points", probability: 1.0 },
  { name: "New York G wins by over 9 points", probability: 0.0 },
];

/**
 * SYNTHETIC. The losing side of a full-game rail, which 14637256 does not serve
 * — Kalshi filed no Cowboys cover rungs for this game. Without it a fix that
 * grades every rung `cleared` passes the production arm above.
 */
const LOSING_SIDE: Spread[] = [
  { name: "New York G wins by over 1.5 points", probability: 1.0 },
  { name: "Dallas wins by over 1.5 points", probability: 0.0 },
  { name: "Dallas wins by over 6.5 points", probability: 0.0 },
];

function fullGameRow(s: Spread) {
  return {
    market_name: "Dallas vs New York: Spread",
    outcome_name: s.name,
    probability: s.probability,
    source: "kalshi",
    market_type: null,
    // Deliberately production's values: the grade must not read them.
    is_winner: true,
    resolution_source: "api_settlement",
    movement: 0,
  };
}

function halfRow(s: Spread) {
  return {
    market_name: "DAL Cowboys vs NY Giants: 1st Half Spread",
    outcome_name: s.name,
    probability: s.probability,
    source: "kalshi",
    market_type: "half_spread",
    period: "1H",
    is_winner: true,
    resolution_source: "api_settlement",
    movement: 0,
  };
}

function markets(
  spreads: Spread[],
  opts: { half?: Spread[]; scored?: boolean } = {}
) {
  const scored = opts.scored ?? true;
  return {
    event_id: 14637256,
    home_team: HOME,
    away_team: AWAY,
    home_score: scored ? 28 : null,
    away_score: scored ? 20 : null,
    status: "completed",
    player_props: [],
    team_totals: [],
    period_markets: (opts.half ?? []).map(halfRow),
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: spreads.map(fullGameRow),
    totals: [],
  };
}

/**
 * The section as the finished event page mounts it. No `totals`, so the only
 * cards in the markup are margin rails and every verdict below belongs to one.
 */
function renderMap(
  spreads: Spread[],
  opts: {
    half?: Spread[];
    scored?: boolean;
    eventStatus?: string;
    espnHistory?: typeof ESPN_HISTORY | undefined;
  } = {}
): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={markets(spreads, opts) as never}
      eventStatus={opts.eventStatus ?? "completed"}
      homeTeam={HOME}
      awayTeam={AWAY}
      homeAbbr="NYG"
      awayAbbr="DAL"
      sportKey="americanfootball_nfl"
      espnHistory={"espnHistory" in opts ? opts.espnHistory : ESPN_HISTORY}
    />
  );
}

describe("#6203 the settled margin ladder grades instead of quoting", () => {
  it("stops quoting the card Alex would have read, and prints no price at all", () => {
    const text = visibleText(renderMap(SNF_FULL_GAME));

    // The card is still here with every rung named. This is what makes the
    // absences below assertions rather than a description of a card that
    // vanished.
    expect(text).toContain("Margin: expected vs final");
    for (const t of [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]) {
      expect(text).toContain(`NYG by ${t}+`);
    }

    // The photograph, gone.
    expect(text).toContain("Each line vs the final");
    expect(text).not.toContain("Last quote for winning by");
    expect(text).not.toContain("Chance of winning by");

    // A graded ladder prints no percentage, so the resolved `1.0` the venue
    // served can no longer reach the reader as "100%".
    const ladder = text.slice(text.indexOf("Each line vs the final"));
    expect(ladder).not.toContain("100%");

    // Giants by 8: every one of these lines was cleared.
    expect(
      verdictsOf(
        ladderOf(text, "Margin: expected vs final"),
        [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5].map((t) => `NYG by ${t}+`)
      )
    ).toEqual([
      "NYG by 1.5+:cleared",
      "NYG by 2.5+:cleared",
      "NYG by 3.5+:cleared",
      "NYG by 4.5+:cleared",
      "NYG by 5.5+:cleared",
      "NYG by 6.5+:cleared",
      "NYG by 7.5+:cleared",
    ]);
  });

  it("grades the losing side against the mirror of the same final", () => {
    const text = visibleText(renderMap(LOSING_SIDE));

    expect(text).toContain("Each line vs the final");
    expect(
      verdictsOf(ladderOf(text, "Margin: expected vs final"), [
        "DAL by 6.5+",
        "DAL by 1.5+",
        "NYG by 1.5+",
      ])
    ).toEqual([
      "DAL by 6.5+:not cleared",
      "DAL by 1.5+:not cleared",
      "NYG by 1.5+:cleared",
    ]);
  });

  it("grades a rung sitting exactly on the final as cleared, matching its own label", () => {
    const text = visibleText(renderMap(ON_THE_NUMBER));

    expect(text).toContain("Each line vs the final");
    expect(
      verdictsOf(ladderOf(text, "Margin: expected vs final"), [
        "NYG by 7+",
        "NYG by 8+",
        "NYG by 9+",
      ])
    ).toEqual([
      "NYG by 7+:cleared",
      // `NYG by 8+` on an 8-point win. A `>` test would call this one "not
      // cleared" while the rail's own FINAL marker reads NYG by 8.
      "NYG by 8+:cleared",
      "NYG by 9+:not cleared",
    ]);
  });

  it("grades the half margin rail too, against the half's own score", () => {
    const text = visibleText(renderMap(SNF_FULL_GAME, { half: SNF_1H }));

    expect(text).toContain("1st half margin");
    expect(text).toContain("Each line vs the final");
    expect(text).not.toContain("Last quote for winning by");

    // 1H was 14-7. The Giants' 6.5 cleared and their 7.5 did not — and the
    // grade is the HALF's +7, not the game's +8, which is what separates this
    // arm from a fix that grades every rail against the final score.
    const verdicts = verdictsOf(ladderOf(text, "1st half margin"), [
      "DAL by 6.5+",
      "DAL by 4.5+",
      "DAL by 3.5+",
      "DAL by 2.5+",
      "NYG by 2.5+",
      "NYG by 3.5+",
      "NYG by 4.5+",
      "NYG by 6.5+",
      "NYG by 7.5+",
      "NYG by 9.5+",
      "NYG by 10.5+",
    ]);
    expect(verdicts).toEqual([
      "DAL by 6.5+:not cleared",
      "DAL by 4.5+:not cleared",
      "DAL by 3.5+:not cleared",
      "DAL by 2.5+:not cleared",
      "NYG by 2.5+:cleared",
      "NYG by 3.5+:cleared",
      "NYG by 4.5+:cleared",
      "NYG by 6.5+:cleared",
      "NYG by 7.5+:not cleared",
      "NYG by 9.5+:not cleared",
      "NYG by 10.5+:not cleared",
    ]);
  });

  it("stops calling graded rows 'quoted' in the sentence over them", () => {
    // Production's own Cowboys rungs from that 1st half — every one served
    // `null`, because they all lost. A ladder of losers paints no shape in the
    // band, which is the ONE arm where this card names its rungs in a sentence
    // instead of promising a curve (#3210) — so it is also the one arm where
    // "Four lines quoted" could appear over four graded rows.
    //
    // #6169 fixed exactly this on the half TOTALS card. The grading this ship
    // adds is what newly makes the arm reachable on the margin card, so the
    // third arm comes with it rather than after it.
    const text = visibleText(
      renderMap([], {
        half: [
          { name: "DAL Cowboys wins 1H by over 2.5 points", probability: null },
          { name: "DAL Cowboys wins 1H by over 3.5 points", probability: null },
          { name: "DAL Cowboys wins 1H by over 4.5 points", probability: null },
          { name: "DAL Cowboys wins 1H by over 6.5 points", probability: null },
        ],
      })
    );

    expect(text).toContain("1st half margin");
    expect(text).toContain("Four lines settled");
    expect(text).not.toContain("Four lines quoted");
    expect(
      verdictsOf(ladderOf(text, "1st half margin"), [
        "DAL by 6.5+",
        "DAL by 4.5+",
        "DAL by 3.5+",
        "DAL by 2.5+",
      ])
    ).toEqual([
      "DAL by 6.5+:not cleared",
      "DAL by 4.5+:not cleared",
      "DAL by 3.5+:not cleared",
      "DAL by 2.5+:not cleared",
    ]);
  });

  it("keeps quoting a match that has not been played", () => {
    const text = visibleText(
      renderMap(SNF_FULL_GAME, { eventStatus: "scheduled", scored: false, espnHistory: undefined })
    );

    // Same rungs, same card — and a live chance, because there is nothing to
    // grade against.
    expect(text).toContain("NYG by 1.5+");
    expect(text).toContain("Chance of winning by");
    expect(text).not.toContain("Each line vs the final");
    expect(text).not.toContain("cleared");
  });

  it("keeps quoting a finished match whose scoreboard the page does not have", () => {
    const text = visibleText(
      renderMap(SNF_FULL_GAME, { scored: false, espnHistory: undefined })
    );

    // #3769's gate: the ladder grades exactly when the rail draws the number it
    // grades against. Without a score there is no FINAL marker and no grade —
    // the card says the numbers are last quotes rather than inventing a verdict.
    expect(text).toContain("NYG by 1.5+");
    expect(text).toContain("Last quote for winning by");
    expect(text).not.toContain("Each line vs the final");
    expect(text).not.toContain("cleared");
  });
});
