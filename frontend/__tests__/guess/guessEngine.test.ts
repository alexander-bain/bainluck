// /guess — scoring, the Coin, the group's joint guess, the steps, standings,
// the link and the chance of winning.
//
// TWO SETS ARE USED. `pack` is the live set: three steps, taps then sliders
// (430: A). `sliders` is set two, fourteen sliders, kept as a helper so the
// count card and the two-number card stay tested though the live set has
// neither. A test says which it needs by which helpers it calls.

import {
  cleanName,
  coinEntry,
  coinGuess,
  duoParts,
  emptyEntry,
  fullGuess,
  fullPoints,
  guessLabel,
  isTap,
  isValidGuess,
  joinNames,
  kindLabel,
  optionCount,
  packDuo,
  pointsFor,
  spokenNames,
  standings,
  startGuess,
  stepIsTaps,
  stepMax,
  stepOf,
  stepRange,
  stepScore,
  stepScoreLabel,
  stepWins,
  tapNote,
  timeLabel,
  togetherGuess,
  togetherReport,
  topicWins,
  totalPoints,
} from "@/lib/guess/engine";
import { decodeGroup, encodeGroup, mergeFromLink, shareMessage, stepShareMessage } from "@/lib/guess/link";
import { GUESS_PACK as pack } from "@/lib/guess/pack";
import type { GamePack, PackCard, PlayerEntry } from "@/lib/guess/types";
import { winChanceHistory, winChances } from "@/lib/guess/winChance";

import { SLIDER_PACK as sliders } from "../helpers/guessSliderSet";

const byKind = <K extends PackCard["kind"]>(kind: K, from: GamePack = pack) => {
  const card = from.cards.find((c) => c.kind === kind);
  if (!card) throw new Error(`no ${kind} card in set ${from.code}`);
  return card as Extract<PackCard, { kind: K }>;
};

/** A player who answers every card of a set with whatever `pick` returns. */
function player(
  name: string,
  pick: (card: PackCard, index: number) => number,
  from: PlayerEntry["from"] = "here",
  set: GamePack = pack,
): PlayerEntry {
  const entry = emptyEntry(set, name, from);
  entry.guesses = set.cards.map((card, i) => pick(card, i));
  return entry;
}
const perfect = (card: PackCard): number => fullGuess(card);
const farEnd = (answer: number, max: number): number => (answer >= max / 2 ? 0 : max);
const hopeless = (card: PackCard): number => {
  if (isTap(card)) return (fullGuess(card) + 1) % optionCount(card);
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

  it("a right tap pays 10 when there are two to choose from and 15 when there are four, and any other tap pays nothing", () => {
    for (const card of pack.cards.filter(isTap)) {
      const right = fullGuess(card);
      const worth = optionCount(card) === 2 ? 10 : 15;
      expect(fullPoints(card)).toBe(worth);
      for (let place = 0; place < optionCount(card); place += 1) {
        expect({ card: card.id, place, points: pointsFor(card, place) }).toEqual({ card: card.id, place, points: place === right ? worth : 0 });
      }
      expect(pointsFor(card, optionCount(card))).toBe(0);
      expect(pointsFor(card, -1)).toBe(0);
      expect(pointsFor(card, null)).toBe(0);
      expect(pointsFor(card, 0.5)).toBe(0);
      expect(isValidGuess(card, optionCount(card) - 1)).toBe(true);
      expect(isValidGuess(card, optionCount(card))).toBe(false);
    }
  });

  it("the right tap is the side of 50 the world is on, the bigger of two, the world's number, or the favorite", () => {
    const side = byKind("side");
    expect(fullGuess(side)).toBe(side.answer > 50 ? 1 : 0);
    const versus = byKind("versus");
    expect(versus.options[fullGuess(versus)].percent).toBe(Math.max(...versus.options.map((o) => o.percent)));
    const four = byKind("four");
    expect(four.options[fullGuess(four)]).toBe(four.answer);
    const leader = byKind("leader");
    expect(leader.options[fullGuess(leader)].percent).toBe(Math.max(...leader.options.map((o) => o.percent)));
  });

  it("a count card loses its step for each one off", () => {
    const card = byKind("count", sliders);
    expect(pointsFor(card, card.answer)).toBe(20);
    expect(pointsFor(card, card.answer + 3)).toBe(Math.max(0, 20 - 3 * card.step));
    expect(pointsFor(card, card.max + 1)).toBe(0);
  });

  it("a two-number card holds both guesses in one number and pays the average of the two", () => {
    const card = byKind("duo", sliders);
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

  it("a perfect game scores every card's worth and a hopeless one scores nothing, in both sets", () => {
    for (const set of [pack, sliders]) {
      expect(totalPoints(set, player("A", perfect, "here", set))).toBe(set.cards.reduce((sum, c) => sum + fullPoints(c), 0));
      expect(totalPoints(set, player("Z", hopeless, "here", set))).toBe(0);
    }
    expect(totalPoints(pack, player("A", perfect))).toBe(50 + 75 + 100);
    expect(totalPoints(sliders, player("A", perfect, "here", sliders))).toBe(20 * 14);
    expect(fullPoints(byKind("chance"))).toBe(20);
    expect(fullPoints(byKind("count", sliders))).toBe(20);
    expect(fullPoints(byKind("duo", sliders))).toBe(20);
  });

  it("says a guess in words, and names what each card asks for", () => {
    expect(guessLabel(byKind("chance"), 42)).toBe("42%");
    expect(guessLabel(byKind("count", sliders), 9)).toBe(`9 of ${byKind("count", sliders).max}`);
    expect(guessLabel(byKind("duo", sliders), packDuo(80, 5))).toBe("80% and 5%");
    expect(guessLabel(byKind("chance"), null)).toBe("");
    expect(guessLabel(byKind("side"), 1)).toBe("Above 50%");
    expect(guessLabel(byKind("side"), 0)).toBe("Below 50%");
    expect(guessLabel(byKind("side"), 2)).toBe("");
    const versus = byKind("versus");
    expect(guessLabel(versus, 1)).toBe(versus.options[1].short);
    const four = byKind("four");
    expect(guessLabel(four, 2)).toBe(`${four.options[2]}%`);
    const leader = byKind("leader");
    expect(guessLabel(leader, 3)).toBe(leader.options[3].short);
    for (const set of [pack, sliders]) {
      expect(new Set(set.cards.map(kindLabel)).size).toBe(new Set(set.cards.map((c) => c.flavor)).size);
    }
  });
});

describe("/guess — the three steps", () => {
  it("knows which step a card is in and where each step starts and ends", () => {
    expect(pack.cards.map((_, i) => stepOf(pack, i))).toEqual([0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2]);
    expect(stepRange(pack, 0)).toEqual([0, 5]);
    expect(stepRange(pack, 2)).toEqual([10, 15]);
    expect([0, 1, 2].map((s) => stepIsTaps(pack, s))).toEqual([true, true, false]);
  });

  it("scores a step on its own: 'right of five' for taps, points for sliders, a dash when not played", () => {
    const ace = player("Ace", perfect);
    expect(stepScore(pack, ace, 0)).toEqual({ points: 50, right: 5, answered: 5, cards: 5 });
    expect(stepScore(pack, ace, 1)).toEqual({ points: 75, right: 5, answered: 5, cards: 5 });
    expect([0, 1, 2].map((s) => stepScoreLabel(pack, ace, s))).toEqual(["5 of 5", "5 of 5", "100"]);
    expect([0, 1, 2].map((s) => stepMax(pack, s))).toEqual([50, 75, 100]);
    // Four right on Easy, then stopped.
    const some = emptyEntry(pack, "Some", "here");
    pack.cards.slice(0, 5).forEach((card, i) => {
      some.guesses[i] = i === 2 ? hopeless(card) : perfect(card);
    });
    expect(stepScore(pack, some, 0)).toEqual({ points: 40, right: 4, answered: 5, cards: 5 });
    expect([0, 1, 2].map((s) => stepScoreLabel(pack, some, s))).toEqual(["4 of 5", "–", "–"]);
    // A slider seven off is 13 points and is not "right".
    const near = emptyEntry(pack, "Near", "here");
    const first = pack.cards[10];
    if (first.kind !== "chance") throw new Error("the Hard step starts with a slider");
    near.guesses[10] = first.answer + 7 > 100 ? first.answer - 7 : first.answer + 7;
    expect(stepScore(pack, near, 2)).toEqual({ points: 13, right: 0, answered: 1, cards: 5 });
    expect(stepScoreLabel(pack, near, 2)).toBe("13");
  });

  it("a player who loses overall can still win a step", () => {
    const easyOnly = player("Eve", (card, i) => (i < 5 ? perfect(card) : hopeless(card)));
    const rest = player("Rex", (card, i) => (i < 5 ? hopeless(card) : perfect(card)));
    expect(totalPoints(pack, rest)).toBeGreaterThan(totalPoints(pack, easyOnly));
    expect(stepWins(pack, [easyOnly, rest]).map((w) => w.names)).toEqual([["Eve"], ["Rex"], ["Rex"]]);
    const nobody = player("Zed", hopeless);
    expect(stepWins(pack, [nobody]).map((w) => w.names)).toEqual([[], [], []]);
    const tie = stepWins(pack, [player("A", perfect), player("B", perfect)]);
    expect(tie[0].names).toEqual(["A", "B"]);
    expect(tie.map((w) => w.points)).toEqual([50, 75, 100]);
  });

  it("says in one plain sentence who got a tap card", () => {
    expect(tapNote([], [])).toBe("");
    expect(tapNote(["Ann"], [true])).toBe("You got it.");
    expect(tapNote(["Ann"], [false])).toBe("Not this time.");
    expect(tapNote(["Ann", "Bo"], [true, true])).toBe("Everybody got it.");
    expect(tapNote(["Ann", "Bo"], [false, false])).toBe("Nobody got it.");
    expect(tapNote(["Ann", "Bo", "Cy"], [false, true, false])).toBe("Only Bo got it.");
    expect(tapNote(["Ann", "Bo", "Cy"], [true, true, false])).toBe("Everybody but Cy got it.");
    expect(tapNote(["Ann", "Bo", "Cy", "Di"], [true, true, false, false])).toBe("Ann and Bo got it.");
  });

  it("writes a time as a stopwatch does", () => {
    expect(timeLabel(0)).toBe("0:00");
    expect(timeLabel(42.4)).toBe("0:42");
    expect(timeLabel(67)).toBe("1:07");
    expect(timeLabel(-3)).toBe("0:00");
  });
});

describe("/guess — the Coin and the group", () => {
  it("the Coin leaves every slider in the middle", () => {
    for (const set of [pack, sliders]) {
      set.cards.forEach((card, i) => {
        if (isTap(card)) return;
        const g = coinGuess(set, i);
        expect(g).toBe(startGuess(card));
        if (card.kind === "chance") expect(g).toBe(50);
        if (card.kind === "count") expect(g).toBe(Math.round(card.max / 2));
        if (card.kind === "duo") expect(duoParts(g)).toEqual([50, 50]);
      });
    }
    expect(coinEntry(pack).from).toBe("house");
  });

  it("the Coin flips for every tap: a real option, the same one every time it is asked", () => {
    const taps = pack.cards.map((card, i) => ({ card, i })).filter((x) => isTap(x.card));
    for (const { card, i } of taps) {
      const g = coinGuess(pack, i);
      expect(isValidGuess(card, g)).toBe(true);
      expect(coinGuess(pack, i)).toBe(g);
      expect(startGuess(card)).toBeNull(); // a person starts with nothing tapped; the Coin does not
    }
    // It is a flip, not a habit: over the ten taps it does not always tap the first thing.
    expect(new Set(taps.map((x) => coinGuess(pack, x.i))).size).toBeGreaterThan(1);
    expect(coinEntry(pack).guesses.every((g) => g !== null)).toBe(true);
    // A set that carries no flips, or a flip that is not on the card, still gets a real option, the same every time.
    for (const coinTaps of [undefined, pack.cards.map(() => 9)]) {
      const bare = { ...pack, coinTaps };
      for (const { card, i } of taps) {
        const g = coinGuess(bare, i);
        expect(isValidGuess(card, g)).toBe(true);
        expect(coinGuess(bare, i)).toBe(g);
      }
    }
  });

  it("the group's guess is the average of every slider, each of a pair on its own", () => {
    expect(togetherGuess(byKind("chance"), [10, 20, 60])).toBe(30);
    expect(togetherGuess(byKind("count", sliders), [4, 9])).toBe(7);
    expect(togetherGuess(byKind("duo", sliders), [packDuo(90, 10), packDuo(70, 30)])).toBe(packDuo(80, 20));
    expect(togetherGuess(byKind("chance"), [])).toBeNull();
    expect(togetherGuess(byKind("chance"), [40, 999])).toBe(40);
  });

  it("on a tap card the group's guess is the most common tap, and a level vote goes to the earlier option", () => {
    const four = byKind("four");
    expect(togetherGuess(four, [2, 2, 1])).toBe(2);
    expect(togetherGuess(four, [3, 1])).toBe(1);
    expect(togetherGuess(four, [3, 3, 0, 0, 2])).toBe(0);
    expect(togetherGuess(four, [])).toBeNull();
    expect(togetherGuess(four, [9, 3])).toBe(3); // a tap that is not on the card is not counted
    expect(togetherGuess(byKind("side"), [1, 1, 0])).toBe(1);
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
    expect(report.best).toBe(225);
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
    expect(pack.topics).toContain("Sports");
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
  ann.ratings[12] = 5;
  ann.good[0] = true;
  ann.times = [31, 44.4, 97];
  ann.fun = 2;
  const n = pack.cards.length;
  const steps = pack.steps.length;
  const noTimes = "000".repeat(steps);

  it("round-trips names, guesses, ratings, marks, times and the favorite step, using only characters a chat keeps", () => {
    const fragment = encodeGroup(pack, [ann, bo, coinEntry(pack)]);
    expect(fragment).toMatch(/^g=[A-Za-z0-9%._=-]+$/);
    expect(fragment).toMatch(/[0-9a-zA-Z]$/);
    const back = decodeGroup(pack, `#${fragment}`);
    expect(back.ok).toBe(true);
    if (!back.ok) return;
    expect(back.players.map((p) => p.name)).toEqual(["Ann", "Bo ONeil-2"]);
    expect(back.players[0].guesses).toEqual(ann.guesses);
    expect(back.players[1].guesses).toEqual(bo.guesses);
    expect(back.players[0].ratings[12]).toBe(5);
    expect(back.players[0].good[0]).toBe(true);
    expect(back.players[0].times).toEqual([31, 44, 97]); // whole seconds travel
    expect(back.players[0].fun).toBe(2);
    expect(back.players[1].times).toEqual([0, 0, 0]);
    expect(back.players[1].fun).toBe(0);
    expect(back.players.every((p) => p.from === "link")).toBe(true);
  });

  it("carries both numbers of a two-number card, at every corner of the two sliders", () => {
    const at = sliders.cards.findIndex((c) => c.kind === "duo");
    for (const pair of [packDuo(0, 0), packDuo(100, 100), packDuo(0, 100), packDuo(100, 0), packDuo(63, 7)]) {
      const one = player("Dee", perfect, "here", sliders);
      one.guesses[at] = pair;
      const back = decodeGroup(sliders, encodeGroup(sliders, [one]));
      expect(back.ok && back.players[0].guesses[at]).toBe(pair);
    }
  });

  it("carries a game stopped after one step, so someone can send just Easy", () => {
    const half = player("Half", perfect);
    half.guesses = half.guesses.map((g, i) => (i < pack.perRound ? g : null));
    half.times = [38, 0, 0];
    const back = decodeGroup(pack, encodeGroup(pack, [half]));
    expect(back.ok && back.players[0].guesses).toEqual(half.guesses);
    expect(back.ok && back.players[0].times).toEqual([38, 0, 0]);
    expect(back.ok && stepScoreLabel(pack, back.players[0], 0)).toBe("5 of 5");
    expect(back.ok && stepScoreLabel(pack, back.players[0], 1)).toBe("–");
  });

  it("treats a link as data from a stranger: never throws, drops what is not valid", () => {
    expect(decodeGroup(pack, "")).toEqual({ ok: false, reason: "none" });
    expect(decodeGroup(pack, "#section")).toEqual({ ok: false, reason: "none" });
    expect(decodeGroup(pack, "#g=zz.Ann-000-0-0-000-0")).toEqual({ ok: false, reason: "other-edition" });
    // A link from an earlier set on this page: another code, and four fields a player.
    expect(decodeGroup(pack, `#g=b1.Ann-${"00a".repeat(14)}-${"1".repeat(14)}-${"0".repeat(14)}`)).toEqual({ ok: false, reason: "other-edition" });
    // That older shape under this set's code is not read as a player.
    expect(decodeGroup(pack, `#g=${pack.code}.Ann-${"001".repeat(n)}-${"0".repeat(n)}-${"0".repeat(n)}`)).toEqual({ ok: false, reason: "unreadable" });
    expect(decodeGroup(pack, `#g=${pack.code}.%E0%A4%A-xxx-0-0-000-0`)).toEqual({ ok: false, reason: "unreadable" });
    expect(decodeGroup(pack, `#g=${pack.code}.<script>-fff-9-9-zzz-9`)).toEqual({ ok: false, reason: "unreadable" });
    const wild = `#g=${pack.code}.${encodeURIComponent("<img src=x>")}-${"fff".repeat(n)}-${"9".repeat(n)}-${"7".repeat(n)}-${noTimes}-0`;
    expect(decodeGroup(pack, wild)).toEqual({ ok: false, reason: "unreadable" }); // every guess out of range
    const mixed = `#g=${pack.code}.${encodeURIComponent("<b>Eve</b>")}-${"001".repeat(n)}-${"9".repeat(n)}-${"1".repeat(n)}-${"zzz".repeat(steps)}-9`;
    const back = decodeGroup(pack, mixed);
    expect(back.ok).toBe(true);
    if (back.ok) {
      expect(back.players[0].name).toBe("bEveb");
      expect(back.players[0].ratings.every((r) => r === 0)).toBe(true);
      back.players[0].guesses.forEach((g) => expect(g === null || g === 1).toBe(true));
      // A time no step could honestly hold is cut to the most a step allows, and a step that does not exist is no vote.
      expect(back.players[0].times).toEqual([600, 600, 600]);
      expect(back.players[0].fun).toBe(0);
    }
    const crowd = `#g=${pack.code}.${Array.from({ length: 60 }, (_, i) => `P${i}-${"001".repeat(n)}-${"0".repeat(n)}-${"0".repeat(n)}-${noTimes}-0`).join(".")}`;
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
    expect(shareMessage([{ name: "Ann", points: 143 }], 96, "https://bainluck.com/guess#g=c1.x")).toBe(
      "I scored 143 on Guess the Chance. That beats a coin flip by 47. Your turn:\nhttps://bainluck.com/guess#g=c1.x",
    );
    expect(shareMessage([{ name: "Ann", points: 211 }], 140, "u", ["Easy 4 of 5", "Medium 3 of 5", "Hard 71"])).toBe(
      "I scored 211 on Guess the Chance (Easy 4 of 5, Medium 3 of 5, Hard 71). That beats a coin flip by 71. Your turn:\nu",
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

  it("writes a message for one step, so a person can send just that", () => {
    expect(stepShareMessage("Easy", true, 50, [{ name: "Ann", label: "4 of 5", points: 40 }], "u")).toBe("I got 4 of 5 on Easy in Guess the Chance. Your turn:\nu");
    expect(stepShareMessage("Hard", false, 100, [{ name: "Ann", label: "71", points: 71 }], "u")).toBe(
      "I scored 71 of 100 on Hard in Guess the Chance. Your turn:\nu",
    );
    expect(
      stepShareMessage(
        "Medium",
        true,
        75,
        [
          { name: "Ann", label: "2 of 5", points: 30 },
          { name: "Bo", label: "4 of 5", points: 60 },
        ],
        "u",
      ),
    ).toBe("We played Medium on Guess the Chance. Bo got 4 of 5. Your turn:\nu");
    expect(
      stepShareMessage(
        "Hard",
        false,
        100,
        [
          { name: "Ann", label: "58", points: 58 },
          { name: "Bo", label: "71", points: 71 },
        ],
        "u",
      ),
    ).toBe("We played Hard on Guess the Chance. Bo scored 71 of 100. Your turn:\nu");
    expect(stepShareMessage("Easy", true, 50, [], "u")).toBe("Guess the Chance, Easy. Your turn:\nu");
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
    // the player in last is above 5%. (Fourteen sliders, as that set was.)
    const scores = [
      [13, 20],
      [3, 0],
      [9, 0],
    ];
    const first = sliders.cards[0];
    const second = sliders.cards[1];
    if (first.kind !== "chance" || second.kind !== "chance") throw new Error("this test wants two chance cards first");
    const off = (answer: number, points: number) => (answer + (20 - points) <= 100 ? answer + (20 - points) : answer - (20 - points));
    const people = scores.map((s, i) => {
      const entry = emptyEntry(sliders, `P${i + 1}`, "here");
      entry.guesses[0] = off(first.answer, s[0]);
      entry.guesses[1] = off(second.answer, s[1]);
      return entry;
    });
    expect(people.map((p) => totalPoints(sliders, p))).toEqual([33, 3, 9]);
    const early = winChances(sliders, people, 2);
    expect(early[0]).toBeLessThan(0.85);
    expect(early[0]).toBeGreaterThan(0.5);
    expect(early[1]).toBeGreaterThan(0.05);
    expect(early[2]).toBeGreaterThan(early[1]);
  });

  it("someone who sent just one step is not played out as if they were still at the table", () => {
    // Dee came in a link with Easy only, five for five. Eli is here, two for five,
    // with ten cards still to play. Dee's game is over: she cannot add to fifty.
    const dee = emptyEntry(pack, "Dee", "link");
    const eli = emptyEntry(pack, "Eli", "here");
    pack.cards.slice(0, 5).forEach((card, i) => {
      dee.guesses[i] = perfect(card);
      eli.guesses[i] = i < 2 ? perfect(card) : hopeless(card);
    });
    const stopped = winChances(pack, [dee, eli], 5);
    const stillHere = winChances(pack, [{ ...dee, from: "here" }, eli], 5);
    expect(stillHere[0]).toBeGreaterThan(0.5); // thirty up, and playing on
    expect(stopped[0]).toBeLessThan(0.2); // thirty up, and finished: Eli needs thirty-one from ten cards
    expect(stopped[0] + stopped[1]).toBeCloseTo(1, 6);
    // Someone in a link who answered every card is still played out blind: nothing of theirs to come is read.
    const full = player("Ann", perfect, "link");
    const bo = player("Bo", hopeless);
    expect(winChances(pack, [full, bo], 5)).toEqual(winChances(pack, [{ ...full, guesses: full.guesses.map((g, i) => (i < 5 ? g : 0)) }, live(bo, 5)], 5));
  });

  it("a good Easy step is a lead, not a verdict: the taps say little about the sliders to come", () => {
    // Five for five against three for five: twenty points up with ten cards to
    // go, none of them the sort of card just played.
    const sharp = emptyEntry(pack, "Sharp", "here");
    const fair = emptyEntry(pack, "Fair", "here");
    pack.cards.slice(0, 5).forEach((card, i) => {
      sharp.guesses[i] = perfect(card);
      fair.guesses[i] = i < 3 ? perfect(card) : hopeless(card);
    });
    const afterEasy = winChances(pack, [sharp, fair], 5);
    expect(afterEasy[0]).toBeGreaterThan(0.55);
    expect(afterEasy[0]).toBeLessThan(0.9);
    // One card ahead after one card is close to level.
    const one = winChances(pack, [live(sharp, 1), { ...live(fair, 1), guesses: fair.guesses.map((g, i) => (i === 0 ? hopeless(pack.cards[0]) : null)) }], 1);
    expect(one[0]).toBeGreaterThan(0.5);
    expect(one[0]).toBeLessThan(0.7);
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
