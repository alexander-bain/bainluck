// /guess — scoring, the Coin, the group's joint guess, standings, the link and
// the chance of winning. Every card is a slider (429: A).

import {
  cleanName,
  coinEntry,
  coinGuess,
  duoParts,
  emptyEntry,
  fullGuess,
  guessLabel,
  isValidGuess,
  joinNames,
  kindLabel,
  packDuo,
  pointsFor,
  spokenNames,
  standings,
  startGuess,
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
const perfect = (card: PackCard): number => fullGuess(card);
const farEnd = (answer: number, max: number): number => (answer >= max / 2 ? 0 : max);
const hopeless = (card: PackCard): number => {
  if (card.kind === "chance") return farEnd(card.answer, 100);
  if (card.kind === "count") return farEnd(card.answer, card.max);
  return packDuo(farEnd(card.parts[0].answer, 100), farEnd(card.parts[1].answer, 100));
};
const live = (p: PlayerEntry, upTo: number): PlayerEntry => ({ ...p, guesses: p.guesses.map((g, i) => (i < upTo ? g : null)) });

describe("/guess — scoring", () => {
  it("a chance card pays 20 less one for every point off, never below zero", () => {
    const card = byKind("chance");
    expect(pointsFor(card, card.answer)).toBe(20);
    expect(pointsFor(card, card.answer + 7 > 100 ? card.answer - 7 : card.answer + 7)).toBe(13);
    expect(pointsFor(card, card.answer >= 50 ? card.answer - 40 : card.answer + 40)).toBe(0);
    expect(pointsFor(card, null)).toBe(0);
    expect(pointsFor(card, 101)).toBe(0);
    expect(pointsFor(card, 12.5)).toBe(0);
  });

  it("a count card loses its step for each one off", () => {
    const card = byKind("count");
    expect(pointsFor(card, card.answer)).toBe(20);
    expect(pointsFor(card, card.answer + 3)).toBe(Math.max(0, 20 - 3 * card.step));
    expect(pointsFor(card, card.max + 1)).toBe(0);
  });

  it("a two-number card holds both guesses in one number and pays the average of the two", () => {
    const card = byKind("duo");
    const [a, b] = [card.parts[0].answer, card.parts[1].answer];
    expect(duoParts(packDuo(37, 100))).toEqual([37, 100]);
    expect(duoParts(packDuo(0, 0))).toEqual([0, 0]);
    expect(pointsFor(card, packDuo(a, b))).toBe(20);
    // One slider dead on, the other hopeless: half marks.
    expect(pointsFor(card, packDuo(a, farEnd(b, 100)))).toBe(10);
    // 4 off and 7 off: 16 and 13, which average to 14.5 and round up.
    const near = (v: number, by: number) => (v + by > 100 ? v - by : v + by);
    expect(pointsFor(card, packDuo(near(a, 4), near(b, 7)))).toBe(15);
    expect(isValidGuess(card, packDuo(100, 100))).toBe(true);
    expect(isValidGuess(card, packDuo(100, 100) + 1)).toBe(false);
    expect(isValidGuess(card, -1)).toBe(false);
  });

  it("a perfect game scores 20 a card and a hopeless one scores nothing", () => {
    expect(totalPoints(pack, player("A", perfect))).toBe(20 * pack.cards.length);
    expect(totalPoints(pack, player("Z", hopeless))).toBe(0);
  });

  it("says a guess in words, and names what each card asks for", () => {
    expect(guessLabel(byKind("chance"), 42)).toBe("42%");
    expect(guessLabel(byKind("count"), 9)).toBe(`9 of ${byKind("count").max}`);
    expect(guessLabel(byKind("duo"), packDuo(80, 5))).toBe("80% and 5%");
    expect(guessLabel(byKind("chance"), null)).toBe("");
    expect(new Set(pack.cards.map(kindLabel)).size).toBe(new Set(pack.cards.map((c) => c.flavor)).size);
  });
});

describe("/guess — the Coin and the group", () => {
  it("the Coin leaves every slider in the middle", () => {
    pack.cards.forEach((card, i) => {
      const g = coinGuess(pack, i);
      expect(g).toBe(startGuess(card));
      if (card.kind === "chance") expect(g).toBe(50);
      if (card.kind === "count") expect(g).toBe(Math.round(card.max / 2));
      if (card.kind === "duo") expect(duoParts(g)).toEqual([50, 50]);
    });
    expect(coinEntry(pack).from).toBe("house");
  });

  it("the group's guess is the average of every slider, each of a pair on its own", () => {
    expect(togetherGuess(byKind("chance"), [10, 20, 60])).toBe(30);
    expect(togetherGuess(byKind("count"), [4, 9])).toBe(7);
    expect(togetherGuess(byKind("duo"), [packDuo(90, 10), packDuo(70, 30)])).toBe(packDuo(80, 20));
    expect(togetherGuess(byKind("chance"), [])).toBeNull();
    expect(togetherGuess(byKind("chance"), [40, 999])).toBe(40);
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

  it("cleans names, joins them, and calls people by first name unless two would clash", () => {
    expect(cleanName("  Dr. <b>Evil</b>!!  ")).toBe("Dr bEvilb");
    expect(cleanName("a".repeat(40)).length).toBe(12);
    expect(cleanName("José-María")).toBe("José-María");
    expect(joinNames(["A"])).toBe("A");
    expect(joinNames(["A", "B"])).toBe("A and B");
    expect(joinNames(["A", "B", "C"])).toBe("A, B and C");
    expect(spokenNames(["Sam Lee", "Jo"]).get("Sam Lee")).toBe("Sam");
    expect(spokenNames(["Sam Lee", "Sam Roe"]).get("Sam Lee")).toBe("Sam Lee");
    expect(spokenNames(["Sam Lee", "sam"]).get("sam")).toBe("sam");
  });
});

describe("/guess — the link carries the group", () => {
  const ann = player("Ann", perfect);
  const bo = player("Bo O'Neil-2", hopeless);
  bo.name = cleanName("Bo O'Neil-2");
  ann.ratings[3] = 5;
  ann.good[0] = true;
  const n = pack.cards.length;

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

  it("carries both numbers of a two-number card, at every corner of the two sliders", () => {
    const at = pack.cards.findIndex((c) => c.kind === "duo");
    for (const pair of [packDuo(0, 0), packDuo(100, 100), packDuo(0, 100), packDuo(100, 0), packDuo(63, 7)]) {
      const one = player("Dee", perfect);
      one.guesses[at] = pair;
      const back = decodeGroup(pack, encodeGroup(pack, [one]));
      expect(back.ok && back.players[0].guesses[at]).toBe(pair);
    }
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
    expect(decodeGroup(pack, "#g=zz.Ann-000-0-0")).toEqual({ ok: false, reason: "other-edition" });
    // A link from the first set on this page, which used two characters a card.
    expect(decodeGroup(pack, `#g=a1.Ann-${"0a".repeat(14)}-${"1".repeat(14)}-${"0".repeat(14)}`)).toEqual({ ok: false, reason: "other-edition" });
    expect(decodeGroup(pack, `#g=${pack.code}.%E0%A4%A-xxx-0-0`)).toEqual({ ok: false, reason: "unreadable" });
    expect(decodeGroup(pack, `#g=${pack.code}.<script>-fff-9-9`)).toEqual({ ok: false, reason: "unreadable" });
    const wild = `#g=${pack.code}.${encodeURIComponent("<img src=x>")}-${"fff".repeat(n)}-${"9".repeat(n)}-${"7".repeat(n)}`;
    expect(decodeGroup(pack, wild)).toEqual({ ok: false, reason: "unreadable" }); // every guess out of range
    const mixed = `#g=${pack.code}.${encodeURIComponent("<b>Eve</b>")}-${"001".repeat(n)}-${"9".repeat(n)}-${"1".repeat(n)}`;
    const back = decodeGroup(pack, mixed);
    expect(back.ok).toBe(true);
    if (back.ok) {
      expect(back.players[0].name).toBe("bEveb");
      expect(back.players[0].ratings.every((r) => r === 0)).toBe(true);
      back.players[0].guesses.forEach((g) => expect(g === null || g === 1).toBe(true));
    }
    const crowd = `#g=${pack.code}.${Array.from({ length: 60 }, (_, i) => `P${i}-${"001".repeat(n)}-${"0".repeat(n)}-${"0".repeat(n)}`).join(".")}`;
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
    expect(shareMessage([{ name: "Ann", points: 143 }], 96, "https://bainluck.com/guess#g=b1.x")).toBe(
      "I scored 143 on Guess the Chance. That beats a coin flip by 47. Your turn:\nhttps://bainluck.com/guess#g=b1.x",
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
    for (const upTo of [0, 1, 4, 10]) {
      expect(winChances(pack, [ann, cy], upTo)).toEqual(winChances(pack, [live(ann, upTo), live(cy, upTo)], upTo));
    }
  });

  it("ends certain: whoever has the most points has all of it, and a tie is shared", () => {
    expect(winChances(pack, [ann, cy], pack.cards.length)).toEqual([1, 0]);
    expect(winChances(pack, [ann, player("Bo", perfect)], pack.cards.length)).toEqual([0.5, 0.5]);
    expect(winChances(pack, [ann], 3)).toEqual([1]);
  });

  it("does not make a no-hoper of anyone after two cards", () => {
    // The scores three people really had after two cards of the first live set:
    // 33, 3 and 9. The first version then showed 86%, 4% and 10%, on two cards'
    // evidence. Two cards are mostly luck, so the leader is short of 85% and
    // the player in last is above 5%.
    const scores = [
      [13, 20],
      [3, 0],
      [9, 0],
    ];
    const first = pack.cards[0];
    const second = pack.cards[1];
    if (first.kind !== "chance" || second.kind !== "chance") throw new Error("this test wants two chance cards first");
    const off = (answer: number, points: number) => (answer + (20 - points) <= 100 ? answer + (20 - points) : answer - (20 - points));
    const people = scores.map((s, n) => {
      const entry = emptyEntry(pack, `P${n + 1}`, "here");
      entry.guesses[0] = off(first.answer, s[0]);
      entry.guesses[1] = off(second.answer, s[1]);
      return entry;
    });
    expect(people.map((p) => totalPoints(pack, p))).toEqual([33, 3, 9]);
    const early = winChances(pack, people, 2);
    expect(early[0]).toBeLessThan(0.85);
    expect(early[0]).toBeGreaterThan(0.5);
    expect(early[1]).toBeGreaterThan(0.05);
    expect(early[2]).toBeGreaterThan(early[1]);
  });

  it("still favors a player who has been far better over half the game", () => {
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
