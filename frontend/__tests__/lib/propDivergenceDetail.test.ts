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
 *
 * ── UX-P105 (#2011): THESE ASSERTIONS NOW RUN IN-GAME, AND THAT IS THE POINT ──
 *
 * Every travel-fold claim below used to be driven with `status: "completed"`,
 * which was only ever a convenient label — the mock measures a distance between
 * two PRICES, and the travel fold is now an in-game concept, because post-game
 * the fold is the distance from the mark to the OUTCOME.
 *
 * The 14788546 payload carries **zero graded rows** (0 of 100 have a typed
 * `hit`), so post-game it has nothing to rank and nothing to say. That is not
 * hidden by moving these to `live`: it is pinned below, in "the same payload,
 * after the whistle".
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
    const d = selectDivergenceDetail({ playerProps: REDS, status: "live" });
    // The mock's prose, re-derived from the payload by the shipped parser.
    expect(d.offScriptCount).toBe(34);
    expect(PROP_OFF_SCRIPT_TRAVEL).toBe(0.1);
  });

  it("every off-script row really did travel at least the fold, and every on-script row did not", () => {
    const d = selectDivergenceDetail({ playerProps: REDS, status: "live" });
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
    const d = selectDivergenceDetail({ playerProps: REDS, status: "live" });
    expect(d.offScript.length + d.onScript.length).toBe(d.eligible);
    expect(d.eligible).toBe(100);
  });
});

describe("the detail view reaches what the rail cannot", () => {
  it("surfaces the 95 questions the five-row rail leaves behind", () => {
    const rail = selectDivergenceRows({ playerProps: REDS, status: "live" });
    const detail = selectDivergenceDetail({ playerProps: REDS, status: "live" });

    expect(rail.rows).toHaveLength(RAIL_MAX_ROWS);
    expect(rail.notSelected).toBe(95);
    // The whole point of the slice: the expand is a destination, not a re-render.
    expect(detail.eligible).toBe(rail.eligible);
    expect(detail.offScript.length + detail.onScript.length).toBe(
      rail.rows.length + rail.notSelected,
    );
  });

  it("agrees with the rail about the rail's own rows — one admission rule, not two", () => {
    const rail = selectDivergenceRows({ playerProps: REDS, status: "live" });
    const detail = selectDivergenceDetail({ playerProps: REDS, status: "live" });
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
    const detail = selectDivergenceDetail({ playerProps: REDS, status: "live" });
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
    const d = selectDivergenceDetail({ playerProps: REDS, status: "live" });

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
    const d = selectDivergenceDetail({ playerProps: REDS, status: "live" });
    const sentences = d.offScript.filter((r) => r.sentence).length;
    // 13 of 100 questions clear 0.20 on this payload — p90. If a change makes
    // most of the list prose, the escalation has stopped meaning anything.
    expect(sentences).toBe(13);
    expect(sentences).toBeLessThan(d.offScript.length / 2);
  });

  it("in-game the sentence says now, not finished", () => {
    const d = selectDivergenceDetail({ playerProps: REDS, status: "live" });
    const withSentence = d.offScript.filter((r) => r.sentence);
    expect(withSentence.length).toBeGreaterThan(0);
    for (const r of withSentence) {
      expect(r.settled).toBe(false);
      expect(r.sentence).toMatch(/it's \d+% now\.$/);
      expect(r.sentence).not.toMatch(/finished at/);
    }
  });
});

describe("the same payload, after the whistle (UX-P105, #2011)", () => {
  /**
   * 14788546 is a COMPLETED game whose 100 eligible questions carry not one
   * published verdict. The rail used to render 34 "off script" travelled bars
   * on it, each ending at a last traded price and labelled `final NN%` — a
   * price wearing the grammar of a result, which is precisely what Alex called
   * out and what #2011 removes.
   *
   * So the post-game rendering of this payload is a wall of "not graded", and
   * that is the honest one. It is pinned here rather than left as a surprise,
   * and the size of it — 100 of 100 — is the supply-side finding routed out of
   * this cycle, not a rendering bug.
   */
  it("has zero published verdicts, so it ranks nothing and claims nothing", () => {
    const d = selectDivergenceDetail({ playerProps: REDS, status: "completed" });
    expect(d.settled).toBe(true);
    expect(d.eligible).toBe(100);
    expect(d.ungraded).toHaveLength(100);
    expect(d.offScript).toHaveLength(0);
    expect(d.onScript).toHaveLength(0);
    for (const r of d.ungraded) {
      expect(r.surprise).toBeNull();
      expect(r.resolution).toBeNull();
      expect(r.sentence).toBeNull();
    }
  });

  it("does NOT quietly become an empty section — the loss reaches the reader", () => {
    const d = selectDivergenceDetail({ playerProps: REDS, status: "completed" });
    // `eligible` still counts them: they are questions, not drops. V3's
    // distinction between "hidden" and "accounted for" is what makes the
    // ungraded group renderable instead of a silent filter.
    expect(d.eligible).toBe(d.ungraded.length);
    expect(d.emptyReason).toBeNull();
  });

  it("the rail says so in words instead of filling five slots with nothing", () => {
    const rail = selectDivergenceRows({ playerProps: REDS, status: "completed" });
    expect(rail.rows).toHaveLength(0);
    expect(rail.emptyReason).toBe("ungraded");
    expect(rail.ungraded).toBe(100);
    expect(rail.settled).toBe(true);
    // The expand still leads somewhere — every question is reachable.
    expect(rail.notSelected).toBe(100);
    expect(rail.eligible).toBe(100);
  });

  it("in-game the SAME payload fills the rail normally — the change is post-game only", () => {
    const rail = selectDivergenceRows({ playerProps: REDS, status: "live" });
    expect(rail.rows).toHaveLength(RAIL_MAX_ROWS);
    expect(rail.emptyReason).toBeNull();
    expect(rail.ungraded).toBe(0);
    expect(rail.settled).toBe(false);
  });
});

describe("both directions, per gotcha #43", () => {
  it("populates on a quiet game without pretending it was eventful", () => {
    // Marlins @ Phillies: 40 questions, almost none of which moved. The detail
    // view must render the whole set with a nearly empty off-script section
    // rather than lowering the fold to manufacture drama.
    //
    // UX-P106 MOVED THIS FROM "scheduled" TO "live", AND THAT IS A STATE
    // CORRECTION, NOT A WEAKENED ASSERTION. Every number here is unchanged.
    // When this was written the selector had two states and `scheduled` was how
    // you asked for the non-settled one. There are three now — script, moving,
    // landed — and the thing being asserted, the TRAVEL fold on a quiet game,
    // is the moving state's contract. Its pregame twin is the test below.
    const d = selectDivergenceDetail({ playerProps: PHILLIES, status: "live" });
    expect(d.eligible).toBe(40);
    expect(d.offScriptCount).toBe(3);
    expect(d.onScript.length).toBe(37);
    expect(d.emptyReason).toBeNull();
    expect(d.pregame).toBe(false);
  });

  it("PREGAME the same quiet game still does not lower its fold to fill a section", () => {
    // The twin, and the guard that matters for THE SCRIPT: a favourite-heavy
    // card must not put half its questions above the fold just because the
    // market has opinions about all of them.
    //
    // 8 of 40 = 20%, against the salience fold's measured 25.1% pooled. A first
    // draft folded on bare conviction and put **20 of 40** here — 50% — because
    // this card is favourite-heavy; that is the exact "lowering the fold to
    // manufacture drama" failure this describe block exists to catch, and it
    // caught it.
    const d = selectDivergenceDetail({ playerProps: PHILLIES, status: "scheduled" });
    expect(d.pregame).toBe(true);
    expect(d.eligible).toBe(40);
    expect(d.offScriptCount).toBe(8);
    expect(d.onScript.length).toBe(32);
    expect(d.emptyReason).toBeNull();
    // Non-vacuity in the other direction (gotcha #43): the section is neither
    // empty nor a majority of the page.
    expect(d.offScriptCount / d.eligible).toBeLessThan(0.35);
    expect(d.offScriptCount).toBeGreaterThan(0);
  });

  it("carries BOTH provider shapes — the Kalshi one must not collapse", () => {
    // 97 Kalshi rows (player in the OUTCOME, one market name over many people)
    // + 6 Polymarket rows (player in the MARKET, bare Over/Under legs).
    const sources = new Set(REDS.map((r) => r.source));
    expect(sources).toEqual(new Set(["kalshi", "polymarket"]));

    const d = selectDivergenceDetail({ playerProps: REDS, status: "live" });
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
