/**
 * #11040 — guard tests for the departure-story reader. Each block names the
 * acceptance case in ACCEPTANCE-CASES.md it pins.
 *
 * Before: the reader knew only the AI and Oscars theme identities, so a
 * departure collection (`{kind: "theme_edition", subject, edition, family:
 * "departure", role}`) threw "This collection isn't available right now.";
 * collection cards printed the stored per-write change as "+N pts" with no
 * age; and a Search answers family had no way to the collection.
 *
 * After: the family's label, section titles, section notes and page note come
 * from the family (never the person), movement is dropped on a departure page
 * until a dated basis is served, an old number carries the existing age mark,
 * and the Search family draws the same link a Discover theme card draws.
 *
 * Fixtures are shaped like `_serve_theme_page` responses (the same shape
 * themeReader9925 pins); the departure edition fields are the proposed
 * contract in IMPLEMENTATION-HANDOFF.md.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/lib/api", () => ({ ...jest.requireActual("@/lib/api"), API_URL: "http://fixture.invalid" }));
jest.mock("next/link", () => {
  const ReactLib = require("react");
  return { __esModule: true, default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => ReactLib.createElement("a", { href, ...props }, children) };
});
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));

import CollectionHub from "@/components/collections/CollectionHub";
import { CollectionMemberCard } from "@/components/collections/CollectionMemberCard";
import SearchFamilyCard from "@/components/SearchFamilyCard";
import { fetchCollection, forgetAcceptedCollections, parseCollection, settleCollectionRead } from "@/lib/collections";
import type { FuturesFamily } from "@/lib/types";

const SLUG = "katie-zacharia-press-secretary-2026";
const EDITION = { kind: "theme_edition", subject: "katie-zacharia-press-secretary", edition: 2026, family: "departure", role: "White House press secretary" };
const READ_AT = "2026-10-14T23:51:09Z"; // the retained read (Wed Oct 14, 4:51 PM PT)

type Outcome = { name: string; probability: number | null; movement?: number | null; is_winner?: boolean | null; resolution_source?: string | null };
function market(id: number, name: string, outcomes: Outcome[], o: { source?: string; status?: string; pricesAt?: string | null } = {}) {
  return { type: "market", id, event_id: null, class: null,
    destination: { kind: "market", id, web: `/futures/${id}`, api: `/api/futures/${id}` },
    card: { id, name, sport: null, sport_name: null, llm_sport_category: "politics", source: o.source ?? "polymarket", source_count: 1,
      market_tier: 2, status: o.status ?? "open", resolution_date: "2026-11-01T03:59:00+00:00", outcome_count: outcomes.length, canonical_market_key: null,
      prices_updated_at: o.pricesAt === undefined ? "2026-10-14T23:38:28.890565+00:00" : o.pricesAt,
      top_outcomes: outcomes.map((x, i) => ({ id: id * 10 + i, name: x.name, probability: x.probability, rank: i + 1, movement: x.movement ?? null, is_winner: x.is_winner ?? null, ...(x.resolution_source !== undefined ? { resolution_source: x.resolution_source } : {}) })) } };
}
const OCT31 = (o = {}) => market(65678073, "Katie Zacharia out as Press Secretary by October 31?", [{ name: "No", probability: 0.927, movement: -0.034 }, { name: "Yes", probability: 0.073, movement: 0.034 }], o);
const DEC31 = (o = {}) => market(65678074, "Katie Zacharia out as Press Secretary by December 31?", [{ name: "No", probability: 0.755, movement: 0.065 }, { name: "Yes", probability: 0.245, movement: -0.065 }], o);
const KALSHI = () => market(900000001, "Katie Zacharia out as White House Press Secretary?", [{ name: "Before Oct 20, 2026", probability: 0.03 }, { name: "Before Nov 1, 2026", probability: 0.1 }], { source: "kalshi" });
const NEW_ROLE = () => market(66944824, "Will Katie Zacharia be officially given a new role in the Trump administration by December 31?", [{ name: "Yes", probability: 0.28 }]);
const BRIEFING = () => market(65809353, "Will Katie Zacharia give another press briefing as Press Secretary?", [{ name: "Yes", probability: 0.035 }]);
const LEAVE_ADMIN = () => market(990000002, "Will Katie Zacharia leave the Trump administration by December 31?", [{ name: "Yes", probability: 0.2 }]);

type Section = { class: string; members: ReturnType<typeof market>[] };
function departurePage(sections: Section[], o: { slug?: string; edition?: Record<string, unknown> } = {}) {
  const slug = o.slug ?? SLUG;
  const built = sections.map((s) => ({ class: s.class, count: s.members.length, members: s.members }));
  const total = built.reduce((n, s) => n + s.count, 0);
  return {
    state: "published", slug, revision: 7, reason: null, edition: o.edition ?? EDITION,
    container: { id: 9401, kind: "theme", name: "Katie Zacharia", slug, category: "politics", status: "active", window_start: null, window_end: null, parent_container_id: null },
    children: [], sections: built, member_count: total, withheld: [], withheld_count: 0, assembled: true,
    known_classes: ["after_role", "departure_announced", "departure_left_administration", "departure_rules_unread", "departure_vacated", "side_question", "unclassified"],
    revision_moved: false,
    counts: { shown_count: total, eligible_count: total, withheld_count: { low_quality: 0, public_source_disagreement: 0, row_missing: 0, suppressed: 0 }, inventory_complete: true },
    page: { limit: 50, next_cursor: null },
  };
}
const ALL = () => departurePage([
  { class: "departure_announced", members: [OCT31(), DEC31()] },
  { class: "departure_vacated", members: [KALSHI()] },
  { class: "departure_left_administration", members: [LEAVE_ADMIN()] },
  { class: "after_role", members: [NEW_ROLE()] },
  { class: "side_question", members: [BRIEFING()] },
]);
function aiPage() {
  const base = departurePage([{ class: "side_question", members: [market(101, "OpenAI releases GPT-6 before 2027?", [{ name: "Yes", probability: 0.42, movement: 0.034 }])] }], { slug: "ai", edition: { kind: "theme_continuing", subject: "ai" } });
  return { ...base, container: { ...base.container, id: 9301, name: "AI", category: "ai" } };
}

const respond = (body: unknown) => {
  global.fetch = jest.fn(async () => ({ status: 200, ok: true, json: async () => body })) as unknown as typeof fetch;
};
const accept = async (slug: string, body: unknown) => {
  respond(body);
  return settleCollectionRead(slug, { hub: await fetchCollection(slug) });
};
const frame = (slug: string) => renderToStaticMarkup(<CollectionHub slug={slug} />);

beforeEach(() => { forgetAcceptedCollections(); jest.useRealTimers(); });

describe("AC-R1 a departure story parses only for the slug its own identity builds", () => {
  test("the label is the role plus 'Story', from the served edition", () => {
    const hub = parseCollection(ALL(), SLUG);
    expect(hub).toMatchObject({ state: "published", title: "Katie Zacharia", edition: "White House press secretary · Story", family: "departure" });
  });
  test.each([
    ["the slug is not subject-edition", { slug: "katie-zacharia-2026" }, EDITION],
    ["a family this reader does not know", {}, { ...EDITION, family: "succession" }],
    ["no role", {}, { ...EDITION, role: undefined }],
    ["a role too long to be a label", {}, { ...EDITION, role: "x".repeat(61) }],
    ["the continuing shape", {}, { kind: "theme_continuing", subject: "katie-zacharia-press-secretary", family: "departure", role: "White House press secretary" }],
  ])("refused, never drawn under a guessed label: %s", (_name, page, edition) => {
    const slug = (page as { slug?: string }).slug ?? SLUG;
    const body = departurePage([{ class: "departure_announced", members: [OCT31()] }], { slug, edition });
    expect(() => parseCollection(body, slug)).toThrow("This collection isn't available right now.");
  });
  test("AI and Oscars identities are unchanged by the family branch", () => {
    expect(parseCollection(aiPage(), "ai")).toMatchObject({ edition: "AI · Ongoing", family: null, dek: null });
  });
  test("a server that writes `family: null` on an ordinary theme does not take that page down", () => {
    const body = { ...aiPage(), edition: { kind: "theme_continuing", subject: "ai", family: null, role: null } };
    expect(parseCollection(body, "ai")).toMatchObject({ edition: "AI · Ongoing", family: null, dek: null });
  });
});

describe("AC-R2 every section says what its markets have in common", () => {
  test("titles and notes come from the family, in the served order", () => {
    const hub = parseCollection(ALL(), SLUG);
    expect(hub.sections.map((s) => [s.cls, s.title])).toEqual([
      ["departure_announced", "An announced exit counts"],
      ["departure_vacated", "Only an actual departure counts"],
      ["departure_left_administration", "Leaving the administration"],
      ["after_role", "What comes next"],
      ["side_question", "About the job"],
    ]);
    expect(hub.sections.every((s) => typeof s.note === "string" && s.note.length > 0)).toBe(true);
    expect(hub.sections[0].note).toMatch(/announced resignation or removal counts/);
    expect(hub.sections[1].note).toMatch(/An announcement alone doesn't/);
  });
  test("a section this reader cannot name stays visible as 'More', with no note", () => {
    const hub = parseCollection(departurePage([{ class: "departure_announced", members: [OCT31()] }, { class: "unclassified", members: [BRIEFING()] }]), SLUG);
    expect(hub.sections.map((s) => [s.title, s.note])).toEqual([["An announced exit counts", expect.any(String)], ["More", null]]);
  });
  test("the rules-unknown fallback is honest about it", () => {
    const hub = parseCollection(departurePage([{ class: "departure_rules_unread", members: [OCT31(), DEC31()] }]), SLUG);
    expect(hub.sections[0]).toMatchObject({ title: "Leaving the job · rules not checked yet" });
    expect(hub.sections[0].note).toMatch(/hasn't been checked/);
  });
});

describe("AC-R3 no movement on a story page without a dated basis", () => {
  test("every outcome's movement is dropped on a departure page", () => {
    const hub = parseCollection(ALL(), SLUG);
    const moves = hub.members.flatMap((m) => ((m.item.data as { top_outcomes: { movement: unknown }[] }).top_outcomes).map((o) => o.movement));
    expect(moves.length).toBeGreaterThan(0);
    expect(moves.every((x) => x === null)).toBe(true);
  });
  test("an AI page keeps its served movement (this slice does not change it)", () => {
    const hub = parseCollection(aiPage(), "ai");
    expect((hub.members[0].item.data as { top_outcomes: { movement: unknown }[] }).top_outcomes[0].movement).toBe(0.034);
  });
  test("the drawn page prints no points move, and keeps every number", async () => {
    await accept(SLUG, departurePage([{ class: "departure_announced", members: [OCT31(), DEC31()] }]));
    const html = frame(SLUG);
    expect(html).not.toMatch(/[+-]\d+(\.\d+)? pts/);
    expect(html).toMatch(/7%|7\.3%/);
    expect(html).toMatch(/24%|25%|24\.5%/);
  });
});

describe("AC-R4 the page says what it is once", () => {
  test("a one-line page note on a departure page, and each section's note under its heading", async () => {
    await accept(SLUG, ALL());
    const html = frame(SLUG);
    expect(html).toContain("data-collection-dek");
    expect(html).toContain("Each market keeps its own number, because their rules can differ.");
    for (const cls of ["departure_announced", "departure_vacated", "departure_left_administration", "after_role", "side_question"])
      expect(html).toContain(`data-section-note="${cls}"`);
  });
  test("no page note anywhere else", async () => {
    await accept("ai", aiPage());
    expect(frame("ai")).not.toContain("data-collection-dek");
  });
});

describe("AC-R5 an old number says how old it is", () => {
  const card = (body: unknown, slug = SLUG) => renderToStaticMarkup(<CollectionMemberCard member={parseCollection(body, slug).members[0]} />);
  test("9 hours after its last change: the existing futures age mark", () => {
    jest.useFakeTimers({ now: new Date("2026-10-15T08:38:28Z") });
    const html = card(departurePage([{ class: "departure_announced", members: [OCT31()] }]));
    expect(html).toContain('data-testid="price-age-mark"');
    expect(html).toContain('data-cadence="futures"');
  });
  test("fresh: nothing is drawn", () => {
    jest.useFakeTimers({ now: new Date(READ_AT) });
    expect(card(departurePage([{ class: "departure_announced", members: [OCT31()] }]))).not.toContain("price-age-mark");
  });
  test("a settled card shows its result and no age", () => {
    jest.useFakeTimers({ now: new Date("2026-10-25T03:45:00Z") });
    const settled = market(65678073, "Katie Zacharia out as Press Secretary by October 31?", [{ name: "Yes", probability: 1, is_winner: true }, { name: "No", probability: 0, is_winner: false }], { status: "resolved" });
    const html = card(departurePage([{ class: "departure_announced", members: [settled] }]));
    expect(html).toContain("Won");
    expect(html).not.toContain("price-age-mark");
  });
  test("a missing price says so instead of showing 0% or an age", () => {
    jest.useFakeTimers({ now: new Date("2026-10-15T08:38:28Z") });
    const missing = market(65678074, "Katie Zacharia out as Press Secretary by December 31?", [{ name: "Yes", probability: null }]);
    const html = card(departurePage([{ class: "departure_announced", members: [missing] }]));
    expect(html).toContain("1 outcome without a price yet");
    expect(html).not.toMatch(/>0%</);
    expect(html).not.toContain("price-age-mark");
  });
  test("a partially priced card with a stale supported number still discloses its age", () => {
    jest.useFakeTimers({ now: new Date("2026-10-15T08:38:28Z") });
    const partialStale = market(65678073, "Katie Zacharia out as Press Secretary by October 31?", [{ name: "Yes", probability: 0.55 }, { name: "No", probability: null }], { pricesAt: "2026-10-14T23:38:28Z" });
    const html = card(departurePage([{ class: "departure_announced", members: [partialStale] }]));
    expect(html).toContain("55%");
    expect(html).toContain("1 more without a price yet");
    expect(html).toContain('data-testid="price-age-mark"');
    expect(html).toContain('data-cadence="futures"');
  });
  test("a partially priced card with a fresh number or unusable timestamp shows no age", () => {
    jest.useFakeTimers({ now: new Date("2026-10-15T08:38:28Z") });
    const partialFresh = market(65678073, "Katie Zacharia out as Press Secretary by October 31?", [{ name: "Yes", probability: 0.55 }, { name: "No", probability: null }], { pricesAt: "2026-10-15T08:30:00Z" });
    const partialUndatable = market(65678073, "Katie Zacharia out as Press Secretary by October 31?", [{ name: "Yes", probability: 0.55 }, { name: "No", probability: null }], { pricesAt: null });
    const resultOnlyOpen = market(65678073, "Katie Zacharia out as Press Secretary by October 31?", [{ name: "Yes", probability: 1, is_winner: true, resolution_source: "api_settlement" }, { name: "No", probability: null }], { status: "open", pricesAt: "2026-10-14T23:38:28Z" });
    for (const row of [partialFresh, partialUndatable, resultOnlyOpen]) {
      expect(card(departurePage([{ class: "departure_announced", members: [row] }]))).not.toContain("price-age-mark");
    }
  });
});

describe("AC-E2 the Search answers family links the story only when the server proved it", () => {
  const family = (ref: unknown): FuturesFamily => ({
    family_key: "entity:zacharia", label: "Zacharia",
    headline: NEW_ROLE().card as unknown as FuturesFamily["headline"],
    members: [BRIEFING().card as unknown as FuturesFamily["headline"]],
    more_count: 0, member_count: 2,
    collection_ref: ref as FuturesFamily["collection_ref"],
  });
  test("a proved ref draws the existing collection link", () => {
    const html = renderToStaticMarkup(<SearchFamilyCard family={family({ slug: SLUG, name: "Katie Zacharia", revision: 14, collection_count: 2 })} />);
    expect(html).toContain(`href="/collections/${SLUG}"`);
    expect(html).toContain("View the Katie Zacharia collection");
    expect(html).toMatch(/2 markets/);
  });
  test.each([
    ["no ref", null],
    ["a malformed revision", { slug: SLUG, name: "Katie Zacharia", revision: 0, collection_count: 2 }],
    ["an unsafe slug", { slug: "../admin", name: "Katie Zacharia", revision: 14, collection_count: 2 }],
  ])("no link: %s", (_name, ref) => {
    expect(renderToStaticMarkup(<SearchFamilyCard family={family(ref)} />)).not.toContain("/collections/");
  });
});
