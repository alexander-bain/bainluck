// /guess — THE LINE AFTER A CARD HAS TO BE EARNED (429: A).
//
// Who it is about, from playtesting: "Roast the person who's furthest away or
// closest. A bunch of times it seemed random who was chosen." And what the
// first live set taught: a line on nearly every card is not funny. So a line
// names only the farthest person, only when they scored nothing on the card;
// or someone dead on; or, when nobody earned one, sometimes the whole table.
// It calls people by first name and reads correctly for one name or several.
//
// A TAP CARD NEVER GETS ONE (430: A). It is right or wrong, the answer screen
// already says who got it, and five quick taps should not stop five times.
//
// TWO SETS ARE USED. `pack` is set two, fourteen sliders, kept as a helper: the
// rules for a line are rules about sliders, and that set has every kind of
// slider. `live` is the set on the page, whose first ten cards are taps.

import { coinEntry, emptyEntry, fullGuess, isTap, optionCount, packDuo, pointsFor } from "@/lib/guess/engine";
import { GUESS_PACK as live } from "@/lib/guess/pack";
import { earnsLine, fillLine, isTableLine, roastFor, roastHistory, sayNames } from "@/lib/guess/roast";
import type { ChanceCard, CountCard, DuoCard, GamePack, PackCard, PlayerEntry } from "@/lib/guess/types";

import { SLIDER_PACK as pack } from "../helpers/guessSliderSet";

function person(name: string, guesses: Record<number, number>, set: GamePack = pack): PlayerEntry {
  const entry = emptyEntry(set, name, "here");
  Object.entries(guesses).forEach(([i, g]) => {
    entry.guesses[Number(i)] = g;
  });
  return entry;
}

const LOW = pack.cards.findIndex((c) => c.kind === "chance" && c.answer <= 20 && Boolean(c.roastHigh));
const MID = pack.cards.findIndex((c) => c.kind === "chance" && c.answer >= 40 && c.answer <= 60);
const COUNT = pack.cards.findIndex((c) => c.kind === "count");
const DUO = pack.cards.findIndex((c) => c.kind === "duo");
const low = pack.cards[LOW] as ChanceCard;
const mid = pack.cards[MID] as ChanceCard;
const count = pack.cards[COUNT] as CountCard;
const duo = pack.cards[DUO] as DuoCard;

describe("/guess — who the line is about", () => {
  it("names only the farthest person, whatever order they joined in", () => {
    const near = person("Near", { [LOW]: low.answer + 4 });
    const middling = person("Mid", { [LOW]: low.answer + 15 });
    const far = person("Far", { [LOW]: low.answer + 40 });
    for (const order of [
      [near, middling, far],
      [far, near, middling],
      [middling, far, near],
    ]) {
      const line = roastFor(pack, LOW, order, null, false);
      expect(line?.rule).toBe("far");
      expect(line?.names).toEqual(["Far"]);
      expect(line?.text).toContain("Far");
      expect(line?.text).not.toContain("Near");
    }
  });

  it("says nothing unless the farthest person scored nothing on the card", () => {
    const a = person("Ann", { [MID]: mid.answer + 4 });
    const b = person("Bo", { [MID]: mid.answer - 19 });
    expect(pointsFor(mid, mid.answer - 19)).toBe(1);
    expect(roastFor(pack, MID, [a, b], null, false)).toBeNull();
    const c = person("Cy", { [MID]: mid.answer - 20 });
    expect(pointsFor(mid, mid.answer - 20)).toBe(0);
    expect(roastFor(pack, MID, [a, c], null, false)?.names).toEqual(["Cy"]);
  });

  it("someone dead on gets the line instead, unless somebody else missed by 30 or more", () => {
    const exact = person("Dee", { [LOW]: low.answer });
    const off = person("Off", { [LOW]: low.answer + 20 });
    const line = roastFor(pack, LOW, [off, exact], null, false);
    expect(line?.rule).toBe("exact");
    expect(line?.names).toEqual(["Dee"]);
    const howler = person("How", { [LOW]: low.answer + 45 });
    const other = roastFor(pack, LOW, [exact, howler], null, false);
    expect(other?.rule).toBe("far");
    expect(other?.names).toEqual(["How"]);
  });

  it("names two people together only when they made the very same worst guess", () => {
    const a = person("Ann", { [LOW]: low.answer + 40 });
    const b = person("Bo", { [LOW]: low.answer + 40 });
    const c = person("Cy", { [LOW]: low.answer + 39 });
    const line = roastFor(pack, LOW, [a, b, c], null, false);
    expect(line?.names).toEqual(["Ann", "Bo"]);
    expect(line?.text).toContain("Ann and Bo");
    expect(line?.text).not.toMatch(/\bCy\b/);
  });

  it("calls people by first name, unless two at the table share one", () => {
    const far = person("Sam Lee", { [LOW]: low.answer + 40 });
    const near = person("Jo", { [LOW]: low.answer });
    const line = roastFor(pack, LOW, [far, person("Kit", { [LOW]: low.answer + 3 })], null, false);
    expect(line?.text).toContain("Sam");
    expect(line?.text).not.toContain("Sam Lee");
    expect(line?.names).toEqual(["Sam Lee"]); // the record keeps the whole name
    const clash = roastFor(pack, LOW, [far, person("Sam Roe", { [LOW]: low.answer + 3 })], null, false);
    expect(clash?.text).toContain("Sam Lee");
    expect(near.name).toBe("Jo");
  });

  it("on a count card, the line follows the direction of the miss and needs a big one", () => {
    const high = roastFor(pack, COUNT, [person("Hi", { [COUNT]: count.max })], null, false);
    expect(high?.rule).toBe("far");
    expect(high?.text).toBe(fillLine(count.roastHigh as string, ["Hi"], { g: count.max, w: count.answer }));
    const lowLine = roastFor(pack, COUNT, [person("Lo", { [COUNT]: 0 })], null, false);
    expect(lowLine?.text).toBe(fillLine(count.roastLow as string, ["Lo"], { g: 0, w: count.answer }));
    expect(roastFor(pack, COUNT, [person("Ok", { [COUNT]: count.answer + 2 })], null, false)).toBeNull();
  });

  it("on a two-number card, having the two the wrong way round gets its own line", () => {
    const [a, b] = [duo.parts[0].answer, duo.parts[1].answer];
    const worldFirstHigher = a > b;
    const flipped = worldFirstHigher ? packDuo(20, 70) : packDuo(70, 20);
    const line = roastFor(pack, DUO, [person("Flip", { [DUO]: flipped })], null, false);
    expect(line?.rule).toBe("flip");
    expect(line?.text).toContain("Flip");
    expect(line?.text).not.toMatch(/[{}]/);
  });

  it("on a two-number card, otherwise names the slider that was missed by more, and by how much", () => {
    const [a, b] = [duo.parts[0].answer, duo.parts[1].answer];
    // Level sliders are not "the wrong way round". The first is the bigger miss here.
    const level = roastFor(pack, DUO, [person("Lev", { [DUO]: packDuo(30, 30) })], null, false);
    const missA = Math.abs(30 - a);
    const missB = Math.abs(30 - b);
    expect(level?.rule).toBe("far");
    expect(level?.text).toContain(duo.parts[missB > missA ? 1 : 0].short);
    expect(level?.text).toContain(String(Math.max(missA, missB)));
    // Both sliders close: no line.
    expect(roastFor(pack, DUO, [person("Ok", { [DUO]: packDuo(a > 50 ? a - 5 : a + 5, b > 50 ? b - 5 : b + 5) })], null, false)).toBeNull();
  });

  it.each([
    ["the fourteen sliders", pack],
    ["the live set", live],
  ])("in %s, every slider's own lines fill completely, for one name and for several, in every direction they can be earned", (_label, set) => {
    set.cards.forEach((card, i) => {
      if (isTap(card)) return;
      const guesses: number[] = [];
      if (card.kind === "chance") {
        if (card.answer + 20 <= 100) guesses.push(Math.min(100, card.answer + 29));
        if (card.answer - 20 >= 0) guesses.push(Math.max(0, card.answer - 29));
      } else if (card.kind === "count") {
        guesses.push(0, card.max);
      } else {
        // The two the wrong way round, both far, and one dead on with the other 50 off.
        const [a, b] = [card.parts[0].answer, card.parts[1].answer];
        guesses.push(packDuo(20, 70), packDuo(70, 20), packDuo(30, 30), packDuo(a, b > 50 ? b - 50 : b + 50));
      }
      const earning = guesses.filter((g) => earnsLine(card, g));
      expect({ card: card.id, earning: earning.length >= (card.kind === "duo" ? 2 : guesses.length) && earning.length > 0 }).toEqual({ card: card.id, earning: true });
      for (const guess of earning) {
        for (const names of [["Sam Lee"], ["Sam Lee", "Jo"], ["Sam Lee", "Jo", "Kit", "Di", "Ed"]]) {
          const line = roastFor(set, i, names.map((n) => person(n, { [i]: guess }, set)), null, false);
          expect({ card: card.id, guess, got: line !== null }).toEqual({ card: card.id, guess, got: true });
          if (!line) continue;
          expect({ card: card.id, text: line.text, holes: /[{}]|undefined|NaN/.test(line.text) }).toEqual({ card: card.id, text: line.text, holes: false });
          expect(line.text.charAt(0)).toBe(line.text.charAt(0).toUpperCase());
          expect(line.text.length).toBeLessThanOrEqual(150);
          expect(line.text).not.toContain("Sam Lee");
          if (names.length === 5) expect(line.text.toLowerCase()).toContain("all of you");
        }
      }
    });
  });
});

describe("/guess — playing alone, and the lines about the whole table", () => {
  const coin = coinEntry(pack);

  it("alone, the farthest person is you, and the Coin is never the target", () => {
    const line = roastFor(pack, LOW, [person("Solo", { [LOW]: low.answer + 40 }), coin], coin, false);
    expect(line?.names).toEqual(["Solo"]);
    // A person who did well gets no line even though the Coin did badly.
    expect(pointsFor(low, 50)).toBe(0);
    expect(roastFor(pack, LOW, [person("Solo", { [LOW]: low.answer + 3 }), coin], coin, false)).toBeNull();
  });

  it("the Coin gets a line when it beats everyone by five or more and nobody earned one", () => {
    const a = person("Ann", { [MID]: mid.answer + 9 });
    const b = person("Bo", { [MID]: mid.answer + 10 });
    expect(pointsFor(mid, 50) - pointsFor(mid, mid.answer + 9)).toBeGreaterThanOrEqual(5);
    const line = roastFor(pack, MID, [a, b], coin, false);
    expect(line?.rule).toBe("coin");
    expect(line?.text).toContain("Ann and Bo");
    expect(line?.text).not.toMatch(/[{}]/);
    // Without the Coin on the board there is no such line.
    expect(roastFor(pack, MID, [a, b], null, false)?.rule).not.toBe("coin");
  });

  it("says so when the whole table was too high, and never shows two table lines in a row", () => {
    const first = pack.cards.findIndex((c, i) => c.kind === "chance" && pack.cards[i + 1]?.kind === "chance" && c.answer <= 80 && (pack.cards[i + 1] as ChanceCard).answer <= 80);
    const a0 = (pack.cards[first] as ChanceCard).answer;
    const a1 = (pack.cards[first + 1] as ChanceCard).answer;
    const ann = person("Ann", { [first]: a0 + 6, [first + 1]: a1 + 6 });
    const bo = person("Bo", { [first]: a0 + 8, [first + 1]: a1 + 8 });
    expect(roastFor(pack, first, [ann, bo], null, false)?.rule).toBe("allhigh");
    expect(roastFor(pack, first + 1, [ann, bo], null, false)?.rule).toBe("allhigh");
    const history = roastHistory(pack, first + 1, [ann, bo], null);
    expect(isTableLine(history[first])).toBe(true);
    expect(history[first + 1]).toBeNull();
  });

  it("notices one person being the closest three cards running", () => {
    // Ann two off and Bo five off on the first three cards: nobody far, nobody dead on.
    const off = (i: number, by: number): number => {
      const card = pack.cards[i];
      if (isTap(card)) return fullGuess(card);
      if (card.kind === "chance") return card.answer + (card.answer > 50 ? -by : by);
      if (card.kind === "count") return card.answer + (by > 2 ? 2 : 1);
      return packDuo(card.parts[0].answer + (card.parts[0].answer > 50 ? -by : by), card.parts[1].answer + (card.parts[1].answer > 50 ? -by : by));
    };
    const ann = person("Ann", { 0: off(0, 2), 1: off(1, 2), 2: off(2, 2) });
    const bo = person("Bo", { 0: off(0, 5), 1: off(1, 5), 2: off(2, 5) });
    const history = roastHistory(pack, 2, [ann, bo], null);
    expect(history[0]).toBeNull();
    expect(history[1]).toBeNull();
    expect(history[2]?.rule).toBe("hot");
    expect(history[2]?.names).toEqual(["Ann"]);
  });

  it("rebuilds the same lines on any phone from the guesses alone", () => {
    // Ann is close on every other card and hopeless on the rest. Bo is always close.
    const toward = (answer: number, max: number, by: number) => (answer > max / 2 ? answer - by : answer + by);
    const close = (card: PackCard, by: number): number => {
      if (isTap(card)) return fullGuess(card);
      if (card.kind === "chance") return toward(card.answer, 100, by);
      if (card.kind === "count") return toward(card.answer, card.max, 1);
      return packDuo(toward(card.parts[0].answer, 100, by), toward(card.parts[1].answer, 100, by));
    };
    const wayOff = (card: PackCard): number => {
      if (isTap(card)) return (fullGuess(card) + 1) % optionCount(card);
      if (card.kind === "chance") return card.answer > 50 ? 0 : 100;
      if (card.kind === "count") return card.answer > card.max / 2 ? 0 : card.max;
      return packDuo(card.parts[0].answer > 50 ? 0 : 100, card.parts[1].answer > 50 ? 0 : 100);
    };
    const ann = person("Ann", {});
    const bo = person("Bo", {});
    pack.cards.forEach((card, i) => {
      ann.guesses[i] = i % 2 === 0 ? close(card, 3) : wayOff(card);
      bo.guesses[i] = close(card, 4);
      expect(pointsFor(card, fullGuess(card))).toBe(20);
    });
    const once = roastHistory(pack, pack.cards.length - 1, [ann, bo], coin);
    expect(roastHistory(pack, pack.cards.length - 1, [ann, bo], coin)).toEqual(once);
    expect(once.length).toBe(pack.cards.length);
    // A line has to be earned: the cards where Ann was hopeless have one about her, and the rest say nothing.
    once.forEach((l, i) => {
      if (i % 2 === 1) expect({ at: i, names: l?.names }).toEqual({ at: i, names: ["Ann"] });
      else expect({ at: i, line: l }).toEqual({ at: i, line: null });
    });
    once.forEach((l, i) => {
      if (i > 0) expect(isTableLine(l) && isTableLine(once[i - 1])).toBe(false);
    });
  });

  it("a tap card never gets a line: not for a wrong tap, not when the Coin beats the table", () => {
    const liveCoin = coinEntry(live);
    live.cards.forEach((card, i) => {
      if (!isTap(card)) return;
      const right = fullGuess(card);
      const wrong = (right + 1) % optionCount(card);
      expect(earnsLine(card, wrong)).toBe(false);
      for (const guess of [right, wrong]) {
        const table = [person("Ann", { [i]: guess }, live), person("Bo", { [i]: guess }, live), person("Cy", { [i]: wrong }, live)];
        expect({ card: card.id, guess, line: roastFor(live, i, table, liveCoin, false) }).toEqual({ card: card.id, guess, line: null });
      }
    });
  });

  it("in the live set the first line can only come once the sliders start", () => {
    // Everyone taps wrong for ten cards, then one person is hopeless on every slider.
    const firstSlider = live.cards.findIndex((c) => !isTap(c));
    expect(firstSlider).toBe(10);
    const wayOff = (card: PackCard): number => {
      if (isTap(card)) return (fullGuess(card) + 1) % optionCount(card);
      if (card.kind === "chance") return card.answer > 50 ? 0 : 100;
      return 0;
    };
    const ann = person("Ann", {}, live);
    const bo = person("Bo", {}, live);
    live.cards.forEach((card, i) => {
      ann.guesses[i] = wayOff(card);
      bo.guesses[i] = isTap(card) ? wayOff(card) : fullGuess(card) + (fullGuess(card) > 50 ? -4 : 4);
    });
    const history = roastHistory(live, live.cards.length - 1, [ann, bo], coinEntry(live));
    history.forEach((line, i) => {
      if (i < firstSlider) expect({ at: i, line }).toEqual({ at: i, line: null });
      else expect({ at: i, names: line?.names, rule: line?.rule }).toEqual({ at: i, names: ["Ann"], rule: "far" });
    });
  });

  it("fills singular and plural forms", () => {
    expect(fillLine("{n} {has} it. {n} {is} sure, {n} {was} not, and {n} believe{s}.", ["Ann"])).toBe("Ann has it. Ann is sure, Ann was not, and Ann believes.");
    expect(fillLine("{n} {has} it. {n} {is} sure, {n} {was} not, and {n} believe{s}.", ["Ann", "Bo"])).toBe(
      "Ann and Bo have it. Ann and Bo are sure, Ann and Bo were not, and Ann and Bo believe.",
    );
    expect(fillLine("{n} said {g}, off by {d} on {part}. The world says {w}.", ["Ann"], { g: "5%", w: "40%", d: 35, part: "the first" })).toBe(
      "Ann said 5%, off by 35 on the first. The world says 40%.",
    );
  });

  it("does not read out a whole table of names", () => {
    expect(sayNames(["A", "B", "C"], false)).toBe("A, B and C");
    expect(sayNames(["A", "B", "C", "D", "E"], false)).toBe("A, B and 3 others");
    expect(sayNames(["A", "B", "C"], true)).toBe("all of you");
    expect(sayNames(["A", "B"], true)).toBe("A and B");
    expect(fillLine("{n} said so. Tell {n}.", ["A", "B", "C"], {}, true)).toBe("All of you said so. Tell all of you.");
  });
});
