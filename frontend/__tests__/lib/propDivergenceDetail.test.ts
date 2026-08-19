/**
 * THE DIVERGENCE detail view — UX-P101 (UX-AMBITION-1 slice 2).
 *
 * THE ORACLE IS THE RATIFIED MOCK'S OWN PAYLOAD. Mock 2 in
 * `docs/mockups/event-props-script-divergence-mock.html` is drawn from event
 * **14788546** (Cardinals @ Reds) and asserts, in prose, "34 of 97 rungs moved
 * 10+ points from their own pregame mark". That exact production payload is
 * fixtured here, so the fold threshold is checked against the design it came
 * from rather than against a number this file made up.
 *
 * This is the #1639 discipline applied deliberately: in UX-P098 a hand-written
 * census AGREED WITH THE BUGGY CODE because both shared an assumption, and only
 * a real-payload assertion separated them. So every claim below that could be
 * satisfied by a plausible reimplementation is instead pinned to the fixture.
 */

import {
  PROP_OFF_SCRIPT_TRAVEL,
  PROP_SURPRISE_TRAVEL,
  RAIL_MAX_ROWS,
  RAIL_MAX_PER_PLAYER,
  selectDivergenceDetail,
  selectDivergenceRows,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import reds from "../fixtures/eventPlayerProps.14788546.json";
import phillies from "../fixtures/eventPlayerProps.15199886.json";

const REDS = reds as unknown as PlayerPropRow[];
const PHILLIES = phillies as unknown as PlayerPropRow[];

describe("the fold is the mock's own measurement", () => {
  it("reproduces Mock 2's '34 rungs moved 10+ points' on Mock 2's own game", () => {
    const d = selectDivergenceDetail({ playerProps: REDS, status: "completed" });
    // The mock's prose, re-derived from the payload by the shipped parser.
    expect(d.offScriptCount).toBe(34);
    expect(PROP_OFF_SCRIPT_TRAVEL).toBe(0.1);
  });

  it("every off-script row really did travel at least the fold, and every on-script row did not", () => {
    const d = selectDivergenceDetail({ playerProps: REDS, status: "completed" });
    expect(d.offScript.length).toBeGreaterThan(0);
    expect(d.onScript.length).toBeGreaterThan(0);
    for (const r of d.offScript) expect(r.travel).toBeGreaterThanOrEqual(PROP_OFF_SCRIPT_TRAVEL);
    for (const r of d.onScript) expect(r.travel).toBeLessThan(PROP_OFF_SCRIPT_TRAVEL);
  });

  it("puts a row sitting EXACTLY on the fold above it — '10+' is inclusive", () => {
    // The fixture contains no row at exactly 0.10, so this boundary is
    // invisible to every payload-derived assertion above: a `>=` -> `>`
    // mutation survives all of them. Found by mutation, pinned here.
    // The mock's own words are "moved 10+ points", which is inclusive.
    const onTheLine: PlayerPropRow = {
      market_name: "Boundary Batter: Hits O/U 0.5",
      outcome_name: "Over",
      threshold: 0.5,
      over_probability: 0.6,
      pregame_mark: 0.5,
      source: "polymarket",
    } as unknown as PlayerPropRow;

    const d = selectDivergenceDetail({ playerProps: [onTheLine], status: "live" });
    expect(d.offScript.map((r) => r.player)).toEqual(["Boundary Batter"]);
    expect(d.onScript).toHaveLength(0);
    expect(d.offScript[0].travel).toBeCloseTo(PROP_OFF_SCRIPT_TRAVEL, 10);
  });

  it("puts a row exactly on the SURPRISE threshold into prose — '20 pts or above'", () => {
    const onTheLine: PlayerPropRow = {
      market_name: "Boundary Batter: Hits O/U 0.5",
      outcome_name: "Over",
      threshold: 0.5,
      over_probability: 0.7,
      pregame_mark: 0.5,
      source: "polymarket",
    } as unknown as PlayerPropRow;

    const d = selectDivergenceDetail({ playerProps: [onTheLine], status: "live" });
    expect(d.offScript[0].travel).toBeCloseTo(PROP_SURPRISE_TRAVEL, 10);
    expect(d.offScript[0].surprising).toBe(true);
    expect(d.offScript[0].sentence).toBeTruthy();
  });

  it("shows every eligible question — the fold splits, it never drops", () => {
    const d = selectDivergenceDetail({ playerProps: REDS, status: "completed" });
    expect(d.offScript.length + d.onScript.length).toBe(d.eligible);
    expect(d.eligible).toBe(100);
  });
});

describe("the detail view reaches what the rail cannot", () => {
  it("surfaces the 95 questions the five-row rail leaves behind", () => {
    const rail = selectDivergenceRows({ playerProps: REDS, status: "completed" });
    const detail = selectDivergenceDetail({ playerProps: REDS, status: "completed" });

    expect(rail.rows).toHaveLength(RAIL_MAX_ROWS);
    expect(rail.notSelected).toBe(95);
    // The whole point of the slice: the expand is a destination, not a re-render.
    expect(detail.eligible).toBe(rail.eligible);
    expect(detail.offScript.length + detail.onScript.length).toBe(
      rail.rows.length + rail.notSelected,
    );
  });

  it("agrees with the rail about the rail's own rows — one admission rule, not two", () => {
    const rail = selectDivergenceRows({ playerProps: REDS, status: "completed" });
    const detail = selectDivergenceDetail({ playerProps: REDS, status: "completed" });
    const all = [...detail.offScript, ...detail.onScript];
    const byKey = new Map(all.map((r) => [r.key, r]));

    for (const railRow of rail.rows) {
      const mine = byKey.get(railRow.key);
      expect(mine).toBeDefined();
      // Identical numbers on both sides of the expand. A reader who opens the
      // detail must not see a different figure for a row they were just shown.
      expect(mine!.pregameMark).toBe(railRow.pregameMark);
      expect(mine!.current).toBe(railRow.current);
      expect(mine!.travel).toBe(railRow.travel);
      expect(mine!.label).toBe(railRow.label);
      expect(mine!.sentence).toBe(railRow.sentence);
    }
  });

  it("drops the rail's per-player cap, because completeness is the contract", () => {
    const detail = selectDivergenceDetail({ playerProps: REDS, status: "completed" });
    const all = [...detail.offScript, ...detail.onScript];
    const perPlayer = new Map<string, number>();
    for (const r of all) perPlayer.set(r.player, (perPlayer.get(r.player) ?? 0) + 1);
    const worst = Math.max(...perPlayer.values());

    // Non-vacuity: this fixture actually CONTAINS a player with more questions
    // than the rail would ever show, so the assertion is doing work.
    expect(worst).toBeGreaterThan(RAIL_MAX_PER_PLAYER);
  });
});

describe("V2's escalation is unchanged across the fold", () => {
  it("gives a sentence to exactly the surprising rows, and never below the fold", () => {
    const d = selectDivergenceDetail({ playerProps: REDS, status: "completed" });

    for (const r of d.offScript) {
      expect(Boolean(r.sentence)).toBe(r.travel >= PROP_SURPRISE_TRAVEL);
    }
    // 0.10 < 0.20, so an on-script row cannot be surprising. Asserted rather
    // than assumed — it is the reason there is no second rule down there.
    for (const r of d.onScript) {
      expect(r.surprising).toBe(false);
      expect(r.sentence).toBeNull();
    }
  });

  it("keeps the sentence a minority of the off-script list", () => {
    const d = selectDivergenceDetail({ playerProps: REDS, status: "completed" });
    const sentences = d.offScript.filter((r) => r.sentence).length;
    // 13 of 100 questions clear 0.20 on this payload — p90. If a change makes
    // most of the list prose, the escalation has stopped meaning anything.
    expect(sentences).toBe(13);
    expect(sentences).toBeLessThan(d.offScript.length / 2);
  });

  it("settled games freeze — the sentence says finished, not now", () => {
    const d = selectDivergenceDetail({ playerProps: REDS, status: "completed" });
    const withSentence = d.offScript.filter((r) => r.sentence);
    expect(withSentence.length).toBeGreaterThan(0);
    for (const r of withSentence) {
      expect(r.settled).toBe(true);
      expect(r.sentence).toMatch(/finished at \d+%\.$/);
      expect(r.sentence).not.toMatch(/now\./);
    }
  });
});

describe("both directions, per gotcha #43", () => {
  it("populates on a quiet game without pretending it was eventful", () => {
    // Marlins @ Phillies: 40 questions, almost none of which moved. The detail
    // view must render the whole set with a nearly empty off-script section
    // rather than lowering the fold to manufacture drama.
    const d = selectDivergenceDetail({ playerProps: PHILLIES, status: "scheduled" });
    expect(d.eligible).toBe(40);
    expect(d.offScriptCount).toBe(3);
    expect(d.onScript.length).toBe(37);
    expect(d.emptyReason).toBeNull();
  });

  it("carries BOTH provider shapes — the Kalshi one must not collapse", () => {
    // 97 Kalshi rows (player in the OUTCOME, one market name over many people)
    // + 6 Polymarket rows (player in the MARKET, bare Over/Under legs).
    const sources = new Set(REDS.map((r) => r.source));
    expect(sources).toEqual(new Set(["kalshi", "polymarket"]));

    const d = selectDivergenceDetail({ playerProps: REDS, status: "completed" });
    const players = new Set([...d.offScript, ...d.onScript].map((r) => r.player));
    // #1639: keying on market_name would collapse the Kalshi rows onto a
    // handful of matchup-titled cards. Many distinct players is the proof it
    // did not happen.
    expect(players.size).toBeGreaterThan(20);
    expect(players.has("Over")).toBe(false);
    expect(players.has("Under")).toBe(false);
  });

  it("an empty input says which empty it is, and invents nothing", () => {
    expect(selectDivergenceDetail({ playerProps: [], status: "live" }).emptyReason).toBe(
      "none",
    );

    const unreadable = selectDivergenceDetail({
      playerProps: [
        { market_name: "", outcome_name: "", threshold: null } as unknown as PlayerPropRow,
      ],
      status: "live",
    });
    expect(unreadable.emptyReason).toBe("unreadable");
    expect(unreadable.nonBenignCount).toBe(1);
    expect(unreadable.dropped.map((d) => d.reason)).toContain("unknown");
  });

  it("a benign-only loss is a clean empty, not an alarming one", () => {
    const clean = selectDivergenceDetail({
      playerProps: [
        {
          market_name: "Alec Bohm: Home Runs O/U 0.5",
          outcome_name: "Over",
          threshold: 0.5,
          over_probability: null,
          pregame_mark: null,
          source: "polymarket",
        } as unknown as PlayerPropRow,
      ],
      status: "live",
    });
    expect(clean.emptyReason).toBe("clean");
    expect(clean.nonBenignCount).toBe(0);
  });
});
