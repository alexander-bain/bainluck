// UX-P269 (#2662) — /search renders four different questions as four identical rows.
//
// Market 59669267 is one Polymarket "market" whose four outcomes are four separate
// condition_ids, each named with the parent's full title plus a suffix. The card
// truncates from the right, so precisely the distinguishing text is what gets cut:
//
//     US Open WTA: Zeynep Sonmez vs Coco Gauff Set 1 O/U 8.5   ->  "US Open WTA: Zeynep Sonmez vs Coco Ga…"  52%
//     US Open WTA: Zeynep Sonmez vs Coco Gauff Set 1 Winner    ->  "US Open WTA: Zeynep Sonmez vs Coco Gau…" 15%
//     US Open WTA: Zeynep Sonmez vs Coco Gauff Set 2 Winner    ->  "US Open WTA: Zeynep Sonmez vs Coco Gau…" 14%
//     US Open WTA: Zeynep Sonmez vs Coco Gauff                 ->  "US Open WTA: Zeynep Sonmez vs Coco Gauff" 10%
//
// 🔴 THE FIXTURE IS THE LIVE PAYLOAD, VERBATIM. `parentPrefixOutcomes2662.json` is
// all ten markets carrying outcomes from `GET /api/events/search?q=Gauff`, captured
// 2026-09-02 while the defect was in production. One of the ten is the reported
// market; the other nine are controls, and two of them are the controls #2662 names
// by hand (`Set 1 Winner: Sonmez vs Gauff` and `Will Coco Gauff advance to the Round
// of 16…`), whose outcomes are NOT prefixed with their market name — which is
// exactly the discriminator the fix keys on.
//
// 🔴 WHY EVERY CLAIM IS AN EQUALITY ON AN EXTRACTED ROW LABEL, NEVER `toContain`.
// The broken label is `"US Open WTA: … Coco Gauff Set 1 Winner"`, which CONTAINS the
// string `"Set 1 Winner"`. So `expect(html).toContain("Set 1 Winner")` passes on the
// bug and on the fix — it asserts nothing. Worse, the card prints the market's own
// title in its heading, so a whole-document `toContain` of the parent name is true in
// both arms too. Every assertion below therefore pulls the row-label spans out of the
// markup and compares the WHOLE label. (Same family as ux/1011's singular/plural trap,
// where the singular is a substring of the plural.)
//
// 🔴 AND WHY A COUNTER-CASE ARM EXISTS. "Strip the parent name off every outcome" is
// not the ship. Two ways to get that wrong are pinned below and both are red on a
// naive implementation: a market where only SOME outcomes are prefixed must be left
// completely alone, and an outcome named EXACTLY the market name must keep its full
// name rather than becoming the empty string. The second is not an edge case — it is
// 354 of the 2,325 outcomes in the measured population, across 353 of the 375
// markets, so a fix without it would blank a row on 94% of the cards it touches.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FuturesMarket } from "@/lib/types";
import FuturesCard from "@/components/FuturesCard";
import { outcomeDisplayNames, stripParentPrefix } from "@/lib/outcomeLabels";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const FIXTURE = require("../fixtures/parentPrefixOutcomes2662.json") as Record<
  string,
  FuturesMarket
>;

/** The market #2662 reports. */
const DEFECT_ID = "59669267";
const PARENT = "US Open WTA: Zeynep Sonmez vs Coco Gauff";

/** The two controls named by hand in the issue body. */
const NAMED_CONTROL_IDS = ["59678644", "59556774"];

function market(id: string): FuturesMarket {
  const m = FIXTURE[id];
  if (!m) throw new Error(`fixture market ${id} missing — the capture changed`);
  return m;
}

/**
 * The outcome-row labels as a reader sees them.
 *
 * Anchored on `data-outcome-label`, NOT on the Tailwind classes. The first version
 * of this helper selected every `<span>` carrying `truncate` and silently picked up
 * the card's sport chip ("tennis") as if it were a fifth outcome — which made the
 * control arms red for a reason that had nothing to do with the ship. A class-based
 * selector is also hostage to a restyle; the data attribute names the intent.
 *
 * Reading the rendered span (rather than the whole document) is what stops these
 * assertions being satisfied by the market title printed in the card heading.
 */
function rowLabels(m: FuturesMarket): string[] {
  const html = renderToStaticMarkup(<FuturesCard market={m} />);
  const labels: string[] = [];
  const re = /<span data-outcome-label="true" class="[^"]*">([^<]*)<\/span>/g;
  let hit: RegExpExecArray | null;
  while ((hit = re.exec(html)) !== null) labels.push(decodeEntities(hit[1]));
  return labels;
}

/**
 * Decode the entities `renderToStaticMarkup` emits.
 *
 * ONE regex with a lookup map, deliberately — not a chain of `.replace()` calls.
 * A chain that unescapes `&amp;` before the numeric entities re-reads its own
 * output, so `&amp;#39;` wrongly yields `'`; CodeQL flags that as a HIGH
 * `js/double-escaping` and it is a real bug, not a style note (ux/1009's lesson #3,
 * which cost that session a whole CI cycle in a test helper exactly like this one).
 */
function decodeEntities(s: string): string {
  const MAP: Record<string, string> = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#x27;": "'",
    "&#39;": "'",
    "&#x2F;": "/",
  };
  return s.replace(/&(?:amp|lt|gt|quot|#x27|#39|#x2F);/g, (e) => MAP[e] ?? e);
}

// ───────────────────────────────────────────────────────────────────────────
// THE SHIP
// ───────────────────────────────────────────────────────────────────────────

describe("#2662 — the reported card's four rows read as four different questions", () => {
  it("renders the three suffixed outcomes as their suffix ALONE, not as the parent title", () => {
    const labels = rowLabels(market(DEFECT_ID));
    // Equality, not containment: the broken label contains all three of these.
    expect(labels).toEqual([
      "Set 1 O/U 8.5",
      "Set 1 Winner",
      "Set 2 Winner",
      PARENT,
    ]);
  });

  it("CONTROL (green on master too): the four labels stay four, and stay distinct as strings", () => {
    // Measured, not assumed: this one is GREEN IN BOTH ARMS. The raw names already
    // differ in their suffixes, so string-level distinctness is not what was broken —
    // the defect is that the difference sits past the truncation boundary, which is
    // the assertion two tests below. Kept anyway, and labelled, because it pins that
    // the fix neither drops a row nor merges two rows into one. Reporting it as a
    // ship claim would misrepresent what the red arm proves (ux/1012's lesson #6).
    const labels = rowLabels(market(DEFECT_ID));
    expect(labels).toHaveLength(4);
    expect(new Set(labels).size).toBe(4);
  });

  it("no longer prints the parent title on more than the one row that IS the parent", () => {
    const labels = rowLabels(market(DEFECT_ID));
    expect(labels.filter((l) => l.startsWith(PARENT))).toEqual([PARENT]);
  });

  it("CONTROL (green on master too): never renders an EMPTY row label — the bare-match outcome keeps its full name", () => {
    // Green in both arms by construction — master cannot produce an empty label
    // because it does not strip at all. This is the REGRESSION arm for the fix's own
    // worst failure mode: 353 of the 375 population markets contain an outcome named
    // exactly the market name, so a strip without the fallback blanks a row on 94% of
    // them. It goes red against a naive implementation, which is the arm it is for.
    const labels = rowLabels(market(DEFECT_ID));
    expect(labels.every((l) => l.trim().length > 0)).toBe(true);
    expect(labels).toContain(PARENT);
  });

  it("CONTROL (green on master too): keeps the rows in payload order, so the probabilities still line up with their questions", () => {
    // Green in both arms — master reorders nothing either. It is here because the
    // fix maps labels onto rows by INDEX, so an off-by-one or a sort would reattach
    // every probability to the wrong question while all the distinctness assertions
    // above still passed. The payload order is 51.5 / 15.0 / 13.5 / 9.5.
    const raw = (market(DEFECT_ID).top_outcomes ?? []).map((o) => o.name);
    const labels = rowLabels(market(DEFECT_ID));
    expect(labels).toHaveLength(raw.length);
    raw.forEach((name, i) => {
      expect(name.endsWith(labels[i]) || labels[i] === name).toBe(true);
    });
  });

  it("puts the distinguishing text where truncation cannot reach it", () => {
    // The user-visible complaint restated as a measurement: on master every label
    // shares a 38-character prefix, so a right-truncating column shows one string
    // four times. After the fix no two labels share their first 38 characters.
    const labels = rowLabels(market(DEFECT_ID));
    const visible = labels.map((l) => l.slice(0, 38));
    expect(new Set(visible).size).toBe(labels.length);
  });

  it("labels the accessible progressbar with the same distinguishing text", () => {
    // A screen reader hears four identical strings on master too. The aria-label is
    // built from the same value, so it must move with the visible label.
    const html = renderToStaticMarkup(<FuturesCard market={market(DEFECT_ID)} />);
    expect(html).toContain('aria-label="Set 1 Winner probability"');
    expect(html).toContain('aria-label="Set 2 Winner probability"');
    expect(html).toContain('aria-label="Set 1 O/U 8.5 probability"');
  });
});

// ───────────────────────────────────────────────────────────────────────────
// CONTROLS — GREEN IN BOTH ARMS BY DESIGN
// ───────────────────────────────────────────────────────────────────────────

describe("#2662 controls — every market outside the population renders byte-identically", () => {
  const controlIds = Object.keys(FIXTURE).filter((id) => id !== DEFECT_ID);

  it("has nine controls, so this is not a one-example claim", () => {
    expect(controlIds).toHaveLength(9);
  });

  it.each(controlIds)("market %s renders its outcome names verbatim", (id) => {
    const m = market(id);
    const raw = (m.top_outcomes ?? []).map((o) => o.name);
    expect(rowLabels(m)).toEqual(raw);
  });

  it.each(NAMED_CONTROL_IDS)(
    "the control #2662 names by hand (%s) is untouched, and for the stated reason",
    (id) => {
      const m = market(id);
      const raw = (m.top_outcomes ?? []).map((o) => o.name);
      // The discriminator the issue identifies: these outcomes are NOT prefixed with
      // their market name. Assert the discriminator itself, not just the outcome —
      // otherwise this passes for the wrong reason if the fixture ever drifts.
      expect(raw.every((n) => n.startsWith(m.name))).toBe(false);
      expect(rowLabels(m)).toEqual(raw);
    },
  );
});

// ───────────────────────────────────────────────────────────────────────────
// THE RULE ITSELF
// ───────────────────────────────────────────────────────────────────────────

describe("outcomeDisplayNames — the per-row prefix rule (#2662, gate reversed by #3538)", () => {
  it("strips when EVERY name is prefixed", () => {
    expect(outcomeDisplayNames("Match", ["Match Set 1", "Match Set 2"])).toEqual([
      "Set 1",
      "Set 2",
    ]);
  });

  // ── REVERSED BY #3538 (ux/1097), deliberately, with the measurement below ──
  //
  // 🔴 This assertion used to read `toEqual(names)` — leave a partly-prefixed market
  // completely alone — on the reasoning that "a partial strip makes rows less
  // comparable, not more". That reasoning was never measured: #2662's population was
  // defined by a HAVING clause that admits only all-prefixed markets, so the partial
  // case was not in the data behind it.
  //
  // It is the larger half of the defect. Measured over every open market resolving in
  // the next 7 days (`POST /api/admin/db-query`, 2026-09-06):
  //
  //     all-prefixed  (this file's original population)   238 markets /  1,348 outcomes
  //     PARTLY prefixed (refused by the old gate)         446 markets /  2,216 outcomes
  //
  // and over those 446, applying the per-row rule: **0 lose label distinctness**, and
  // 15 contain a row that strips to "" — already covered by the `|| name` fallback
  // this file's next test pins.
  //
  // The rendered case that forced it: `/hub/tennis` drew four different prices under
  // four identical `US Open ATP: Karen Khacha…` labels, and the gate was what withheld
  // the fix, because a tenth outcome on that card is the unprefixed match-winner leg
  // `Karen Khachanov`. 0 of the 4 affected hub cards were all-prefixed.
  //
  // The case is KEPT, not deleted, because the property that matters is unchanged and
  // is what the next line asserts: the UNPREFIXED row is still returned untouched.
  it("strips the prefixed rows and leaves the unprefixed ones exactly as served", () => {
    expect(outcomeDisplayNames("Match", ["Match Set 1", "Somebody Else"])).toEqual([
      "Set 1",
      "Somebody Else",
    ]);
  });

  it("🔴 the real match-winner leg survives beside its prefixed siblings", () => {
    // The production shape from `/hub/tennis` in miniature, and the reason the gate
    // could not simply be kept: strip nothing and the card is unreadable, strip the
    // unprefixed row too and a genuine outcome name is destroyed.
    expect(
      outcomeDisplayNames("US Open ATP: Karen Khachanov vs Learner Tien", [
        "US Open ATP: Karen Khachanov vs Learner Tien Total Sets: O/U 3.5",
        "US Open ATP: Karen Khachanov vs Learner Tien Set 1 Winner",
        "Karen Khachanov",
      ]),
    ).toEqual(["Total Sets: O/U 3.5", "Set 1 Winner", "Karen Khachanov"]);
  });

  it("COUNTER-CASE: an outcome named exactly the market name keeps its full name", () => {
    // 354 of 2,325 outcomes in the measured population, across 353 of 375 markets.
    // Returning "" here would blank a row on 94% of the cards this touches.
    expect(outcomeDisplayNames("Match", ["Match", "Match Set 1"])).toEqual([
      "Match",
      "Set 1",
    ]);
  });

  it("is a no-op on a single-outcome market — there is nothing to disambiguate", () => {
    expect(outcomeDisplayNames("Match", ["Match Set 1"])).toEqual(["Match Set 1"]);
  });

  it("is a no-op when the market name is empty, null or undefined", () => {
    // An empty parent would make `startsWith` vacuously true for every string and
    // strip nothing while claiming to have fired.
    const names = ["Alpha", "Beta"];
    expect(outcomeDisplayNames("", names)).toEqual(names);
    expect(outcomeDisplayNames(null, names)).toEqual(names);
    expect(outcomeDisplayNames(undefined, names)).toEqual(names);
  });

  it("trims the separator the data actually uses, and only that", () => {
    // Measured across all 2,325 population outcomes: the separator is a single space
    // (1,971) or nothing (354). No colons, no dashes. An internal colon must survive
    // — "Total Sets: O/U 2.5" is a real label in the population.
    expect(outcomeDisplayNames("M", ["M Total Sets: O/U 2.5", "M Set 1 Winner"])).toEqual([
      "Total Sets: O/U 2.5",
      "Set 1 Winner",
    ]);
  });

  it("returns one label per input, in order, always", () => {
    const names = ["M a", "M b", "M c", "M d", "M e"];
    expect(outcomeDisplayNames("M", names)).toEqual(["a", "b", "c", "d", "e"]);
    expect(outcomeDisplayNames("M", names)).toHaveLength(names.length);
  });

  it("does not mutate its input", () => {
    const names = ["M a", "M b"];
    const copy = [...names];
    outcomeDisplayNames("M", names);
    expect(names).toEqual(copy);
  });

  it("creates no duplicate label that the raw names did not already have", () => {
    // Measured: 64 of the 375 markets carry outcomes whose FULL names are already
    // byte-identical upstream. Stripping must not add to that count — verified over
    // all 375 markets, 0 new duplicates.
    const raw = ["M Set Handicap +/-1.5", "M Set Handicap +/-1.5", "M Set 1 Winner"];
    const out = outcomeDisplayNames("M", raw);
    const dupsBefore = raw.length - new Set(raw).size;
    const dupsAfter = out.length - new Set(out).size;
    expect(dupsAfter).toBe(dupsBefore);
  });

  it("is case-sensitive, mirroring the SQL LIKE that defines the population", () => {
    // 🔴 REWRITTEN BY #3538, and the rewrite makes it a stronger test than it was.
    // It used to expect BOTH names back unchanged — but under the old all-or-nothing
    // gate that happened because one name was unprefixed, so the market was skipped
    // wholesale. Case sensitivity was never what the assertion exercised; the gate
    // was. Now the two rows are judged independently, so the lowercase row coming
    // back untouched WHILE its exact-case sibling strips is a direct reading of the
    // property this test is named for.
    expect(outcomeDisplayNames("Match", ["match Set 1", "Match Set 2"])).toEqual([
      "match Set 1",
      "Set 2",
    ]);
  });
});

describe("stripParentPrefix — the single-row form", () => {
  it("strips a prefixed name", () => {
    expect(stripParentPrefix("Match", "Match Set 1")).toBe("Set 1");
  });

  it("keeps a name that is exactly the parent", () => {
    expect(stripParentPrefix("Match", "Match")).toBe("Match");
  });

  it("leaves an unprefixed name alone", () => {
    expect(stripParentPrefix("Match", "Somebody Else")).toBe("Somebody Else");
  });
});

// ───────────────────────────────────────────────────────────────────────────
// THE POPULATION, REPLAYED
// ───────────────────────────────────────────────────────────────────────────

describe("#2662 — the fixture reproduces the measured population predicate", () => {
  it("exactly one of the ten captured markets is in the population", () => {
    // If the capture ever drifts so that zero markets qualify, every ship assertion
    // above would still pass while proving nothing. This is the seed-is-real check.
    const inPopulation = Object.values(FIXTURE).filter((m) => {
      const names = (m.top_outcomes ?? []).map((o) => o.name);
      return names.length >= 2 && names.every((n) => n.startsWith(m.name));
    });
    expect(inPopulation.map((m) => String(m.id))).toEqual([DEFECT_ID]);
  });

  it("CONTROL: the reported market really does ship four outcomes all named with the parent title", () => {
    const m = market(DEFECT_ID);
    const names = (m.top_outcomes ?? []).map((o) => o.name);
    expect(names).toHaveLength(4);
    expect(names.every((n) => n.startsWith(PARENT))).toBe(true);
    // And the defect restated: on the raw names, the first 38 characters are the
    // same string four times over. This is the "before" the ship removes.
    expect(new Set(names.map((n) => n.slice(0, 38))).size).toBe(1);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// THE WHOLE MEASURED POPULATION, THROUGH THE REAL FUNCTION
// ───────────────────────────────────────────────────────────────────────────
//
// `parentPrefixPopulation2662.json` is every market matching the population's own
// HAVING clause, pulled from production 2026-09-02: 375 markets / 2,325 outcomes,
// all polymarket, all tier 5. The numbers asserted below are the ones quoted in the
// commit message and the cert, and they are asserted by running the SHIPPED
// `outcomeDisplayNames` over the real names — not a reimplementation of it in the
// test, and not a Python script whose behaviour could drift from the TypeScript
// (ux/1015's lesson #3: exec the real function, do not re-derive it from reading).

// eslint-disable-next-line @typescript-eslint/no-var-requires
const POPULATION = require("../fixtures/parentPrefixPopulation2662.json") as Array<{
  id: number;
  name: string;
  outcomes: string[];
}>;

describe("#2662 — the shipped rule, replayed over all 375 production markets", () => {
  it("the corpus is the population it claims to be", () => {
    expect(POPULATION).toHaveLength(375);
    expect(POPULATION.reduce((n, m) => n + m.outcomes.length, 0)).toBe(2325);
    // Every market really does satisfy the HAVING clause. If this ever fails the
    // corpus has drifted and every count below is measuring something else.
    expect(
      POPULATION.every(
        (m) => m.outcomes.length >= 2 && m.outcomes.every((o) => o.startsWith(m.name)),
      ),
    ).toBe(true);
  });

  it("changes at least one label on 374 of the 375 — and correctly changes nothing on the 1 it cannot help", () => {
    // I asserted "all 375" first and the run corrected me, which is the point of
    // running your own test before believing your own expected numbers. Market
    // 59586279 ("Delhi Premier League: Purani Dilli 6 vs Outer Delhi Warriors") has
    // TWO outcomes and both are named exactly the market name — there is no suffix
    // to recover, so both keep their full name and the card still shows one string
    // twice. That is not a renderer defect and this fix does not claim it: it is the
    // data half of #2662 (four condition_ids should be four markets), which is
    // explicitly out of scope. Pinned here so the limitation is a measured 1, not an
    // unstated exception.
    const untouched = POPULATION.filter((m) => {
      const out = outcomeDisplayNames(m.name, m.outcomes);
      return out.every((label, i) => label === m.outcomes[i]);
    });
    expect(untouched.map((m) => m.id)).toEqual([59586279]);
    expect(untouched[0].outcomes.every((o) => o === untouched[0].name)).toBe(true);
    expect(POPULATION.length - untouched.length).toBe(374);
  });

  it("never produces an empty label — 354 outcomes across 353 markets strip to nothing", () => {
    const emptied = POPULATION.flatMap((m) =>
      outcomeDisplayNames(m.name, m.outcomes).filter((l) => l.trim() === ""),
    );
    expect(emptied).toEqual([]);
    // And the fallback really is load-bearing at that scale: count the outcomes
    // named exactly the market name, which are the ones it catches.
    const exact = POPULATION.flatMap((m) => m.outcomes.filter((o) => o === m.name));
    expect(exact).toHaveLength(354);
    expect(POPULATION.filter((m) => m.outcomes.some((o) => o === m.name))).toHaveLength(353);
  });

  it("creates ZERO new duplicate labels across the whole population", () => {
    // 64 markets already carry byte-identical duplicate outcome names upstream. The
    // strip must not add to that on any market — this is the property that makes it
    // safe, and it is checked on all 375 rather than argued.
    const worse = POPULATION.filter((m) => {
      const out = outcomeDisplayNames(m.name, m.outcomes);
      const before = m.outcomes.length - new Set(m.outcomes).size;
      const after = out.length - new Set(out).size;
      return after > before;
    });
    expect(worse).toEqual([]);
    expect(
      POPULATION.filter((m) => m.outcomes.length !== new Set(m.outcomes).size),
    ).toHaveLength(64);
  });

  it("keeps one label per outcome, in order, on all 375", () => {
    const wrongShape = POPULATION.filter(
      (m) => outcomeDisplayNames(m.name, m.outcomes).length !== m.outcomes.length,
    );
    expect(wrongShape).toEqual([]);
  });

  it("takes 335 markets from 'every row looks identical' to 'rows a reader can tell apart'", () => {
    // The ship, counted. A row label is truncated by the column, so what a reader
    // compares is the leading text; on these 335 markets that leading text was one
    // string repeated down the card.
    const VISIBLE = 38;
    const fixed = POPULATION.filter((m) => {
      const before = new Set(m.outcomes.map((o) => o.slice(0, VISIBLE))).size;
      const after = new Set(
        outcomeDisplayNames(m.name, m.outcomes).map((l) => l.slice(0, VISIBLE)),
      ).size;
      return before === 1 && after > 1;
    });
    expect(fixed).toHaveLength(335);
  });
});
