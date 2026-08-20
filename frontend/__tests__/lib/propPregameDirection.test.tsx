/**
 * PREGAME DIRECTION, and the settled card's dropped unit — UX-P107.
 *
 * Two Alex rulings, both from his FIRST READ of the UX-P106 capture, and both
 * of the same kind: a green suite could not see either, because each row was
 * individually correct and the defect lived in how a stranger reads the page.
 *
 * ── RULING 1: ONE DIRECTION ──────────────────────────────────────────────────
 *
 *   "Every script row quotes the CHANCE IT HAPPENS, one consistent direction —
 *    Stowers reads '5% chance', Schwarber '55% chance'. The bar stays centred on
 *    the coin flip as built. 'market says YES/NO' is DROPPED entirely."
 *
 * Three separate faults were live in one four-word phrase:
 *   * the NUMBER flipped subject row to row — 55% meant "chance of yes", the
 *     next row's 95% meant "chance of no";
 *   * "NO" read as a VERDICT (the thing didn't happen) on a page where nothing
 *     has happened, and the site's settled vocabulary really does put a verdict
 *     in that position (#1650);
 *   * "market says" attributes our one blended number to somebody else, which
 *     is against the standing doctrine that *the blend is the product*.
 *
 * ── RULING 2: NOTHING BEATS UNHELPFUL ────────────────────────────────────────
 *
 *   "DROP the unlabeled grey 'NN pts' from the how-the-props-landed card. The
 *    sentence already carries the information; the card stays ranked by
 *    surprise, unannotated. Ruling 5 — an unlabeled unit invites exactly the
 *    misread it just got."
 *
 * ── THE GUARD SHAPE IS THE BANKED ONE, ON A NEW AXIS ─────────────────────────
 *
 * UX-P106's differential census (a fourth settled vocabulary, found by nobody
 * predicting the word) is banked practice, and the directive's carry says to
 * cite it when the next vocabulary class appears. This is that class.
 *
 * The settled census flips the VERDICT and diffs the rendered token multisets;
 * the tokens that differ ARE the settled vocabulary. Here the same machinery
 * flips the PRICE across the coin flip — 7% against 93%, everything else held —
 * and the tokens that differ ARE the direction vocabulary. Under one consistent
 * direction there must be NONE: two mirrored rows should differ only in their
 * numbers. Under the shipped design the delta contained YES and NO, and it
 * would contain any future word invented for the same job without anyone having
 * to guess it in advance.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { selectDivergenceRows, selectDivergenceDetail } from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";
import PropTravelBar, { chanceLabel } from "@/components/PropTravelBar";
import PropDivergenceRail from "@/components/PropDivergenceRail";
import PropDivergenceDetail from "@/components/PropDivergenceDetail";
import { renderedTokens, vocabularyDelta } from "../helpers/renderedTokens";

import phillies from "../fixtures/eventPlayerProps.15199886.json";
import dodgers from "../fixtures/eventPlayerProps.15199902.settled.json";

const PHILLIES = phillies as unknown as PlayerPropRow[];
const DODGERS = dodgers as unknown as PlayerPropRow[];

function kalshiRow(player: string, line: number, mark: number, current = mark): PlayerPropRow {
  return {
    market_name: "Philadelphia vs Miami: Hits",
    outcome_name: `${player}: ${line}+`,
    threshold: line,
    over_probability: current,
    pregame_mark: mark,
    source: "kalshi",
  } as unknown as PlayerPropRow;
}

function scriptRow(price: number): string {
  const row = selectDivergenceRows({
    playerProps: [kalshiRow("Mirror Player", 2, price)],
    status: "scheduled",
  }).rows[0];
  return renderToStaticMarkup(React.createElement(PropTravelBar, { row }));
}

// ---------------------------------------------------------------------------
// RULING 1 — the census
// ---------------------------------------------------------------------------

describe("the direction census: mirrored prices may differ ONLY in their numbers", () => {
  it.each([
    [0.07, 0.93],
    [0.05, 0.95],
    [0.27, 0.73],
    [0.44, 0.56],
  ])("%s vs %s: the vocabulary delta is empty", (low, high) => {
    // If ANY word differs between a row priced 7% and its mirror at 93%, that
    // word is stating the direction — which is the thing the ruling removed.
    // The failure names the token, so a NEW direction word reds this without
    // anyone having predicted it.
    expect(vocabularyDelta(scriptRow(low), scriptRow(high))).toEqual([]);
  });

  it("NON-VACUITY: the census DOES see a direction word when one is present", () => {
    // A census that always passes is worse than none. The shipped-and-ruled-out
    // rendering, reconstructed, must red it — otherwise the empty delta above
    // is proving nothing about the machinery.
    const asShipped = (price: number) =>
      `<div aria-label="Mirror Player: 2+ hits: the market says this ${
        price > 0.5 ? "will" : "will not"
      } happen, ${Math.round((price > 0.5 ? price : 1 - price) * 100)}%"></div>` +
      `<span>market says <span>${price > 0.5 ? "YES" : "NO"}</span></span>`;
    const delta = vocabularyDelta(asShipped(0.07), asShipped(0.93));
    expect(delta).toContain("YES");
    expect(delta).toContain("NO");
    expect(delta).toContain("not");
  });

  it("the census reads aria-labels, which no screenshot can check", () => {
    // The half a rendered capture cannot review — and the half where the banned
    // phrasing survived a fix once already.
    const tokens = renderedTokens(scriptRow(0.07));
    expect(tokens).toContain("chance");
    expect(tokens.join(" ")).toContain("Mirror Player: 2+ hits: 7% chance");
  });
});

// ---------------------------------------------------------------------------
// RULING 1 — the contract itself
// ---------------------------------------------------------------------------

describe("every pregame number is the chance the question HAPPENS", () => {
  it("the helper never states the complement", () => {
    expect(chanceLabel(0.05)).toBe("5% chance");
    expect(chanceLabel(0.55)).toBe("55% chance");
    // Alex's two worked examples, verbatim.
    expect(chanceLabel(0.05)).not.toContain("95");
    expect(chanceLabel(0.55)).not.toContain("45");
  });

  it("ON THE REAL CARD: every rail row quotes its own over-side price", () => {
    const rail = selectDivergenceRows({ playerProps: PHILLIES, status: "scheduled" });
    const html = renderToStaticMarkup(
      React.createElement(PropDivergenceRail, { playerProps: PHILLIES, status: "scheduled" }),
    );
    expect(rail.rows.length).toBe(5);
    for (const row of rail.rows) {
      expect(html).toContain(chanceLabel(row.current));
      // and the complement of that same row appears nowhere on the page
      const complement = `${Math.round((1 - row.current) * 100)}% chance`;
      if (complement !== chanceLabel(row.current)) {
        expect(html).not.toContain(complement);
      }
    }
  });

  it("THE MONOTONICITY A READER RELIES ON: a bigger number is always a likelier thing", () => {
    // The property the flip destroyed, stated directly. Sort the rendered
    // percentages and the rows must sort the same way by `current`. Under the
    // old rendering this was false by construction on any mixed card.
    const rail = selectDivergenceRows({ playerProps: PHILLIES, status: "scheduled" });
    const quoted = rail.rows.map((r) => ({
      current: r.current,
      shown: Number(chanceLabel(r.current).replace("% chance", "")),
    }));
    const byCurrent = [...quoted].sort((a, b) => a.current - b.current).map((q) => q.shown);
    const byShown = [...quoted].sort((a, b) => a.shown - b.shown).map((q) => q.shown);
    expect(byCurrent).toEqual(byShown);
    // non-vacuity: the card really does straddle the flip
    expect(Math.min(...quoted.map((q) => q.current))).toBeLessThan(0.5);
    expect(Math.max(...quoted.map((q) => q.current))).toBeGreaterThan(0.5);
  });

  it("THE BANNED VOCABULARY, across every pregame surface", () => {
    const surfaces = [
      renderToStaticMarkup(
        React.createElement(PropDivergenceRail, { playerProps: PHILLIES, status: "scheduled" }),
      ),
      renderToStaticMarkup(
        React.createElement(PropDivergenceDetail, { playerProps: PHILLIES, status: "scheduled" }),
      ),
      scriptRow(0.07),
      scriptRow(0.93),
      scriptRow(0.5),
    ];
    for (const html of surfaces) {
      const tokens = renderedTokens(html);
      const text = tokens.join(" ").toLowerCase();
      // "market" — the number is ours, not a market's (the blend is the product)
      expect(text).not.toContain("market");
      // The direction words, CASE-SENSITIVELY, which is the banked census's
      // deliberate choice and earns itself again here: a lowercase "no" is the
      // section heading "No strong view", which is a label for a group of rows
      // and not a verdict about one. A case-folded check reds on it and teaches
      // the next reader to loosen the guard.
      expect(tokens).not.toContain("YES");
      expect(tokens).not.toContain("NO");
      expect(text).not.toContain("will happen");
      expect(text).not.toContain("will not happen");
      expect(text).not.toContain("won't happen");
    }
  });

  it("NO NUMBER IS ANNOUNCED TWICE — the bar speaks, the sr-only line does not repeat it", () => {
    // Caught by the census output rather than by design: restating the ruled
    // sentence in the detail view's sr-only paragraph made it identical to the
    // bar's aria-label, so every row said its number twice to a screen reader.
    const html = renderToStaticMarkup(
      React.createElement(PropDivergenceDetail, { playerProps: PHILLIES, status: "scheduled" }),
    );
    const detail = selectDivergenceDetail({ playerProps: PHILLIES, status: "scheduled" });
    const eligible = detail.offScript.length + detail.onScript.length;
    expect(eligible).toBe(40);
    // Once in the visible cell and once in the aria-label. Not three times.
    expect(html.match(/% chance/g) ?? []).toHaveLength(eligible * 2);
    expect(html).not.toContain("Script says");
  });

  it("the bar itself is UNCHANGED — centred, and 7% still draws as loud as 93%", () => {
    // Alex kept this half explicitly ("The bar stays centred on the coin flip as
    // built"), so the ruling must not have quietly cost it.
    const low = scriptRow(0.07);
    const high = scriptRow(0.93);
    const width = (h: string) => h.match(/width:\s*([\d.]+)%/)?.[1];
    expect(width(low)).toBe(width(high));
    expect(high).toContain("left:50%");
    expect(low).toContain("right:50%");
  });

  it("a coin flip is in the column, not exempt from it", () => {
    expect(scriptRow(0.5)).toContain("50% chance");
  });

  it("the detail view speaks it through the bar, once, in the ruled direction", () => {
    const html = renderToStaticMarkup(
      React.createElement(PropDivergenceDetail, { playerProps: PHILLIES, status: "scheduled" }),
    );
    expect(html).toMatch(/aria-label="[^"]*: \d+% chance"/);
    expect(html).not.toContain("will NOT happen");
    expect(html).not.toContain("will not happen");
    // The footer legend went with it — it was the last place a "a bar growing
    // left means the market says NO" gloss could have survived the ruling.
    expect(html).toContain("every number is the chance it happens");
    expect(html).not.toContain("saying it will NOT happen");
  });

  it("the in-game and settled screen-reader lines are NOT collateral", () => {
    // Only the pregame line was redundant with the bar. The other two describe
    // a journey the bar draws and a screen reader cannot see.
    const live = renderToStaticMarkup(
      React.createElement(PropDivergenceDetail, { playerProps: PHILLIES, status: "live" }),
    );
    expect(live).toMatch(/Script said \d+%, now \d+%\./);
    const settled = renderToStaticMarkup(
      React.createElement(PropDivergenceDetail, { playerProps: DODGERS, status: "completed" }),
    );
    expect(settled).toMatch(/Script said \d+%; it (hit|missed)/);
  });
});

// ---------------------------------------------------------------------------
// RULING 2 — the dropped unit
// ---------------------------------------------------------------------------

describe("the settled card is ranked by surprise and no longer annotated with it", () => {
  const settledRail = renderToStaticMarkup(
    React.createElement(PropDivergenceRail, { playerProps: DODGERS, status: "completed" }),
  );

  it("no bare 'NN pts' anywhere a sighted reader can see it", () => {
    expect(settledRail).not.toMatch(/\d+\s*pts/);
  });

  it("THE INFORMATION IS STILL THERE, in the sentence — this is a drop, not a loss", () => {
    // Ruling 5 is "nothing beats unhelpful", not "less is more". If the sentence
    // stopped carrying the mark and the outcome, the number would have been
    // removed from a card that then said nothing.
    expect(settledRail).toContain("was marked 93%");
    expect(settledRail).toMatch(/and it (hit|missed)\./);
    expect(settledRail).toContain("marked");
  });

  it("THE RANKING IS UNTOUCHED — the key is still surprise, it is just not printed", () => {
    const rail = selectDivergenceRows({ playerProps: DODGERS, status: "completed" });
    const surprises = rail.rows.map((r) => r.surprise ?? -1);
    expect(surprises).toEqual([...surprises].sort((a, b) => b - a));
    expect(surprises[0]).toBeGreaterThan(0.9);
  });

  it("the LABELLED screen-reader form survives, because it is not the failure mode", () => {
    // A bare number in a grey column invites "93 what?". The same number spoken
    // as "93 pts from the mark" does not, and dropping it would cost a screen
    // reader the ordering a sighted reader gets from the row order itself.
    const detail = renderToStaticMarkup(
      React.createElement(PropDivergenceDetail, { playerProps: DODGERS, status: "completed" }),
    );
    expect(detail).toMatch(/\d+ pts from the mark/);
    // and it is ONLY in the sr-only line — never in a visible cell
    const visibleText = detail.replace(/<p class="sr-only">.*?<\/p>/g, " ");
    expect(visibleText).not.toMatch(/\d+\s*pts/);
  });

  it("the in-game movement pill is NOT what was dropped", () => {
    // `signedTravelPoints` renders "+28" in-game and is a different element with
    // a different job. A ruling about the settled card must not have eaten it.
    const live = renderToStaticMarkup(
      React.createElement(PropDivergenceDetail, { playerProps: PHILLIES, status: "live" }),
    );
    expect(live).toMatch(/[+-]\d+/);
  });
});

// ---------------------------------------------------------------------------
// The first-read test, as far as a test can carry it
// ---------------------------------------------------------------------------

describe("the first-read bar", () => {
  it("a stranger reading the rail sees ONE unit, named, on every row", () => {
    const html = renderToStaticMarkup(
      React.createElement(PropDivergenceRail, { playerProps: PHILLIES, status: "scheduled" }),
    );
    const text = renderedTokens(html).join(" ");
    const rail = selectDivergenceRows({ playerProps: PHILLIES, status: "scheduled" });

    // ── THE PROPERTY, STATED AS A CLOSED SET ────────────────────────────────
    //
    // A first draft of this asserted that EVERY percentage on the page is
    // followed by the word "chance", and it failed on the escalation sentence
    // ("opened at 27% — it's 55% now"). That sentence is not a violation: both
    // of its numbers are over-side probabilities, so the direction is the same
    // one the bar states — V2's escalation, which Alex did not rule on.
    //
    // The real property is stronger and does cover it: every percentage the
    // page prints must be a number the rows actually carry, on the over side.
    // A complement — the shape the ruling removed — is by construction not in
    // that set, and neither is an invented figure.
    const allowed = new Set<number>();
    for (const row of rail.rows) {
      allowed.add(Math.round(row.current * 100));
      allowed.add(Math.round(row.pregameMark * 100));
    }
    const percentages = (text.match(/\d+%/g) ?? []).map((p) => Number(p.replace("%", "")));
    expect(percentages.length).toBeGreaterThan(0);
    for (const p of percentages) expect([...allowed]).toContain(p);

    // And every number the BAR prints — the column a reader scans — is named.
    const named = text.match(/\d+% chance/g) ?? [];
    expect(named).toHaveLength(rail.rows.length * 2); // visible cell + aria-label
  });

  it("and on the settled rail, every number is inside a sentence", () => {
    const html = renderToStaticMarkup(
      React.createElement(PropDivergenceRail, { playerProps: DODGERS, status: "completed" }),
    );
    const text = renderedTokens(html).join(" ");
    for (const m of text.match(/\d+%/g) ?? []) {
      expect(text).toMatch(new RegExp(`marked ${m}`));
    }
  });
});
