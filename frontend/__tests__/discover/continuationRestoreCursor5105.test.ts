/**
 * #5105 — the opt-in resume cursor a section edition carries through the
 * Back-restore snapshot (`lib/discover/feedRestore`, `FeedSectionWrite`).
 *
 * The snapshot keeps the first `FEED_SNAPSHOT_MAX_ITEMS` cards. The cursor it
 * stores is the deck's raw server cursor, moved back to the lowest position the
 * deck received but did not keep — so a restore never skips a dropped card and
 * never strands one behind an old `hasMore: false`.
 */
import { foldContinuationPage, type ContinuationSections as Sections } from "@/lib/discover/continuationSections";
import {
  FEED_SECTION_SNAPSHOT_VERSION,
  FEED_SNAPSHOT_MAX_ITEMS,
  parseFeedSnapshot,
  serializeFeedSnapshot,
} from "@/lib/discover/feedRestore";

type Card = { id: string };
const getId = (card: Card) => card.id;
const cards = (n: number) => Array.from({ length: n }, (_, i) => ({ id: `c${i}` }));

function sectionDeck(all: Card[], boundary: number, received: number, edition = "ed-1"): Sections<Card> {
  let deck: Sections<Card> | null = null;
  for (let offset = 0; offset < received; offset += 20) {
    const result = foldContinuationPage(deck, {
      items: all.slice(offset, Math.min(offset + 20, received)),
      offset,
      total: all.length,
      edition,
      continuation_start: boundary,
    }, getId);
    if (result.status !== "ok") throw new Error(result.reason);
    deck = result.sections;
  }
  return deck!;
}

function stored(raw: string | null) {
  return JSON.parse(raw!);
}

describe("#5105 the cursor is optional and opt-in", () => {
  it("without a cursor the section bytes are exactly the existing section edition", () => {
    const all = cards(40);
    const deck = sectionDeck(all, 3, 40);
    const raw = serializeFeedSnapshot({ page1: all.slice(0, 20), rest: all.slice(20), visibleCount: 40, hasMore: false }, { deck, getId });
    expect("cursor" in stored(raw)).toBe(false);
    const read = parseFeedSnapshot<Card>(raw, { getId })!;
    expect(read.cursor).toBeUndefined();
    expect(read.sections).not.toBeNull();
  });

  it("a legacy deck with a cursor still writes today's v2 bytes", () => {
    const all = cards(20);
    const legacy = foldContinuationPage(null, { items: all, offset: 0, total: 20 }, getId);
    if (legacy.status !== "ok") throw new Error(legacy.reason);
    const snap = { page1: all, rest: [], visibleCount: 20, hasMore: true };
    expect(serializeFeedSnapshot(snap, { deck: legacy.sections, cursor: 20, getId })).toBe(serializeFeedSnapshot(snap));
  });
});

describe("#5105 the stored cursor is the retained frontier", () => {
  it("keeps the deck's own cursor and hasMore when every received card was kept", () => {
    const all = cards(60);
    const deck = sectionDeck(all, 3, 40);
    const raw = serializeFeedSnapshot({ page1: all.slice(0, 20), rest: all.slice(20, 40), visibleCount: 40, hasMore: true }, { deck, cursor: 40, getId });
    const read = parseFeedSnapshot<Card>(raw, { getId })!;
    expect(stored(raw).v).toBe(FEED_SECTION_SNAPSHOT_VERSION);
    expect(read.cursor).toBe(40);
    expect(read.hasMore).toBe(true);
  });

  it("an exhausted 160-card deck capped at 120 resumes at 120 with more to fetch", () => {
    const all = cards(160);
    const deck = sectionDeck(all, 5, 160);
    const raw = serializeFeedSnapshot({ page1: all.slice(0, 20), rest: all.slice(20), visibleCount: 160, hasMore: false }, { deck, cursor: 160, getId });
    const s = stored(raw);
    expect(s.page1.length + s.rest.length).toBe(FEED_SNAPSHOT_MAX_ITEMS);
    // Not the old cursor (skips c120..c159) and not the old hasMore (strands them).
    expect(s.cursor).toBe(120);
    expect(s.hasMore).toBe(true);
    const read = parseFeedSnapshot<Card>(raw, { getId })!;
    expect(read.cursor).toBe(120);
    expect(read.sections!.positions.has("c120")).toBe(false);
  });

  it("a received card the caller did not keep moves the cursor back, never forward", () => {
    const all = cards(40);
    const deck = sectionDeck(all, 3, 40);
    const kept = all.filter((c) => c.id !== "c27");
    const raw = serializeFeedSnapshot({ page1: kept.slice(0, 20), rest: kept.slice(20), visibleCount: 40, hasMore: false }, { deck, cursor: 40, getId });
    expect(stored(raw).cursor).toBe(27);
    expect(stored(raw).hasMore).toBe(true);
  });

  it.each([
    ["past total", 41],
    ["negative", -1],
    ["fractional", 12.5],
  ])("refuses to write a cursor that is %s", (_label, cursor) => {
    const all = cards(40);
    const deck = sectionDeck(all, 3, 40);
    expect(serializeFeedSnapshot({ page1: all.slice(0, 20), rest: all.slice(20), visibleCount: 40, hasMore: false }, { deck, cursor, getId })).toBeNull();
  });
});

describe("#5105 a stored cursor that is not a raw offset of the deck refuses the edition", () => {
  const base = () => {
    const all = cards(40);
    const deck = sectionDeck(all, 3, 40);
    return stored(serializeFeedSnapshot({ page1: all.slice(0, 20), rest: all.slice(20), visibleCount: 40, hasMore: false }, { deck, cursor: 40, getId }));
  };

  it("starts from a body the section reader accepts", () => {
    expect(parseFeedSnapshot<Card>(JSON.stringify(base()), { getId })!.cursor).toBe(40);
  });

  it.each([
    ["past total", 41],
    ["negative", -1],
    ["a string", "40"],
    ["null", null],
    ["fractional", 3.5],
  ])("refuses a cursor that is %s", (_label, cursor) => {
    const body = base();
    body.cursor = cursor;
    expect(parseFeedSnapshot<Card>(JSON.stringify(body), { getId })).toBeNull();
  });

  it("the default reader refuses the section edition, cursor or not", () => {
    expect(parseFeedSnapshot<Card>(JSON.stringify(base()))).toBeNull();
  });
});
