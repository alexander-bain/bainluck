/**
 * #5973 — THE RAIL PREFERS CARDS THAT NAME A SIDE OF THIS MATCH.
 *
 * The unit half. `__tests__/components/relatedByTagParticipantOrder5973.test.tsx`
 * pins what the rail DRAWS on a real production payload; this file pins the
 * ordering rule itself, and in particular the three ways it is allowed to do
 * nothing.
 *
 * The rule's safety property is that it is a SORT. #8093 — in this same
 * component, two days ago — is the cautionary case: narrowing the rail's query
 * by league was right for basketball and emptied the section on every Champions
 * League tie and every Grand Slam match page. A stable partition cannot lose an
 * item, cannot duplicate one, and cannot change how many there are, so the
 * worst case on any page is the order it already had. Those three invariants
 * are asserted directly rather than inferred from the happy path.
 */

import {
  cardNamesParticipant,
  cardPrintedText,
  normalizeForMatch,
  orderByParticipant,
  participantNames,
} from "@/lib/railParticipantOrder";
import type { FeedItem } from "@/lib/types";

/** A futures card carrying a name and the outcomes it prints. */
const futures = (name: string, outcomes: string[] = []): FeedItem =>
  ({
    type: "futures",
    data: {
      id: Math.floor(Math.random() * 1e6),
      name,
      top_outcomes: outcomes.map((n, i) => ({
        name: n,
        probability: 0.5 - i * 0.01,
      })),
    },
  }) as unknown as FeedItem;

const game = (away: string, home: string): FeedItem =>
  ({ type: "event", data: { id: 1, away_team: away, home_team: home } }) as unknown as FeedItem;

const concept = (name: string, leader?: string): FeedItem =>
  ({
    type: "concept",
    data: { key: "k", name, leader: leader ? { name: leader, probability: 0.4 } : null },
  }) as unknown as FeedItem;

const names = (items: FeedItem[]) =>
  items.map((i) => (i.data as { name?: string }).name ?? "game");

describe("participantNames", () => {
  it("folds both sides to comparable words", () => {
    expect(participantNames("Detroit Tigers", "Washington Nationals")).toEqual([
      "detroit tigers",
      "washington nationals",
    ]);
  });

  it("drops a side that is absent or blank rather than yielding an empty needle", () => {
    // An empty needle would match every card, which is the failure mode that
    // turns a preference into a shuffle.
    expect(participantNames("Detroit Tigers", null)).toEqual(["detroit tigers"]);
    expect(participantNames("   ", undefined)).toEqual([]);
  });

  it("drops a name too short to be evidence of anything", () => {
    /* MEASURED: `teams` carries 1,147 single-word names and the short end is
       `OTR · Tau · IPK · PSG · UAE · GAS · USA · TBD`. `TBD` is the placeholder
       an unscheduled fixture carries — promoting on it would lift every card
       that happens to say the same. Only 19 of 10,011 names are 3 characters,
       so the floor costs almost nothing. */
    expect(participantNames("TBD", "TBD")).toEqual([]);
    expect(participantNames("Tau", "GAS")).toEqual([]);
    // Four characters is a real club and keeps its boost.
    expect(participantNames("Nice", "Lyon")).toEqual(["nice", "lyon"]);
  });

  it("normalizes punctuation so a trademark or colon cannot block a match", () => {
    expect(normalizeForMatch("Stanley Cup® Finals")).toBe("stanley cup finals");
    expect(normalizeForMatch("Novak Djokovic: Retirement")).toBe("novak djokovic retirement");
  });
});

describe("cardPrintedText — only what the reader can see", () => {
  it("reads a futures card's name and its printed outcomes", () => {
    const text = cardPrintedText(futures("AL Central Champion", ["Detroit Tigers", "Cleveland Guardians"]));
    expect(text).toBe("al central champion detroit tigers cleveland guardians");
  });

  it("stops at the four outcomes the card actually prints", () => {
    /* `RelatedByTag`'s MAX_FIELD_ROWS is 4. A card promoted for the 57th
       outcome of `NBA Finals MVP Winner` would look to a reader like an
       arbitrary shuffle, because the name it was promoted for is not on it. */
    const card = futures("Big Field", ["A", "B", "C", "D", "Detroit Tigers"]);
    expect(cardPrintedText(card)).not.toContain("detroit tigers");
  });

  it("ignores an unpriced outcome, which the card also drops", () => {
    const card = {
      type: "futures",
      data: {
        id: 2,
        name: "Field",
        top_outcomes: [
          { name: "Detroit Tigers", probability: null },
          { name: "Cleveland Guardians", probability: 0.3 },
        ],
      },
    } as unknown as FeedItem;
    expect(cardPrintedText(card)).toBe("field cleveland guardians");
  });

  it("reads a game card's two sides and a concept's leader", () => {
    expect(cardPrintedText(game("New York Giants", "Los Angeles Rams"))).toBe(
      "new york giants los angeles rams"
    );
    expect(cardPrintedText(concept("UFC 332", "Alex Pereira"))).toBe("ufc 332 alex pereira");
  });
});

describe("cardNamesParticipant — whole words only", () => {
  it("matches a side named in the title or in a printed outcome", () => {
    const n = participantNames("Detroit Tigers", "Washington Nationals");
    expect(cardNamesParticipant(futures("AL Central Champion", ["Detroit Tigers"]), n)).toBe(true);
    expect(cardNamesParticipant(futures("Detroit Tigers: Win Total"), n)).toBe(true);
  });

  it("does not match a needle sitting INSIDE a longer word", () => {
    /* The real collision, and the reason the word boundary is load-bearing
       rather than defensive: `Como` is a Serie A club, `Comoros` is a national
       side that turns up in the same soccer feeds. A substring test puts an
       Africa Cup market on a Como fixture.

       A single-word needle is not a corner case — 1,147 of the 10,011 names in
       `teams` are one word (`Nice`, `Lyon`, `León`, `Vado`, `Boom`). */
    const como = participantNames("Como", "Lazio");
    expect(cardNamesParticipant(futures("Comoros to win the Africa Cup of Nations?"), como)).toBe(
      false
    );
    expect(cardNamesParticipant(futures("Group F Winner", ["Comoros", "Morocco"]), como)).toBe(false);
    // …and still matches the club itself, so the guard has not simply broken it.
    expect(cardNamesParticipant(futures("Serie A Winner", ["Como", "Napoli"]), como)).toBe(true);
  });

  it("declines a partial team name rather than guessing", () => {
    /* Measured on the captured MLB payload: `National League Champion` prints
       the outcome `Milwaukee`, not `Milwaukee Brewers`. Conservative by
       choice — a false promotion is visible to a reader and a missed one is
       just today's order. */
    const n = participantNames("Milwaukee Brewers", "Philadelphia Phillies");
    expect(cardNamesParticipant(futures("National League Champion", ["Milwaukee"]), n)).toBe(false);
  });

  it("is false for every card when there are no participants", () => {
    expect(cardNamesParticipant(futures("Anything", ["Detroit Tigers"]), [])).toBe(false);
  });
});

describe("orderByParticipant", () => {
  it("lifts naming cards above the rest", () => {
    const items = [
      futures("World Series Winner", ["Los Angeles Dodgers"]),
      futures("AL Platinum Glove"),
      futures("AL Central Champion", ["Detroit Tigers"]),
    ];
    expect(names(orderByParticipant(items, participantNames("Detroit Tigers", null)))).toEqual([
      "AL Central Champion",
      "World Series Winner",
      "AL Platinum Glove",
    ]);
  });

  it("keeps the feed's own rank WITHIN each group", () => {
    /* A stable partition, not a comparator: this adds a preference to the
       server's ordering instead of replacing it. */
    const items = [
      futures("hit A", ["Detroit Tigers"]),
      futures("miss A"),
      futures("hit B", ["Detroit Tigers"]),
      futures("miss B"),
    ];
    expect(names(orderByParticipant(items, participantNames("Detroit Tigers", null)))).toEqual([
      "hit A",
      "hit B",
      "miss A",
      "miss B",
    ]);
  });

  it("NEVER loses, duplicates or adds an item", () => {
    const items = [
      futures("a", ["Detroit Tigers"]),
      futures("b"),
      game("Detroit Tigers", "Cleveland Guardians"),
      concept("c"),
    ];
    const out = orderByParticipant(items, participantNames("Detroit Tigers", null));
    expect(out).toHaveLength(items.length);
    /* BY REFERENCE, exactly once each. `[...out].sort()` was the first draft of
       this line and it is a tied sort: the default comparator coerces every
       object to `"[object Object]"`, so it compares nothing and the assertion
       passes or fails on insertion order rather than on membership. */
    for (const item of items) {
      expect(out.filter((candidate) => candidate === item)).toHaveLength(1);
    }
  });

  // ── the three ways it must do nothing ──────────────────────────────────
  it("returns the input untouched when there are no participants", () => {
    const items = [futures("a"), futures("b")];
    expect(orderByParticipant(items, [])).toBe(items);
  });

  it("returns the input untouched when nothing matches", () => {
    const items = [futures("a"), futures("b")];
    expect(orderByParticipant(items, participantNames("Detroit Tigers", null))).toBe(items);
  });

  it("returns the input untouched when EVERYTHING matches", () => {
    const items = [futures("a", ["Detroit Tigers"]), futures("Detroit Tigers win total")];
    expect(orderByParticipant(items, participantNames("Detroit Tigers", null))).toBe(items);
  });

  it("is a no-op on a rail of one", () => {
    const items = [futures("only")];
    expect(orderByParticipant(items, participantNames("Detroit Tigers", null))).toBe(items);
  });
});
