/**
 * ONE SETTLED VOCABULARY — the guard that does not need to know the next word.
 *
 * UX-P106, item 1. Standing Alex ruling: *settled means settled* — one
 * system-wide settled language; heroes show winners, cards show results, props
 * show the script graded.
 *
 * ── WHY THE PREVIOUS GUARD COULD NOT HAVE CAUGHT THIS ────────────────────────
 *
 * UX-P105 shipped a guard alongside the near-miss it was written for: THE
 * DIVERGENCE rail's first draft returned "HAPPENED" / "DIDN'T HAPPEN", a THIRD
 * settled vocabulary on a screen that already stacks three settled surfaces. It
 * was caught in a rendered screenshot and by no test at all.
 *
 * That guard (`propResolution.test.ts`, "ONE settled vocabulary") asserts, over
 * a HARD-CODED list of three files, that the literals `HIT` and `MISS` do not
 * appear. Both halves of that shape are structurally blind:
 *
 *   1. It bans the words it ALREADY KNOWS. A denylist of known-good words is
 *      unable, in principle, to see a new pair. "HAPPENED" / "DIDN'T HAPPEN"
 *      passes it. So does WON/LOST, CASHED/BUSTED, ✅/❌.
 *   2. It reads THREE NAMED FILES. A fourth surface is simply not looked at.
 *
 * Both were live defects in the tree this file was written against, not
 * hypotheticals:
 *
 *   * `components/event/PropsSection.tsx` — the WHAT HIT section, which stacks
 *     directly beneath the rail on the event page — rendered `"Hit"` / `"Push"`
 *     / `"Miss"` as title-case literals. Not in the three-file list.
 *   * `components/PlayerPropsDashboard.tsx` — IS in the three-file list, and
 *     still carried `didHit ? "✓" : "—"`, a GLYPH pair stating the verdict a
 *     second time. Not a banned word, so invisible.
 *
 * ── THE SHAPE THAT DOES WORK: A DIFFERENTIAL CENSUS ──────────────────────────
 *
 * Render each settled surface TWICE — once resolving hit, once resolving miss —
 * with every other input held identical. Diff the rendered token multisets. The
 * tokens that DIFFER between the two renders ARE the settled vocabulary, whatever
 * it happens to be, and every one of them must be in `SETTLED_VOCABULARY`.
 *
 * A fourth vocabulary is by construction a pair of strings that differ between
 * hit and miss. So it lands in that difference set and reds this suite without
 * anyone having predicted the word. That is the property item 1 asks for.
 *
 * Two supporting parts make it hold at the edges:
 *
 *   * ENROLMENT IS ASSERTED, NOT MAINTAINED. The surface list is checked against
 *     every component transitively reachable from `lib/propGrade`. A new
 *     settled surface that is not enrolled in the census reds the suite — the
 *     three-file list's failure cannot recur.
 *   * NON-VACUITY BY MUTATION. The census is run against a component that
 *     deliberately speaks the "HAPPENED" / "DIDN'T HAPPEN" pair, and must
 *     reject it. A detector nobody has seen fail is not a detector.
 *
 * The census reads aria-labels and `sr-only` prose as well as visible text. A
 * screen reader is a rendered surface, and it is the one a screenshot cannot
 * check.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import fs from "node:fs";
import path from "node:path";

import PropTravelBar from "@/components/PropTravelBar";
import PropDivergenceDetail from "@/components/PropDivergenceDetail";
import PropDivergenceRail from "@/components/PropDivergenceRail";
import PropsSection, { type PropMark } from "@/components/event/PropsSection";
import PlayerPropsDashboard from "@/components/PlayerPropsDashboard";
import TotalPointsSpectrum from "@/components/TotalPointsSpectrum";
import { NFLEventCardDeck } from "@/components/event/NFLEventCards";
import EventCardReader, { LineDetails } from "@/components/event/EventCardReader";
import { milestoneCards, rowsForCards, type NflPropRow } from "@/lib/nflEventCardDeck";
import { decodeQuestionMatrix, totalLadderCard } from "@/lib/nbaEventCards";
import nbaFinalBody from "../fixtures/nbaFinalMatrix15320337.json";
import {
  isSettledVocabularyToken,
  PROP_HIT_LABEL,
  PROP_MISS_LABEL,
  PROP_PUSH_LABEL,
  propResultLabel,
  propVerdictLabel,
  SETTLED_VOCABULARY,
} from "@/lib/propGrade";
import type { DivergenceRow } from "@/lib/propDivergence";
import type { GameMarketsResponse } from "@/lib/api";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import HockeyJourneyAllProps from "@/components/event/eventpage10868/HockeyJourneyAllProps";
import HockeyJourneyContributionCard from "@/components/event/eventpage10868/HockeyJourneyContributionCard";
import HockeyJourneyPage from "@/components/event/eventpage10868/HockeyJourneyPage";
import HockeyJourneyStories from "@/components/event/eventpage10868/HockeyJourneyStories";
import {
  buildHockeyJourney,
  hockeyJourneyContribution,
  hockeyJourneyOriginals,
  NO_HELD_CHOICE,
} from "@/lib/eventPage10868/hockeyJourney";
import hockeyFixtures from "./hockeyJourney10868.fixtures.json";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";
import { vocabularyDelta } from "../helpers/renderedTokens";
import soccerFixtures from "./soccerMatch10868.fixtures.json";
import { buildSoccerMatch, type SoccerMatchAdmission } from "@/lib/eventPage10868/soccerMatch";
import SoccerMatchPage from "@/components/event/eventpage10868/SoccerMatchPage";
import SoccerMatchStories from "@/components/event/eventpage10868/SoccerMatchStories";
import mlbFixtures from "./mlbGame10868.fixtures.json";
import { buildMlbGame } from "@/lib/eventPage10868/mlbGame";
import MlbGamePage from "@/components/event/eventpage10868/MlbGamePage";

const FRONTEND_ROOT = path.resolve(__dirname, "../..");

// ---------------------------------------------------------------------------
// The census
// ---------------------------------------------------------------------------

/**
 * ── THE CENSUS MACHINERY NOW LIVES IN ONE PLACE (extracted UX-P107) ──────────
 *
 * `__tests__/helpers/renderedTokens.ts`. UX-P107 minted a SECOND vocabulary
 * class — the pregame direction one — and built its guard from this same shape
 * on a different axis (flip the PRICE across the coin flip rather than the
 * VERDICT). Two copies of a differential census would be free to drift on
 * exactly the thing both of them exist to pin: what counts as a token a reader
 * receives. So there is one, and both suites import it.
 */

/**
 * The assertion itself. Returns the offending tokens so a failure NAMES the new
 * vocabulary rather than just reporting a boolean.
 */
export function unregisteredVocabulary(hitHtml: string, missHtml: string): string[] {
  return vocabularyDelta(hitHtml, missHtml).filter((t) => !isSettledVocabularyToken(t));
}

// ---------------------------------------------------------------------------
// Fixtures — one per surface, parameterised by the verdict and NOTHING else
// ---------------------------------------------------------------------------

/**
 * `pregameMark` is 0.5 on purpose. `surprise` is then |resolution − mark| = 0.5
 * either way, so BOTH renders clear `PROP_SURPRISE_RESOLUTION` and both
 * escalate to a sentence. Otherwise the pair would differ by an entire
 * paragraph's worth of prose and the census would be measuring the escalation
 * rule instead of the vocabulary.
 */
function divergenceRow(hit: boolean): DivergenceRow {
  const resolution: 0 | 1 = hit ? 1 : 0;
  return {
    key: "freeman-hits-1",
    label: "Freddie Freeman: 1+ hits",
    player: "Freddie Freeman",
    stat: "hits",
    threshold: 1,
    pregameMark: 0.5,
    current: 0.5,
    travel: 0,
    direction: "flat",
    surprising: true,
    sentence: `Freeman's 1+ hits was marked 50% — and it ${hit ? "hit" : "missed"}.`,
    settled: true,
    pregame: false,
    conviction: 0,
    scriptSide: "toss_up",
    // UX-P107. A settled fixture is never structural — the flag is a fact about
    // ladder position, this row is a family of one, and the settled rail does
    // not consult it in any case.
    structural: false,
    resolution,
    surprise: 0.5,
    grade: { state: hit ? "HIT" : "MISS", reason: "explicit_hit", hit, actual: null } as DivergenceRow["grade"],
  };
}

/** Raw payload rows for the two surfaces that select their own rows. */
function rawPropRows(hit: boolean): PlayerPropRow[] {
  // Shaped like the production payload the rail was measured on
  // (`eventPlayerProps.15199902.settled.json`): the STAT lives in `market_name`,
  // the outcome is "Player: N+". A synthetic shape that the row parser rejects
  // renders an empty rail, which passes a census vacuously — hence the
  // `statesAVerdict` guard above.
  const rows = [
    { outcome_name: "Freddie Freeman: 3+", threshold: 3 },
    { outcome_name: "Mookie Betts: 2+", threshold: 2 },
  ].map((r) => ({
    market_name: "Los Angeles D vs Colorado: Hits + Runs + RBIs",
    source: "kalshi",
    movement: 0,
    // `pregame_mark` 0.5 ⇒ surprise 0.5 in BOTH directions, so both renders
    // clear the escalation line and the delta is the verdict, not the prose.
    over_probability: 0.5,
    opening_over_probability: 0.5,
    pregame_mark: 0.5,
    // Held identical across the pair: `actual` is data, and letting it move
    // would put a number in the delta rather than a word.
    actual: 1,
    hit,
    is_winner: hit,
    resolution_source: "box_score",
    ...r,
  }));
  return rows as unknown as PlayerPropRow[];
}

function gameMarkets(hit: boolean, extra: Record<string, unknown> = {}): GameMarketsResponse {
  return {
    player_props: rawPropRows(hit),
    other: [],
    totals: [],
    ...extra,
  } as unknown as GameMarketsResponse;
}

function propMarks(hit: boolean): PropMark[] {
  return [
    {
      key: "freeman-hits",
      label: "Freddie Freeman: 1+ hits",
      pregame_mark: 0.5,
      current: 0.5,
      // `graded_label` is BACKEND prose about the number ("31 pts — hit"), not
      // the verdict slot, and it is null here so the census sees the words this
      // client chooses.
      graded_label: null,
      graded_result: hit ? "hit" : "miss",
    },
  ];
}

/**
 * The total-points spectrum types its verdict off the realised score, so the
 * pair flips scores rather than a boolean. Only NUMBERS move; `DATA_ONLY`
 * discards them and the delta is the verdict word alone.
 */
function spectrumPayload(hit: boolean): GameMarketsResponse {
  return {
    player_props: [],
    other: [],
    totals: [
      {
        market_name: "Total Runs",
        outcome_name: "Over 8.5",
        market_type: "game_total",
        threshold: 8.5,
        over_probability: 0.5,
        source: "kalshi",
        movement: null,
      },
    ],
    home_score: hit ? 9 : 1,
    away_score: 0,
  } as unknown as GameMarketsResponse;
}

interface Surface {
  /** Repo-relative path, so the enrolment assertion can compare like with like. */
  file: string;
  /**
   * A surface may state its verdict in more than one BRANCH, and a census that
   * only walks one of them passes vacuously on the others. Found by mutation:
   * restoring `PlayerPropsDashboard`'s `didHit ? "✓" : "—"` did NOT red this
   * suite on the first draft, because the fixture carried an `actual` and the
   * glyph branch only renders when there isn't one. One entry per branch.
   */
  variant?: string;
  /** Callback-owned verdicts are exercised through their enrolled parent. */
  delegatesTo?: string;
  render: (hit: boolean) => string;
}

/**
 * #9483 — the NFL game-story cards' graded ladder: one finished game, the same
 * box-score number both ways, only the server's grade differs.
 */
function nflGradedRows(hit: boolean): NflPropRow[] {
  return [39.5, 49.5, 59.5].map((threshold, i) => ({
    market_name: "Seattle vs Denver: Receiving Yards",
    outcome_name: `Jaxon Smith-Njigba: ${threshold}+`,
    threshold,
    over_probability: [0.8, 0.6, 0.4][i],
    source: "kalshi",
    observed_at: "2026-10-16T00:00:00Z",
    pregame_mark: [0.78, 0.55, 0.38][i],
    player_team: "away" as const,
    actual: 52,
    hit,
  }));
}
function nflGradedDeck(hit: boolean) {
  return milestoneCards({
    props: nflGradedRows(hit),
    eventStatus: "completed",
    commenceTime: "2026-10-16T00:15:00Z",
    homeTeam: "Denver Broncos",
    awayTeam: "Seattle Seahawks",
    nowMs: Date.parse("2026-10-16T04:00:00Z"),
  });
}
const NFL_TEAMS = { awayName: "Seattle Seahawks", homeName: "Denver Broncos" };

/** #9483 NBA — the final total ladder (15320337) with every producer verdict forced one way. */
function nbaGradedTotal(hit: boolean) {
  const m = JSON.parse(JSON.stringify(nbaFinalBody.game_question_matrix));
  for (const q of m.questions) for (const o of q.options) o.result = { state: hit ? "won" : "lost" };
  return totalLadderCard({
    questions: decodeQuestionMatrix(m),
    status: "completed",
    commenceTime: "2026-10-04T23:00:00Z",
    homeScore: 104,
    awayScore: 101,
    pregameProjection: null,
    homeShort: "Clippers",
    awayShort: "Warriors",
    nowMs: Date.parse("2026-10-05T04:00:00Z"),
  })!;
}

/**
 * #10868 — the hockey journey (`nhl-journey`): one finished game (15169793,
 * the verbatim subset in `hockeyJourney10868.fixtures.json`) with EVERY player
 * prop's served settlement forced one way (`is_winner` and `hit` together) and
 * nothing else changed. CONSTRUCTED: the box score is removed, so a count can
 * never overrule a forced settlement ("Result unconfirmed") and the pair differs
 * by the verdict alone. Game-line originals keep their served grades both ways.
 */
const HOCKEY_NOW = Date.parse("2026-10-11T04:56:41Z");
function hockeyBodies(hit: boolean): { event: EventDetailResponse; markets: GameMarketsResponse } {
  const event = { ...hockeyFixtures.finalDetail, box_score_data: null } as unknown as EventDetailResponse;
  const markets = {
    ...hockeyFixtures.finalMarkets,
    player_props: hockeyFixtures.finalMarkets.player_props.map((row) => ({ ...row, is_winner: hit, hit })),
  } as unknown as GameMarketsResponse;
  return { event, markets };
}
function hockeyJourney(hit: boolean) {
  const { event, markets } = hockeyBodies(hit);
  return buildHockeyJourney({
    event,
    history: hockeyFixtures.finalHistory as unknown as EventHistoryResponse,
    gameMarkets: markets,
    host: { nowMs: HOCKEY_NOW, hero: null, probabilityObservedAt: null },
  });
}
const HOCKEY = "components/event/eventpage10868";

/**
 * #10868 — the soccer match screen: one finished match (15325054, Real
 * Valladolid CF 5–0 Albacete, the verbatim native subset in
 * `soccerMatch10868.fixtures.json`) with EVERY served row's settlement forced
 * one way (`is_winner`, with `resolution_source: "api_settlement"`) and nothing
 * else changed but this: CONSTRUCTED, the matrix options' own `result` is
 * removed so no matrix grade can disagree with the forced settlement, and the
 * story markets are admitted with native's `liveAdmission` ids (no production
 * owner admits them). The pair then differs by the verdict alone.
 */
const SOCCER_FINAL_NOW = Date.parse(soccerFixtures.provenance.clocks.finalNow);
function soccerMatch(hit: boolean) {
  const body = JSON.parse(soccerFixtures.bodies.finalMarkets.raw) as Record<string, unknown>;
  for (const key of ["totals", "spreads", "team_totals", "period_markets", "other"]) {
    body[key] = ((body[key] as Array<Record<string, unknown>> | undefined) ?? []).map((row) => ({
      ...row,
      is_winner: hit,
      resolution_source: "api_settlement",
    }));
  }
  const matrix = body.game_question_matrix as Record<string, unknown>;
  matrix.questions = (matrix.questions as Array<Record<string, unknown>>).map((q) => ({
    ...q,
    options: (q.options as Array<Record<string, unknown>>).map((o) => {
      const rest = { ...o };
      delete rest.result;
      return rest;
    }),
  }));
  return buildSoccerMatch({
    event: JSON.parse(soccerFixtures.bodies.finalDetail.raw) as EventDetailResponse,
    history: JSON.parse(soccerFixtures.bodies.finalHistory.raw) as EventHistoryResponse,
    gameMarkets: body as unknown as GameMarketsResponse,
    admitted: (soccerFixtures.constructed as unknown as { liveAdmission: SoccerMatchAdmission }).liveAdmission,
    host: { nowMs: SOCCER_FINAL_NOW, hero: null, probabilityObservedAt: null },
  });
}

/**
 * #10868 — the MLB game screen, core checkpoint: one finished game (15321836,
 * White Sox 7–3 Astros, the REAL retained subset in `mlbGame10868.fixtures.json`).
 * CONSTRUCTED forced admission: EVERY served market row's settlement is forced
 * one way (`is_winner` and `hit` together, with `resolution_source:
 * "api_settlement"`) and nothing else changes, so the pair differs by All
 * props' verdict words alone. CONSTRUCTED host: the capture's retrieval
 * instant, the displayed pair equal to the row (3–7), no hero, no projection,
 * delivery and live claim answered explicitly. The forced pair's non-vacuity is
 * checked in `mlbGame10868.test.ts` ("the census pair").
 */
const MLB_FINAL_NOW = Date.parse("2026-10-11T04:57:23.592725Z");
function mlbGame(hit: boolean) {
  const markets = JSON.parse(JSON.stringify(mlbFixtures.finalMarkets)) as Record<string, unknown>;
  for (const key of ["totals", "spreads", "team_totals", "period_markets", "player_props", "other"]) {
    markets[key] = ((markets[key] as Array<Record<string, unknown>> | undefined) ?? []).map((row) => ({
      ...row,
      is_winner: hit,
      hit,
      resolution_source: "api_settlement",
    }));
  }
  return buildMlbGame({
    event: mlbFixtures.finalDetail as unknown as EventDetailResponse,
    history: mlbFixtures.finalHistory as unknown as EventHistoryResponse,
    gameMarkets: markets as unknown as GameMarketsResponse,
    host: {
      nowMs: MLB_FINAL_NOW,
      hero: null,
      probabilityObservedAt: null,
      deliveryInterrupted: false,
      liveClaimUnbacked: false,
      score: { home: 3, away: 7, observedAt: null },
      projectedFinal: null,
    },
  });
}

/**
 * EVERY component that can state a settled prop verdict. Not hand-maintained:
 * `enrolment` below proves this list covers the transitive closure.
 */
const SURFACES: Surface[] = [
  {
    file: "components/PropTravelBar.tsx",
    render: (hit) => renderToStaticMarkup(<PropTravelBar row={divergenceRow(hit)} />),
  },
  {
    file: "components/PropDivergenceDetail.tsx",
    render: (hit) =>
      renderToStaticMarkup(
        <PropDivergenceDetail playerProps={rawPropRows(hit)} status="completed" />,
      ),
  },
  {
    file: "components/PropDivergenceRail.tsx",
    render: (hit) =>
      renderToStaticMarkup(
        <PropDivergenceRail playerProps={rawPropRows(hit)} status="completed" />,
      ),
  },
  {
    file: "components/event/PropsSection.tsx",
    render: (hit) =>
      renderToStaticMarkup(<PropsSection items={propMarks(hit)} state="graded" />),
  },
  {
    file: "components/PlayerPropsDashboard.tsx",
    variant: "graded with a box-score number",
    render: (hit) =>
      renderToStaticMarkup(
        <PlayerPropsDashboard
          data={gameMarkets(hit)}
          eventStatus="completed"
          homeTeam="Los Angeles Dodgers"
          awayTeam="Colorado Rockies"
        />,
      ),
  },
  {
    file: "components/PlayerPropsDashboard.tsx",
    // The branch the glyph pair lived in: a typed verdict with NO `actual`.
    variant: "graded with no box-score number",
    render: (hit) =>
      renderToStaticMarkup(
        <PlayerPropsDashboard
          data={gameMarkets(hit, { player_props: rawPropRows(hit).map((r) => ({ ...r, actual: null })) })}
          eventStatus="completed"
          homeTeam="Los Angeles Dodgers"
          awayTeam="Colorado Rockies"
        />,
      ),
  },
  ...[false, true].map((withoutActual): Surface => ({
    file: "components/event/CompactPlayerProps.tsx",
    variant: withoutActual ? "compact without box score" : "compact with box score",
    delegatesTo: "components/PlayerPropsDashboard.tsx",
    render: (hit) => renderToStaticMarkup(
      <PlayerPropsDashboard
        compact
        data={gameMarkets(hit, withoutActual ? {
          player_props: rawPropRows(hit).map((r) => ({ ...r, actual: null })),
        } : {})}
        eventStatus="completed"
        homeTeam="Los Angeles Dodgers"
        awayTeam="Colorado Rockies"
      />,
    ),
  })),
  {
    file: "components/event/NFLEventCards.tsx",
    render: (hit) =>
      renderToStaticMarkup(
        <NFLEventCardDeck
          cards={nflGradedDeck(hit)}
          teams={NFL_TEAMS}
          selection={{}}
          onSelect={() => undefined}
          onOpen={() => undefined}
          openerRef={() => undefined}
        />,
      ),
  },
  {
    file: "components/event/EventCardReader.tsx",
    variant: "full-size card",
    render: (hit) => {
      const cards = nflGradedDeck(hit);
      return renderToStaticMarkup(
        <EventCardReader
          openCardId={cards[0].id}
          liveCards={cards}
          liveHeader={{ match: "SEA 27–17 DEN · Final", chances: "" }}
          liveRows={rowsForCards(cards, nflGradedRows(hit))}
          teams={NFL_TEAMS}
          selection={{}}
          onSelect={() => undefined}
          onClose={() => undefined}
        />,
      );
    },
  },
  {
    file: "components/event/NFLEventCards.tsx",
    variant: "NBA total ladder",
    render: (hit) =>
      renderToStaticMarkup(
        <NFLEventCardDeck
          cards={[nbaGradedTotal(hit)]}
          teams={{ awayName: "Golden State Warriors", homeName: "Los Angeles Clippers" }}
          selection={{}}
          onSelect={() => undefined}
          onOpen={() => undefined}
          openerRef={() => undefined}
        />,
      ),
  },
  {
    file: "components/event/EventCardReader.tsx",
    variant: "NBA option details",
    render: (hit) => renderToStaticMarkup(<LineDetails row={nbaGradedTotal(hit).points[0].detail} onDone={() => undefined} />),
  },
  {
    file: "components/event/EventCardReader.tsx",
    variant: "line details",
    render: (hit) => renderToStaticMarkup(<LineDetails row={nflGradedRows(hit)[1]} onDone={() => undefined} />),
  },
  {
    file: "components/TotalPointsSpectrum.tsx",
    render: (hit) =>
      renderToStaticMarkup(
        <TotalPointsSpectrum data={spectrumPayload(hit)} eventStatus="completed" />,
      ),
  },
  // #10868 — the hockey journey. The two verdict surfaces first, then the two
  // wrappers that only render them.
  ...(["points", "assists"] as const).map((stat): Surface => ({
    file: `${HOCKEY}/HockeyJourneyContributionCard.tsx`,
    variant: `hockey ${stat}, final`,
    render: (hit) => {
      const { event, markets } = hockeyBodies(hit);
      return renderToStaticMarkup(
        <HockeyJourneyContributionCard
          card={hockeyJourneyContribution(stat, event, markets, HOCKEY_NOW)!}
          held={NO_HELD_CHOICE}
          onHold={() => undefined}
        />,
      );
    },
  })),
  {
    file: `${HOCKEY}/HockeyJourneyAllProps.tsx`,
    render: (hit) => {
      const { event, markets } = hockeyBodies(hit);
      return renderToStaticMarkup(
        <HockeyJourneyAllProps originals={hockeyJourneyOriginals(event, markets, HOCKEY_NOW)} entryLabel="All props" />,
      );
    },
  },
  // The two wrappers only render the surfaces above; each satisfies the import
  // contract by importing the enrolled surface it delegates to (VERDICT_EXPORTS).
  {
    file: `${HOCKEY}/HockeyJourneyStories.tsx`,
    render: (hit) => renderToStaticMarkup(<HockeyJourneyStories journey={hockeyJourney(hit)} />),
  },
  {
    file: `${HOCKEY}/HockeyJourneyPage.tsx`,
    render: (hit) => renderToStaticMarkup(<HockeyJourneyPage journey={hockeyJourney(hit)} />),
  },
  // #10868 — the soccer match screen: the story stream states results in the
  // registered words (`propVerdictLabel`); the page renders it and All props.
  {
    file: `${HOCKEY}/SoccerMatchStories.tsx`,
    render: (hit) => renderToStaticMarkup(<SoccerMatchStories stream={soccerMatch(hit).stories} />),
  },
  {
    file: `${HOCKEY}/SoccerMatchPage.tsx`,
    render: (hit) => renderToStaticMarkup(<SoccerMatchPage match={soccerMatch(hit)} />),
  },
  // #10868 — the MLB game screen (core checkpoint): it states verdicts only through All props.
  {
    file: `${HOCKEY}/MlbGamePage.tsx`,
    render: (hit) => renderToStaticMarkup(<MlbGamePage model={mlbGame(hit)} />),
  },
];

// ---------------------------------------------------------------------------
// 1. The differential census
// ---------------------------------------------------------------------------

describe("the settled vocabulary is closed — a fourth pair reds this suite", () => {
  it.each(
    SURFACES.map((s) => [s.variant ? `${s.file} (${s.variant})` : s.file, s] as const),
  )("%s says the verdict only in the registered words", (name, surface) => {
    const hitHtml = surface.render(true);
    const missHtml = surface.render(false);

    // Non-vacuity FIRST. A surface that rendered nothing, or rendered the same
    // thing both ways, would pass the census trivially — which is how a guard
    // quietly stops guarding.
    const delta = vocabularyDelta(hitHtml, missHtml);
    expect({ surface: name, statesAVerdict: delta.length > 0 }).toEqual({
      surface: name,
      statesAVerdict: true,
    });

    expect({ surface: name, unregistered: unregisteredVocabulary(hitHtml, missHtml) }).toEqual({
      surface: name,
      unregistered: [],
    });
  });

  it("the registry is the only place the words are spelled", () => {
    // Round-trips through the exported API rather than restating the strings,
    // so a rename of a constant cannot leave this test asserting the old value.
    expect(SETTLED_VOCABULARY).toContain(PROP_HIT_LABEL);
    expect(SETTLED_VOCABULARY).toContain(PROP_MISS_LABEL);
    expect(SETTLED_VOCABULARY).toContain(PROP_PUSH_LABEL);
    expect(propVerdictLabel(true)).toBe(PROP_HIT_LABEL);
    expect(propVerdictLabel(false)).toBe(PROP_MISS_LABEL);
    expect(propResultLabel("hit")).toBe(PROP_HIT_LABEL);
    expect(propResultLabel("miss")).toBe(PROP_MISS_LABEL);
    expect(propResultLabel("push")).toBe(PROP_PUSH_LABEL);
  });
});

// ---------------------------------------------------------------------------
// 2. Non-vacuity by mutation — the detector must be shown to fail
// ---------------------------------------------------------------------------

describe("the census actually detects a new vocabulary", () => {
  /** The exact pair UX-P105's rail invented, and the screenshot caught. */
  function ThirdVocabulary({ hit }: { hit: boolean }) {
    return (
      <div>
        <span>marked 50%</span>
        <span>{hit ? "HAPPENED" : "DIDN'T HAPPEN"}</span>
      </div>
    );
  }

  it("rejects HAPPENED / DIDN'T HAPPEN — the pair no existing test could see", () => {
    const hitHtml = renderToStaticMarkup(<ThirdVocabulary hit />);
    const missHtml = renderToStaticMarkup(<ThirdVocabulary hit={false} />);
    expect(unregisteredVocabulary(hitHtml, missHtml).sort()).toEqual([
      "DIDN'T",
      "HAPPEN",
      "HAPPENED",
    ]);
  });

  it("rejects a GLYPH vocabulary — the shape a word-denylist cannot express", () => {
    // `PlayerPropsDashboard` carried `didHit ? "✓" : "—"` until UX-P106.
    const hitHtml = renderToStaticMarkup(<span>{"✓"}</span>);
    const missHtml = renderToStaticMarkup(<span>{"✗"}</span>);
    expect(unregisteredVocabulary(hitHtml, missHtml)).toEqual(["✓", "✗"]);
  });

  it("rejects a vocabulary built from words that are individually innocent", () => {
    const hitHtml = renderToStaticMarkup(<span>IT HIT</span>);
    const missHtml = renderToStaticMarkup(<span>DID NOT HIT</span>);
    expect(unregisteredVocabulary(hitHtml, missHtml).sort()).toEqual(["DID", "IT", "NOT"]);
  });

  it("rejects a vocabulary spoken ONLY to a screen reader", () => {
    // The failure mode a rendered screenshot is structurally unable to catch.
    const hitHtml = renderToStaticMarkup(<span aria-label="the bet CASHED">·</span>);
    const missHtml = renderToStaticMarkup(<span aria-label="the bet BUSTED">·</span>);
    expect(unregisteredVocabulary(hitHtml, missHtml).sort()).toEqual(["BUSTED", "CASHED"]);
  });

  it("does NOT reject a pure number moving — data is not vocabulary", () => {
    const hitHtml = renderToStaticMarkup(<span>93%</span>);
    const missHtml = renderToStaticMarkup(<span>7%</span>);
    expect(unregisteredVocabulary(hitHtml, missHtml)).toEqual([]);
  });

  it("does NOT reject a colour or class changing", () => {
    const hitHtml = renderToStaticMarkup(<span className="text-accent-live">{PROP_HIT_LABEL}</span>);
    const missHtml = renderToStaticMarkup(
      <span className="text-accent-danger">{PROP_MISS_LABEL}</span>,
    );
    expect(unregisteredVocabulary(hitHtml, missHtml)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// 3. Enrolment — the three-file list's failure cannot recur
// ---------------------------------------------------------------------------

describe("every settled surface is enrolled in the census", () => {
  /**
   * Resolve one import specifier to a repo-relative source path, or null when
   * it leaves the two directories this closure walks.
   */
  function resolveImport(fromFile: string, spec: string): string | null {
    let base: string;
    if (spec.startsWith("@/")) base = spec.slice(2);
    else if (spec.startsWith(".")) base = path.normalize(path.join(path.dirname(fromFile), spec));
    else return null;
    if (!/^(components|lib)\//.test(base)) return null;
    for (const ext of [".tsx", ".ts", "/index.tsx", "/index.ts"]) {
      if (fs.existsSync(path.join(FRONTEND_ROOT, base + ext))) return base + ext;
    }
    return null;
  }

  /** Every `components/**` + `lib/**` file, and what each one imports. */
  function sourceGraph(): Map<string, string[]> {
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const e of fs.readdirSync(path.join(FRONTEND_ROOT, dir), { withFileTypes: true })) {
        const rel = `${dir}/${e.name}`;
        if (e.isDirectory()) walk(rel);
        else if (/\.tsx?$/.test(e.name)) files.push(rel);
      }
    };
    walk("components");
    walk("lib");

    const graph = new Map<string, string[]>();
    for (const f of files) {
      const src = fs.readFileSync(path.join(FRONTEND_ROOT, f), "utf8");
      const out: string[] = [];
      for (const m of src.matchAll(/from\s+["']([^"']+)["']/g)) {
        const r = resolveImport(f, m[1]);
        if (r) out.push(r);
      }
      graph.set(f, out);
    }
    return graph;
  }

  /** Everything that transitively imports `lib/propGrade.ts`. */
  function settledClosure(): Set<string> {
    const graph = sourceGraph();
    const reachers = new Set<string>(["lib/propGrade.ts"]);
    // Fixed point: cheap at this graph size, and correct without ordering care.
    for (let changed = true; changed; ) {
      changed = false;
      for (const [file, imports] of graph) {
        if (reachers.has(file)) continue;
        if (imports.some((i) => reachers.has(i))) {
          reachers.add(file);
          changed = true;
        }
      }
    }
    reachers.delete("lib/propGrade.ts");
    return reachers;
  }

  const closure = settledClosure();
  const components = [...closure].filter((f) => f.startsWith("components/")).sort();

  it("finds the surfaces (non-vacuity — an empty closure would pass everything)", () => {
    expect(closure.size).toBeGreaterThan(3);
    expect(components).toContain("components/event/PropsSection.tsx");
    expect(components).toContain("components/PropTravelBar.tsx");
  });

  it("no component that can state a verdict is left out of the census", () => {
    const enrolled = new Set(SURFACES.map((s) => s.file));
    const missing = components.filter((f) => !enrolled.has(f));
    // A new settled surface lands here. Enrol it in SURFACES with a hit/miss
    // fixture — that is the whole cost, and it is the cost UX-P105's
    // three-file list was avoiding when it missed PropsSection.
    expect(missing).toEqual([]);
  });

  it("no enrolled surface has drifted out of the closure", () => {
    // The other direction: a census entry that no longer reaches propGrade is
    // asserting nothing, and would sit here green forever.
    const stale = SURFACES.map((s) => s.file).filter((f) => !closure.has(f));
    expect(stale).toEqual([]);
  });

  it("every enrolled surface IMPORTS its verdict words rather than typing them", () => {
    /**
     * The differential census catches a new WORD. This catches the other
     * direction — a surface that reproduces a currently-correct word by hand.
     * That is not a hypothetical distinction: `PropsSection` was rendering the
     * right three verdicts, spelled by hand in title case, and drifting was the
     * only thing left for it to do.
     *
     * Deliberately an IMPORT check, not a literal hunt. A literal hunt over this
     * closure cannot work: `grade.state === "HIT"` is a type discriminant and
     * `resolution === 1 ? "hit" : "missed"` is an aria verb, both legitimate and
     * both indistinguishable from a hard-coded badge by regex.
     */
    const VERDICT_EXPORTS = [
      "propVerdictLabel",
      "propResultLabel",
      "PROP_HIT_LABEL",
      "PROP_MISS_LABEL",
      "PROP_PUSH_LABEL",
      "resolutionLabel", // PropTravelBar's re-export, itself built on propVerdictLabel
      "SETTLED_NO_GRADE_LABEL",
      // A surface may also DELEGATE the whole verdict slot to another enrolled
      // surface — which is what `PropDivergenceRail` does, and is the reason
      // `PropTravelBar` was extracted rather than copied in the first place.
      "PropTravelBar",
      // #10868 — the hockey journey's wrappers delegate the same way: Stories to
      // the contribution card, the page to All props and the stories.
      "HockeyJourneyContributionCard",
      "HockeyJourneyAllProps",
      "HockeyJourneyStories",
    ];
    // The compact browser delegates its verdict slot to the parent's existing
    // StatBox. Pin BOTH sides of that callback instead of exempting wrappers
    // from the import contract or copying verdict words into the browser.
    const delegated = SURFACES.filter((s) => s.delegatesTo);
    for (const surface of delegated) {
      expect(SURFACES.some((s) => s.file === surface.delegatesTo && !s.delegatesTo)).toBe(true);
      const child = fs.readFileSync(path.join(FRONTEND_ROOT, surface.file), "utf8");
      const parent = fs.readFileSync(path.join(FRONTEND_ROOT, surface.delegatesTo!), "utf8");
      expect(child).toMatch(/settled\s*\?\s*\(\s*renderSettled\(stat, player.color\)/);
      expect(parent).toContain('renderSettled={(stat, color) => <StatBox stat={stat} gameState="settled" teamColor={color} />}');
    }
    const offenders = SURFACES.filter((s) => !s.delegatesTo).map((s) => s.file).filter((f) => {
      const src = fs.readFileSync(path.join(FRONTEND_ROOT, f), "utf8");
      const imports = src.match(/import[\s\S]*?from\s+["'][^"']+["']/g)?.join("\n") ?? "";
      return !VERDICT_EXPORTS.some((e) => imports.includes(e));
    });
    expect(offenders).toEqual([]);
  });
});
