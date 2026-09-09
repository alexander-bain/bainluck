// #4430 — a Discover reader keeps their cards across a background refresh tick.
//
// ## The defect
//
// `app/discover/page.tsx` revalidates page one every 120 s
// (`useSWR(..., { refreshInterval: 120000 })`) and the effect that consumed the
// payload read:
//     if (decision.acceptItems) setPage1Items(data.items ?? []);
// The comment directly above it says that effect runs for "initial load AND
// background revalidation" — so every tick assigned the whole page-one array
// over the top, with no reconciliation of any kind. Any re-rank between two
// ticks moved or deleted a card out from under a reader who had asked for
// nothing. Alex hit it twice on the morning of 2026-09-09 ("cards vanished
// mid-read... crude-oil card, others"). It is the web half of #4110, which
// fixed the same class on iOS.
//
// The contrast was inside the same file: pagination already reconciled by
// `getItemId`. Page one was the one writer that did not.
//
// ## What the fix must NOT do
//
// "Merge and prune" — reconciling by id but dropping ids the new payload omits —
// still reproduces the harm, because a card missing from page one has almost
// never gone anywhere; it has been re-ranked onto page two. So the contract is
// that a background tick NEVER removes and NEVER reorders. Every genuine reason
// to drop a card (dismissal, staleness, the L2-215 empty-envelope fail-closed)
// is enforced per render, downstream, in `processedItems` — holding an id here
// cannot resurrect a card any of those would refuse.
//
// ## Why this is a lib test plus a source guard
//
// `jest.config.js` sets `testEnvironment: "node"` and component tests SSR via
// `renderToStaticMarkup`, which never runs effects — the reconcile is reached
// only from inside a `useEffect`, so it has no assertable path through a render.
// It therefore lives in `lib/discover/feedPaging` and is driven directly, with a
// source-shape guard at the bottom proving the page actually calls it. Without
// that guard the component could go back to assigning over the top and every
// assertion here would stay green.

import { readFileSync } from "fs";
import { join } from "path";
import { reconcilePage1 } from "@/lib/discover/feedPaging";

const PAGE_SOURCE = readFileSync(
  join(__dirname, "..", "..", "app", "discover", "page.tsx"),
  "utf8"
);

interface Card { id: string; price: number }
const getId = (c: Card) => c.id;
const ids = (cards: Card[]) => cards.map(getId);

// The reader's page one, as it stands when a tick arrives.
const READING: Card[] = [
  { id: "futures-oil", price: 28 },
  { id: "event-101", price: 75 },
  { id: "bundle-fed", price: 57 },
];

// What the pre-fix line did, kept executable so the regression is caught rather
// than described. Every "the ship" assertion below is also asserted against
// this, so the arm cannot quietly stop discriminating.
const wholesaleAssign = (_prev: Card[], incoming: Card[]) => incoming;

describe("#4430 — page one holds the reader's edition across a refresh tick", () => {
  it("CONTROL: a cold load takes the served page wholesale", () => {
    // The observable has to fire in the ordinary direction, or every assertion
    // below could pass on a function that simply returns `prev` and nothing
    // would ever reach the screen at all.
    const served = [{ id: "event-1", price: 10 }, { id: "event-2", price: 20 }];
    expect(reconcilePage1([], served, getId)).toEqual(served);
  });

  it("🔴 THE SHIP: a card the server dropped from page one is HELD, not removed", () => {
    // The crude-oil card re-ranks off page one while the reader is on it.
    const tick = [
      { id: "event-101", price: 75 },
      { id: "bundle-fed", price: 57 },
    ];
    const out = reconcilePage1(READING, tick, getId);
    expect(ids(out)).toContain("futures-oil");

    // ...and the pre-fix line is what made it vanish.
    expect(ids(wholesaleAssign(READING, tick))).not.toContain("futures-oil");
  });

  it("🔴 THE SHIP: a server re-rank does not reorder the cards under the reader", () => {
    const reranked = [
      { id: "bundle-fed", price: 57 },
      { id: "futures-oil", price: 28 },
      { id: "event-101", price: 75 },
    ];
    const out = reconcilePage1(READING, reranked, getId);
    expect(ids(out)).toEqual(["futures-oil", "event-101", "bundle-fed"]);

    // The pre-fix line adopted the server's order wholesale.
    expect(ids(wholesaleAssign(READING, reranked))).toEqual([
      "bundle-fed", "futures-oil", "event-101",
    ]);
  });

  it("🔴 still-served cards take the FRESH copy — holding must not freeze prices", () => {
    // The arm that stops the lazy fix. A reconcile that simply returned `prev`
    // would pass both assertions above and quietly stop every live price,
    // score and clock on page one — a worse bug than the one being fixed.
    const tick = [
      { id: "futures-oil", price: 31 },
      { id: "event-101", price: 80 },
      { id: "bundle-fed", price: 57 },
    ];
    const out = reconcilePage1(READING, tick, getId);
    expect(out.find((c) => c.id === "futures-oil")!.price).toBe(31);
    expect(out.find((c) => c.id === "event-101")!.price).toBe(80);
  });

  it("a card the server no longer sends keeps the copy the reader already has", () => {
    const tick = [{ id: "event-101", price: 80 }];
    const out = reconcilePage1(READING, tick, getId);
    expect(out.find((c) => c.id === "futures-oil")!.price).toBe(28);
  });

  it("genuinely new cards are appended, after the ones being read", () => {
    const tick = [...READING, { id: "event-999", price: 42 }];
    const out = reconcilePage1(READING, tick, getId);
    expect(ids(out)).toEqual([
      "futures-oil", "event-101", "bundle-fed", "event-999",
    ]);
  });

  it("an empty tick removes nothing — an unavailable-ish page cannot blank page one", () => {
    expect(ids(reconcilePage1(READING, [], getId))).toEqual(ids(READING));
  });

  it("never emits a duplicate id, even when the tick repeats what is held", () => {
    const out = reconcilePage1(READING, [...READING, ...READING], getId);
    expect(ids(out)).toEqual(ids(READING));
  });

  it("does not mutate the array the reader is rendering", () => {
    const before = [...READING];
    reconcilePage1(READING, [{ id: "event-999", price: 1 }], getId);
    expect(READING).toEqual(before);
  });
});

describe("#4430 — the page uses the shared reconcile, not its own assignment", () => {
  it("🔴 the wholesale page-one assignment is GONE from the component", () => {
    // Required by the lib/source two-layer pattern: without this the component
    // can drop everything proved above and nothing goes red.
    expect(PAGE_SOURCE).toContain("reconcilePage1");
    // The exact pre-fix statement must not come back.
    expect(PAGE_SOURCE).not.toMatch(/setPage1Items\(\s*data\.items/);
  });

  it("page one is still fed by the availability decision, not around it", () => {
    // The reconcile is inside the `decision.acceptItems` branch — an
    // unavailable payload must still contribute nothing (L2-238).
    expect(PAGE_SOURCE).toMatch(
      /decision\.acceptItems[\s\S]{0,220}reconcilePage1\(prev, incoming, getItemId\)/
    );
  });
});
