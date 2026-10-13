/** #5343: the shared reader accepts canonical provider-event collections. */
import {
  parseCollection, reconcileCollectionContext, settleCollectionRead, forgetAcceptedCollections,
} from "@/lib/collections";
import { mlbHub, nflHub } from "./fixtures";

function providerHub(eventId: string, title = "Election outlook", category = "politics") {
  const slug = `polymarket-event-${eventId}`;
  const markets = [41, 42, 43].map((id) => ({
    type: "market", id, event_id: null,
    destination: { kind: "market", id, web: `/futures/${id}`, api: `/api/futures/${id}` },
    card: { id, name: `${title}: outcome ${id}`, status: "open", source: "polymarket",
      llm_sport_category: category, top_outcomes: [{ name: "Yes", probability: 0.6 }] },
  }));
  return { slug, state: "published", revision: 8,
    edition: { kind: "provider_event", provider: "polymarket", event_id: eventId },
    container: { slug, name: title }, children: [],
    sections: [{ class: "unclassified", count: markets.length, members: markets }],
    member_count: markets.length, withheld_count: 0, withheld: [],
  };
}

describe("provider-event identity, independent of subject or member IDs", () => {
  test.each([
    ["143201", "Election outlook", "politics"],
    ["145916", "Awards outlook", "entertainment"],
    ["879654321098765432", "Held-out provider event", "technology"],
  ])("%s opens the same complete simple hub", (eventId, title, category) => {
    const raw = providerHub(eventId, title, category);
    const hub = parseCollection(raw, raw.slug);
    expect(hub.state).toBe("published"); expect(hub.edition).toBe("Polymarket · Event");
    expect(hub.title).toBe(title); expect(hub.theme).toBeNull();
    expect(hub.members).toHaveLength(raw.member_count); expect(hub.note).toBeNull();
    expect(hub.sections[0].title).toBe("More");
    expect(hub.members.map((m) => m.href)).toEqual(["/futures/41", "/futures/42", "/futures/43"]);
  });

  test.each([
    { provider: "kalshi" }, { event_id: 145916 }, { event_id: "0" },
    { event_id: "0145916" }, { event_id: "145916x" }, { event_id: "145916\n" },
    { event_id: "1234567890123456789" }, { event_id: "" }, { event_id: null },
    { kind: "provider_events" }, { kind: undefined },
  ])("refuses malformed descriptor %j", (patch) => {
    const raw = providerHub("145916");
    expect(() => parseCollection({ ...raw, edition: { ...raw.edition, ...patch } }, raw.slug)).toThrow();
    // Also bind the slug to the malformed id: failure must not merely come
    // from a descriptor/slug mismatch (including JavaScript's newline `$`).
    if ("event_id" in patch && typeof patch.event_id === "string") {
      const slug = `polymarket-event-${patch.event_id}`;
      expect(() => parseCollection({ ...raw, slug, container: { ...raw.container, slug },
        edition: { ...raw.edition, ...patch } }, slug)).toThrow();
    }
  });

  test.each([
    "polymarket-event-145917", "event-145916", "polymarket-polymarket-event-145916",
    "nfl-2026-week-4", "mlb-2026-postseason", "ai", "oscars-2027",
  ])("refuses descriptor spliced onto %s", (slug) => {
    const raw = providerHub("145916");
    expect(() => parseCollection({ ...raw, slug, container: { ...raw.container, slug } }, slug)).toThrow();
  });

  test("accepts the full digit-string range without number coercion", () => {
    for (const id of ["1", "999999999999999999"]) {
      const raw = providerHub(id); expect(parseCollection(raw, raw.slug).edition).toBe("Polymarket · Event");
    }
  });
});

describe("existing shared hub safeguards remain intact", () => {
  afterEach(forgetAcceptedCollections);
  test("withheld/count and destination failures stay visible beside healthy members", () => {
    const raw = providerHub("145916");
    raw.sections[0].members[1].destination.web = "https://other.invalid";
    const hub = parseCollection({ ...raw, withheld_count: 1, withheld: [{ id: 99 }] }, raw.slug);
    expect(hub.members.map((m) => m.id)).toEqual([41, 43]);
    expect(hub.note).toBe("Some games or questions aren't available right now.");
    expect(parseCollection({ ...providerHub("145916"), member_count: 99 }, raw.slug).note).toBeTruthy();
  });

  test("Back retains accepted members and an authoritative withdrawal clears them", () => {
    const raw = providerHub("145916"), hub = parseCollection(raw, raw.slug);
    const context = { slug: raw.slug, memberKey: "market:42", offset: -20, expanded: [] };
    expect(reconcileCollectionContext(context, hub)).toEqual(context);
    settleCollectionRead(raw.slug, { hub });
    expect(settleCollectionRead(raw.slug, { failed: true }).hub).toEqual(hub);
    const withdrawn = parseCollection({ ...raw, state: "withdrawn" }, raw.slug);
    expect(settleCollectionRead(raw.slug, { hub: withdrawn }).hub?.members).toEqual([]);
    expect(reconcileCollectionContext(context, withdrawn)).toBeNull();
  });

  test("existing sports descriptors and fixture projections are preserved", () => {
    const nfl = nflHub(), mlb = mlbHub();
    expect(parseCollection(nfl, nfl.slug).edition).toBe("NFL · 2026 · Regular Season · Week 4");
    expect(parseCollection(nfl, nfl.slug).members).toHaveLength(6);
    expect(parseCollection(mlb, mlb.slug).edition).toBe("MLB · 2026 · Postseason");
    expect(parseCollection(mlb, mlb.slug).members).toHaveLength(3);
  });

  test.each([
    ["ai", { kind: "theme_continuing", subject: "ai" }, "AI · Ongoing"],
    ["oscars-2027", { kind: "theme_edition", subject: "oscars", edition: 2027 }, "Oscars · 2027"],
  ])("existing theme %s retains its pagination contract", (slug, edition, label) => {
    const raw = providerHub("145916");
    const hub = parseCollection({ ...raw, slug, container: { ...raw.container, slug }, edition,
      counts: { shown_count: 40, inventory_complete: true }, page: { next_cursor: "opaque" },
    }, slug as string);
    expect(hub.edition).toBe(label);
    expect(hub.theme).toEqual({ totalCount: 40, inventoryComplete: true, nextCursor: "opaque", revisionMoved: false });
    expect(hub.members).toHaveLength(3);
  });
});
