/**
 * #6816 — a fight's two displayed percentages agree, on the page a reader opens.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/event/ufc/331-van-vs-pantoja-26sep19`, production 2026-09-17:
 *
 *     Arman Tsarukyan   74%
 *     Mauricio Ruffy    28%      <- 102%
 *
 * ═══ WHAT THIS FILE EXECUTES ═══
 *
 * The two REAL renderers of a UFC card's numbers — `MatchupsRail` (the bout rail) and
 * `TwoSidedTimeline` (the main-event hero) — through `formatProbability`, over two payloads:
 *
 *   SAVED   `eventConceptUfc26sep19.native209.20260917.json` — the public response, byte for
 *           byte (sha256 2ba8d8cb…), captured by Native209. HISTORICAL evidence, not a fresh
 *           production read. It carries no `rendered_percent`.
 *   SERVED  `eventConceptUfc26sep19.served6816.SYNTHETIC.json` — the patched combat builder's
 *           OWN output for those same names and quotes. SYNTHETIC: the rows that drove the
 *           builder are invented (see `backend/tests/test_combat_pair_display_6816.py`, which
 *           pins this file to the builder byte for byte). Nobody typed these integers.
 *
 * The SAVED arm is the defect reproduced through the actual consumer, and doubles as the
 * old-payload guarantee: a cached envelope from before the field shipped prints exactly what
 * it printed. The SERVED arm is the ship. On the unpatched renderers the SERVED arm is RED —
 * a server field the clients ignore is not a fix — which is the call-site control recorded in
 * GATES.md.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("swr", () => ({ __esModule: true, default: () => ({ data: undefined }) }));
jest.mock("@/components/FuturesChart", () => ({ __esModule: true, FuturesChart: () => null }));
jest.mock("../../components/event/FighterAvatar", () => ({
  __esModule: true,
  default: () => null,
}));

import MatchupsRail from "../../components/event/MatchupsRail";
import TwoSidedTimeline from "../../components/event/TwoSidedTimeline";
import { formatProbability } from "../../lib/api";
import { renderedDuelPercents, renderedPercent } from "../../lib/renderedPercent";
import { servedBoutPercents } from "../../lib/servedBoutPercents";
import type { EventConceptChild, EventConceptCompetitor } from "../../lib/types";
import saved from "../fixtures/eventConceptUfc26sep19.native209.20260917.json";
import served from "../fixtures/eventConceptUfc26sep19.served6816.SYNTHETIC.json";

type Payload = { children: EventConceptChild[]; primary: { competitors: EventConceptCompetitor[] } };

const fightsOf = (payload: Payload) => payload.children.filter((c) => c.kind === "fight");

/** Every printed percentage in a card, in DOM order. */
function printed(html: string): string[] {
  // Static markup escapes the boundary markers, so they are matched escaped.
  return Array.from(html.matchAll(/>\s*((?:&lt;|&gt;)?\d{1,3}%)\s*</g)).map((m) =>
    m[1].replace("&lt;", "<").replace("&gt;", ">"),
  );
}

function railNumbers(child: EventConceptChild): string[] {
  return printed(renderToStaticMarkup(<MatchupsRail items={[child]} sport="ufc" />));
}

function heroNumbers(competitors: EventConceptCompetitor[]): string[] {
  return printed(
    renderToStaticMarkup(
      <TwoSidedTimeline competitors={competitors} label="Main event" evolutionMarketId={null} />,
    ),
  );
}

const childNamed = (payload: Payload, name: string) =>
  fightsOf(payload).find((c) => c.market_name === name) as EventConceptChild;

const total = (numbers: string[]) => numbers.reduce((sum, n) => sum + parseInt(n, 10), 0);

const NAMED: Array<[string, string[], string[]]> = [
  ["331: Tsarukyan vs Ruffy", ["74%", "28%"], ["73%", "27%"]],
  ["331: Chikadze vs Brito", ["79%", "23%"], ["78%", "22%"]],
  ["331: Pitbull vs Choi", ["73%", "29%"], ["72%", "28%"]],
  ["331: Aswell vs Yoo", ["67%", "33%"], ["67%", "33%"]],
];

describe("#6816 — the bout rail", () => {
  test.each(NAMED)("SAVED payload, %s: the rail prints what the reader saw", (name, saw) => {
    expect(railNumbers(childNamed(saved as Payload, name))).toEqual(saw);
  });

  test("SAVED payload: Tsarukyan / Ruffy really does add up to 102 on screen", () => {
    expect(total(railNumbers(childNamed(saved as Payload, "331: Tsarukyan vs Ruffy")))).toBe(102);
  });

  test.each(NAMED)("🔴 SERVED payload, %s: the rail prints a pair that agrees", (name, _saw, now) => {
    const numbers = railNumbers(childNamed(served as Payload, name));
    expect(numbers).toEqual(now);
    expect(total(numbers)).toBe(100);
  });

  test("SERVED payload: every one of the twelve bouts prints 100; SAVED printed 100 on one", () => {
    const sums = (payload: Payload) => fightsOf(payload).map((c) => total(railNumbers(c)));
    expect(sums(served as Payload)).toEqual(Array(12).fill(100));
    expect(sums(saved as Payload).filter((s) => s === 100)).toHaveLength(1);
  });

  test("the prop on the same card is untouched: no field, no pairing, same render", () => {
    const prop = (payload: Payload) =>
      payload.children.find((c) => c.kind === "prop") as EventConceptChild;
    expect(prop(served as Payload).outcomes?.every((o) => !("rendered_percent" in o))).toBe(true);
    expect(renderToStaticMarkup(<MatchupsRail items={[prop(served as Payload)]} />)).toBe(
      renderToStaticMarkup(<MatchupsRail items={[prop(saved as Payload)]} />),
    );
  });
});

describe("#6816 — the main-event hero", () => {
  /* 🔴 THE HERO'S "BEFORE" MOVED UNDER THIS FILE, AND THE CONTROL FOLLOWS IT.
     Brief 22A was written against a master where the hero rounded each side on
     its own — 0.565 / 0.435 printed 57 / 44. ux's #6844 (`6ef991e04`, merged
     2026-09-18 ~02:5xZ) then gave THIS component a LOCAL pairing
     (`renderedDuelPercents`), so on current master the hero already prints
     57 / 43 with no served field at all. Verified on production the same night:
     `/event/ufc/331-van-vs-pantoja-26sep19` at 390px reads `57%` / `43%` over a
     payload of 0.565 / 0.435 carrying no `rendered_percent`
     (`artifacts-discover/6816-look/BEFORE-ufc-331-390.png`).

     So "as before" now MEANS #6844's pair, and these assertions say so. What
     #6816 must prove here is narrower and still worth pinning: the served value
     takes precedence when the builder made a claim, and when it did not, #6844's
     number is still the one on the screen — #6816 removes nothing ux put there.
     The rail (`MatchupsRail`) never had a local pairing, which is why every
     assertion in the block above is unaffected. */
  test("the hero's own baseline is #6844's local pair, not two independent roundings", () => {
    expect(heroNumbers((saved as Payload).primary.competitors)).toEqual(["57%", "43%"]);
  });

  test("🔴 SERVED payload: the hero prints 57 / 43, the same pair as its rail row", () => {
    const hero = heroNumbers((served as Payload).primary.competitors);
    expect(hero).toEqual(["57%", "43%"]);
    expect(hero).toEqual(railNumbers(childNamed(served as Payload, "331: Van vs Pantoja")));
  });

  test("stored order cannot put a number on the wrong fighter", () => {
    const reversed = [...(served as Payload).primary.competitors].reverse();
    expect(heroNumbers(reversed)).toEqual(["57%", "43%"]);
  });

  test("the top two of a LONGER field are never treated as a pair, served OR local", () => {
    /* #6816's own arity rule: three rows are not a bout, so `servedBoutPercents`
       makes no claim and the served 73 / 27 is not used.

       WHAT PRINTS INSTEAD CHANGED — this asserted 73 / 27 (#6844's local pairing)
       until #6991. The note routed to ux here was right that `renderedDuelPercents`
       ran on the top two of a longer field; it was WRONG that the case is
       unreachable. `co_equal_list` is emitted by `event_awards` and
       `event_election` as well as `event_combat`, and the page renders the hero on
       `isCoEqual` alone, so a five-nominee category reached it: production
       2026-09-18 printed `Schmigadoon! >99%` on `/event/awards/tonys-2026` over a
       quote of exactly 0.99. #6991 fences the local arm on the SAME predicate this
       test's subject already uses, so a longer field now prints each value on its
       own — 74 / 28 here, which no longer claims to be a sum. */
    const field = [
      { name: "A", probability: 0.735, rendered_percent: 73 },
      { name: "B", probability: 0.275, rendered_percent: 27 },
      { name: "C", probability: 0.01, rendered_percent: 1 },
    ] as EventConceptCompetitor[];
    expect(servedBoutPercents(field)).toEqual([null, null, null]);
    expect(heroNumbers(field)).toEqual(["74%", "28%"]);
  });
});

describe("#6816 — both served or neither", () => {
  const row = (probability: number | null, rendered_percent?: unknown) =>
    ({ name: "x", probability, rendered_percent }) as EventConceptCompetitor;

  test.each([
    ["one side missing", [row(0.735, 73), row(0.275)]],
    ["one side null", [row(0.735, 73), row(0.275, null)]],
    ["a fraction", [row(0.735, 72.5), row(0.275, 27.5)]],
    ["a string", [row(0.735, "73"), row(0.275, "27")]],
    ["out of range", [row(0.735, 173), row(0.275, -73)]],
    ["NaN", [row(0.735, Number.NaN), row(0.275, 27)]],
    ["both null — the server's own 'no claim'", [row(0.735, null), row(0.275, null)]],
  ])("%s: NEITHER served value is used, and the pair prints as before", (_label, rows) => {
    expect(servedBoutPercents(rows)).toEqual([null, null]);
    // "As before" on THIS surface is #6844's local pair (see the block above),
    // which #6816 falls back to whole rather than replacing.
    expect(heroNumbers(rows)).toEqual(["73%", "27%"]);
  });

  test("arity other than two is no claim, whatever the rows carry", () => {
    expect(servedBoutPercents([row(1, 100)])).toEqual([null]);
    expect(servedBoutPercents(null)).toEqual([]);
    expect(servedBoutPercents([row(0.5, 50), row(0.3, 30), row(0.2, 20)])).toEqual([null, null, null]);
  });

  test("a withheld bout stays withheld: a served integer never prints over a null price", () => {
    // Not a shape the builder emits — it serves null beside null — pinned anyway,
    // because "no complement may resurrect a refused leg" must not depend on that.
    expect(heroNumbers([row(null, 73), row(null, 27)])).toEqual([]);
  });
});

describe("#6816 — what was deliberately left alone", () => {
  test("the <1% / >99% boundary rule still runs on the PROBABILITY", () => {
    const pair = [
      { name: "A", probability: 0.995, rendered_percent: 100 },
      { name: "B", probability: 0.005, rendered_percent: 0 },
    ] as EventConceptCompetitor[];
    expect(heroNumbers(pair)).toEqual([">99%", "<1%"]);
  });

  test("a genuinely settled 1 / 0 prints the result, and a real 50 / 50 stays 50 / 50", () => {
    expect(
      heroNumbers([
        { name: "A", probability: 1, rendered_percent: 100 },
        { name: "B", probability: 0, rendered_percent: 0 },
      ] as EventConceptCompetitor[]),
    ).toEqual(["100%", "0%"]);
    expect(
      heroNumbers([
        { name: "A", probability: 0.5, rendered_percent: 50 },
        { name: "B", probability: 0.5, rendered_percent: 50 },
      ] as EventConceptCompetitor[]),
    ).toEqual(["50%", "50%"]);
  });

  test("the served integers ARE the shared contract's — Python and TypeScript agree on all 12", () => {
    for (const child of fightsOf(served as Payload)) {
      const [a, b] = child.outcomes ?? [];
      expect([a.rendered_percent, b.rendered_percent]).toEqual(
        renderedDuelPercents(a.probability, b.probability),
      );
    }
  });

  test("no probability moved: SERVED differs from SAVED by the new field and nothing else", () => {
    const strip = (payload: Payload) =>
      payload.children.map((c) => ({
        ...c,
        outcomes: c.outcomes?.map(({ rendered_percent: _dropped, ...rest }) => rest),
      }));
    expect(strip(served as Payload)).toEqual(strip(saved as Payload));
  });

  test("an independent formatter still reads each quote the way it always did", () => {
    expect(formatProbability(0.735)).toBe("74%");
    expect(renderedPercent(0.275)).toBe(28);
  });
});
