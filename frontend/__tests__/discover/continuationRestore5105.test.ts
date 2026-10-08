/**
 * #5105 (thin supply) — a section deck survives the Back-restore snapshot.
 *
 * The snapshot (`lib/discover/feedRestore`) stores cards as JSON; the deck's
 * edition, global boundary, total and per-card server positions live in Maps
 * JSON drops. These pin the opt-in carriage (`lib/discover/continuationSnapshot`)
 * and that the legacy snapshot and scroll mark are byte-for-byte today's.
 *
 * Synthetic minimal fixtures: a card is `{ id, data }`, identity is the
 * caller's callback. The page is not wired.
 */
import {
  foldContinuationPage,
  partitionBySection,
  type ContinuationPageInput,
  type ContinuationSections as Sections,
} from "@/lib/discover/continuationSections";
import {
  FEED_SECTION_SNAPSHOT_VERSION,
  FEED_SNAPSHOT_KEY,
  FEED_SNAPSHOT_MAX_ITEMS,
  FEED_SNAPSHOT_VERSION,
  parseFeedSnapshot,
  parseScrollMark,
  readFeedSnapshot,
  serializeFeedSnapshot,
  serializeScrollMark,
  writeFeedSnapshot,
} from "@/lib/discover/feedRestore";

type Card = { id: string; data: { n: number } };
const getId = (card: Card) => card.id;
const ids = (cards: readonly Card[]) => cards.map(getId);

function deck(total: number): Card[] {
  return Array.from({ length: total }, (_, n) => ({ id: `c${n}`, data: { n } }));
}

function fold(prior: Sections<Card> | null, input: ContinuationPageInput<Card>): Sections<Card> {
  const result = foldContinuationPage(prior, input, getId);
  if (result.status !== "ok") throw new Error(`unexpected ${result.reason}`);
  return result.sections;
}

/** Fold `[offset, limit]` pages of `cards` into one section deck. */
function sectionDeck(cards: Card[], boundary: number, pages: Array<[number, number]>, edition = "ed-1"): Sections<Card> {
  let sections: Sections<Card> | null = null;
  for (const [offset, limit] of pages) {
    sections = fold(sections, {
      items: cards.slice(offset, offset + limit),
      offset,
      total: cards.length,
      edition,
      continuation_start: boundary,
    });
  }
  return sections!;
}

function positionsOf(sections: Sections<Card>): Record<string, number> {
  return Object.fromEntries(sections.positions);
}

const opt = { getId };

/** A stored section body to tamper with. */
function storedSection(): Record<string, any> {
  const cards = deck(10);
  const sections = sectionDeck(cards, 3, [[0, 5], [5, 5]]);
  const page1 = cards.slice(0, 5);
  const rest = [cards[6], cards[8]];
  return JSON.parse(serializeFeedSnapshot({ page1, rest, visibleCount: 20, hasMore: true }, { deck: sections, getId })!);
}

describe("#5105 legacy snapshot and scroll mark are unchanged", () => {
  const cards = deck(3);
  const legacy = { page1: [cards[0], cards[1]], rest: [cards[2]], visibleCount: 40, hasMore: false };
  const LEGACY_BYTES =
    '{"v":2,"page1":[{"id":"c0","data":{"n":0}},{"id":"c1","data":{"n":1}}],' +
    '"rest":[{"id":"c2","data":{"n":2}}],"visibleCount":40,"hasMore":false}';

  it("writes today's exact bytes with no section option, a null deck, or a legacy deck", () => {
    const legacyDeck = fold(null, { items: cards, offset: 0, total: 3 });
    expect(legacyDeck.boundary).toBeNull();
    expect(serializeFeedSnapshot(legacy)).toBe(LEGACY_BYTES);
    expect(serializeFeedSnapshot(legacy, { deck: null, getId })).toBe(LEGACY_BYTES);
    expect(serializeFeedSnapshot(legacy, { deck: legacyDeck, getId })).toBe(LEGACY_BYTES);
    expect(FEED_SNAPSHOT_VERSION).toBe(2);
  });

  it("round-trips a legacy edition through both readers; the section reader marks it legacy", () => {
    expect(parseFeedSnapshot<Card>(LEGACY_BYTES)).toEqual(legacy);
    expect(parseFeedSnapshot<Card>(LEGACY_BYTES, opt)).toEqual({ ...legacy, sections: null });
  });

  it("keeps the scroll mark's version and bytes", () => {
    const now = 1_700_000_000_000;
    const raw = serializeScrollMark({ scrollY: 4558, savedAt: now - 1000 });
    expect(raw).toBe(`{"v":2,"scrollY":4558,"savedAt":${now - 1000}}`);
    expect(parseScrollMark(raw, now)).toEqual({ scrollY: 4558, savedAt: now - 1000 });
  });
});

describe("#5105 a section deck round-trips with its boundary, positions and holes", () => {
  it("carries boundary 0 (the whole deck is continuation) with holes left as holes", () => {
    const cards = deck(8);
    const sections = sectionDeck(cards, 0, [[0, 4], [4, 4]]);
    // The page filtered c1, c4 and c5: the stored arrays are dense, the
    // positions are not.
    const page1 = [cards[0], cards[2], cards[3]];
    const rest = [cards[6], cards[7]];
    const raw = serializeFeedSnapshot({ page1, rest, visibleCount: 20, hasMore: false }, { deck: sections, getId })!;
    expect(JSON.parse(raw).v).toBe(FEED_SECTION_SNAPSHOT_VERSION);

    const restored = parseFeedSnapshot<Card>(raw, opt)!;
    expect(restored.page1).toEqual(page1);
    expect(restored.rest).toEqual(rest);
    const r = restored.sections!;
    expect(r.boundary).toBe(0);
    expect(r.edition).toBe("ed-1");
    expect(r.total).toBe(8);
    expect(positionsOf(r)).toEqual({ c0: 0, c2: 2, c3: 3, c6: 6, c7: 7 });
    expect(ids(r.opening)).toEqual([]);
    expect(ids(r.continuation)).toEqual(["c0", "c2", "c3", "c6", "c7"]);
  });

  it("keeps a mid-deck boundary and exact positions; membership is the adapter's", () => {
    const cards = deck(10);
    const sections = sectionDeck(cards, 3, [[0, 5], [5, 5]]);
    const page1 = [cards[0], cards[2], cards[4]];
    const rest = [cards[7], cards[9]];
    const raw = serializeFeedSnapshot({ page1, rest, visibleCount: 20, hasMore: true }, { deck: sections, getId })!;
    const r = parseFeedSnapshot<Card>(raw, opt)!.sections!;
    expect(r.boundary).toBe(3);
    expect(r.total).toBe(10);
    expect(positionsOf(r)).toEqual({ c0: 0, c2: 2, c4: 4, c7: 7, c9: 9 });
    expect(ids(r.opening)).toEqual(["c0", "c2"]);
    expect(ids(r.continuation)).toEqual(["c4", "c7", "c9"]);
    // Membership agrees with the deck it came from for every retained card.
    for (const card of [...page1, ...rest]) {
      expect(r.membership.get(card.id)).toBe(sections.membership.get(card.id));
    }
  });

  it("restores sections in server order whatever order the stored arrays hold", () => {
    const cards = deck(10);
    // Pages arrived offset 5 then offset 0, and the page appended in arrival order.
    const sections = sectionDeck(cards, 3, [[5, 5], [0, 5]]);
    const page1 = cards.slice(5, 10);
    const rest = cards.slice(0, 5);
    const r = parseFeedSnapshot<Card>(
      serializeFeedSnapshot({ page1, rest, visibleCount: 20, hasMore: false }, { deck: sections, getId })!,
      opt,
    )!.sections!;
    expect(ids(r.opening)).toEqual(ids(sections.opening));
    expect(ids(r.continuation)).toEqual(ids(sections.continuation));
  });

  it("keeps section membership stable when the first continuation card was removed", () => {
    const cards = deck(10);
    const sections = sectionDeck(cards, 3, [[0, 5], [5, 5]]);
    // c3 — the card AT the boundary — was filtered before the snapshot. The
    // boundary is not re-derived from it, so c4 is still continuation and
    // c2 still opening.
    const page1 = [cards[0], cards[1], cards[2], cards[4]];
    const rest = [cards[5], cards[6]];
    const r = parseFeedSnapshot<Card>(
      serializeFeedSnapshot({ page1, rest, visibleCount: 20, hasMore: true }, { deck: sections, getId })!,
      opt,
    )!.sections!;
    expect(r.boundary).toBe(3);
    expect(r.positions.has("c3")).toBe(false);
    const retained = [...page1, ...rest];
    expect(partitionBySection(retained, r, getId)).toEqual(partitionBySection(retained, sections, getId));
    expect(ids(partitionBySection(retained, r, getId).continuation)).toEqual(["c4", "c5", "c6"]);
  });

  it("accepts a card held twice at the same position (page one and the tail), once in the deck", () => {
    const cards = deck(10);
    const sections = sectionDeck(cards, 3, [[0, 5], [5, 5]]);
    const page1 = cards.slice(0, 5);
    const rest = [cards[4], cards[5]];
    const r = parseFeedSnapshot<Card>(
      serializeFeedSnapshot({ page1, rest, visibleCount: 20, hasMore: true }, { deck: sections, getId })!,
      opt,
    )!.sections!;
    expect(ids(r.continuation)).toEqual(["c3", "c4", "c5"]);
  });

  it("stores position evidence only — no card payload is duplicated", () => {
    const stored = storedSection();
    expect(Object.keys(stored.sections).sort()).toEqual(["boundary", "cards", "edition", "total"]);
    expect(stored.sections.cards).toEqual([["c0", 0], ["c1", 1], ["c2", 2], ["c3", 3], ["c4", 4], ["c6", 6], ["c8", 8]]);
  });

  it("hands back a deck the adapter keeps folding into, under the same edition only", () => {
    const cards = deck(10);
    const sections = sectionDeck(cards, 3, [[0, 5]]);
    const r = parseFeedSnapshot<Card>(
      serializeFeedSnapshot({ page1: cards.slice(0, 5), rest: [], visibleCount: 20, hasMore: true }, { deck: sections, getId })!,
      opt,
    )!.sections!;
    const next = { items: cards.slice(5, 10), offset: 5, total: 10, continuation_start: 3 };
    const more = foldContinuationPage(r, { ...next, edition: "ed-1" }, getId);
    expect(more.status).toBe("ok");
    if (more.status === "ok") expect(ids(more.sections.continuation)).toEqual(["c3", "c4", "c5", "c6", "c7", "c8", "c9"]);
    expect(foldContinuationPage(r, { ...next, edition: "ed-2" }, getId)).toEqual({
      status: "unsupported",
      reason: "edition_mismatch",
    });
  });
});

describe("#5105 the cap prunes the tail without renumbering or moving the boundary", () => {
  it("keeps global boundary and total, and the kept cards' own positions", () => {
    const cards = deck(250);
    const sections = sectionDeck(cards, 100, [[0, 20], [20, 100], [120, 100]]);
    const page1 = cards.slice(0, 20);
    const rest = cards.slice(20, 220);
    const raw = serializeFeedSnapshot({ page1, rest, visibleCount: 220, hasMore: true }, { deck: sections, getId })!;
    const stored = JSON.parse(raw);
    expect(stored.page1.length + stored.rest.length).toBe(FEED_SNAPSHOT_MAX_ITEMS);
    expect(stored.sections.cards).toHaveLength(FEED_SNAPSHOT_MAX_ITEMS);
    const r = parseFeedSnapshot<Card>(raw, opt)!.sections!;
    expect(r.boundary).toBe(100);
    expect(r.total).toBe(250);
    expect(r.positions.get("c119")).toBe(119);
    expect(r.membership.get("c99")).toBe("opening");
    expect(r.membership.get("c100")).toBe("continuation");
    expect(r.positions.has("c120")).toBe(false);
    expect(ids(r.continuation)).toEqual(ids(cards.slice(100, 120)));
  });
});

describe("#5105 contradictory or unbound evidence is refused, never guessed", () => {
  const cases: Array<[string, (s: Record<string, any>) => void]> = [
    ["an id that is not the stored card's", (s) => { s.sections.cards[1][0] = "c9"; }],
    ["two ids at one position", (s) => { s.sections.cards[1][1] = 0; }],
    ["one id at two positions", (s) => { s.rest.push(s.page1[0]); s.sections.cards.push(["c0", 7]); }],
    ["a position at or past total", (s) => { s.sections.cards[6][1] = 10; }],
    ["a fractional position", (s) => { s.sections.cards[6][1] = 8.5; }],
    ["a boundary at total", (s) => { s.sections.boundary = 10; }],
    ["a negative boundary", (s) => { s.sections.boundary = -1; }],
    ["a string boundary", (s) => { s.sections.boundary = "3"; }],
    ["a null boundary (a section body cannot be legacy)", (s) => { s.sections.boundary = null; }],
    ["an empty edition", (s) => { s.sections.edition = ""; }],
    ["a missing edition", (s) => { delete s.sections.edition; }],
    ["a missing total", (s) => { delete s.sections.total; }],
    ["an entry for a card that is not stored", (s) => { s.sections.cards.push(["c9", 9]); }],
    ["a stored card with no entry", (s) => { s.sections.cards.pop(); }],
    ["an entry of the wrong shape", (s) => { s.sections.cards[0] = { id: "c0", position: 0 }; }],
    ["an entry missing its position", (s) => { s.sections.cards[0] = ["c0"]; }],
    ["missing section evidence", (s) => { delete s.sections; }],
    ["null section evidence", (s) => { s.sections = null; }],
    ["array section evidence", (s) => { s.sections = []; }],
    ["a broken legacy field", (s) => { s.visibleCount = 0; }],
    ["a card the caller's getId cannot read", (s) => { s.rest[0] = null; }],
  ];

  it("starts from a body the section reader accepts", () => {
    expect(parseFeedSnapshot<Card>(JSON.stringify(storedSection()), opt)).not.toBeNull();
  });

  it.each(cases)("refuses %s", (_label, tamper) => {
    const stored = storedSection();
    tamper(stored);
    const readId = (card: Card) => card.id; // throws on a null card
    expect(parseFeedSnapshot<Card>(JSON.stringify(stored), { getId: readId })).toBeNull();
  });

  it("refuses a v2 body carrying section evidence in BOTH readers instead of reading it as legacy", () => {
    const stored = storedSection();
    stored.v = FEED_SNAPSHOT_VERSION;
    const raw = JSON.stringify(stored);
    expect(parseFeedSnapshot<Card>(raw, opt)).toBeNull();
    expect(parseFeedSnapshot<Card>(raw)).toBeNull();
    // The marker alone is enough — even null or empty section evidence.
    for (const sections of [null, {}, []]) {
      const marked = JSON.stringify({ ...stored, sections });
      expect(parseFeedSnapshot<Card>(marked)).toBeNull();
      expect(parseFeedSnapshot<Card>(marked, opt)).toBeNull();
    }
    // Strawman: the same body without the reserved field is an ordinary v2 edition.
    delete stored.sections;
    expect(parseFeedSnapshot<Card>(JSON.stringify(stored))).toEqual({
      page1: stored.page1,
      rest: stored.rest,
      visibleCount: 20,
      hasMore: true,
    });
  });

  it("refuses to encode when the caller's getId throws on a retained card", () => {
    const cards = deck(10);
    const sections = sectionDeck(cards, 3, [[0, 5]]);
    const readId = (card: Card) => card.id; // throws on a null card
    const page1 = cards.slice(0, 5);
    expect(() =>
      serializeFeedSnapshot({ page1, rest: [null as unknown as Card], visibleCount: 20, hasMore: true }, { deck: sections, getId: readId }),
    ).not.toThrow();
    expect(
      serializeFeedSnapshot({ page1, rest: [null as unknown as Card], visibleCount: 20, hasMore: true }, { deck: sections, getId: readId }),
    ).toBeNull();
  });

  it("will not write a section deck as legacy when a retained card has no recorded position", () => {
    const cards = deck(10);
    const sections = sectionDeck(cards, 3, [[0, 5]]);
    const stray: Card = { id: "synthetic", data: { n: -1 } };
    expect(
      serializeFeedSnapshot({ page1: cards.slice(0, 5), rest: [stray], visibleCount: 20, hasMore: true }, { deck: sections, getId }),
    ).toBeNull();
  });

  it("will not write a section deck that has no edition to bind it", () => {
    const cards = deck(10);
    const sections = { ...sectionDeck(cards, 3, [[0, 5]]), edition: null };
    expect(
      serializeFeedSnapshot({ page1: cards.slice(0, 5), rest: [], visibleCount: 20, hasMore: true }, { deck: sections, getId }),
    ).toBeNull();
  });
});

describe("#5105 a reader that has not opted in refuses a section edition", () => {
  it("returns the cold-load outcome rather than a flattened deck", () => {
    const raw = JSON.stringify(storedSection());
    expect(parseFeedSnapshot<Card>(raw)).toBeNull();
    // An older build's check is `v !== 2`; the section version can never pass it.
    expect(JSON.parse(raw).v).not.toBe(FEED_SNAPSHOT_VERSION);
  });
});

describe("#5105 storage wrappers", () => {
  let store: Map<string, string>;
  let ops: string[];
  let failSet: boolean;
  beforeEach(() => {
    store = new Map();
    ops = [];
    failSet = false;
    (globalThis as any).window = {
      sessionStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => {
          ops.push(`set:${k}`);
          if (failSet) throw new Error("QuotaExceededError");
          store.set(k, v);
        },
        removeItem: (k: string) => {
          ops.push(`remove:${k}`);
          store.delete(k);
        },
      },
    };
  });
  afterEach(() => {
    delete (globalThis as any).window;
  });

  /** Store an accepted section edition, then forget the calls that did it. */
  function acceptedSectionEdition(cards: Card[], sections: Sections<Card>): string {
    writeFeedSnapshot({ page1: cards.slice(0, 5), rest: [], visibleCount: 20, hasMore: true }, { deck: sections, getId });
    const before = store.get(FEED_SNAPSHOT_KEY);
    expect(JSON.parse(before!).v).toBe(FEED_SECTION_SNAPSHOT_VERSION);
    ops.length = 0;
    return before!;
  }

  it("writes and reads a section edition; the legacy read refuses it without touching storage", () => {
    const cards = deck(10);
    const sections = sectionDeck(cards, 3, [[0, 5]]);
    writeFeedSnapshot({ page1: cards.slice(0, 5), rest: [], visibleCount: 20, hasMore: true }, { deck: sections, getId });
    const raw = store.get(FEED_SNAPSHOT_KEY);
    expect(readFeedSnapshot<Card>()).toBeNull();
    expect(store.get(FEED_SNAPSHOT_KEY)).toBe(raw);
    expect(ids(readFeedSnapshot<Card>(opt)!.sections!.continuation)).toEqual(["c3", "c4"]);
  });

  it("an unbound retained card refuses the write and leaves the accepted edition's bytes untouched", () => {
    const cards = deck(10);
    const sections = sectionDeck(cards, 3, [[0, 5]]);
    const before = acceptedSectionEdition(cards, sections);
    const stray: Card = { id: "synthetic", data: { n: -1 } };
    writeFeedSnapshot({ page1: cards.slice(0, 5), rest: [stray], visibleCount: 20, hasMore: true }, { deck: sections, getId });
    expect(ops).toEqual([]);
    expect(store.get(FEED_SNAPSHOT_KEY)).toBe(before);
  });

  it("an unbound retained card leaves an older legacy edition untouched too", () => {
    const cards = deck(10);
    writeFeedSnapshot({ page1: cards.slice(0, 2), rest: [], visibleCount: 20, hasMore: true });
    const before = store.get(FEED_SNAPSHOT_KEY);
    ops.length = 0;
    const sections = sectionDeck(cards, 3, [[0, 5]]);
    const stray: Card = { id: "synthetic", data: { n: -1 } };
    writeFeedSnapshot({ page1: cards.slice(0, 5), rest: [stray], visibleCount: 20, hasMore: true }, { deck: sections, getId });
    expect(ops).toEqual([]);
    expect(store.get(FEED_SNAPSHOT_KEY)).toBe(before);
  });

  it("a malformed retained card whose getId throws refuses without deleting the accepted edition", () => {
    const cards = deck(10);
    const sections = sectionDeck(cards, 3, [[0, 5]]);
    const before = acceptedSectionEdition(cards, sections);
    const readId = (card: Card) => card.id; // throws on a null card
    expect(() =>
      writeFeedSnapshot(
        { page1: cards.slice(0, 5), rest: [null as unknown as Card], visibleCount: 20, hasMore: true },
        { deck: sections, getId: readId },
      ),
    ).not.toThrow();
    expect(ops).toEqual([]);
    expect(store.get(FEED_SNAPSHOT_KEY)).toBe(before);
  });

  it("a getId that throws on a well-formed card is also a refusal, not a storage failure", () => {
    const cards = deck(10);
    const sections = sectionDeck(cards, 3, [[0, 5]]);
    const before = acceptedSectionEdition(cards, sections);
    const explode = (card: Card) => {
      if (card.id === "c4") throw new Error("unreadable");
      return card.id;
    };
    writeFeedSnapshot({ page1: cards.slice(0, 5), rest: [], visibleCount: 20, hasMore: true }, { deck: sections, getId: explode });
    expect(ops).toEqual([]);
    expect(store.get(FEED_SNAPSHOT_KEY)).toBe(before);
  });

  it("a genuine failed setItem on a section write still drops the edition (quota cleanup kept)", () => {
    const cards = deck(10);
    const sections = sectionDeck(cards, 3, [[0, 5]]);
    acceptedSectionEdition(cards, sections);
    failSet = true;
    writeFeedSnapshot({ page1: cards.slice(0, 5), rest: [], visibleCount: 20, hasMore: false }, { deck: sections, getId });
    expect(ops).toEqual([`set:${FEED_SNAPSHOT_KEY}`, `remove:${FEED_SNAPSHOT_KEY}`]);
    expect(store.has(FEED_SNAPSHOT_KEY)).toBe(false);
  });

  it("a genuine failed setItem on a legacy write still drops the edition (today's behaviour)", () => {
    const cards = deck(10);
    writeFeedSnapshot({ page1: cards.slice(0, 2), rest: [], visibleCount: 20, hasMore: true });
    ops.length = 0;
    failSet = true;
    writeFeedSnapshot({ page1: cards.slice(0, 3), rest: [], visibleCount: 20, hasMore: true });
    expect(ops).toEqual([`set:${FEED_SNAPSHOT_KEY}`, `remove:${FEED_SNAPSHOT_KEY}`]);
    expect(store.has(FEED_SNAPSHOT_KEY)).toBe(false);
  });

  it("a legacy write stores today's exact bytes with one setItem", () => {
    const cards = deck(10);
    const legacy = { page1: cards.slice(0, 2), rest: [cards[2]], visibleCount: 20, hasMore: true };
    writeFeedSnapshot(legacy);
    writeFeedSnapshot(legacy, { deck: null, getId });
    expect(ops).toEqual([`set:${FEED_SNAPSHOT_KEY}`, `set:${FEED_SNAPSHOT_KEY}`]);
    expect(store.get(FEED_SNAPSHOT_KEY)).toBe(JSON.stringify({ v: FEED_SNAPSHOT_VERSION, ...legacy }));
    expect(readFeedSnapshot<Card>()).toEqual(legacy);
  });

  it("keeps today's empty-page-one no-op", () => {
    const cards = deck(10);
    writeFeedSnapshot({ page1: cards.slice(0, 2), rest: [], visibleCount: 20, hasMore: true });
    const before = store.get(FEED_SNAPSHOT_KEY);
    ops.length = 0;
    writeFeedSnapshot({ page1: [], rest: [], visibleCount: 20, hasMore: true });
    writeFeedSnapshot({ page1: [], rest: [], visibleCount: 20, hasMore: true }, { deck: sectionDeck(cards, 3, [[0, 5]]), getId });
    expect(ops).toEqual([]);
    expect(store.get(FEED_SNAPSHOT_KEY)).toBe(before);
  });

  it("the default reader refuses a stored v2 body carrying section evidence", () => {
    const stored = storedSection();
    stored.v = FEED_SNAPSHOT_VERSION;
    store.set(FEED_SNAPSHOT_KEY, JSON.stringify(stored));
    expect(readFeedSnapshot<Card>()).toBeNull();
    expect(readFeedSnapshot<Card>(opt)).toBeNull();
  });
});
