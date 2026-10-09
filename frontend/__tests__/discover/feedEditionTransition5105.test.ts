/**
 * #5105 / #5102 — an expired Discover edition is replaced from page zero
 * without mixing its continuation with the old edition or blanking the deck.
 *
 * Synthetic minimal fixtures only: a card is `{ id, p }` (`p` stands for the
 * live price a pinned page refreshes), identity is the caller's callback. The
 * helper is not wired into any page; these pin its decisions.
 */
import {
  decideEditionTransition,
  deckSections,
  nextPageRequest,
  readFeedEditionStatus,
  type EditionDeck,
  type EditionTransition,
  type FeedEditionRequest,
} from "@/lib/discover/feedEditionTransition";

type Card = { id: string; p: number };
const getId = (card: Card) => card.id;

function cards(prefix: string, total: number, p = 50): Card[] {
  return Array.from({ length: total }, (_, n) => ({ id: `${prefix}${n}`, p }));
}

/** A served page of `deck`: the window at `offset`, with the envelope fields the server sends. */
function reply(deck: Card[], offset: number, limit: number, extra: Record<string, unknown> = {}) {
  const items = deck.slice(offset, offset + limit);
  return {
    items,
    offset,
    limit,
    total: deck.length,
    has_more: offset + limit < deck.length,
    edition: "E1",
    ...extra,
  };
}

function decide(
  accepted: EditionDeck<Card> | null,
  request: FeedEditionRequest,
  payload: unknown,
  hasRenderedItems = accepted !== null,
): EditionTransition<Card> {
  return decideEditionTransition({ accepted, request, payload, hasRenderedItems, getId });
}

function deckOf(result: EditionTransition<Card>, kind: "accept" | "replace" = "replace"): EditionDeck<Card> {
  if (result.kind !== kind) throw new Error(`expected ${kind}, got ${JSON.stringify(result)}`);
  return result.deck;
}

const first = (edition: string | null = null): FeedEditionRequest => ({ edition, offset: 0, generation: null });

/** A held E1 deck of 40 with pages 0 and 20 loaded, boundary at 25. */
function heldAtTwenty() {
  const e1 = cards("a", 50);
  const zero = deckOf(decide(null, first(), reply(e1, 0, 20, { continuation_start: 25 })));
  const request = nextPageRequest(zero)!;
  const twenty = deckOf(
    decide(zero, request, reply(e1, 20, 20, { continuation_start: 25, edition_status: "pinned" })),
    "accept",
  );
  return { e1, deck: twenty };
}

describe("readFeedEditionStatus", () => {
  it("reads the four served statuses exactly and refuses anything else", () => {
    expect(readFeedEditionStatus(undefined)).toBe("absent");
    for (const status of ["pinned", "expired", "superseded", "invalidated"]) {
      expect(readFeedEditionStatus(status)).toBe(status);
    }
    for (const bad of [null, "", "unpinned", "Expired", 0, true, {}]) {
      expect(readFeedEditionStatus(bad)).toBe("malformed");
    }
  });
});

describe("a retired edition is never appended", () => {
  it.each(["expired", "superseded", "invalidated"] as const)(
    "a held page at offset 20 that gets %s with a new-token tail restarts from page zero and keeps the deck",
    (status) => {
      const { deck } = heldAtTwenty();
      const current = cards("b", 50);
      const request = nextPageRequest(deck)!;
      expect(request).toEqual({ edition: "E1", offset: 40, generation: 1 });

      const result = decide(deck, request, reply(current, 40, 20, { edition: "E2", edition_status: status }));

      expect(result).toEqual({
        kind: "restart",
        reason: status,
        request: { edition: null, offset: 0, generation: 1 },
      });
    },
  );

  it("a restart's own reply carries no status, so it replaces and cannot restart again", () => {
    const { deck } = heldAtTwenty();
    const restart = decide(deck, nextPageRequest(deck)!, reply(cards("b", 50), 40, 20, { edition: "E2", edition_status: "expired" }));
    if (restart.kind !== "restart") throw new Error("expected restart");

    const replaced = deckOf(decide(deck, restart.request, reply(cards("b", 50), 0, 20, { edition: "E2" })));
    expect(replaced.edition).toBe("E2");
    expect(replaced.generation).toBe(2);
    expect(replaced.sections.opening.map(getId)).toEqual(cards("b", 20).map(getId));
    expect(replaced.nextOffset).toBe(20);
  });

  it.each(["expired", "superseded", "invalidated"] as const)(
    "a %s reply already at offset 0 replaces directly, without the retired token",
    (status) => {
      const { deck } = heldAtTwenty();
      const result = decide(
        deck,
        { edition: "E1", offset: 0, generation: 1 },
        reply(cards("b", 30), 0, 20, { edition: "E2", edition_status: status }),
      );
      const replaced = deckOf(result);
      expect(replaced.edition).toBe("E2");
      expect(replaced.nextOffset).toBe(20);
      expect(nextPageRequest(replaced)).toEqual({ edition: "E2", offset: 20, generation: 2 });
    },
  );

  it("a retired reply whose own offset is nonzero restarts even when page zero was asked", () => {
    const { deck } = heldAtTwenty();
    const result = decide(
      deck,
      { edition: "E1", offset: 0, generation: 1 },
      reply(cards("b", 50), 20, 20, { edition: "E2", edition_status: "expired" }),
    );
    expect(result.kind).toBe("restart");
  });

  it("a page-zero replacement that is unavailable preserves, then a supported one replaces", () => {
    const { deck } = heldAtTwenty();
    const request: FeedEditionRequest = { edition: null, offset: 0, generation: 1 };

    const unavailable = decide(deck, request, { items: [], offset: 0, total: 0, has_more: false, cache: { status: "unavailable" } });
    expect(unavailable).toEqual({ kind: "preserve", reason: "unavailable", showUnavailable: true, hasMore: true });

    const replaced = deckOf(decide(deck, request, reply(cards("b", 30), 0, 20, { edition: "E2" })));
    expect(replaced.edition).toBe("E2");
  });

  it("an unavailable reply at a nonzero offset preserves rather than restarting on a status it cannot vouch for", () => {
    const { deck } = heldAtTwenty();
    const result = decide(deck, nextPageRequest(deck)!, {
      items: [],
      offset: 40,
      total: 0,
      has_more: false,
      cache: { status: "unavailable" },
      edition_status: "expired",
    });
    expect(result).toEqual({ kind: "preserve", reason: "unavailable", showUnavailable: true, hasMore: true });
  });

  it("a degraded empty page zero over rendered cards preserves; a complete empty one replaces with an empty deck", () => {
    const { deck } = heldAtTwenty();
    const request: FeedEditionRequest = { edition: null, offset: 0, generation: 1 };

    const degraded = decide(deck, request, { items: [], offset: 0, total: 0, has_more: false, edition: "E2", build_quality: "partial" });
    expect(degraded).toEqual({ kind: "preserve", reason: "degraded_empty", showUnavailable: false, hasMore: true });

    const empty = deckOf(decide(deck, request, { items: [], offset: 0, total: 0, has_more: false, edition: "E2" }));
    expect(empty.sections.opening).toEqual([]);
    expect(empty.hasMore).toBe(false);
    expect(nextPageRequest(empty)).toBeNull();
  });
});

describe("same order, moving boundary", () => {
  it("boundary 2 -> 1 -> 0 each replace from page zero, never fold into the held boundary", () => {
    const order = cards("s", 5);
    const two = deckOf(decide(null, first(), reply(order, 0, 5, { edition: "B2", continuation_start: 2 })));
    expect(two.sections.opening.map(getId)).toEqual(["s0", "s1"]);

    const oneRequest: FeedEditionRequest = { edition: "B2", offset: 0, generation: two.generation };
    const one = deckOf(decide(two, oneRequest, reply(order, 0, 5, { edition: "B1", continuation_start: 1, edition_status: "invalidated" })));
    expect(one.sections.boundary).toBe(1);
    expect(one.sections.opening.map(getId)).toEqual(["s0"]);

    const zeroRequest: FeedEditionRequest = { edition: "B1", offset: 0, generation: one.generation };
    const zero = deckOf(decide(one, zeroRequest, reply(order, 0, 5, { edition: "B0", continuation_start: 0, edition_status: "invalidated" })));
    expect(zero.sections.boundary).toBe(0);
    expect(zero.sections.opening).toEqual([]);
    expect(zero.sections.continuation.map(getId)).toEqual(order.map(getId));
  });

  it("a pinned page claiming the held token with a different boundary is refused, deck kept", () => {
    const { e1, deck } = heldAtTwenty();
    const result = decide(deck, nextPageRequest(deck)!, reply(e1, 40, 10, { continuation_start: 24, edition_status: "pinned" }));
    expect(result).toEqual({ kind: "preserve", reason: "boundary_mismatch", showUnavailable: false, hasMore: true });
  });
});

describe("compatible pinned pages", () => {
  it("carry fresh bodies while sections keep server identity and position", () => {
    const { e1, deck } = heldAtTwenty();
    const repriced = e1.map((card) => ({ ...card, p: 71 }));
    const result = decide(deck, { edition: "E1", offset: 20, generation: 1 }, reply(repriced, 20, 20, { continuation_start: 25, edition_status: "pinned" }));
    const next = deckOf(result, "accept");
    if (result.kind !== "accept") throw new Error("expected accept");

    expect(result.items.every((card) => card.p === 71)).toBe(true);
    // The fold keeps first-seen bodies; display reads the latest one.
    expect(next.sections.continuation[0].p).toBe(50);
    const display = deckSections(next, getId);
    expect(display.continuation.map((card) => card.p)).toEqual(Array(15).fill(71));
    expect(display.opening.slice(0, 20).map((card) => card.p)).toEqual(Array(20).fill(50));
    expect(display.opening.slice(20).map((card) => card.p)).toEqual(Array(5).fill(71));
    expect(next.sections.positions.get("a25")).toBe(25);
    expect(next.nextOffset).toBe(40);
  });

  it("a client filter hole leaves the raw cursor at the end of what the server sent", () => {
    const e1 = cards("a", 60);
    const zero = deckOf(decide(null, first(), reply(e1, 0, 20)));
    // The page hides five cards; the helper never sees the visible count.
    const visible = zero.sections.opening.filter((_, n) => n % 4 !== 0);
    expect(visible).toHaveLength(15);
    expect(zero.nextOffset).toBe(20);
    expect(nextPageRequest(zero)).toEqual({ edition: "E1", offset: 20, generation: 1 });
  });

  it("a duplicate or overlapping page is idempotent and never moves the cursor backwards", () => {
    const { e1, deck } = heldAtTwenty();
    const again = deckOf(decide(deck, { edition: "E1", offset: 20, generation: 1 }, reply(e1, 20, 20, { continuation_start: 25, edition_status: "pinned" })), "accept");
    expect(again.nextOffset).toBe(40);
    expect(again.hasMore).toBe(true);
    expect([...again.sections.membership.keys()]).toEqual([...deck.sections.membership.keys()]);

    const overlap = deckOf(decide(deck, { edition: "E1", offset: 30, generation: 1 }, reply(e1, 30, 20, { continuation_start: 25, edition_status: "pinned" })), "accept");
    expect(overlap.nextOffset).toBe(50);
    expect(overlap.hasMore).toBe(false);
    expect(overlap.sections.continuation.map(getId)).toEqual(e1.slice(25, 50).map(getId));
  });

  it("a gap past the cursor is refused, and an empty reply to the next window ends paging instead of looping", () => {
    const { e1, deck } = heldAtTwenty();
    const gap = decide(deck, { edition: "E1", offset: 45, generation: 1 }, reply(e1, 45, 5, { continuation_start: 25, edition_status: "pinned" }));
    expect(gap).toEqual({ kind: "preserve", reason: "offset_gap", showUnavailable: false, hasMore: true });

    const empty = deckOf(
      decide(deck, nextPageRequest(deck)!, { items: [], offset: 40, total: 50, has_more: true, edition: "E1", continuation_start: 25, edition_status: "pinned" }),
      "accept",
    );
    expect(empty.nextOffset).toBe(40);
    expect(nextPageRequest(empty)).toBeNull();
  });
});

describe("refusals keep the accepted state", () => {
  const malformed: Array<[string, Record<string, unknown>, string]> = [
    ["false boundary", { continuation_start: false }, "invalid_boundary"],
    ["string boundary", { continuation_start: "25" }, "invalid_boundary"],
    ["unknown status", { edition_status: "unpinned" }, "status_malformed"],
    ["null status", { edition_status: null }, "status_malformed"],
    ["missing status on a pinned request", { edition_status: undefined }, "status_missing"],
    ["other token", { edition_status: "pinned", edition: "E9" }, "edition_mismatch"],
    ["absent token", { edition_status: "pinned", edition: undefined }, "edition_mismatch"],
  ];

  it.each(malformed)("%s", (_, extra, reason) => {
    const { e1, deck } = heldAtTwenty();
    const result = decide(deck, nextPageRequest(deck)!, reply(e1, 40, 10, { continuation_start: 25, edition_status: "pinned", ...extra }));
    expect(result).toEqual({ kind: "preserve", reason, showUnavailable: false, hasMore: true });
  });

  it("a legacy deck (no boundary, so the fold reads no token) still refuses a pinned page of another token", () => {
    const legacy = cards("l", 40);
    const zero = deckOf(decide(null, first(), reply(legacy, 0, 20)));
    expect(zero.sections.boundary).toBeNull();
    const result = decide(zero, nextPageRequest(zero)!, reply(legacy, 20, 20, { edition: "E9", edition_status: "pinned" }));
    expect(result).toMatchObject({ kind: "preserve", reason: "edition_mismatch" });
  });

  it("boundary 0 is a real boundary, not legacy", () => {
    const zero = deckOf(decide(null, first(), reply(cards("z", 10), 0, 10, { continuation_start: 0 })));
    expect(zero.sections.boundary).toBe(0);
    expect(zero.sections.continuation).toHaveLength(10);
  });

  it("a held position under another identity is refused", () => {
    const { e1, deck } = heldAtTwenty();
    const swapped = [...e1];
    [swapped[20], swapped[21]] = [swapped[21], swapped[20]];
    const result = decide(deck, { edition: "E1", offset: 20, generation: 1 }, reply(swapped, 20, 20, { continuation_start: 25, edition_status: "pinned" }));
    expect(result).toMatchObject({ kind: "preserve", reason: "position_conflict" });
  });

  it("a response offset that is not the requested one is refused", () => {
    const { e1, deck } = heldAtTwenty();
    const result = decide(deck, nextPageRequest(deck)!, reply(e1, 30, 10, { continuation_start: 25, edition_status: "pinned" }));
    expect(result).toMatchObject({ kind: "preserve", reason: "offset_mismatch" });
  });

  it("a status the request never asked for is refused", () => {
    const result = decide(null, first(), reply(cards("a", 30), 0, 20, { edition_status: "expired" }), false);
    expect(result).toMatchObject({ kind: "preserve", reason: "status_unrequested" });
  });

  it("a section page zero without an edition is refused, never flattened to legacy", () => {
    const result = decide(null, first(), reply(cards("a", 30), 0, 20, { continuation_start: 5, edition: undefined }), false);
    expect(result).toMatchObject({ kind: "preserve", reason: "edition_missing" });
  });
});

describe("late replies are inert", () => {
  it("an old in-flight page of the replaced edition cannot roll the new deck back or retire it", () => {
    const { e1, deck: oldDeck } = heldAtTwenty();
    const inFlight = nextPageRequest(oldDeck)!;
    const fresh = deckOf(decide(oldDeck, { edition: null, offset: 0, generation: 1 }, reply(cards("b", 40), 0, 20, { edition: "E2" })));

    const latePinned = decide(fresh, inFlight, reply(e1, 40, 10, { continuation_start: 25, edition_status: "pinned" }));
    expect(latePinned).toEqual({ kind: "preserve", reason: "stale_request", showUnavailable: false, hasMore: true });

    const lateRetired = decide(fresh, inFlight, reply(cards("c", 50), 40, 10, { edition: "E3", edition_status: "expired" }));
    expect(lateRetired).toMatchObject({ kind: "preserve", reason: "stale_request" });

    const latePageZero = decide(fresh, { edition: null, offset: 0, generation: 1 }, reply(cards("c", 40), 0, 20, { edition: "E3" }));
    expect(latePageZero).toMatchObject({ kind: "preserve", reason: "stale_request" });
  });
});

describe("legacy decks without a token", () => {
  it("fold by offset with no status, and refuse a status they never asked for", () => {
    const legacy = cards("l", 30);
    const zero = deckOf(decide(null, first(), reply(legacy, 0, 20, { edition: undefined }), false));
    expect(zero.edition).toBeNull();
    expect(zero.sections.boundary).toBeNull();

    const request = nextPageRequest(zero)!;
    expect(request).toEqual({ edition: null, offset: 20, generation: 1 });
    const next = deckOf(decide(zero, request, reply(legacy, 20, 20, { edition: undefined })), "accept");
    expect(next.nextOffset).toBe(30);
    expect(next.hasMore).toBe(false);
  });

  it("a tokened deck is not extended by a page that did not send its token", () => {
    const { e1, deck } = heldAtTwenty();
    const result = decide(deck, { edition: null, offset: 40, generation: 1 }, reply(e1, 40, 10, { continuation_start: 25 }));
    expect(result).toMatchObject({ kind: "preserve", reason: "token_not_sent" });
  });
});
