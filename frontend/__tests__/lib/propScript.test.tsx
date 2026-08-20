/**
 * THE SCRIPT — the pregame half. UX-P106 item 3.
 *
 * P105 gave the post-game rail its surprise ranking. This is the other end of
 * the same arc: what the props EXPECTED before first pitch, so that THE
 * DIVERGENCE has something to diverge from. Alex's done bar for this program is
 * the pre-game ritual test, on mobile.
 *
 * ── THE ONE FINDING THAT SHAPED EVERY DECISION BELOW ─────────────────────────
 *
 * **84.2% of pregame marks sit BELOW 0.5** — 154 of 183 questions across four
 * production payloads. THE SCRIPT is overwhelmingly a set of confident NEGATIVE
 * predictions, and that breaks two things a naive implementation does:
 *
 *   1. A left-anchored bar renders the majority of the page as nearly empty —
 *      "nothing here" — when the market is making its loudest claims.
 *   2. A rail ordered on the MARK rather than on distance from a coin flip puts
 *      every confident "will NOT happen" at the bottom. Willi Castro's 2+ hits
 *      was marked 17.0% and produced an 83-point surprise; mark-ordered, it is
 *      39th of 41.
 *
 * That number is re-derived here from the fixtures, not quoted.
 *
 * ── RULING (a), CARRIED FORWARD ──────────────────────────────────────────────
 *
 * #2011's prescribed rule inverted 9 of 57 rows because it typed on the ROW'S
 * OWN OUTCOME while the bar was quoted on the OVER side. The same trap is open
 * here and is wider, because pregame there is no `actual` to catch it with. So
 * `scriptSide` is typed off the over-side price (`current` pregame, which is
 * `over_probability`), never off `outcome_name`, and that is asserted against a
 * lone Polymarket "Under" leg — the exact shape that broke the settled rule.
 *
 * ── AND A SCREENSHOT CAUGHT WHAT THE TESTS DID NOT ───────────────────────────
 *
 * Two defects reached a rendered capture with a green suite behind them, both
 * recorded in the code they fixed:
 *
 *   * the bar quoted `pregameMark` while the sentence quoted `current`, so
 *     Schwarber's row printed "opened at 27% — it's 55% now" above a bar
 *     reading "market says NO, 73%". One row, two answers.
 *   * FIVE sentences on a five-row rail, four near-identical. V2 says the
 *     sentence is an escalation; at 5 of 5 it is the default rendering. The
 *     pooled rate was right (11.5%) and the PER-CARD rate was not.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import {
  isPregameStatus,
  isSettledStatus,
  PROP_SCRIPT_CONVICTION,
  PROP_SCRIPT_FOLD,
  PROP_SURPRISE_TRAVEL,
  selectDivergenceDetail,
  selectDivergenceRows,
  type DivergenceRow,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";
import PropDivergenceRail from "@/components/PropDivergenceRail";
import PropTravelBar from "@/components/PropTravelBar";

import phillies from "../fixtures/eventPlayerProps.15199886.json";
import reds from "../fixtures/eventPlayerProps.14788546.json";
import dodgers from "../fixtures/eventPlayerProps.15199902.settled.json";
import braves from "../fixtures/eventPlayerProps.15194472.settled.json";

const PHILLIES = phillies as unknown as PlayerPropRow[];
const REDS = reds as unknown as PlayerPropRow[];
const DODGERS = dodgers as unknown as PlayerPropRow[];
const BRAVES = braves as unknown as PlayerPropRow[];
const ALL: Array<[string, PlayerPropRow[]]> = [
  ["15199886", PHILLIES],
  ["14788546", REDS],
  ["15199902", DODGERS],
  ["15194472", BRAVES],
];

/** Every eligible question across the four payloads, read as pregame. */
function pooled(): DivergenceRow[] {
  const out: DivergenceRow[] = [];
  for (const [, rows] of ALL) {
    const d = selectDivergenceDetail({ playerProps: rows, status: "scheduled" });
    out.push(...d.offScript, ...d.onScript, ...d.ungraded);
  }
  return out;
}

function kalshiRow(
  player: string,
  line: number,
  mark: number,
  current = mark,
): PlayerPropRow {
  return {
    market_name: "Philadelphia vs Miami: Hits",
    outcome_name: `${player}: ${line}+`,
    threshold: line,
    over_probability: current,
    pregame_mark: mark,
    source: "kalshi",
  } as unknown as PlayerPropRow;
}

// ---------------------------------------------------------------------------
// The measurement
// ---------------------------------------------------------------------------

describe("the pregame constants are measurements, not preferences", () => {
  it("re-derives the 84% negative-direction finding from the fixtures", () => {
    const rows = pooled();
    const below = rows.filter((r) => r.pregameMark < 0.5).length;
    expect(rows.length).toBe(183);
    expect(below).toBe(154);
    expect(below / rows.length).toBeCloseTo(0.842, 3);
  });

  it("PROP_SCRIPT_CONVICTION is p90 of the conviction distribution", () => {
    const conv = pooled().map((r) => r.conviction);
    const p90 = [...conv].sort((a, b) => a - b)[Math.round(0.9 * (conv.length - 1))];
    expect(PROP_SCRIPT_CONVICTION).toBeCloseTo(p90, 6);
    // ... and selects the same 11-ish% the other two states escalate at.
    const rate = conv.filter((c) => c >= PROP_SCRIPT_CONVICTION - 1e-9).length / conv.length;
    expect(rate).toBeGreaterThan(0.09);
    expect(rate).toBeLessThan(0.13);
  });

  it("PROP_SCRIPT_FOLD is p75 of the SALIENCE distribution, and holds per-card", () => {
    const sal = pooled().map((r) =>
      Math.max(r.travel / PROP_SURPRISE_TRAVEL, r.conviction / PROP_SCRIPT_CONVICTION),
    );
    const p75 = [...sal].sort((a, b) => a - b)[Math.round(0.75 * (sal.length - 1))];
    expect(PROP_SCRIPT_FOLD).toBeCloseTo(p75, 2);

    // The property a bare-conviction fold did NOT have: stability across cards.
    // On the favourite-heavy Phillies card a conviction fold put 50% above the
    // line; salience keeps every card inside a narrow band.
    for (const [name, rows] of ALL) {
      const d = selectDivergenceDetail({ playerProps: rows, status: "scheduled" });
      if (d.eligible < 10) continue; // 15194472 has 2 questions; no rate to speak of
      const rate = d.offScriptCount / d.eligible;
      expect({ name, tooWide: rate > 0.35 }).toEqual({ name, tooWide: false });
      expect({ name, empty: rate === 0 }).toEqual({ name, empty: false });
    }
  });
});

// ---------------------------------------------------------------------------
// Ruling (a): the direction is typed off the OVER side
// ---------------------------------------------------------------------------

describe("the script's DIRECTION is typed off the over-side mark", () => {
  it("a lone Polymarket 'Under' leg does not invert the claim", () => {
    // The exact shape that made #2011's prescribed rule wrong on 9 of 57 rows:
    // the leg's own outcome says "Under", while every price on the row —
    // including `pregame_mark` — is quoted on the OVER side.
    const under = {
      market_name: "Alec Bohm: Home Runs O/U 0.5",
      outcome_name: "Under",
      threshold: 0.5,
      over_probability: 0.0545,
      pregame_mark: 0.0545,
      source: "polymarket",
    } as unknown as PlayerPropRow;

    const row = selectDivergenceRows({ playerProps: [under], status: "scheduled" }).rows[0];
    // The OVER side is at 5.45%, so the script says the over will NOT happen.
    // Reading the leg's own outcome would have produced "will".
    expect(row.scriptSide).toBe("wont");
    expect(row.pregameMark).toBeCloseTo(0.0545, 6);
  });

  it("both legs of one O/U question agree, because they are one question", () => {
    const legs = ["Over", "Under"].map(
      (side) =>
        ({
          market_name: "Alec Bohm: Home Runs O/U 0.5",
          outcome_name: side,
          threshold: 0.5,
          over_probability: 0.0545,
          pregame_mark: 0.0545,
          source: "polymarket",
        }) as unknown as PlayerPropRow,
    );
    const rows = selectDivergenceRows({ playerProps: legs, status: "scheduled" }).rows;
    expect(rows).toHaveLength(1); // collapsed to one question
    expect(rows[0].scriptSide).toBe("wont");
  });

  it("names all three directions, and a coin flip is its own value", () => {
    const rows = selectDivergenceRows({
      playerProps: [
        kalshiRow("Heavy Yes", 1, 0.93),
        kalshiRow("Heavy No", 4, 0.07),
        kalshiRow("Coin Flip", 2, 0.5),
      ],
      status: "scheduled",
    }).rows;
    const by = (n: string) => rows.find((r) => r.player === n)!;
    expect(by("Heavy Yes").scriptSide).toBe("will");
    expect(by("Heavy No").scriptSide).toBe("wont");
    // Not "wont" by default: a market at 50% is making no claim, and rendering
    // it as a weak one is the surface inventing a view nobody has.
    expect(by("Coin Flip").scriptSide).toBe("toss_up");
  });

  it("EVERY ROW QUOTES THE CHANCE IT HAPPENS — one direction, all the way down", () => {
    // ── AMENDED BY UX-P107 (Alex, on the P106 capture) ──────────────────────
    //
    // This test used to assert the opposite, and it was RIGHT about the defect
    // it was written for and WRONG about the fix. It pinned "market says NO —
    // 93%" for a row priced at 7%: the direction word and the probability of
    // THAT direction, internally consistent, and asserted to be so.
    //
    // What it could not see is the page. Read down a five-row rail, 93% here
    // measures "does not happen" and 55% on the next row measures "does" — a
    // column of percentages whose subject alternates. Every row correct, the
    // column unreadable. Alex's first read caught it, no test could have, and
    // that is the second time in two cycles a suite has PINNED the exact string
    // a capture then ruled out (#1650's `toContain("Hit")`).
    //
    // The contract is now: the number is always the chance it HAPPENS.
    const render = (mark: number) =>
      renderToStaticMarkup(
        <PropTravelBar
          row={
            selectDivergenceRows({
              playerProps: [kalshiRow("X", 1, mark)],
              status: "scheduled",
            }).rows[0]
          }
        />,
      );
    const unlikely = render(0.07);
    const likely = render(0.93);

    expect(unlikely).toContain("7% chance");
    expect(likely).toContain("93% chance");
    // The complement must appear NOWHERE — not in the cell, not in the label.
    expect(unlikely).not.toContain("93%");
    expect(likely).not.toContain("7%");

    // The banned vocabulary, in both renders and in both cases. A direction
    // word reads as a verdict on a page where nothing has happened, and
    // "market" attributes our one number to somebody else.
    for (const html of [unlikely, likely]) {
      expect(html).not.toMatch(/YES|NO\b/);
      expect(html.toLowerCase()).not.toContain("market");
      expect(html.toLowerCase()).not.toContain("will happen");
      expect(html.toLowerCase()).not.toContain("will not happen");
    }

    // The aria-label states the SAME quantity as the visible cell — it was the
    // second place the direction was spelled out, so it was the second place
    // the flip could hide.
    expect(unlikely).toMatch(/aria-label="[^"]*7% chance/);
    expect(likely).toMatch(/aria-label="[^"]*93% chance/);
  });

  it("a coin flip states its chance too, rather than opting out of the column", () => {
    // The old row rendered the words "coin flip" and NO number. Under one
    // consistent direction that is a hole in the column, and a reader scanning
    // for the number finds prose.
    const html = renderToStaticMarkup(
      <PropTravelBar
        row={
          selectDivergenceRows({
            playerProps: [kalshiRow("Coin Flip", 2, 0.5)],
            status: "scheduled",
          }).rows[0]
        }
      />,
    );
    expect(html).toContain("50% chance");
  });

  it("quotes the CURRENT price, on a row whose opening mark disagrees with it", () => {
    // NON-VACUITY, AND IT WAS FOUND BY MUTATION. The assertions above hold
    // `pregame_mark === over_probability`, so a mutation that reads the OPENING
    // mark for the number while reading the CURRENT price for the direction
    // passes every one of them — and that mutation is not hypothetical, it is
    // the exact draft the rendered capture caught.
    //
    // Kyle Schwarber's real row on `15199886`: opened 27%, now 55%. The
    // direction flipped between those two numbers, which is what makes this the
    // specimen.
    const row = selectDivergenceRows({
      playerProps: [kalshiRow("Kyle Schwarber", 1, 0.27, 0.55)],
      status: "scheduled",
    }).rows[0];
    const html = renderToStaticMarkup(<PropTravelBar row={row} />);

    expect(row.scriptSide).toBe("will"); // 55% ⇒ the bar grows to the yes side
    expect(html).toContain("55% chance");
    // 27% is the OPENING mark and 73% and 45% are complements. Any of them
    // appearing here means the cell was read off a different number than the
    // bar was drawn from.
    expect(html).not.toContain("27%");
    expect(html).not.toContain("73%");
    expect(html).not.toContain("45%");
    expect(html).toMatch(/aria-label="[^"]*55% chance/);
  });

  it("conviction is SYMMETRIC — a 7% claim ranks with a 93% claim, not below it", () => {
    const rows = selectDivergenceRows({
      playerProps: [
        kalshiRow("Heavy No", 4, 0.07),
        kalshiRow("Heavy Yes", 1, 0.93),
        kalshiRow("Lukewarm", 2, 0.62),
      ],
      status: "scheduled",
    }).rows;
    expect(rows.map((r) => r.player).slice(0, 2).sort()).toEqual(["Heavy No", "Heavy Yes"]);
    expect(rows[2].player).toBe("Lukewarm");
    const no = rows.find((r) => r.player === "Heavy No")!;
    const yes = rows.find((r) => r.player === "Heavy Yes")!;
    expect(no.conviction).toBeCloseTo(yes.conviction, 6);
  });
});

// ---------------------------------------------------------------------------
// Three states, three keys
// ---------------------------------------------------------------------------

describe("the state machine is a triple, not a boolean", () => {
  it.each([
    ["scheduled", true, false],
    ["", true, false],
    ["postponed", true, false],
    ["live", false, false],
    ["in_progress", false, false],
    ["halftime", false, false],
    ["completed", false, true],
    ["closed", false, true],
    ["final", false, true],
  ])("%s -> pregame=%s settled=%s", (status, pregame, settled) => {
    expect(isPregameStatus(status)).toBe(pregame);
    expect(isSettledStatus(status)).toBe(settled);
  });

  it("an UNKNOWN status lands on THE SCRIPT, which is the safe end", () => {
    // The script states pregame marks, which are true at every point in the
    // game. The other two states make claims about a clock we would be guessing
    // at — a live rail on a finished game, or a settled rail on one in progress.
    expect(isPregameStatus("who_knows")).toBe(true);
    expect(isSettledStatus("who_knows")).toBe(false);
  });

  it("pregame escalates on TRAVEL ONLY — conviction ranks, it does not narrate", () => {
    // `pregame_mark` is the OPENING capture, not the price at first pitch, so
    // pregame travel is the line move since the market opened — real, and up to
    // 27.7 points on this population. Replacing travel with conviction outright
    // deleted V1/V2's ruled escalation; three slice-1 tests caught it.
    //
    // The other direction took a rendered capture: escalating on conviction TOO
    // put five sentences on a five-row rail, four of them restating their own
    // bars. A pregame script sentence has nothing to escalate to — the bar
    // already says "market says NO, 95%".
    const moved = kalshiRow("Line Moved", 2, 0.5, 0.5 + PROP_SURPRISE_TRAVEL);
    const convicted = kalshiRow("Heavy Favourite", 1, 0.5 + PROP_SCRIPT_CONVICTION);
    const neither = kalshiRow("Quiet", 3, 0.6, 0.62);
    const rows = selectDivergenceRows({
      playerProps: [moved, convicted, neither],
      status: "scheduled",
    }).rows;
    const by = (n: string) => rows.find((r) => r.player === n)!;
    expect(by("Line Moved").surprising).toBe(true);
    expect(by("Line Moved").sentence).toBeTruthy();

    // ── UX-P108 FLIPPED THE ORDER, AND ONLY THE ORDER ────────────────────────
    //
    // UX-P106 asserted `rows[0].player === "Heavy Favourite"` — conviction
    // decided the order. Alex's movement-first ruling reverses it: a question
    // the market CHANGED ITS MIND about outranks one it has merely been
    // confident about since the board opened.
    //
    // ** AND THE FULL ORDER IS PINNED, BECAUSE ITS THIRD PLACE IS THE RULING'S
    // SHARPEST EDGE. ** "Quiet" moved two points (60% -> 62%) and outranks a 93%
    // favourite that has not moved at all. That is not an accident of this
    // fixture, it is what a strict movement TIER means, and it is asserted here
    // so the trade is visible in the suite rather than discovered on a card.
    // See `PROP_TRAVEL_FLOOR` for why the tier's floor is the same half-point
    // line that types `direction`: any higher and a row whose bar visibly draws
    // a journey would rank below a flat one, which is the complaint this ruling
    // came from, re-created one tier down.
    expect(rows.map((r) => r.player)).toEqual(["Line Moved", "Quiet", "Heavy Favourite"]);
    // … and the favourite STILL says nothing beyond its own bar. Demoting a row
    // is not the same as narrating it, and this is the half UX-P106 established.
    expect(by("Heavy Favourite").surprising).toBe(false);
    expect(by("Heavy Favourite").sentence).toBeNull();

    expect(by("Quiet").surprising).toBe(false);
    expect(by("Quiet").sentence).toBeNull();
  });

  it("a five-row pregame rail is not five sentences", () => {
    // The capture's finding, pinned. On the real Phillies payload the rail
    // carried 5 of 5 before this was corrected.
    const rows = selectDivergenceRows({ playerProps: PHILLIES, status: "scheduled" }).rows;
    expect(rows).toHaveLength(5);
    const withProse = rows.filter((r) => r.sentence != null).length;
    expect(withProse).toBeLessThanOrEqual(2);
    // Non-vacuity, both directions (gotcha #43): the escalation still HAPPENS.
    expect(withProse).toBeGreaterThan(0);
  });

  it("a pregame row that MOVED gets the movement sentence, not the script one", () => {
    const rows = selectDivergenceRows({
      playerProps: [kalshiRow("Line Moved", 2, 0.3, 0.7)],
      status: "scheduled",
    }).rows;
    expect(rows[0].sentence).toContain("opened at 30%");
    expect(rows[0].sentence).toContain("70% now");
    expect(rows[0].sentence).not.toContain("The market says");
  });
});

// ---------------------------------------------------------------------------
// Coherence with the other half — the reason this ranking is right
// ---------------------------------------------------------------------------

describe("THE SCRIPT and THE DIVERGENCE describe the same game", () => {
  it("the rows the script leads with are the rows the settled rail ranks first", () => {
    // NOT a claim that conviction predicts surprise — n=41 cannot support that
    // (2 of 6 high-conviction rows surprised, against 2 of 35 below the line).
    // It is a coherence claim: the two halves agree about which questions on
    // this game were the loud ones, which is what makes "the divergence has
    // something to diverge from" mean anything.
    // THE COMPARISON HAS TO BE ON THE OPENING MARKS, NOT THE LIVE SURFACE.
    // Pregame the script surface reads `current`, because before first pitch
    // that IS the standing expectation. On a payload that has already settled,
    // `current` is the last traded price — worthless (#2011) — so replaying the
    // script surface over a settled fixture compares the wrong number. What the
    // script SAID when it opened is `conviction` on the settled rows, which is
    // exactly the mark-based value.
    const landedResult = selectDivergenceRows({ playerProps: DODGERS, status: "completed" });
    const landed = landedResult.rows;
    const all = selectDivergenceDetail({ playerProps: DODGERS, status: "completed" });
    const everyQuestion = [...all.offScript, ...all.onScript, ...all.ungraded];
    const openedLoudest = [...everyQuestion]
      .sort((a, b) => b.conviction - a.conviction)
      .slice(0, landed.length);

    const scriptKeys = new Set(openedLoudest.map((r) => r.key));
    const overlap = landed.filter((r) => scriptKeys.has(r.key)).length;

    // TWO of the five rows the post-game rail promotes were among the five the
    // script opened loudest on — Freeman's 3+ HRR (marked 93%) and Fulford's 1+
    // HRR (92.5%), the two biggest surprises of the game. A first draft of this
    // test asserted three; the number was wishful, written before it was
    // measured. It is 2.
    expect(overlap).toBe(2);

    // Which is only interesting against chance. Five slots drawn from 41
    // eligible questions overlap ~0.61 rows at random; 2 is roughly 3x that.
    // Stated as a comparison so the claim survives a fixture with a different
    // question count.
    const byChance = (openedLoudest.length * landed.length) / landedResult.eligible;
    expect(overlap).toBeGreaterThan(2 * byChance);

    // And the mechanism, stated: the biggest surprises came from the strongest
    // pregame claims.
    const top = landed[0];
    expect(top.surprise).toBeGreaterThan(0.9);
    expect(top.conviction).toBeGreaterThanOrEqual(PROP_SCRIPT_CONVICTION);
  });
});

// ---------------------------------------------------------------------------
// Rendered — mobile-first, and the bar the 84% finding is about
// ---------------------------------------------------------------------------

describe("the rendered pregame surface", () => {
  const html = renderToStaticMarkup(
    <PropDivergenceRail playerProps={PHILLIES} status="scheduled" />,
  );

  it("leads with THE SCRIPT, and stops promising movement", () => {
    expect(html).toContain("The script");
    // The header is a promise. Pregame it cannot promise movement, which is
    // #2011's defect read on the other clock.
    expect(html).not.toContain("What&#x27;s moving");
    expect(html).not.toContain("What's moving");
    expect(html).not.toContain("How the props landed");
  });

  it("STATES ONE QUANTITY, AND ATTRIBUTES IT TO NOBODY", () => {
    // ── THIS TEST'S PREMISE WAS INVERTED BY ALEX'S RULING, AND SAYING SO IS
    //    THE POINT OF LEAVING IT HERE ─────────────────────────────────────────
    //
    // It used to read "states the direction in words, not only as a number",
    // reasoning from the 84% finding that a page of sub-50% marks rendering
    // only numbers reads as "nothing is going to happen tonight". The reasoning
    // was sound and the remedy was wrong: the words that were added read as a
    // VERDICT, and the number they attached to changed meaning row to row. The
    // 84% finding is answered by the BAR — centred, growing out, 7% as loud as
    // 93% — which is the half of the P106 design Alex explicitly kept.
    expect(html).toMatch(/\d+% chance/);
    // TWICE PER ROW ON A FIVE-ROW RAIL, and the doubling is the assertion: the
    // visible cell and the bar's aria-label print the identical string from the
    // identical function. A count of 5 would mean one of the two had drifted
    // into its own phrasing, which is precisely how the banned wording survived
    // in an aria-label after being fixed on screen.
    expect(html.match(/% chance/g) ?? []).toHaveLength(10);
    const visible = html.match(/>(\d+% chance)</g) ?? [];
    const spoken = html.match(/aria-label="[^"]*?(\d+% chance)"/g) ?? [];
    expect(visible).toHaveLength(5);
    expect(spoken).toHaveLength(5);
    expect(html.toLowerCase()).not.toContain("market says");
    expect(html).not.toMatch(/>YES</);
    expect(html).not.toMatch(/>NO</);
  });

  it("draws a 7% claim and a 93% claim at the SAME weight", () => {
    const yes = renderToStaticMarkup(
      <PropTravelBar
        row={selectDivergenceRows({ playerProps: [kalshiRow("A", 1, 0.93)], status: "scheduled" }).rows[0]}
      />,
    );
    const no = renderToStaticMarkup(
      <PropTravelBar
        row={selectDivergenceRows({ playerProps: [kalshiRow("A", 1, 0.07)], status: "scheduled" }).rows[0]}
      />,
    );
    // Equal conviction ⇒ equal bar length; the side it grows to is the only
    // difference. A left-anchored fill would have drawn 93% and 7%.
    const width = (h: string) => h.match(/width:\s*([\d.]+)%/)?.[1];
    expect(width(yes)).toBe(width(no));
    expect(yes).toContain("left:50%");
    expect(no).toContain("right:50%");
  });

  it("renders no travel bar and no 'now' price pregame", () => {
    // Nothing has travelled from anywhere yet. The in-game bar's grammar —
    // opened X, now Y — is a story this page does not have.
    const row = selectDivergenceRows({
      playerProps: [kalshiRow("A", 1, 0.93)],
      status: "scheduled",
    }).rows[0];
    const bar = renderToStaticMarkup(<PropTravelBar row={row} />);
    expect(bar).not.toContain("opened");
    expect(bar).not.toContain("now ");
  });

  it("speaks the SAME sentence to a screen reader that it shows on the screen", () => {
    // The bar is a shape, so it says nothing on its own. It used to say "the
    // market says this will not happen, 93%" — the banned phrasing, in the one
    // place a rendered capture cannot show it. Now it speaks the identical
    // string the visible cell prints, from the same function.
    expect(html).toMatch(/aria-label="[^"]*: \d+% chance"/);
    expect(html).not.toMatch(/aria-label="[^"]*(will not happen|market)/);
  });
});
