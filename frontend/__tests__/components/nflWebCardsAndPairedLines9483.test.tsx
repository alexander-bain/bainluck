/**
 * #9483 — the NFL web slice's ink (design freeze v328): the game-story deck
 * under the chart, the full-size reader and a line's exact details. The
 * chart's second team line was retired by #11356 (one line, two poles). The decisions are pinned in
 * `__tests__/nflEventCardDeck9483.test.ts`; this file reads the markup.
 *
 * Control: `pairedAwayLine` is inert since #11356 — a chart with it is
 * byte-identical to one without.
 *
 * 🪤 recharts draws nothing inside a `ResponsiveContainer` without a viewport,
 * so it is mocked to 390×300, as in `oddsChartDrawsRecordedCheckpoints4974`.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OddsChart from "@/components/OddsChart";
import { AnalyticsProvider } from "@/components/Analytics";
import EventCardReader, { LineDetails } from "@/components/event/EventCardReader";
import { NFLEventCardDeck } from "@/components/event/NFLEventCards";
import {
  lineLead,
  milestoneCards,
  propRowId,
  readerHeader,
  rowsForCards,
  type FinishCard,
  type NflEventCard,
  type NflPropRow,
} from "@/lib/nflEventCardDeck";
import { projectedTeamStrokes } from "@/lib/teamLineStrokes";

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 390, height: 300 }),
  };
});

const KICKOFF = Date.UTC(2026, 9, 16, 0, 15, 0);
const MIN = 60_000;
const iso = (offsetMin: number) => new Date(KICKOFF + offsetMin * MIN).toISOString();
const HOME = "Denver Broncos";
const AWAY = "Seattle Seahawks";
// Production colours for /events/14780559: two navies (#10547's case).
const HOME_HEX = "#0a2343";
const AWAY_HEX = "#002a5c";

const row = (player: string, line: number, p: number, extra: Partial<NflPropRow> = {}): NflPropRow => ({
  market_name: "Seattle vs Denver: Receiving Yards",
  outcome_name: `${player}: ${line}+`,
  threshold: line,
  over_probability: p,
  source: "kalshi",
  observed_at: iso(-30),
  pregame_mark: p - 0.05,
  player_team: "away",
  ...extra,
});
const PROPS = [
  ...[39.5, 49.5, 59.5, 69.5, 79.5].map((l, i) => row("Jaxon Smith-Njigba", l, [0.85, 0.71, 0.58, 0.4, 0.27][i], { actual: 84, hit: true })),
  ...[29.5, 39.5, 49.5].map((l, i) => row("Courtland Sutton", l, [0.7, 0.5, 0.3][i], { player_team: "home", actual: 0, hit: false })),
];
const FINISH: FinishCard = {
  kind: "finish",
  id: "finish",
  phase: "after",
  pregame: { away: 20.5, home: 23.5, at: KICKOFF - MIN },
  projectedNow: null,
  final: { away: 27, home: 17, at: KICKOFF + 200 * MIN },
};
const strokes = projectedTeamStrokes(HOME_HEX, AWAY_HEX);
const TEAMS = { awayName: AWAY, homeName: HOME, awayShort: "Seahawks", homeShort: "Broncos", awayColor: strokes.away, homeColor: strokes.home };
const finalCards = milestoneCards({
  props: PROPS,
  eventStatus: "completed",
  commenceTime: iso(0),
  homeTeam: HOME,
  awayTeam: AWAY,
  nowMs: KICKOFF + 240 * MIN,
});
const DECK: NflEventCard[] = [FINISH, ...finalCards];
const HEADER = readerHeader({
  awayShort: "SEA",
  homeShort: "DEN",
  awayScore: 27,
  homeScore: 17,
  stateLabel: "Final",
  awayChance: null,
  homeChance: null,
  finished: true,
});

const noop = () => undefined;

function deck(cards: NflEventCard[] = DECK) {
  return renderToStaticMarkup(
    <NFLEventCardDeck cards={cards} teams={TEAMS} selection={{}} onSelect={noop} onOpen={noop} openerRef={noop} />,
  );
}

function reader(openCardId: string, liveCards: NflEventCard[] = DECK) {
  return renderToStaticMarkup(
    <EventCardReader
      openCardId={openCardId}
      liveCards={liveCards}
      liveHeader={HEADER}
      liveRows={rowsForCards(liveCards, PROPS)}
      teams={TEAMS}
      selection={{}}
      onSelect={noop}
      onClose={noop}
    />,
  );
}

describe("#9483 the deck under the chart", () => {
  it("draws the finish card and both player cards, each with its own Open control", () => {
    const html = deck();
    expect(html).toContain("Game stories");
    expect(html).toContain("3 cards");
    expect(html).toContain("Final vs forecast");
    expect(html).toContain("Seattle Seahawks beat the forecast");
    expect(html).toContain('aria-label="Open Jaxon Smith-Njigba · Receiving Yards full size"');
    expect(html).toContain('aria-label="Open Courtland Sutton · Receiving Yards full size"');
    expect((html.match(/>Open full size</g) ?? []).length).toBe(3);
  });

  it("a final separates the actual (stat axis) from the pregame chances (0–100%) — journey 5", () => {
    const html = deck();
    // 84 sits above every line; 0 sits below the ladder. Both are drawn as a rule on the stat axis.
    expect(html).toContain('data-actual="84"');
    expect(html).toContain('data-actual="0"');
    expect(html).toMatch(/>0%<\/text>/);
    expect(html).toMatch(/>100%<\/text>/);
    expect(html).toContain("Chance before kickoff to reach each line");
    // The selected line (nearest even odds: 59.5+ at the 53% mark) reads its pregame mark and the grade.
    expect(html).toContain("59.5+ · 53%");
    expect(html).toContain("HIT");
    // A final never prints the terminal quote as the chance.
    expect(html).not.toContain("59.5+ · 58%");
  });

  it("an empty deck draws nothing", () => {
    expect(deck([])).toBe("");
  });

  it("the finish card legend says which mark is which", () => {
    expect(deck()).toContain("Points · outline = pregame · cross = final");
  });
});

describe("#11098 the finish card's row labels use the hero's short names", () => {
  // SEA@DEN live, 390px: the rows read "Seattle Se…" / "Denver Bro…" beside the number columns.
  const rowLabels = (html: string) =>
    [...html.matchAll(/<span class="text-sm font-semibold min-w-0 flex-1 truncate"[^>]*>([^<]*)<\/span>/g)].map((m) => m[1]);

  it("labels each row with the short name, keeping the full names in the headline and the spoken label", () => {
    const html = deck([FINISH]);
    expect(rowLabels(html)).toEqual(["Seahawks", "Broncos"]);
    expect(html).toContain("Seattle Seahawks beat the forecast");
    expect(html).toMatch(/aria-label="[^"]*Pregame projection Seattle Seahawks 20\.5, Denver Broncos 23\.5/);
  });

  it("control: a caller with no short names keeps today's full-name rows", () => {
    const html = renderToStaticMarkup(
      <NFLEventCardDeck cards={[FINISH]} teams={{ ...TEAMS, awayShort: undefined, homeShort: undefined }} selection={{}} onSelect={noop} onOpen={noop} openerRef={noop} />,
    );
    expect(rowLabels(html)).toEqual(["Seattle Seahawks", "Denver Broncos"]);
  });
});

describe("#9483 the full-size reader", () => {
  it("opens on the card it was asked for, with a count, and only that card is exposed", () => {
    const target = finalCards[0].id;
    const html = reader(target);
    expect(html).toContain('data-testid="reader-count">2 of 3<');
    expect(html).toContain("SEA 27–17 DEN · Final");
    const active = html.match(/data-card-id="([^"]+)"(?: data-active="true")/);
    expect(active?.[1]).toBe(target);
    // Inactive cards are hidden from assistive reading and inert.
    expect((html.match(/aria-hidden="true" inert=""/g) ?? []).length).toBe(2);
    // A held deck that matches the live one offers no Refresh.
    expect(html).not.toContain('data-testid="reader-refresh"');
  });

  it("an empty deck is a readable empty state, never “1 of 0” — journey 8", () => {
    const html = reader(finalCards[0].id, []);
    expect(html).toContain("No game stories right now");
    expect(html).not.toMatch(/of 0</);
    expect(html).not.toContain('data-testid="reader-count"');
  });

  it("Back is the first control and names where it goes", () => {
    const html = reader("finish");
    expect(html.indexOf('aria-label="Back to the game"')).toBeLessThan(html.indexOf('aria-label="Previous card"'));
    expect(html).toContain('role="dialog" aria-modal="true" aria-label="Game story cards"');
  });
});

describe("#9483 a line's exact details", () => {
  it("names each number for what it is and always dates the last quote", () => {
    const html = renderToStaticMarkup(<LineDetails row={PROPS[2]} lead={{ chance: 0.4, basis: "pregameMark" }} onDone={noop} />);
    expect(html).toContain("Chance before kickoff");
    expect(html).toContain("Last quote");
    expect(html).toContain("Quoted");
    expect(html).not.toContain("Time unknown");
    expect(html).toContain("Kalshi");
    expect(html).toContain("Result");
    expect(html).toContain("Graded");
    expect(html).toContain(">HIT<");
    const undated = renderToStaticMarkup(<LineDetails row={{ ...PROPS[2], observed_at: null }} onDone={noop} />);
    expect(undated).toContain("Time unknown");
  });

  it("v335: the card's chance leads, the result is its own group, and the dated quote is secondary", () => {
    const row = { ...PROPS[2], pregame_mark: 0.295, over_probability: 1, actual: 84, hit: true };
    const html = renderToStaticMarkup(<LineDetails row={row} lead={{ chance: 0.295, basis: "pregameMark" }} onDone={noop} />);
    const pregame = html.indexOf('data-testid="line-details-pregame"');
    const result = html.indexOf('data-testid="line-details-result"');
    const quote = html.indexOf('data-testid="line-details-quote"');
    expect(pregame).toBeGreaterThan(-1);
    expect(result).toBeGreaterThan(pregame);
    expect(quote).toBeGreaterThan(result);
    // The 100% quote lives only in the secondary group, never beside the lead.
    const lead = html.slice(pregame, result);
    expect(lead).toContain("Chance before kickoff");
    expect(lead).toContain("30%");
    expect(lead).not.toContain("100%");
    expect(html.slice(quote)).toContain("100%");
    expect(html.slice(quote)).toContain("Quote &amp; source");
  });

  it("v335: with no lead the sheet has no headline — neither the quote nor the row's mark is promoted", () => {
    const row = { ...PROPS[2], pregame_mark: 0.42, over_probability: 0.62 };
    const html = renderToStaticMarkup(<LineDetails row={row} onDone={noop} />);
    expect(html).not.toContain('data-testid="line-details-pregame"');
    expect(html).not.toContain("42%");
    expect(html.slice(html.indexOf('data-testid="line-details-quote"'))).toContain("62%");
  });

  it("v335: before kickoff the lead is the card's current quote, not the row's mark (the opening line)", () => {
    // Before kickoff the server's `pregame_mark` falls back to the opening line;
    // the card prints the recent quote, and the sheet leads with the card's number.
    const pre: NflPropRow[] = PROPS.slice(0, 5).map((r) => ({ ...r, actual: null, hit: null, observed_at: iso(-30) }));
    const row = pre[2];
    expect(row.pregame_mark).toBeCloseTo(0.53);
    expect(row.over_probability).toBeCloseTo(0.58);
    const cards = milestoneCards({
      props: pre,
      eventStatus: "scheduled",
      commenceTime: iso(0),
      homeTeam: HOME,
      awayTeam: AWAY,
      nowMs: KICKOFF - 25 * MIN,
    });
    const lead = lineLead(cards, propRowId(row));
    expect(lead).toEqual({ chance: 0.58, basis: "pregamePrice" });
    const html = renderToStaticMarkup(<LineDetails row={row} lead={lead} onDone={noop} />);
    const head = html.slice(html.indexOf('data-testid="line-details-pregame"'), html.indexOf('data-testid="line-details-quote"'));
    expect(head).toContain("Pregame chance");
    expect(head).toContain("58%");
    expect(html).not.toContain("53%");
    // A line the displayed cards do not carry has no lead.
    expect(lineLead(cards, "nope")).toBeNull();
  });

  it("a row that is no longer served says so", () => {
    expect(renderToStaticMarkup(<LineDetails row={undefined} onDone={noop} />)).toContain("This line is no longer offered.");
    expect(propRowId(PROPS[0])).toBe("kalshi|Seattle vs Denver: Receiving Yards|Jaxon Smith-Njigba: 39.5+");
  });
});

// ─── The chart's second team line ──────────────────────────────────────────

const series = (f: (m: number) => number, step = 1) => {
  const out: Array<{ timestamp: string; home_probability: number; away_probability: number }> = [];
  for (let m = 0; m <= 180; m += step) {
    const p = f(m);
    out.push({ timestamp: iso(m), home_probability: p, away_probability: 1 - p });
  }
  return out;
};
const blend = (m: number) => 0.6 - 0.3 * (m / 180);
type ChartProps = Partial<React.ComponentProps<typeof OddsChart>>;

function chart(over: ChartProps = {}): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      <OddsChart
        history={series(blend, 10) as never}
        homeTeam={HOME}
        awayTeam={AWAY}
        sportKey="americanfootball_nfl"
        commenceTime={iso(0)}
        eventStatus="live"
        isLive
        winProbHistory={{ espn: series((m) => blend(m) + 0.01, 5), kalshi: series((m) => blend(m) - 0.01, 5) } as never}
        aggregateLine={series(blend)}
        backendBlendServed
        homeTeamColor={HOME_HEX}
        awayTeamColor={AWAY_HEX}
        externalTimeRange="all"
        {...over}
      />,
    ),
  )
    .replace(/recharts\d+-clip/g, "recharts#-clip")
    .replace(/recharts-(line|scatter)-\d+/g, "recharts-$1-#");
}

// #11356 RETIRED the second team line this block used to pin: Alex's approved
// direction is one line between the two team poles, and the decisions live in
// `chartSingleTrajectory11356.test.tsx`. What remains here is that the prop
// the page still passes asks for nothing.
describe("#11356 the NFL chart draws one line; the #9483 paired-line prop is inert", () => {
  it("with the prop: one blend line, both poles, no away copy, no team keys", () => {
    const html = chart({ pairedAwayLine: true });
    expect(html).not.toContain("paired-away-line");
    expect(html).not.toContain('data-testid="paired-team-key"');
    expect(html).not.toMatch(new RegExp(`stroke="${strokes.away}"`));
    expect(html).toContain("The line rises towards");
    expect(html).toContain("+ 3 sources");
  });

  it("CONTROL: with or without the prop the chart is byte-identical", () => {
    expect(chart({ pairedAwayLine: true })).toBe(chart());
  });

  it("CONTROL: a draw-priced winner and a chart with no backend blend are unchanged by it", () => {
    expect(chart({ pairedAwayLine: true, awayWithheld: true })).toBe(chart({ awayWithheld: true }));
    expect(chart({ pairedAwayLine: true, backendBlendServed: false })).toBe(chart({ backendBlendServed: false }));
  });
});

// ─── #9483 NBA slice: the ladder cards' ink ────────────────────────────────

import nbaFinal from "../fixtures/nbaFinalMatrix15320337.json";
import nbaPregame from "../fixtures/nbaPregameMatrix15327183.json";
import { decodeQuestionMatrix, marginLadderCard, totalLadderCard, type LadderInputs } from "@/lib/nbaEventCards";

const NBA_TEAMS = { awayName: "Golden State Warriors", homeName: "Los Angeles Clippers", awayColor: "#1D428A", homeColor: "#C8102E" };

function nbaInputs(body: { game_question_matrix: unknown }, over: Partial<LadderInputs>): LadderInputs {
  return {
    questions: decodeQuestionMatrix(body.game_question_matrix),
    status: "completed",
    commenceTime: "2026-10-04T23:00:00Z",
    homeScore: 104,
    awayScore: 101,
    pregameProjection: null,
    homeShort: "Clippers",
    awayShort: "Warriors",
    nowMs: Date.parse("2026-10-05T04:00:00Z"),
    ...over,
  };
}

describe("#9483 NBA ladder cards", () => {
  it("a final with no admitted pin: actual and verdict, no chance axis and no dot", () => {
    const total = totalLadderCard(nbaInputs(nbaFinal, {}))!;
    const margin = marginLadderCard(nbaInputs(nbaFinal, {}))!;
    const html = deck([margin, total]);
    expect(html).toContain("Winning margin");
    expect(html).toContain("Scoring expectations");
    expect(html).toContain("Clippers by 3");
    expect(html).toContain("205 points");
    expect((html.match(/>Pregame chance unavailable for these lines</g) ?? []).length).toBe(2);
    expect(html).not.toMatch(/>100%<\/text>/);
    expect(html).not.toMatch(/<circle/);
    expect(html).toContain('data-actual="205"');
    expect(html).toContain('data-actual="3"');
    // Opens on the line nearest what happened, with the producer's verdict.
    expect(html).toContain("Over 204.5");
    expect(html).toContain("HIT");
  });

  it("a final with the producer's pregame_reading: one dot, its chance named apart from the verdict", () => {
    const m = JSON.parse(JSON.stringify(nbaFinal.game_question_matrix));
    for (const q of m.questions)
      for (const o of q.options)
        if (o.option_key === "o:240505185")
          o.pregame_reading = { state: "available", reason: null, probability: 0.61, observed_at: "2026-10-04T22:50:00+00:00", basis: "pregame_pin", outcome_id: 240505185 };
    const total = totalLadderCard(nbaInputs({ game_question_matrix: m }, {}))!;
    const html = deck([total]);
    expect(html).toContain("Chance before tip-off of finishing above each line");
    expect((html.match(/<circle/g) ?? []).length).toBe(1);
    expect(html).toContain("Over 206.5 · 61%");
    expect(html).toContain("Before tip-off · MISS");
    expect(html).toContain('data-actual="205"');
    expect(html).not.toMatch(/>Pregame chance unavailable for these lines</);
    // A line beside it with no reading (Over 204.5, won) says so itself, and keeps its verdict.
    const selected = renderToStaticMarkup(
      <NFLEventCardDeck cards={[total]} teams={TEAMS} selection={{ total: "o:240505186" }} onSelect={noop} onOpen={noop} openerRef={noop} />,
    );
    expect(selected).toContain("Pregame chance unavailable · HIT");
    expect(selected).not.toContain("Before tip-off · MISS");
    // Details: the reading is the pregame baseline, dated; the result stays its own row.
    const line = total.points.find((x) => x.optionKey === "o:240505185")!;
    const details = renderToStaticMarkup(<LineDetails row={line.detail} onDone={noop} />);
    expect(details).toContain("Pregame baseline");
    expect(details).toMatch(/61%/);
    expect(details).toContain("Graded");
    expect(details).not.toContain("Last quote");
  });

  // Lane1's review (19:11Z): the line-level "Pregame chance unavailable" belongs only to a
  // final where a sibling line has a chance. An all-null final says it once, in the caption;
  // during play the line says nothing about it.
  const LINE_UNAVAILABLE = /Pregame chance unavailable(?! for these lines)/;

  it("an all-null final: the caption says unavailable, the selected line does not repeat it", () => {
    const total = totalLadderCard(nbaInputs(nbaFinal, {}))!;
    const selected = renderToStaticMarkup(
      <NFLEventCardDeck cards={[total]} teams={TEAMS} selection={{ total: "o:240505186" }} onSelect={noop} onOpen={noop} openerRef={noop} />,
    );
    expect(selected).toContain(">Pregame chance unavailable for these lines<");
    expect(selected).toContain("HIT");
    expect(selected).not.toMatch(LINE_UNAVAILABLE);
  });

  it("during play beside a pinned sibling: an unpinned line says nothing about unavailability", () => {
    const m = JSON.parse(JSON.stringify(nbaPregame.game_question_matrix));
    const overs: string[] = [];
    for (const q of m.questions)
      for (const o of q.options)
        if (o.side === "over" && o.published?.value_state === "quoted" && Array.isArray(o.contributor_outcome_ids)) overs.push(o.option_key);
    expect(overs.length).toBeGreaterThanOrEqual(2);
    for (const q of m.questions)
      for (const o of q.options)
        if (o.option_key === overs[0])
          o.comparison = { state: "comparable", reason: null, baseline: { probability: 0.44, observed_at: "2026-10-15T23:20:00Z", basis: "pregame_pin" } };
    const live = totalLadderCard(
      nbaInputs(
        { game_question_matrix: m },
        { status: "live", commenceTime: "2026-10-15T23:30:00Z", homeScore: 20, awayScore: 18, nowMs: Date.parse("2026-10-15T23:40:00Z") },
      ),
    )!;
    expect(live.phase).toBe("during");
    expect(live.points.find((p) => p.optionKey === overs[0])!.chance).toBe(0.44);
    const unpinned = live.points.find((p) => p.optionKey !== overs[0] && p.chance === null)!;
    const selected = renderToStaticMarkup(
      <NFLEventCardDeck cards={[live]} teams={TEAMS} selection={{ total: unpinned.optionKey }} onSelect={noop} onOpen={noop} openerRef={noop} />,
    );
    expect(selected).toContain(unpinned.label);
    expect(selected).not.toMatch(/Pregame chance unavailable/);
  });

  it("before tip-off: each recent quote is a dot on its own team's side, with the Tie axis", () => {
    const margin = marginLadderCard(
      nbaInputs(nbaPregame, {
        status: "scheduled",
        commenceTime: "2026-10-15T23:30:00Z",
        homeScore: null,
        awayScore: null,
        homeShort: "Knicks",
        awayShort: "Raptors",
        nowMs: Date.parse("2026-10-15T18:40:00Z"),
      }),
    )!;
    const html = deck([margin]);
    expect(html).toContain("Pregame chance of winning by more than each margin");
    expect(html).toMatch(/>Tie<\/text>/);
    expect(html).toContain("← Raptors by");
    expect(html).toContain("Knicks by →");
    expect((html.match(/<circle/g) ?? []).length).toBe(margin.points.filter((p) => p.chance !== null).length);
    expect(html).not.toContain('data-mark="actual"');
  });
});
