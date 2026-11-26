// /guess — scoring, the Coin, the group's joint guess, standings and the link.

import {
  cleanName,
  coinEntry,
  coinGuess,
  emptyEntry,
  joinNames,
  ORDER_PERMS,
  pairsRight,
  pointsFor,
  standings,
  togetherGuess,
  togetherReport,
  topicWins,
  totalPoints,
} from "@/lib/guess/engine";
import { decodeGroup, encodeGroup, mergeFromLink, shareMessage } from "@/lib/guess/link";
import { GUESS_PACK as pack } from "@/lib/guess/pack";
import type { PackCard, PlayerEntry } from "@/lib/guess/types";
import { winChanceHistory, winChances } from "@/lib/guess/winChance";

const byKind = <K extends PackCard["kind"]>(kind: K) =>
  pack.cards.find((c) => c.kind === kind) as Extract<PackCard, { kind: K }>;

/** A player who answers every card with whatever `pick` returns. */
function player(name: string, pick: (card: PackCard, index: number) => number, from: PlayerEntry["from"] = "here"): PlayerEntry {
  const entry = emptyEntry(pack, name, from);
  entry.guesses = pack.cards.map((card, i) => pick(card, i));
  return entry;
}
const perfect = (card: PackCard): number => {
  if (card.kind === "order") return ORDER_PERMS.findIndex((_, i) => pointsFor(card, i) === 20);
  return card.answer;
};
const hopeless = (card: PackCard): number => {
  if (card.kind === "chance") return card.answer >= 50 ? 0 : 100;
  if (card.kind === "count") return card.answer >= card.max / 2 ? 0 : card.max;
  if (card.kind === "order") return ORDER_PERMS.findIndex((_, i) => pointsFor(card, i) === 0);
  return card.options.findIndex((_, i) => pointsFor(card, i) === 0);
};

describe("/guess — scoring", () => {
  it("a chance card pays 20 less one for every point off, never below zero", () => {
    const card = byKind("chance");
    expect(pointsFor(card, card.answer)).toBe(20);
    expect(pointsFor(card, card.answer + 7 > 100 ? card.answer - 7 : card.answer + 7)).toBe(13);
    expect(pointsFor(card, card.answer >= 50 ? card.answer - 40 : card.answer + 40)).toBe(0);
    expect(pointsFor(card, null)).toBe(0);
  });

  it("a pick card pays 20 for the answer, 8 for the next best where there is one, else nothing", () => {
    for (const card of pack.cards) {
      if (card.kind !== "pick" && card.kind !== "ladder") continue;
      const paid = card.options.map((_, i) => pointsFor(card, i));
      expect(paid[card.answer]).toBe(20);
      expect(paid.filter((p) => p === 20).length).toBe(1);
      expect(paid.every((p) => p === 20 || p === 8 || p === 0)).toBe(true);
    }
  });

  it("an order card pays by pairs the right way round: 0, 5, 12, 20", () => {
    const card = byKind("order");
    const paid = ORDER_PERMS.map((_, i) => [pairsRight(card, i), pointsFor(card, i)]);
    expect(paid.map(([, p]) => p).sort((a, b) => a - b)).toEqual([0, 5, 5, 12, 12, 20]);
    for (const [pairs, points] of paid) expect(points).toBe([0, 5, 12, 20][pairs]);
  });

  it("a perfect game scores 20 a card and a hopeless one scores nothing", () => {
    expect(totalPoints(pack, player("P", perfect))).toBe(20 * pack.cards.length);
    expect(totalPoints(pack, player("H", hopeless))).toBe(0);
  });
});

describe("/guess — the Coin and the group", () => {
  it("the Coin says 50% on a chance card, half on a count card, and the same pick on every phone", () => {
    pack.cards.forEach((card, i) => {
      const g = coinGuess(pack, i);
      if (card.kind === "chance") expect(g).toBe(50);
      if (card.kind === "count") expect(g).toBe(Math.round(card.max / 2));
      expect(coinGuess(pack, i)).toBe(g);
      expect(Number.isInteger(g)).toBe(true);
    });
    expect(coinEntry(pack).from).toBe("house");
  });

  it("the group's guess is the average on a slider and the most picked option on a pick", () => {
    const chance = byKind("chance");
    expect(togetherGuess(chance, [10, 20, 60])).toBe(30);
    const pick = byKind("pick");
    expect(togetherGuess(pick, [1, 0, 1])).toBe(1);
    expect(togetherGuess(pick, [0, 1])).toBe(0); // a tie goes to whoever in the tie guessed first
    expect(togetherGuess(pick, [])).toBeNull();
    const order = byKind("order");
    expect(togetherGuess(order, [0, 0, 5])).toBe(0);
  });

  it("names the player who cost the group most, only when leaving them out adds five points or more", () => {
    const a = player("Ann", perfect);
    const b = player("Bo", perfect);
    const c = player("Cy", hopeless);
    const report = togetherReport(pack, [a, b, c]);
    expect(report.without?.name).toBe("Cy");
    expect(report.without!.score).toBeGreaterThan(report.together);
    expect(togetherReport(pack, [a, b, player("Di", perfect)]).without).toBeNull();
    expect(togetherReport(pack, [a, c]).without).toBeNull(); // two players: nobody is singled out
    expect(report.best).toBe(20 * pack.cards.length);
  });

  it("standings share a place on a tie and topic wins go to the best average on that topic", () => {
    const a = player("Ann", perfect);
    const b = player("Bo", perfect);
    const c = player("Cy", hopeless);
    expect(standings(pack, [c, a, b]).map((s) => [s.entry.name, s.place])).toEqual([
      ["Ann", 1],
      ["Bo", 1],
      ["Cy", 3],
    ]);
    const sportsOnly = player("Sam", (card) => (card.topic === "Sports" ? perfect(card) : hopeless(card)));
    const wins = topicWins(pack, [sportsOnly, c]);
    expect(wins.find((w) => w.topic === "Sports")?.names).toEqual(["Sam"]);
    expect(wins.find((w) => w.topic !== "Sports")?.names).toEqual([]);
  });

  it("cleans names and joins them", () => {
    expect(cleanName("  Dr. <b>Evil</b>!!  ")).toBe("Dr bEvilb");
    expect(cleanName("a".repeat(40)).length).toBe(12);
    expect(cleanName("José-María")).toBe("José-María");
    expect(joinNames(["A"])).toBe("A");
    expect(joinNames(["A", "B"])).toBe("A and B");
    expect(joinNames(["A", "B", "C"])).toBe("A, B and C");
  });
});

describe("/guess — the link carries the group", () => {
  const ann = player("Ann", perfect);
  const bo = player("Bo O'Neil-2", hopeless);
  bo.name = cleanName("Bo O'Neil-2");
  ann.ratings[3] = 5;
  ann.good[0] = true;

  it("round-trips names, guesses, ratings and marks, using only characters a chat keeps", () => {
    const fragment = encodeGroup(pack, [ann, bo, coinEntry(pack)]);
    expect(fragment).toMatch(/^g=[A-Za-z0-9%._=-]+$/);
    expect(fragment).toMatch(/[0-9a-zA-Z]$/);
    const back = decodeGroup(pack, `#${fragment}`);
    expect(back.ok).toBe(true);
    if (!back.ok) return;
    expect(back.players.map((p) => p.name)).toEqual(["Ann", "Bo ONeil-2"]);
    expect(back.players[0].guesses).toEqual(ann.guesses);
    expect(back.players[1].guesses).toEqual(bo.guesses);
    expect(back.players[0].ratings[3]).toBe(5);
    expect(back.players[0].good[0]).toBe(true);
    expect(back.players.every((p) => p.from === "link")).toBe(true);
  });

  it("carries a half-finished game", () => {
    const half = player("Half", perfect);
    half.guesses = half.guesses.map((g, i) => (i < pack.perRound ? g : null));
    const back = decodeGroup(pack, encodeGroup(pack, [half]));
    expect(back.ok && back.players[0].guesses).toEqual(half.guesses);
  });

  it("treats a link as data from a stranger: never throws, drops what is not valid", () => {
    expect(decodeGroup(pack, "")).toEqual({ ok: false, reason: "none" });
    expect(decodeGroup(pack, "#section")).toEqual({ ok: false, reason: "none" });
    expect(decodeGroup(pack, "#g=zz.Ann-00-0-0")).toEqual({ ok: false, reason: "other-edition" });
    expect(decodeGroup(pack, `#g=${pack.code}.%E0%A4%A-xx-0-0`)).toEqual({ ok: false, reason: "unreadable" });
    expect(decodeGroup(pack, `#g=${pack.code}.<script>-ff-9-9`)).toEqual({ ok: false, reason: "unreadable" });
    const n = pack.cards.length;
    const wild = `#g=${pack.code}.${encodeURIComponent("<img src=x>")}-${"ff".repeat(n)}-${"9".repeat(n)}-${"7".repeat(n)}`;
    expect(decodeGroup(pack, wild)).toEqual({ ok: false, reason: "unreadable" }); // every guess out of range
    const mixed = `#g=${pack.code}.${encodeURIComponent("<b>Eve</b>")}-${"01".repeat(n)}-${"9".repeat(n)}-${"1".repeat(n)}`;
    const back = decodeGroup(pack, mixed);
    expect(back.ok).toBe(true);
    if (back.ok) {
      expect(back.players[0].name).toBe("bEveb");
      expect(back.players[0].ratings.every((r) => r === 0)).toBe(true);
      back.players[0].guesses.forEach((g) => expect(g === null || g === 1).toBe(true));
    }
    const crowd = `#g=${pack.code}.${Array.from({ length: 60 }, (_, i) => `P${i}-${"01".repeat(n)}-${"0".repeat(n)}-${"0".repeat(n)}`).join(".")}`;
    const many = decodeGroup(pack, crowd);
    expect(many.ok && many.players.length).toBe(24);
  });

  it("does not show a person twice when they open a link that holds their own game", () => {
    const fromLink = decodeGroup(pack, encodeGroup(pack, [ann, bo]));
    if (!fromLink.ok) throw new Error("link did not decode");
    const merged = mergeFromLink([ann], fromLink.players);
    expect(merged.map((p) => p.name)).toEqual(["Bo ONeil-2"]);
    const otherAnn = player("Ann", hopeless);
    expect(mergeFromLink([otherAnn], fromLink.players).map((p) => p.name)).toEqual(["Ann 2", "Bo ONeil-2"]);
  });

  it("writes a short message in the sender's voice, with the link on its own line", () => {
    expect(shareMessage([{ name: "Ann", points: 143 }], 96, "https://bainluck.com/guess#g=a1.x")).toBe(
      "I scored 143 on Guess the Chance. That beats a coin flip by 47. Your turn:\nhttps://bainluck.com/guess#g=a1.x",
    );
    expect(shareMessage([{ name: "Ann", points: 80 }], 92, "u")).toContain("A coin flip beat me by 12.");
    expect(shareMessage([{ name: "Ann", points: 80 }], 80, "u")).toContain("I tied a coin flip.");
    expect(
      shareMessage(
        [
          { name: "Ann", points: 80 },
          { name: "Bo", points: 121 },
        ],
        90,
        "u",
      ),
    ).toBe("We played Guess the Chance. Bo won with 121. Your turn:\nu");
  });
});

describe("/guess — chance of winning", () => {
  const ann = player("Ann", perfect);
  const cy = player("Cy", hopeless);

  it("starts exactly level, sums to one, and is the same every time it is asked", () => {
    expect(winChances(pack, [ann, cy, coinEntry(pack)], 0)).toEqual([1 / 3, 1 / 3, 1 / 3]);
    for (const upTo of [1, 5, 9, pack.cards.length]) {
      const now = winChances(pack, [ann, cy, coinEntry(pack)], upTo);
      expect(now.reduce((s, v) => s + v, 0)).toBeCloseTo(1, 6);
      expect(winChances(pack, [ann, cy, coinEntry(pack)], upTo)).toEqual(now);
    }
  });

  it("never looks at cards still to come, even when they are already answered", () => {
    // Someone who finished yesterday must not give their result away at card 1.
    const live = (p: PlayerEntry, upTo: number): PlayerEntry => ({ ...p, guesses: p.guesses.map((g, i) => (i < upTo ? g : null)) });
    for (const upTo of [0, 1, 4, 10]) {
      expect(winChances(pack, [ann, cy], upTo)).toEqual(winChances(pack, [live(ann, upTo), live(cy, upTo)], upTo));
    }
  });

  it("ends certain: whoever has the most points has all of it, and a tie is shared", () => {
    expect(winChances(pack, [ann, cy], pack.cards.length)).toEqual([1, 0]);
    expect(winChances(pack, [ann, player("Bo", perfect)], pack.cards.length)).toEqual([0.5, 0.5]);
    expect(winChances(pack, [ann], 3)).toEqual([1]);
  });

  it("favors a player still playing who has been far better so far", () => {
    const live = (p: PlayerEntry, upTo: number): PlayerEntry => ({ ...p, guesses: p.guesses.map((g, i) => (i < upTo ? g : null)) });
    const mid = winChances(pack, [live(ann, 7), live(cy, 7)], 7);
    expect(mid[0]).toBeGreaterThan(0.9);
    const history = winChanceHistory(pack, [live(ann, 7), live(cy, 7)], 7);
    expect(history.length).toBe(8);
    expect(history[0]).toEqual([0.5, 0.5]);
    expect(history[7]).toEqual(mid);
    // The chart at the end shows the same numbers the players saw along the way.
    expect(winChanceHistory(pack, [ann, cy], pack.cards.length)[7]).toEqual(mid);
  });
});
