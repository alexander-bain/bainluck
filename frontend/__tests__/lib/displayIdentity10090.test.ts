/** #10090 — the adopted headline and chart identities are read off held state, never values. */
import {
  chartEndpointAttributes, chartEndpointIdentity, foldIdentity, headlineDisplayAttributes,
  headlineDisplayIdentity, previewIdentity,
} from "@/lib/displayIdentity";
import {
  EMPTY_AUTHORITY_PREVIEW, authorityPreviewFrame, authorityPreviewMembership, authorityPreviewOpen,
} from "@/lib/authorityPreview";
import { displayedPreview, previewAfter, type BlendPreviewState } from "@/lib/blendPreview";
import { pinChartEdgeToHero } from "@/lib/chartEdgePin";
import { appendHeroObservation, mergeLiveChartHistory, type LiveChartFrame } from "@/lib/liveChartHistory";

const ID = 15332323;
const AUTH = { incarnation: "7", namespace: "0b6c3d8e-4b5f-4a51-9b55-2b1e8f6b0c11" };
const SESSION = "5d1f9b52-6a4e-4f0e-8c33-9c2a1b7e4d10";
const OTHER_SESSION = "8a2e7c14-1f3b-4d6a-9e55-3b4c2d1e0f22";
const at = (s: number) => new Date(Date.UTC(2026, 9, 27, 20, 0, s)).toISOString();

function openReader(members: Record<string, number> = { [ID]: 10 }) {
  const joined = authorityPreviewMembership(EMPTY_AUTHORITY_PREVIEW, members, ID);
  return authorityPreviewOpen(joined, JSON.stringify({
    protocol: 3, event_id: ID, authority: AUTH, stream_session: SESSION,
    members: Object.keys(members).map(Number).sort((a, b) => a - b),
  }), ID);
}
function frame(seq: number, p: number, session = SESSION, extra: Record<string, unknown> = {}) {
  return JSON.stringify({
    protocol: 3, event_id: ID, authority: AUTH, stream_session: session,
    frame: { event_id: ID, p, status: "live", display_observed_at: at(seq),
      preview: { kind: "blend", epoch: 3, seq, base_rev: 10, ttl_ms: 1000, ...extra } },
  });
}
const heldEvent = { id: ID, status: "live", hero_probability_source: "blend", blend_fold_revision: { [ID]: 10 } };

describe("foldIdentity", () => {
  test("names every row in numeric order and refuses what parseFoldRevision refuses", () => {
    expect(foldIdentity({ 22: 4, 3: 9 })).toBe("fold:3=9,22=4");
    expect(foldIdentity({ [ID]: 11 })).toBe(`fold:${ID}=11`);
    for (const bad of [null, undefined, {}, [], { [ID]: -1 }, { [ID]: 1.5 }, "x"]) expect(foldIdentity(bad)).toBe("");
  });
});

describe("the v3 reader stamps the admitted authority onto the held preview", () => {
  test("an admitted frame carries domain, session, epoch/seq, base and its receipt", () => {
    const r = authorityPreviewFrame(openReader(), frame(1, .6), ID, 100.25, 101);
    const held = r.preview.held!;
    expect(held.authority).toEqual({ ...AUTH, session: SESSION, fold: false });
    expect(held.receivedAt).toBe(100.25);
    expect(previewIdentity(held)).toBe(`v3:7:${AUTH.namespace}:${SESSION}:e3.s1:fold:${ID}=10`);
  });

  test("two equal-valued previews have different identities", () => {
    const first = authorityPreviewFrame(openReader(), frame(1, .6), ID, 100, 100);
    const second = authorityPreviewFrame(first, frame(2, .6), ID, 200, 200);
    expect(first.preview.held!.p).toBe(second.preview.held!.p);
    expect(previewIdentity(first.preview.held)).not.toBe(previewIdentity(second.preview.held));
    expect(second.preview.held!.receivedAt).toBe(200);
  });

  test("a duplicate keeps the original adoption's identity and receipt", () => {
    const first = authorityPreviewFrame(openReader(), frame(1, .6), ID, 100, 100);
    const dup = authorityPreviewFrame(first, frame(1, .6), ID, 150, 150);
    expect(dup.preview.held!.receivedAt).toBe(100);
    expect(previewIdentity(dup.preview.held)).toBe(previewIdentity(first.preview.held));
  });

  test("a refused frame (other session, older seq, expired on arrival) never becomes the held identity", () => {
    const first = authorityPreviewFrame(openReader(), frame(2, .6), ID, 100, 100);
    const other = authorityPreviewFrame(first, frame(3, .7, OTHER_SESSION), ID, 110, 110);
    expect(other.preview.held).toBe(first.preview.held);
    const older = authorityPreviewFrame(first, frame(1, .7), ID, 120, 120);
    expect(older.preview.held).toBe(first.preview.held);
    const late = authorityPreviewFrame(openReader(), frame(4, .7), ID, 100, 1200);
    expect(late.preview.held).toBeNull();
  });

  test("a several-row fold is identified by its fold session sequence and full base", () => {
    const members = { [ID]: 10, [ID + 1]: 4 };
    const r = authorityPreviewFrame(openReader(members), JSON.stringify({
      protocol: 3, event_id: ID, authority: AUTH, stream_session: SESSION,
      frame: { event_id: ID, p: .55, p_away: .45, sport: "basketball_nba", status: "live", display_observed_at: at(5),
        preview: { kind: "blend", folded_version: 2, fold_session: SESSION, fold_seq: 0,
          base_fold_revision: members, ttl_ms: 1000,
          origin_authority: { [ID]: { epoch: 1, seq: 1, state: "pending", ttl_ms: 1000 },
            [ID + 1]: { epoch: 1, seq: 1, state: "pending", ttl_ms: 1000 } } } },
    }), ID, 50, 50);
    const held = r.preview.held;
    if (!held) return expect(r.preview.held).not.toBeNull();
    expect(held.authority?.fold).toBe(true);
    expect(previewIdentity(held)).toBe(`v3:7:${AUTH.namespace}:${SESSION}:f0:fold:${ID}=10,${ID + 1}=4`);
  });

  test("a legacy preview with no admitted authority has no identity", () => {
    const legacy = previewAfter(null, { event_id: ID, p: .6, status: "live",
      preview: { kind: "blend", epoch: 1, seq: 1, base_rev: 10, ttl_ms: 1000 } }, ID, 0);
    expect(previewIdentity(legacy)).toBe("");
  });
});

describe("headline identity", () => {
  const held = authorityPreviewFrame(openReader(), frame(1, .6), ID, 100, 100).preview.held;
  test("preview, committed and fallback each say what is displayed", () => {
    const shown = displayedPreview(held, heldEvent, 500) !== null;
    expect(shown).toBe(true);
    const preview = headlineDisplayIdentity({ heroBlend: true, previewShown: shown, preview: held,
      committedRevision: heldEvent.blend_fold_revision, observedAt: at(1) });
    expect(preview).toEqual({ basis: "preview", state: previewIdentity(held), receivedAt: 100, observedAt: at(1) });
    // Expired: the page's own displayedPreview says null, so committed truth and its revision.
    const expired = displayedPreview(held, heldEvent, 1100) !== null;
    const committed = headlineDisplayIdentity({ heroBlend: true, previewShown: expired, preview: held,
      committedRevision: heldEvent.blend_fold_revision, observedAt: at(0) });
    expect(committed).toEqual({ basis: "committed", state: `fold:${ID}=10`, receivedAt: null, observedAt: at(0) });
    const fallback = headlineDisplayIdentity({ heroBlend: false, previewShown: true, preview: held,
      committedRevision: heldEvent.blend_fold_revision, observedAt: at(1) });
    expect(fallback.basis).toBe("unavailable");
    expect(headlineDisplayAttributes(fallback)).toEqual({
      "data-display-basis": "unavailable", "data-display-state": "",
      "data-display-received": "", "data-display-observed-at": "",
    });
  });

  test("a committed hero whose revision was not carried is committed with no identity, never an older one", () => {
    const id = headlineDisplayIdentity({ heroBlend: true, previewShown: false, preview: null,
      committedRevision: undefined, observedAt: "bad" });
    expect(id).toEqual({ basis: "committed", state: "", receivedAt: null, observedAt: null });
  });
});

describe("chart endpoint identity follows the page's pipeline by object identity and instants", () => {
  const served = {
    aggregate_line: [{ timestamp: at(0), home_probability: .6 }],
    history_fold_revision: { [ID]: 9 }, blend_edge_fold_revision: { [ID]: 9 },
  };
  const coverage = () => `rev=fold:${ID}=9;through=${at(0)}`;
  function run(frames: LiveChartFrame[], hero: Record<string, unknown>, preview: BlendPreviewState | null = null, line?: unknown) {
    const observed = served;
    const pushed = mergeLiveChartHistory(observed, frames);
    const joined = pushed !== observed ? pushed : pinChartEdgeToHero(observed, hero as never);
    const final = appendHeroObservation(joined, hero as never, served);
    return chartEndpointIdentity({ served, final,
      line: (line as never) ?? final?.aggregate_line, frames, heroRevision: hero.blend_fold_revision, preview });
  }
  const hero = (rev: number, p = .6, clock = at(0)) => ({
    status: "live", hero_probability: p, hero_probability_source: "blend",
    hero_probability_observed_at: clock, blend_fold_revision: { [ID]: rev },
  });

  test("the served edge reports its own edge revision", () => {
    expect(run([], hero(9))).toEqual({ at: at(0), basis: "history", state: `fold:${ID}=9`, coverage: coverage() });
  });

  test("repeated equal pushed values report each frame's own revision", () => {
    const one = [{ timestamp: at(10), home_probability: .6, rev: { [ID]: 10 } }];
    const two = [...one, { timestamp: at(20), home_probability: .6, rev: { [ID]: 11 } }];
    expect(run(one, hero(10, .6, at(10)))).toEqual({ at: at(10), basis: "push", state: `fold:${ID}=10`, coverage: coverage() });
    expect(run(two, hero(11, .6, at(20)))).toEqual({ at: at(20), basis: "push", state: `fold:${ID}=11`, coverage: coverage() });
  });

  test("a newer headline appended to the line is the hero's committed revision", () => {
    expect(run([], hero(12, .64, at(30)))).toEqual({ at: at(30), basis: "hero", state: `fold:${ID}=12`, coverage: coverage() });
  });

  test("an equal-valued newer headline is NOT on the chart, so the chart keeps the edge's identity", () => {
    expect(run([], hero(12, .6, at(30)))).toMatchObject({ at: at(0), basis: "history", state: `fold:${ID}=9` });
  });

  test("a pinned served edge reports the hero revision it now carries", () => {
    const pinned = { ...served, blend_edge_pinned: true, blend_edge_observed_at: at(0) };
    const h = hero(12, .62, at(0));
    const joined = pinChartEdgeToHero(pinned, h);
    expect(joined).not.toBe(pinned);
    expect(chartEndpointIdentity({ served: pinned, final: joined,
      line: joined?.aggregate_line, frames: [], heroRevision: h.blend_fold_revision, preview: null }))
      .toMatchObject({ at: at(0), basis: "hero-edge", state: `fold:${ID}=12` });
  });

  test("#8749's synthetic-edge repair is the headline's revision at the served minute", () => {
    const pinned = { ...served, blend_edge_pinned: true, blend_edge_observed_at: at(-30) };
    const h = hero(12, .63, at(-10));
    const final = appendHeroObservation(pinned, h as never, pinned);
    expect(final?.aggregate_line).toHaveLength(1);
    expect(chartEndpointIdentity({ served: pinned, final, line: final?.aggregate_line, frames: [],
      heroRevision: h.blend_fold_revision, preview: null })).toMatchObject({ at: at(0), basis: "hero-edge", state: `fold:${ID}=12` });
  });

  test("an interior served point (the served edge is not last) reports no revision", () => {
    const later = { ...served, aggregate_line: [{ timestamp: at(0), home_probability: .6 }, { timestamp: at(5), home_probability: .61 }] };
    const line = later.aggregate_line.slice(0, 1);
    expect(chartEndpointIdentity({ served: later, final: { aggregate_line: line }, line, frames: [],
      heroRevision: undefined, preview: null })).toMatchObject({ basis: "history", state: "" });
  });

  test("a preview projection reports the preview identity at the preview's own observation", () => {
    const held = authorityPreviewFrame(openReader(), frame(40, .61), ID, 100, 100).preview.held;
    const line = [...served.aggregate_line, { timestamp: at(40), home_probability: .61 }];
    expect(run([], hero(9), held, line)).toEqual({ at: at(40), basis: "preview", state: previewIdentity(held), coverage: coverage() });
  });

  test("the chart prints the identity only for the point its end dot actually draws", () => {
    const id = run([], hero(9))!;
    expect(chartEndpointAttributes(at(0), id)).toEqual({
      "data-chart-endpoint-at": at(0), "data-chart-endpoint-basis": "history",
      "data-chart-endpoint-state": `fold:${ID}=9`, "data-chart-history": coverage(),
    });
    // The dot drew an older point (or a checkpoint/source series): unavailable, not borrowed.
    expect(chartEndpointAttributes(at(-60), id)).toMatchObject({
      "data-chart-endpoint-basis": "unavailable", "data-chart-endpoint-state": "" });
    expect(chartEndpointAttributes(undefined, id)).toMatchObject({
      "data-chart-endpoint-at": "", "data-chart-endpoint-basis": "unavailable" });
  });
});
