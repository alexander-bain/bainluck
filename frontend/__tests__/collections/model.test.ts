jest.mock("@/lib/api", () => ({ API_URL: "http://fixture.invalid" }));
import { collectionPath, fetchCollection, parseCollection, reconcileCollectionContext, collectionRefreshInterval } from "@/lib/collections";
import { event, nflHub, mlbHub, question } from "./fixtures";
import type { FeedEventData, FeedFuturesData } from "@/lib/types";

describe("published collection presentation", () => {
  test("NFL keeps supplied lifecycle, section order and two-sided related identity", () => {
    const hub = parseCollection(nflHub(), "nfl-2026-week-4");
    expect(hub.title).toBe("NFL Week 4");
    expect(hub.edition).toBe("NFL · 2026 · Regular Season · Week 4");
    expect(hub.sections.map((s) => s.title)).toEqual(["Games and winners", "Player and game questions", "Championship"]);
    expect(hub.sections[0].members.map((m) => (m.item.data as FeedEventData).status)).toEqual(["scheduled", "live", "completed"]);
    expect(hub.related["event:7"].map((m) => m.key)).toEqual(["market:70"]);
    expect(hub.related["event:8"]).toEqual([]);
    expect(hub.sections[1].members.map((m) => m.key)).toEqual(["market:71"]);
    expect(hub.members).toHaveLength(6);
    expect(hub.note).toBeNull();
  });
  test("MLB preserves final/absent-price facts and partial state", () => {
    const hub = parseCollection(mlbHub(), "mlb-2026-postseason");
    expect(hub.edition).toBe("MLB · 2026 · Postseason");
    expect(hub.note).toBe("Some games or questions aren't available right now.");
    expect((hub.members[1].item.data as FeedFuturesData).status).toBe("resolved");
    expect((hub.members[2].item.data as { top_outcomes: { probability: number | null }[] }).top_outcomes[0].probability).toBeNull();
  });
  test.each(["unpublished", "withdrawn", "empty", "unavailable", "unknown"])("%s never carries leaked cards or child links", (state) => {
    const hub = parseCollection({ ...nflHub(), state }, "nfl-2026-week-4");
    expect(hub.members).toEqual([]); expect(hub.sections).toEqual([]); expect(hub.children).toEqual([]);
    expect(hub.note).toBeTruthy();
  });
  test("missing revision, wrong edition or response slug is unavailable rather than fabricated empty", () => {
    expect(() => parseCollection({ ...nflHub(), revision: null }, "nfl-2026-week-4")).toThrow();
    expect(() => parseCollection({ ...nflHub(), edition: { kind: "nfl_week", league: "nfl", season: 2025 } }, "nfl-2026-week-4")).toThrow();
    expect(() => parseCollection(nflHub(), "nfl-2026-week-5")).toThrow();
  });
  test("malformed/unsupported siblings and unsafe destinations cannot erase healthy cards", () => {
    const raw = nflHub();
    const wrong = event(10); wrong.destination.web = "https://attacker.invalid";
    raw.sections[0].members.push(wrong, null as unknown as ReturnType<typeof event>);
    const hub = parseCollection(raw, raw.slug);
    expect(hub.sections[0].members.map((m) => m.key)).toEqual(["event:7", "event:8", "event:9"]);
    expect(hub.note).toMatch(/Some games/);
  });
  test("duplicate members are drawn once; linked questions need both directions", () => {
    const raw = nflHub();
    raw.sections[1].members.push(question(70, 7), question(73, 7));
    const hub = parseCollection(raw, raw.slug);
    expect(hub.members.filter((m) => m.key === "market:70")).toHaveLength(1);
    expect(hub.related["event:7"].map((m) => m.key)).toEqual(["market:70"]);
    expect(hub.sections[1].members.map((m) => m.key)).toEqual(["market:71", "market:73"]);
  });
  test("canonical paths refuse path traversal and encoded segments", () => {
    expect(collectionPath("nfl-2026-week-4")).toBe("/collections/nfl-2026-week-4");
    for (const slug of ["../other", "nfl%2fother", "https://x", "", "NFL-2026"]) expect(collectionPath(slug)).toBeNull();
  });
  test("null child web accepts only the exact supplied container identity", () => {
    const raw = { ...nflHub(), children: [
      { slug: "nfl-2026-week-5", name: "NFL Week 5", publication_state: "published", destination: { kind: "container", slug: "nfl-2026-week-5", api: "/api/containers/nfl-2026-week-5", web: null } },
      { slug: "nfl-2026-week-6", name: "NFL Week 6", publication_state: "withdrawn", destination: {} },
    ] };
    expect(parseCollection(raw, raw.slug).children.map((c) => c.href)).toEqual(["/collections/nfl-2026-week-5"]);
  });
  test("return context survives revision but never retains a removed anchor or withdrawal", () => {
    const context = { slug: "nfl-2026-week-4", memberKey: "market:70", offset: -120, expanded: ["event:7", "event:8"] };
    const fresh = parseCollection({ ...nflHub(), revision: 2 }, context.slug);
    expect(reconcileCollectionContext(context, fresh)).toEqual({ ...context, expanded: ["event:7"] });
    const raw = nflHub(); raw.sections[1].members = [];
    expect(reconcileCollectionContext(context, parseCollection(raw, raw.slug))?.memberKey).toBeNull();
    expect(reconcileCollectionContext(context, parseCollection({ ...raw, state: "withdrawn" }, raw.slug))).toBeNull();
  });
  test("corrupt stored context and a different hub cannot restore position", () => {
    const hub = parseCollection(nflHub(), "nfl-2026-week-4");
    expect(reconcileCollectionContext({ slug: "wrong", offset: 1, memberKey: null, expanded: [] }, hub)).toBeNull();
    expect(reconcileCollectionContext({ slug: hub.slug, offset: NaN, memberKey: null, expanded: [] }, hub)).toBeNull();
  });
  test("only live or near-start supplied games earn a polling cadence", () => {
    expect(collectionRefreshInterval(parseCollection(nflHub(), "nfl-2026-week-4"))).toBe(30000);
    expect(collectionRefreshInterval(parseCollection(mlbHub(), "mlb-2026-postseason"))).toBe(0);
  });
});

describe("public fresh read", () => {
  afterEach(() => jest.restoreAllMocks());
  test("404 is unavailable; other failures are retryable errors, never empty", async () => {
    const mock = jest.spyOn(global, "fetch").mockResolvedValue({ status: 404, ok: false } as Response);
    expect((await fetchCollection("nfl-2026-week-4")).state).toBe("unavailable");
    mock.mockResolvedValue({ status: 503, ok: false } as Response);
    await expect(fetchCollection("nfl-2026-week-4")).rejects.toThrow(/Couldn't load/);
    expect(mock.mock.calls[0][1]?.cache).toBe("no-store");
  });
});
