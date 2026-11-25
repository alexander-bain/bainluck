// /guess — THE LINE AFTER A CARD IS ABOUT THE FARTHEST PERSON, OR SOMEONE DEAD ON.
//
// Three rounds of playtesting, in the tester's words: "Roast the person who's
// furthest away or closest. A bunch of times it seemed random who was chosen."
// This file is that sentence as tests. A line never names anyone in between,
// never names whoever is merely leading, and reads correctly for one name or
// several.

import { coinEntry, emptyEntry, ORDER_PERMS, pointsFor } from "@/lib/guess/engine";
import { GUESS_PACK as pack } from "@/lib/guess/pack";
import { fillLine, isEventLine, pickBadness, roastFor, roastHistory, sayNames } from "@/lib/guess/roast";
import type { PackCard, PlayerEntry } from "@/lib/guess/types";

const indexOfKind = (kind: PackCard["kind"], n = 0) =>
  pack.cards.map((c, i) => (c.kind === kind ? i : -1)).filter((i) => i >= 0)[n];

function person(name: string, guesses: Record<number, number>): PlayerEntry {
  const entry = emptyEntry(pack, name, "here");
  Object.entries(guesses).forEach(([i, g]) => {
    entry.guesses[Number(i)] = g;
  });
  return entry;
}

describe("/guess — who the line is about", () => {
  const i = pack.cards.findIndex((c) => c.kind === "chance" && c.answer <= 20);
  const card = pack.cards[i] as Extract<PackCard, { kind: "chance" }>;

  it("on a slider card, names only the farthest person", () => {
    const near = person("Near", { [i]: card.answer + 4 });
    const mid = person("Mid", { [i]: card.answer + 15 });
    const far = person("Far", { [i]: card.answer + 40 });
    for (const order of [
      [near, mid, far],
      [far, near, mid],
      [mid, far, near],
    ]) {
      const line = roastFor(pack, i, order, null, false);
      expect(line?.rule).toBe("far");
      expect(line?.names).toEqual(["Far"]);
      expect(line?.text).toContain("Far");
      expect(line?.text).not.toContain("Mid");
      expect(line?.text).not.toContain("Near");
    }
  });

  it("someone dead on gets the line instead, unless somebody else missed by 30 or more", () => {
    const exact = person("Exact", { [i]: card.answer });
    const off = person("Off", { [i]: card.answer + 18 });
    const howler = person("Howler", { [i]: card.answer + 45 });
    const quiet = roastFor(pack, i, [off, exact], null, false);
    expect(quiet?.rule).toBe("exact");
    expect(quiet?.names).toEqual(["Exact"]);
    const loud = roastFor(pack, i, [exact, howler], null, false);
    expect(loud?.rule).toBe("far");
    expect(loud?.names).toEqual(["Howler"]);
  });

  it("says nothing about a card where nobody was far and nobody was dead on", () => {
    const a = person("A", { [i]: card.answer + 3 });
    const b = person("B", { [i]: card.answer + 6 });
    expect(roastFor(pack, i, [a, b], null, true)).toBeNull();
  });

  it("names two people together only when they made the very same worst guess", () => {
    const a = person("Ann", { [i]: card.answer + 30 });
    const b = person("Bo", { [i]: card.answer + 30 });
    const c = person("Cy", { [i]: card.answer + 5 });
    const line = roastFor(pack, i, [a, b, c], null, false);
    expect(line?.names).toEqual(["Ann", "Bo"]);
    expect(line?.text).toContain("Ann and Bo");
    expect(line?.text).not.toMatch(/Ann and Bo (has|is|was|trusts)\b/);
  });

  it("on a pick card, names everyone who made the worst pick and nobody who was right", () => {
    for (let k = 0; k < pack.cards.length; k += 1) {
      const c = pack.cards[k];
      if (c.kind !== "pick" && c.kind !== "ladder") continue;
      const wrong = c.options.map((_, o) => o).filter((o) => o !== c.answer);
      const worst = wrong.reduce((a, b) => (pickBadness(c, b) > pickBadness(c, a) ? b : a));
      const right = person("Right", { [k]: c.answer });
      const bad1 = person("BadOne", { [k]: worst });
      const bad2 = person("BadTwo", { [k]: worst });
      const line = roastFor(pack, k, [right, bad1, bad2], null, false);
      expect(line?.rule).toBe("wrong");
      expect(line?.names).toEqual(["BadOne", "BadTwo"]);
      expect(line?.text).not.toContain("Right");
      expect(line?.text).not.toMatch(/\{\w+\}/);
      // Everyone right: the card has nothing to say.
      expect(roastFor(pack, k, [right, person("AlsoRight", { [k]: c.answer })], null, true)).toBeNull();
    }
  });

  it("on an order card, names whoever had the fewest pairs right", () => {
    const k = indexOfKind("order");
    const c = pack.cards[k];
    const best = ORDER_PERMS.findIndex((_, g) => pointsFor(c, g) === 20);
    const worst = ORDER_PERMS.findIndex((_, g) => pointsFor(c, g) === 0);
    const line = roastFor(pack, k, [person("Good", { [k]: best }), person("Lost", { [k]: worst })], null, false);
    expect(line?.names).toEqual(["Lost"]);
    expect(roastFor(pack, k, [person("Good", { [k]: best })], null, true)).toBeNull();
  });

  it("every card's own line fills completely, for one name and for several, in both directions", () => {
    pack.cards.forEach((c, k) => {
      const tries: number[] =
        c.kind === "chance"
          ? [0, 100]
          : c.kind === "count"
            ? [0, c.max]
            : c.kind === "order"
              ? ORDER_PERMS.map((_, g) => g)
              : c.options.map((_, o) => o);
      for (const g of tries) {
        for (const names of [["Ann"], ["Ann", "Bo"]]) {
          const people = names.map((n) => person(n, { [k]: g }));
          const line = roastFor(pack, k, people, null, true);
          if (!line) continue;
          expect(line.text).not.toMatch(/\{\w+\}/);
          expect(line.text).not.toMatch(/undefined|NaN|null/);
          expect(line.text).not.toMatch(/Ann and Bo (has|is|was)\b/);
          expect(line.text.length).toBeLessThan(200);
        }
      }
    });
  });
});

describe("/guess — playing alone, and the lines about the whole table", () => {
  const coin = coinEntry(pack);

  it("alone, the farthest person is you", () => {
    const i = pack.cards.findIndex((c) => c.kind === "chance" && c.answer <= 20);
    const line = roastFor(pack, i, [person("Solo", { [i]: 80 })], coin, false);
    expect(line?.names).toEqual(["Solo"]);
  });

  it("the Coin gets a line when it beats everyone by five or more, and is never itself the target", () => {
    const i = pack.cards.findIndex((c) => c.kind === "chance" && Math.abs(c.answer - 50) <= 3);
    expect(i).toBeGreaterThanOrEqual(0);
    const answer = (pack.cards[i] as Extract<PackCard, { kind: "chance" }>).answer;
    const solo = person("Solo", { [i]: answer + 8 });
    const line = roastFor(pack, i, [solo], coin, false);
    expect(line?.rule).toBe("coin");
    expect(line?.text).toContain("Solo");
    for (let k = 0; k < pack.cards.length; k += 1) {
      const any = roastFor(pack, k, [coin], coin, false);
      expect(any).toBeNull();
    }
  });

  it("says so when the whole table was too high, and never shows two table lines in a row", () => {
    const i = pack.cards.findIndex((c) => c.kind === "chance" && c.answer <= 20);
    const answer = (pack.cards[i] as Extract<PackCard, { kind: "chance" }>).answer;
    const a = person("A", { [i]: answer + 6 });
    const b = person("B", { [i]: answer + 8 });
    const line = roastFor(pack, i, [a, b], null, false);
    expect(line?.rule).toBe("allhigh");
    expect(isEventLine(line)).toBe(true);
    expect(roastFor(pack, i, [a, b], null, true)).toBeNull();
  });

  it("rebuilds the same lines on any phone from the guesses alone", () => {
    const everything = (name: string, shift: number) => {
      const entry = emptyEntry(pack, name, "here");
      entry.guesses = pack.cards.map((c) => {
        if (c.kind === "chance") return Math.min(100, c.answer + shift);
        if (c.kind === "count") return Math.min(c.max, c.answer + 1);
        if (c.kind === "order") return 0;
        return 0;
      });
      return entry;
    };
    const people = [everything("A", 12), everything("B", 31)];
    const first = roastHistory(pack, pack.cards.length - 1, people, null);
    expect(first.length).toBe(pack.cards.length);
    expect(roastHistory(pack, pack.cards.length - 1, people, null)).toEqual(first);
    for (let k = 1; k < first.length; k += 1) {
      expect(isEventLine(first[k]) && isEventLine(first[k - 1])).toBe(false);
    }
  });

  it("fills singular and plural forms", () => {
    expect(fillLine("{n} {has} it. {n} trust{s} nobody. {n} {is} here, {n} {was} there.", ["Ann"])).toBe(
      "Ann has it. Ann trusts nobody. Ann is here, Ann was there.",
    );
    expect(fillLine("{n} {has} it. {n} trust{s} nobody. {n} {is} here, {n} {was} there.", ["Ann", "Bo"])).toBe(
      "Ann and Bo have it. Ann and Bo trust nobody. Ann and Bo are here, Ann and Bo were there.",
    );
    expect(fillLine("{n} said {g}%. {mystery}", ["Ann"], { g: 40 })).toBe("Ann said 40%. {mystery}");
  });

  it("does not read out a whole table of names", () => {
    expect(sayNames(["Ann", "Bo", "Cy"], false)).toBe("Ann, Bo and Cy");
    expect(sayNames(["Ann", "Bo", "Cy", "Di", "Ed"], false)).toBe("Ann, Bo and 3 others");
    expect(sayNames(["Ann", "Bo", "Cy"], true)).toBe("all of you");
    expect(sayNames(["Ann", "Bo"], true)).toBe("Ann and Bo");
    expect(fillLine("{n} {was} wrong. Nobody blames {n}. Dead on, {n}.", ["A", "B", "C"], {}, true)).toBe(
      "All of you were wrong. Nobody blames all of you. Dead on, all of you.",
    );
    const k = pack.cards.findIndex((c) => c.kind === "pick" && c.flavor === "pair");
    const c = pack.cards[k] as Extract<PackCard, { kind: "pick" }>;
    const wrong = c.answer === 0 ? 1 : 0;
    const table = ["A", "B", "C", "D"].map((n) => person(n, { [k]: wrong }));
    expect(roastFor(pack, k, table, null, false)?.text).toMatch(/^All of you /);
    const most = [...table, person("E", { [k]: c.answer })];
    expect(roastFor(pack, k, most, null, false)?.text).toMatch(/^A, B and 2 others /);
  });
});
