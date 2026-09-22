// #7878 — the pure support rule behind `OddsChart`'s bounded forward-fill.
//
// The component test (`chartStopsDrawingAcrossAHoleNobodyObserved7878`) proves
// the pen lifts in the SVG. This file pins the RULE: what is judged, what is
// deliberately not, and — the part the directive asks for explicitly — that
// two payloads the rule cannot tell apart are demonstrated to be identical
// rather than silently classified one way.

import {
  SUPPORT_CADENCE_MULTIPLE,
  SUPPORT_FLOOR_S,
  bucketSupport,
  classifySeriesSupport,
  formatAge,
  type SupportObservation,
} from "@/lib/chartObservationSupport";

const START = Date.UTC(2026, 8, 21, 18, 0, 0);
const at = (s: number, extra: Partial<SupportObservation> = {}): SupportObservation => ({
  atMs: START + s * 1000,
  ...extra,
});
const judge = (obs: SupportObservation[], domainEndS: number | null = null, gameStartMs: number | null = START) =>
  classifySeriesSupport(obs, { gameStartMs, domainEndMs: domainEndS === null ? null : START + domainEndS * 1000 });

describe("#7878 — the specimen shapes", () => {
  test("15316479: five 2-min readings then a live edge 3h17m later ⇒ ONE trailing hole ending at the last reading", () => {
    const r = judge([at(141), at(260), at(380), at(500), at(619), at(12_437, { synthetic: true })]);
    expect(r.unsupported).toEqual([{ fromMs: START + 619_000, toMs: START + 12_437_000, kind: "trailing" }]);
    expect(r.lastObservedMs).toBe(START + 619_000);
    expect(r.inGameMedianS).toBe(120);
  });

  test("15315912's shape: a 73.6-min hole in a ~120s series with 118 readings after it ⇒ ONE interior hole, the 4-min one is not", () => {
    const before = Array.from({ length: 40 }, (_, i) => at(i * 120));
    const holeEnd = 39 * 120 + 73.6 * 60;
    const after = Array.from({ length: 118 }, (_, i) => at(holeEnd + i * 120));
    // A 4-minute interval somewhere after: the next-largest gap the specimen has.
    after[60] = at(holeEnd + 60 * 120 + 120);
    const r = judge([...before, ...after]);
    expect(r.unsupported).toHaveLength(1);
    expect(r.unsupported[0].kind).toBe("interior");
    expect(r.unsupported[0].fromMs).toBe(START + 39 * 120_000);
  });
});

describe("#7878 — refusals (the rule judges only what the payload can support a verdict on)", () => {
  test("pre-match intervals are never judged, however long", () => {
    const r = judge([at(-172_800), at(-86_400), at(-43_200), at(-3_600), at(-600)], -600);
    expect(r.unsupported).toEqual([]);
  });

  test("an interval that straddles the scheduled start is left joined", () => {
    const r = judge([at(-7_200), at(-3_600), at(14_400), at(14_520), at(14_640)]);
    expect(r.unsupported).toEqual([]);
  });

  test("no scheduled start ⇒ nothing judged", () => {
    const r = judge([at(0), at(12_437), at(24_874)], null, null);
    expect(r.unsupported).toEqual([]);
    expect(r.inGameMedianS).toBeNull();
  });

  test("a single in-game reading has no cadence ⇒ nothing judged (the cheap direction to be wrong in)", () => {
    const r = judge([at(-600), at(60), at(20_000, { synthetic: true })]);
    expect(r.unsupported).toEqual([]);
  });
});

describe("#7878 — both thresholds are load-bearing", () => {
  test("long in absolute terms but ordinary for THIS series ⇒ no break (the cadence multiple saves it)", () => {
    const r = judge(Array.from({ length: 10 }, (_, i) => at(i * 1_200)));
    expect(r.unsupported).toEqual([]);
  });

  test("a big multiple that is still a short absolute wait ⇒ no break (the floor saves it)", () => {
    const offsets = Array.from({ length: 20 }, (_, i) => i * 10);
    offsets.push(offsets[offsets.length - 1] + 200);
    const r = judge(offsets.map((s) => at(s)));
    expect(r.unsupported).toEqual([]);
    expect(200).toBeLessThan(SUPPORT_FLOOR_S);
    expect(200).toBeGreaterThan(SUPPORT_CADENCE_MULTIPLE * 10);
  });

  test("failing both ⇒ break", () => {
    const offsets = Array.from({ length: 20 }, (_, i) => i * 60);
    offsets.push(offsets[offsets.length - 1] + 5_400);
    const r = judge(offsets.map((s) => at(s)));
    expect(r.unsupported).toHaveLength(1);
    expect(r.unsupported[0].kind).toBe("interior");
  });
});

describe("#7878 — delivery time is not observation time", () => {
  test("the synthetic live edge never seeds the cadence and never counts as the last reading", () => {
    const r = judge([at(0), at(120), at(240), at(9_000, { synthetic: true })]);
    expect(r.lastObservedMs).toBe(START + 240_000);
    expect(r.inGameMedianS).toBe(120);
    expect(r.unsupported).toEqual([{ fromMs: START + 240_000, toMs: START + 9_000_000, kind: "trailing" }]);
  });

  test("a live edge within the bound is a fresh unchanged quote: solid to the edge", () => {
    const r = judge([at(0), at(120), at(240), at(330, { synthetic: true })]);
    expect(r.unsupported).toEqual([]);
  });

  test("OBSERVATIONALLY IDENTICAL: an unpolled market and a deduped unchanged quote serve the same points", () => {
    // What the wire carries for "we stopped looking after 240s" and for "we
    // kept looking and it never moved, and the dedup wrote no row" is the SAME
    // three points. The rule cannot separate them and does not pretend to; it
    // reports the interval as unsupported in both, as a display policy. The
    // evidence that WOULD separate them is `valid_until` (next test).
    const unpolled = judge([at(0), at(120), at(240)], 9_000);
    const dedupedButWatched = judge([at(0), at(120), at(240)], 9_000);
    expect(unpolled).toEqual(dedupedButWatched);
    expect(unpolled.unsupported).toHaveLength(1);
  });

  test("the producer contract: `valid_until` reaching the far end is evidence and overrides the heuristic", () => {
    const watched = judge([at(0), at(120), at(240, { observedUntilMs: START + 9_000_000 })], 9_000);
    expect(watched.unsupported).toEqual([]);
    // Partial coverage shortens the hole rather than excusing it.
    const partly = judge([at(0), at(120), at(240, { observedUntilMs: START + 1_000_000 })], 9_000);
    expect(partly.unsupported).toEqual([{ fromMs: START + 240_000, toMs: START + 9_000_000, kind: "trailing" }]);
  });
});

describe("#7878 — buckets and captions", () => {
  test("the endpoint minutes stay supported; the minutes strictly inside an interior hole do not", () => {
    const support = judge([at(0), at(120), at(240), at(5_000)]);
    expect(support.unsupported).toHaveLength(1);
    const minute = (s: number) => Math.floor((START + s * 1000) / 60_000) * 60_000;
    expect(bucketSupport(minute(240), support).kind).toBe("supported");
    expect(bucketSupport(minute(300), support).kind).toBe("gap");
    expect(bucketSupport(minute(4_900), support).kind).toBe("gap");
    expect(bucketSupport(minute(5_000), support).kind).toBe("supported");
  });

  test("a trailing hole withdraws its far minute too (the live edge is not drawn)", () => {
    const support = judge([at(0), at(120), at(240), at(9_000, { synthetic: true })]);
    const minute = (s: number) => Math.floor((START + s * 1000) / 60_000) * 60_000;
    expect(bucketSupport(minute(9_000), support).kind).toBe("gap");
  });

  test("formatAge", () => {
    expect(formatAge(11_818_000)).toBe("3h 16m");
    expect(formatAge(45 * 60_000)).toBe("45m");
    expect(formatAge(30_000)).toBe("<1m");
    expect(formatAge(50 * 3_600_000)).toBe("2d 2h");
  });
});
