/**
 * #9483 — the NFL game-story cards' decisions on web (design freeze v328,
 * `nfl-web-nba-adoption-v328/ACCEPTANCE.md`), ported from the shipped phone
 * build (`NFLEventCardDeck9483.swift`, `NFLCardReader9483.swift`).
 *
 * Journeys pinned here (the pure half; markup is in the component test):
 *   4  before → live → final: basis switches from current quote to the served
 *      pregame mark; no actual/grade before the final; result fields separate.
 *   5  milestone: separate stat/probability axes, actual 0 below the ladder and
 *      above every line, team subjects and flat/insufficient profiles refused.
 *   6  expiry while reading: a pregame quote and a live projection lose their
 *      current marks; everything else stays held.
 *   7  Back returns to the ORIGIN card, not the last one read.
 *   8  pending update: nothing moves until Refresh; Refresh keeps a surviving
 *      card, else the nearest; empty is empty (never "1 of 0"); Back has a
 *      valid target when the origin left.
 *
 * Every clock is a fixed anchor (gotcha #44).
 */

import {
  buildFinishCard,
  cardAt,
  defaultRungIndex,
  displayedCards,
  finishHeadline,
  isTeamSubject,
  milestoneCards,
  milestoneProfile,
  nflEventCards,
  openReader,
  propRowId,
  readerHasUpdate,
  readerHeader,
  readerReducer,
  reconcileVisible,
  returnTarget,
  rowsForCards,
  statDomain,
  statLabel,
  targetLabel,
  withPagePregame,
  withPageProjection,
  type FinishCard,
  type MilestoneCard,
  type NflEventCard,
  type NflPropRow,
} from "@/lib/nflEventCardDeck";
import type { ProjectedFinalPointsInput } from "@/lib/projectedFinalPointsSeries";

const KICKOFF = Date.UTC(2026, 9, 16, 0, 15, 0);
const MIN = 60_000;
const iso = (offsetMin: number) => new Date(KICKOFF + offsetMin * MIN).toISOString();
const HOME = "Denver Broncos";
const AWAY = "Seattle Seahawks";
const MARKET = "Seattle vs Denver: Receiving Yards";

function rung(player: string, line: number, p: number | null, extra: Partial<NflPropRow> = {}): NflPropRow {
  return {
    market_name: MARKET,
    outcome_name: `${player}: ${line}+`,
    threshold: line,
    over_probability: p,
    source: "kalshi",
    observed_at: iso(-30),
    pregame_mark: p === null ? null : Math.max(0, p - 0.05),
    player_team: "away",
    ...extra,
  };
}

const JSN = [40, 50, 60, 70, 80].map((line, i) => rung("Jaxon Smith-Njigba", line, 0.8 - i * 0.15));

function cards(props: NflPropRow[], status = "scheduled", nowMs = KICKOFF - 20 * MIN) {
  return milestoneCards({ props, eventStatus: status, commenceTime: iso(0), homeTeam: HOME, awayTeam: AWAY, nowMs });
}

describe("#9483 milestone cards — which ladders become cards", () => {
  it("groups one player's ladder, drops the matchup prefix, keeps the venue's wording", () => {
    const [card] = cards(JSN);
    expect(card.player).toBe("Jaxon Smith-Njigba");
    expect(card.stat).toBe("Receiving Yards");
    expect(card.rungs.map((r) => r.threshold)).toEqual([40, 50, 60, 70, 80]);
    expect(card.side).toBe("away");
    const protectedLadder = cards(JSN.map((r) => ({ ...r, market_name: `${MARKET} (Protected)` })));
    expect(protectedLadder[0].stat).toBe("Receiving Yards (Protected)");
  });

  it("the row identity is source + market + outcome, never an array index", () => {
    const [card] = cards(JSN);
    expect(card.rungs[0].rowId).toBe(propRowId(JSN[0]));
    const [reordered] = cards([...JSN].reverse());
    expect(reordered.rungs.map((r) => r.rowId)).toEqual(card.rungs.map((r) => r.rowId));
  });

  it("refuses a team subject (D/ST or a club) as a player", () => {
    const dst = [7, 10, 14].map((line, i) => rung("SEA Seahawks D/ST", line, 0.7 - i * 0.2));
    const club = [7, 10, 14].map((line, i) => rung("Denver", line, 0.7 - i * 0.2));
    expect(cards([...dst, ...club])).toEqual([]);
    expect(isTeamSubject("Seahawks D/ST", [HOME, AWAY])).toBe(true);
    expect(isTeamSubject("Broncos", [HOME, AWAY])).toBe(true);
    expect(isTeamSubject("Bo Nix", [HOME, AWAY])).toBe(false);
  });

  it("refuses a flat ladder and one with fewer than three priced lines", () => {
    const flat = [10, 20, 30].map((line) => rung("Bo Nix", line, 0.5));
    const two = [10, 20].map((line, i) => rung("Courtland Sutton", line, 0.6 - i * 0.2));
    expect(cards([...flat, ...two])).toEqual([]);
  });

  it("reads only the over side (gotcha #17)", () => {
    const unders = JSN.map((r) => ({ ...r, outcome_name: r.outcome_name.replace(/\d+\+$/, "Under") }));
    expect(cards(unders)).toEqual([]);
    const inverted = JSN.map((r) => ({ ...r, _inverted: true }));
    expect(cards(inverted)).toEqual([]);
  });

  it("at most two cards, one per player, most-quoted stat first", () => {
    const rushing = (player: string) =>
      [20, 30, 40].map((line, i) => rung(player, line, 0.75 - i * 0.2, { market_name: "Seattle vs Denver: Rushing Yards" }));
    const deck = cards([...JSN, ...rung3("Courtland Sutton"), ...rushing("Kenneth Walker"), ...rushing("Jaxon Smith-Njigba")]);
    expect(deck).toHaveLength(2);
    expect(new Set(deck.map((c) => c.player)).size).toBe(2);
    expect(deck.every((c) => c.stat === "Receiving Yards")).toBe(true);
  });
});

function rung3(player: string) {
  return [30, 40, 50].map((line, i) => rung(player, line, 0.7 - i * 0.2));
}

describe("#9483 journey 4 — before → live → final", () => {
  it("before kickoff the chance is the current quote, with no actual or grade", () => {
    const graded = JSN.map((r) => ({ ...r, actual: 84, hit: true }));
    const [card] = cards(graded, "scheduled");
    expect(card.basis).toBe("pregamePrice");
    expect(card.rungs[0].chance).toBe(0.8);
    expect(card.actual).toBeNull();
    expect(card.rungs.every((r) => r.hit === null)).toBe(true);
  });

  it("once play starts the chance is the served pregame mark, never the live price", () => {
    const [card] = cards(JSN, "live", KICKOFF + 30 * MIN);
    expect(card.basis).toBe("pregameMark");
    expect(card.rungs[0].chance).toBeCloseTo(0.75);
    expect(card.rungs[0].chance).not.toBe(JSN[0].over_probability);
  });

  it("a live line with no served mark prints no chance, never the quote", () => {
    const noMarks = JSN.map((r, i) => (i === 0 ? { ...r, pregame_mark: null } : r));
    const [card] = cards(noMarks, "live", KICKOFF + 30 * MIN);
    expect(card.rungs[0].chance).toBeNull();
  });

  it("after the final the server's actual and grade appear, separate from the chance", () => {
    const graded = JSN.map((r, i) => ({ ...r, actual: 84, hit: i < 5 }));
    const [card] = cards(graded, "completed", KICKOFF + 240 * MIN);
    expect(card.actual).toBe(84);
    expect(card.rungs.map((r) => r.hit)).toEqual([true, true, true, true, true]);
    expect(card.rungs[0].chance).toBeCloseTo(0.75);
  });
});

describe("#9483 journey 5 — the milestone's two axes", () => {
  const base: MilestoneCard = {
    kind: "milestone",
    id: "m",
    player: "P",
    stat: "Receiving Yards",
    side: "home",
    basis: "pregameMark",
    rungs: [39.5, 49.5, 59.5, 69.5].map((threshold, i) => ({
      threshold,
      chance: [0.8, 0.66, 0.53, 0.31][i],
      observedAt: null,
      rowId: `r${i}`,
      hit: null,
    })),
    actual: null,
  };

  it("stat domain widens for an actual above every line and for an actual 0 below the ladder; chance stays 0–1", () => {
    const profile = milestoneProfile(base)!;
    expect(profile.domain[0]).toBeGreaterThan(0);
    const high = statDomain(profile.domain, 84);
    expect(high[1]).toBeGreaterThan(84);
    const zero = statDomain(profile.domain, 0);
    expect(zero[0]).toBeLessThan(0);
    expect(profile.points.every((p) => p.chance >= 0 && p.chance <= 1)).toBe(true);
  });

  it("opens on the priced line nearest even odds (59.5 at 53%)", () => {
    expect(defaultRungIndex(base)).toBe(2);
    expect(targetLabel(59.5)).toBe("59.5+");
    expect(targetLabel(60)).toBe("60+");
  });

  it("two quotes for one line draw no profile", () => {
    const dup = { ...base, rungs: [...base.rungs, { ...base.rungs[0], rowId: "dup", chance: 0.79 }] };
    expect(milestoneProfile(dup)).toBeNull();
  });
});

describe("#9483 journey 6 — expiry while reading", () => {
  it("a pregame quote whose clock passes 30 minutes loses its number; a mark does not age", () => {
    const [card] = cards(JSN, "scheduled", KICKOFF - 20 * MIN);
    expect(card.rungs[0].chance).toBe(0.8);
    const aged = cardAt(card, KICKOFF + 5 * MIN) as MilestoneCard;
    expect(aged.rungs.every((r) => r.chance === null)).toBe(true);
    const [live] = cards(JSN, "live", KICKOFF + 30 * MIN);
    expect(cardAt(live, KICKOFF + 600 * MIN)).toBe(live);
  });

  it("an undatable quote is not current", () => {
    const undated: NflPropRow[] = JSN.map((r) => ({ ...r, observed_at: null }));
    const [card] = cards([...undated, ...rung3("Bo Nix")], "scheduled");
    expect(card.player).toBe("Bo Nix");
  });

  it("a held live projection leaves when the live one stopped being current; the rest stays held", () => {
    const finish: FinishCard = {
      kind: "finish",
      id: "finish",
      phase: "during",
      pregame: { away: 20.5, home: 23.5, at: KICKOFF - MIN },
      projectedNow: { away: 24, home: 17, at: KICKOFF + 30 * MIN },
      final: null,
    };
    const liveFinish: FinishCard = { ...finish, projectedNow: null };
    const shown = displayedCards([finish], [liveFinish], KICKOFF + 40 * MIN);
    expect((shown[0] as FinishCard).projectedNow).toBeNull();
    expect((shown[0] as FinishCard).pregame).toEqual(finish.pregame);
    const stillCurrent = displayedCards([finish], [finish], KICKOFF + 40 * MIN);
    expect((stillCurrent[0] as FinishCard).projectedNow).toEqual(finish.projectedNow);
  });

  it("a held projection leaves on its OWN clock even while a newer live projection is current (v334)", () => {
    const finish: FinishCard = {
      kind: "finish",
      id: "finish",
      phase: "during",
      pregame: { away: 20.5, home: 23.5, at: KICKOFF - MIN },
      projectedNow: { away: 24, home: 17, at: KICKOFF + 30 * MIN },
      final: null,
    };
    const newer: FinishCard = { ...finish, projectedNow: { away: 27, home: 17, at: KICKOFF + 85 * MIN } };
    // One hour after its own capture it still reads as current.
    const within = displayedCards([finish], [newer], KICKOFF + 90 * MIN);
    expect((within[0] as FinishCard).projectedNow).toEqual(finish.projectedNow);
    // Past the capture gap it leaves: the newer one waits behind Refresh, never swapped in.
    const past = displayedCards([finish], [newer], KICKOFF + 91 * MIN) as FinishCard[];
    expect(past[0].projectedNow).toBeNull();
    expect(past[0].pregame).toEqual(finish.pregame);
    const header = { match: "", chances: "" };
    expect(
      readerHasUpdate({ held: [finish], heldHeader: header, heldRows: {}, live: [newer], liveHeader: header, liveRows: {}, nowMs: KICKOFF + 91 * MIN }),
    ).toBe(true);
    // A live projection whose own capture is that old is not current either.
    expect((cardAt(newer, KICKOFF + 146 * MIN) as FinishCard).projectedNow).toBeNull();
  });
});

describe("#9483 projected finish", () => {
  const pair = (offsetMin: number, home: number, away: number) => ({
    timestamp: iso(offsetMin),
    home,
    away,
    kind: "recorded" as const,
  });
  const input = (over: Partial<ProjectedFinalPointsInput>): ProjectedFinalPointsInput => ({
    sportKey: "americanfootball_nfl",
    sourceKey: "draftkings",
    basis: "same_book_same_capture_full_game_spread_and_total",
    pairs: [pair(-90, 23.5, 20.5), pair(-30, 24, 20)],
    actuals: [],
    kickoffAt: null,
    finalAt: null,
    asOf: iso(-10),
    ...over,
  });

  it("before kickoff: the newest projection, headline names the projected leader", () => {
    const card = buildFinishCard(input({}))!;
    expect(card.phase).toBe("before");
    expect(card.pregame).toMatchObject({ home: 24, away: 20 });
    expect(finishHeadline(card, AWAY, HOME)).toBe("Denver Broncos projected ahead");
  });

  it("a sport without story cards draws no finish card (NBA has its own deck)", () => {
    expect(buildFinishCard(input({ sportKey: "icehockey_nhl" }))).toBeNull();
    expect(buildFinishCard(input({ sportKey: "basketball_wnba" }))).toBeNull();
    expect(nflEventCards("basketball_nba", null, [])).toEqual([]);
  });

  it("after the final: the final is the admitted actual score, a flip reads as beating the forecast", () => {
    const card = buildFinishCard(
      input({
        scoreObservationStartAt: iso(0),
        pairs: [pair(-30, 24, 20), pair(30, 17, 24)],
        actuals: [
          { timestamp: iso(60), home_score: 7, away_score: 14 },
          { timestamp: iso(200), home_score: 17, away_score: 27 },
        ],
        finalAt: iso(200),
        asOf: iso(200),
      }),
    );
    expect(card).not.toBeNull();
    expect(card!.phase).toBe("after");
    expect(card!.pregame).toMatchObject({ home: 24, away: 20 });
    expect(card!.final).toMatchObject({ home: 17, away: 27 });
    expect(card!.projectedNow).toBeNull();
    expect(finishHeadline(card!, AWAY, HOME)).toBe("Seattle Seahawks beat the forecast");
  });
});

describe("#9483 journeys 7–8 — the reader's hold, Refresh and Back", () => {
  const header = readerHeader({
    awayShort: "SEA",
    homeShort: "DEN",
    awayScore: 7,
    homeScore: 10,
    stateLabel: "Q2 · 5:10",
    awayChance: "38%",
    homeChance: "62%",
    finished: false,
  });
  const [a, b] = cards([...JSN, ...rung3("Courtland Sutton")]);
  const finish: FinishCard = {
    kind: "finish",
    id: "finish",
    phase: "before",
    pregame: { away: 20, home: 24, at: KICKOFF - MIN },
    projectedNow: null,
    final: null,
  };
  const deck: NflEventCard[] = [finish, a, b];
  const rows = rowsForCards(deck, [...JSN, ...rung3("Courtland Sutton")]);

  it("the header names the score and state; after the final it prints no chances", () => {
    expect(header).toEqual({ match: "SEA 7–10 DEN · Q2 · 5:10", chances: "Win chances · SEA 38% · DEN 62%" });
    expect(
      readerHeader({ awayShort: "SEA", homeShort: "DEN", awayScore: 27, homeScore: 17, stateLabel: "Final", awayChance: "100%", homeChance: "0%", finished: true }),
    ).toEqual({ match: "SEA 27–17 DEN · Final", chances: "" });
  });

  it("open A, read B, Back returns to A (origin, not last explored)", () => {
    let state = openReader({ cardId: a.id, live: deck, liveHeader: header, liveRows: rows });
    state = readerReducer(state, { type: "step", delta: 1, nowMs: KICKOFF - 20 * MIN, live: deck });
    expect(state.visible).toBe(b.id);
    state = readerReducer(state, { type: "details", rowId: b.rungs[0].rowId });
    state = readerReducer(state, { type: "details", rowId: null });
    expect(returnTarget(state, deck.map((c) => c.id))).toBe(a.id);
  });

  it("new data waits: the held cards, header and rows stay until Refresh", () => {
    const state = openReader({ cardId: b.id, live: deck, liveHeader: header, liveRows: rows });
    const newer = [finish, b, a];
    const newHeader = { ...header, match: "SEA 14–10 DEN · Q3 · 12:00" };
    expect(state.held).toBe(deck);
    expect(state.heldHeader).toBe(header);
    expect(
      readerHasUpdate({ held: state.held, heldHeader: state.heldHeader, heldRows: state.heldRows, live: newer, liveHeader: newHeader, liveRows: rows, nowMs: KICKOFF - 20 * MIN }),
    ).toBe(true);
    expect(
      readerHasUpdate({ held: state.held, heldHeader: state.heldHeader, heldRows: state.heldRows, live: deck, liveHeader: header, liveRows: rows, nowMs: KICKOFF - 20 * MIN }),
    ).toBe(false);
    const refreshed = readerReducer(state, { type: "refresh", live: newer, liveHeader: newHeader, liveRows: rows });
    expect(refreshed.visible).toBe(b.id);
    expect(refreshed.heldHeader).toBe(newHeader);
    expect(refreshed.held.map((c) => c.id)).toEqual(newer.map((c) => c.id));
  });

  it("Refresh after the open card left moves to the nearest surviving card, and Back still has a target", () => {
    const state = openReader({ cardId: a.id, live: deck, liveHeader: header, liveRows: rows });
    const withoutA = [finish, b];
    const refreshed = readerReducer(state, { type: "refresh", live: withoutA, liveHeader: header, liveRows: rows });
    expect(refreshed.visible).toBe(b.id);
    expect(returnTarget(refreshed, withoutA.map((c) => c.id))).toBe(b.id);
    expect(reconcileVisible(b.id, [finish.id, a.id, b.id], [finish.id, a.id])).toBe(a.id);
  });

  it("a removed card hands over to the survivor NEAREST to it, the following one on a tie, never a farther one", () => {
    const old = ["c1", "c2", "c3", "open", "c5", "c6"];
    // c5 left with the open card: c3 is one away, c6 two — c3, not the first survivor after it.
    expect(reconcileVisible("open", old, ["c1", "c2", "c3", "c6"])).toBe("c3");
    expect(reconcileVisible("open", old, ["c6", "c3", "c1"])).toBe("c3");
    // Equal distance: the following card wins.
    expect(reconcileVisible("open", old, ["c3", "c5"])).toBe("c5");
    expect(reconcileVisible("open", old, ["c2", "c6"])).toBe("c6");
    // No old card survived: the new first card; nothing left: null.
    expect(reconcileVisible("open", old, ["n1", "n2"])).toBe("n1");
    expect(reconcileVisible("open", old, [])).toBeNull();
  });

  it("Refresh to an empty deck is the empty state, never a stale id", () => {
    const state = openReader({ cardId: a.id, live: deck, liveHeader: header, liveRows: rows });
    const empty = readerReducer(state, { type: "refresh", live: [], liveHeader: header, liveRows: {} });
    expect(empty.visible).toBeNull();
    expect(empty.held).toEqual([]);
    expect(returnTarget(empty, [])).toBeNull();
  });

  it("Details read the held rows, not the live ones", () => {
    const state = openReader({ cardId: a.id, live: deck, liveHeader: header, liveRows: rows });
    const id = a.rungs[0].rowId;
    const moved = { ...rows, [id]: { ...rows[id], over_probability: 0.1 } };
    expect(state.heldRows[id].over_probability).toBe(0.8);
    expect(
      readerHasUpdate({ held: state.held, heldHeader: state.heldHeader, heldRows: state.heldRows, live: deck, liveHeader: header, liveRows: moved, nowMs: KICKOFF - 20 * MIN }),
    ).toBe(true);
  });

  it("statLabel keeps a prefix that does not name both teams", () => {
    expect(statLabel("Sam Darnold: Passing Touchdowns O/U 2.5", HOME, AWAY, "Sam Darnold")).toBe("Passing Touchdowns O/U 2.5");
    expect(statLabel("Weird: Thing", HOME, AWAY, "Someone")).toBe("Weird: Thing");
  });
});

describe("#11103 one projected final per page", () => {
  const during: FinishCard = {
    kind: "finish",
    id: "finish",
    phase: "during",
    pregame: { away: 21.5, home: 19, at: KICKOFF - MIN },
    projectedNow: { away: 18.8, home: 23.8, at: KICKOFF + 66 * MIN },
    final: null,
  };

  it("the finish card's projected now is the hero's pair, keeping its own capture clock (SEA@DEN 01:21Z)", () => {
    const [shown] = withPageProjection([during], { home: 24, away: 16 }) as FinishCard[];
    expect(shown.projectedNow).toEqual({ away: 16, home: 24, at: during.projectedNow!.at });
    expect(shown.pregame).toEqual(during.pregame);
    expect(finishHeadline(shown, "Seattle Seahawks", "Denver Broncos")).toBe(finishHeadline(during, "Seattle Seahawks", "Denver Broncos"));
  });

  it("control: no hero pair leaves the series' latest; no current projection is not invented; final untouched", () => {
    expect(withPageProjection([during], null)).toEqual([during]);
    const stale: FinishCard = { ...during, projectedNow: null };
    expect(withPageProjection([stale], { home: 24, away: 16 })).toEqual([stale]);
    const after: FinishCard = { ...during, phase: "after", projectedNow: null, final: { away: 13, home: 27, at: KICKOFF + 200 * MIN } };
    expect(withPageProjection([after], { home: 24, away: 16 })).toEqual([after]);
  });

  it("the page hands the deck AND the reader the projected cards — no render site reads the raw series", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const src: string = require("fs").readFileSync(require("path").join(__dirname, "../app/events/[id]/page.tsx"), "utf8");
    expect(src).toMatch(/withPageProjection\(withPagePregame\(nflCards, heroPregamePair\), heroProjectedFinal\)/);
    const sites = [...src.matchAll(/(cards|liveCards)=\{(\w+)\}/g)].map((m) => `${m[1]}=${m[2]}`);
    expect(sites.sort()).toEqual(["cards=nflCardsShown", "liveCards=nflCardsShown"]);
  });
});

describe("#2920 / #11296 one pregame forecast per page", () => {
  // GB–DAL 14780562 (home Packers), retained from the served page at 21:36Z on 10/23: the
  // headline printed "Projection before scheduled start Packers 27 / Cowboys 28" from 21
  // sportsbooks; the card's series picked betrivers out of the since-start window and read its
  // 00:23:06Z capture (27.5 / 26.5), three minutes after the scheduled start, just before Q1.
  const GB = "Green Bay Packers";
  const DAL = "Dallas Cowboys";
  const seriesPregame = { away: 26.5, home: 27.5, at: Date.UTC(2026, 9, 19, 0, 23, 6) };
  const final = { away: 13, home: 23, at: Date.UTC(2026, 9, 19, 3, 43, 13) };
  const after: FinishCard = { kind: "finish", id: "finish", phase: "after", pregame: seriesPregame, projectedNow: null, final };
  const headline = { home: 27, away: 28 };

  it("before: the card graded one book's capture and contradicted the headline", () => {
    expect(finishHeadline(after, DAL, GB)).toBe("Green Bay Packers won as projected");
  });

  it("after: the card prints the headline's pair and grades the winner against it", () => {
    const [shown] = withPagePregame([after], headline) as FinishCard[];
    expect(shown.pregame).toEqual({ away: 28, home: 27, at: seriesPregame.at });
    expect(shown.final).toEqual(final);
    expect(finishHeadline(shown, DAL, GB)).toBe("Green Bay Packers beat the forecast");
  });

  it("orientation: the pair is keyed home/away, never sorted by value", () => {
    const [shown] = withPagePregame([after], { home: 30, away: 17 }) as FinishCard[];
    expect(shown.pregame).toMatchObject({ home: 30, away: 17 });
    expect(finishHeadline(shown, DAL, GB)).toBe("Green Bay Packers won as projected");
  });

  it("during: the 'before kickoff' sentence reads the headline's pair; the live projection is untouched", () => {
    const during: FinishCard = {
      ...after,
      phase: "during",
      final: null,
      projectedNow: { away: 20, home: 24, at: Date.UTC(2026, 9, 19, 1, 30) },
    };
    const [shown] = withPagePregame([during], headline) as FinishCard[];
    expect(shown.projectedNow).toEqual(during.projectedNow);
    expect(finishHeadline(shown, DAL, GB)).toBe("The projected finish has flipped");
    expect(finishHeadline({ ...shown, projectedNow: null }, DAL, GB)).toBe("Dallas Cowboys projected ahead before kickoff");
  });

  it("control: no printed headline pair keeps the series' reading (nothing invented)", () => {
    expect(withPagePregame([after], null)).toEqual([after]);
  });

  it("control: before the game the card already reads the current projection; it is not replaced", () => {
    const before: FinishCard = { ...after, phase: "before", final: null };
    expect(withPagePregame([before], headline)).toEqual([before]);
  });

  it("control: player cards pass through untouched", () => {
    const milestone = { kind: "milestone", id: "m" } as unknown as NflEventCard;
    const out = withPagePregame([milestone, after], headline);
    expect(out[0]).toBe(milestone);
  });

  it("the page passes the hero's PRINTED pregame pair: the final band, else the live baseline only where it renders", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const src: string = require("fs").readFileSync(require("path").join(__dirname, "../app/events/[id]/page.tsx"), "utf8");
    expect(src).toMatch(
      /const heroPregamePair = heroFinalForecast\?\.forecast \?\? \(heroProjectedFinal && heroLiveBaseline \? heroLiveBaseline\.baseline : null\);/,
    );
    expect(src).toMatch(/\{heroProjectedFinal && heroLiveBaseline && \(/);
    expect(src).toMatch(/\{heroFinalForecast && \(/);
  });
});
