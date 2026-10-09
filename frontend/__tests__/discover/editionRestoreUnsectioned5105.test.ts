/**
 * #5105 — a TOKENED deck the server drew no continuation for keeps its edition
 * and raw cursor through the Back-restore snapshot (`FEED_EDITION_SNAPSHOT_VERSION`).
 *
 * The page records such a deck's raw positions itself (the adapter records none
 * without a boundary — `hooks/useDiscoverOpeningEdition`); here the deck is
 * built the same way. Only a section-aware writer that passes the raw cursor
 * produces the new body; everything else stays today's v2 bytes, and every
 * reader that did not opt in refuses it.
 */
import { foldContinuationPage, type ContinuationSections as Sections } from "@/lib/discover/continuationSections";
import {
  FEED_EDITION_SNAPSHOT_VERSION,
  FEED_SECTION_SNAPSHOT_VERSION,
  FEED_SNAPSHOT_KEY,
  FEED_SNAPSHOT_MAX_ITEMS,
  FEED_SNAPSHOT_VERSION,
  parseFeedSnapshot,
  readFeedSnapshot,
  serializeFeedSnapshot,
  writeFeedSnapshot,
} from "@/lib/discover/feedRestore";

type Card = { id: string };
const getId = (card: Card) => card.id;
const cards = (n: number) => Array.from({ length: n }, (_, i) => ({ id: `c${i}` }));
const opt = { getId };

/** A tokened deck without a section, received in 20-card pages, positions recorded as the page does. */
function tokenedDeck(all: Card[], received: number, edition: string | null = "ed-1"): Sections<Card> {
  let deck: Sections<Card> | null = null;
  const positions = new Map<string, number>();
  for (let offset = 0; offset < received; offset += 20) {
    const items = all.slice(offset, Math.min(offset + 20, received));
    const result = foldContinuationPage(deck, { items, offset, total: all.length, ...(edition ? { edition } : {}) }, getId);
    if (result.status !== "ok") throw new Error(result.reason);
    items.forEach((item, i) => { if (!positions.has(item.id)) positions.set(item.id, offset + i); });
    deck = result.sections;
  }
  return { ...deck!, positions };
}

const stored = (raw: string | null) => JSON.parse(raw!);

describe("#5105 a tokened deck without a section is written only on the explicit opt-in", () => {
  it("with its raw cursor it is stored under the edition version and read back with token and cursor", () => {
    const all = cards(40);
    const deck = tokenedDeck(all, 20);
    const raw = serializeFeedSnapshot({ page1: all.slice(0, 20), rest: [], visibleCount: 20, hasMore: true }, { deck, cursor: 20, getId });
    const body = stored(raw);
    expect(body.v).toBe(FEED_EDITION_SNAPSHOT_VERSION);
    expect(body.cursor).toBe(20);
    expect(body.sections).toEqual({ boundary: null, edition: "ed-1", total: 40, cards: all.slice(0, 20).map((c, i) => [c.id, i]) });
    const read = parseFeedSnapshot<Card>(raw, opt)!;
    expect(read.cursor).toBe(20);
    expect(read.hasMore).toBe(true);
    expect(read.sections!.boundary).toBeNull();
    expect(read.sections!.edition).toBe("ed-1");
    expect(read.sections!.positions.get("c19")).toBe(19);
    expect(read.sections!.continuation).toEqual([]);
  });

  it("without a cursor, the same deck still writes today's v2 bytes", () => {
    const all = cards(40);
    const snap = { page1: all.slice(0, 20), rest: [], visibleCount: 20, hasMore: true };
    expect(serializeFeedSnapshot(snap, { deck: tokenedDeck(all, 20), getId })).toBe(serializeFeedSnapshot(snap));
  });

  it("an untokened deck with a cursor still writes today's v2 bytes", () => {
    const all = cards(20);
    const snap = { page1: all, rest: [], visibleCount: 20, hasMore: false };
    expect(serializeFeedSnapshot(snap, { deck: tokenedDeck(all, 20, null), cursor: 20, getId })).toBe(serializeFeedSnapshot(snap));
    expect(stored(serializeFeedSnapshot(snap)).v).toBe(FEED_SNAPSHOT_VERSION);
  });

  it("the default reader refuses it (a cold load), as it refuses a section edition", () => {
    const all = cards(40);
    const raw = serializeFeedSnapshot({ page1: all.slice(0, 20), rest: [], visibleCount: 20, hasMore: true }, { deck: tokenedDeck(all, 20), cursor: 20, getId });
    expect(parseFeedSnapshot<Card>(raw)).toBeNull();
  });

  it("an exhausted 160-card deck capped at 120 resumes at 120 with more to fetch", () => {
    const all = cards(160);
    const deck = tokenedDeck(all, 160);
    const raw = serializeFeedSnapshot({ page1: all.slice(0, 20), rest: all.slice(20), visibleCount: 160, hasMore: false }, { deck, cursor: 160, getId });
    const body = stored(raw);
    expect(body.page1.length + body.rest.length).toBe(FEED_SNAPSHOT_MAX_ITEMS);
    expect(body.cursor).toBe(120);
    expect(body.hasMore).toBe(true);
  });

  it("a retained card with no recorded position refuses the write", () => {
    const all = cards(40);
    const deck = tokenedDeck(all, 20);
    expect(serializeFeedSnapshot({ page1: all.slice(0, 21), rest: [], visibleCount: 20, hasMore: true }, { deck, cursor: 20, getId })).toBeNull();
  });
});

describe("#5105 a stored edition body that is malformed or does not bind is refused", () => {
  const base = (): Record<string, any> => {
    const all = cards(40);
    return stored(serializeFeedSnapshot({ page1: all.slice(0, 20), rest: [], visibleCount: 20, hasMore: true }, { deck: tokenedDeck(all, 20), cursor: 20, getId }));
  };

  it("starts from a body the section-aware reader accepts", () => {
    expect(parseFeedSnapshot<Card>(JSON.stringify(base()), opt)!.cursor).toBe(20);
  });

  it.each<[string, (b: Record<string, any>) => void]>([
    ["a missing cursor", (b) => { delete b.cursor; }],
    ["a cursor past total", (b) => { b.cursor = 41; }],
    ["a string cursor", (b) => { b.cursor = "20"; }],
    ["a boundary (section evidence under the edition version)", (b) => { b.sections.boundary = 3; }],
    ["a missing edition", (b) => { b.sections.edition = ""; }],
    ["a card id that is not the stored card's", (b) => { b.sections.cards[4][0] = "c99"; }],
    ["two ids at one position", (b) => { b.sections.cards[5][1] = 4; }],
    ["one id at two positions", (b) => { b.rest = [b.page1[2]]; b.sections.cards.push(["c2", 30]); }],
    ["a position at or past total", (b) => { b.sections.cards[0][1] = 40; }],
    ["evidence shorter than the cards", (b) => { b.sections.cards.pop(); }],
    ["a broken legacy field", (b) => { b.visibleCount = 0; }],
  ])("refuses %s", (_label, tamper) => {
    const body = base();
    tamper(body);
    expect(parseFeedSnapshot<Card>(JSON.stringify(body), opt)).toBeNull();
  });

  it("a section body with a null boundary is still refused (it does not read as an edition body)", () => {
    const body = base();
    body.v = FEED_SECTION_SNAPSHOT_VERSION;
    expect(parseFeedSnapshot<Card>(JSON.stringify(body), opt)).toBeNull();
  });

  it("a v2 body carrying the edition evidence is refused by both readers", () => {
    const body = base();
    body.v = FEED_SNAPSHOT_VERSION;
    expect(parseFeedSnapshot<Card>(JSON.stringify(body))).toBeNull();
    expect(parseFeedSnapshot<Card>(JSON.stringify(body), opt)).toBeNull();
  });
});

describe("#5105 the edition write's storage behaviour (sessionStorage wrappers)", () => {
  let store: Map<string, string>;
  let ops: string[];
  beforeEach(() => {
    store = new Map();
    ops = [];
    (globalThis as any).window = {
      sessionStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => { ops.push(`set:${k}`); store.set(k, v); },
        removeItem: (k: string) => { ops.push(`remove:${k}`); store.delete(k); },
      },
    };
  });
  afterEach(() => {
    delete (globalThis as any).window;
  });

  it("writes and reads it; the default reader refuses it without touching storage", () => {
    const all = cards(40);
    writeFeedSnapshot({ page1: all.slice(0, 20), rest: [], visibleCount: 20, hasMore: true }, { deck: tokenedDeck(all, 20), cursor: 20, getId });
    const raw = store.get(FEED_SNAPSHOT_KEY);
    expect(stored(raw!).v).toBe(FEED_EDITION_SNAPSHOT_VERSION);
    ops.length = 0;
    expect(readFeedSnapshot<Card>()).toBeNull();
    expect(ops).toEqual([]);
    expect(readFeedSnapshot<Card>(opt)!.sections!.edition).toBe("ed-1");
  });

  it("a refused write leaves the stored edition's bytes untouched", () => {
    const all = cards(40);
    const deck = tokenedDeck(all, 20);
    writeFeedSnapshot({ page1: all.slice(0, 20), rest: [], visibleCount: 20, hasMore: true }, { deck, cursor: 20, getId });
    const before = store.get(FEED_SNAPSHOT_KEY);
    ops.length = 0;
    const stray = { id: "synthetic" };
    writeFeedSnapshot({ page1: all.slice(0, 20), rest: [stray], visibleCount: 20, hasMore: true }, { deck, cursor: 20, getId });
    expect(ops).toEqual([]);
    expect(store.get(FEED_SNAPSHOT_KEY)).toBe(before);
  });
});
