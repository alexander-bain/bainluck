// #7878 — the web consumer of the served evidence contract (Codex card-B,
// producer #8438 / `backend/app/utils/winprob_evidence.py`).
//
// `chartObservationSupport7878.test.ts` pins the pre-contract cadence heuristic,
// which still runs for any payload without `evidence_contract`. This file pins
// what changes when the contract IS served: G replaces the heuristic, only a
// plain reading or `observed` proves coverage, `valid_until` never does, and
// every other kind is drawn but proves nothing.

import {
  EVIDENCE_CONTRACT_V,
  bucketSupport,
  classifySeriesSupport,
  contractObservation,
  evidenceResolutionS,
  type ContractPoint,
  type SupportObservation,
} from "@/lib/chartObservationSupport";

const START = Date.UTC(2026, 8, 21, 18, 0, 0);
const G = 300;
const iso = (s: number) => new Date(START + s * 1000).toISOString();
const pt = (s: number, extra: Partial<ContractPoint> = {}): ContractPoint => ({ timestamp: iso(s), ...extra });

/** Classify served points exactly as `OddsChart` does under the contract. */
function judgeServed(points: ContractPoint[], domainEndS: number | null = null, gameStartMs: number | null = START) {
  const obs = points.map(contractObservation).filter((o): o is SupportObservation => o !== null);
  return classifySeriesSupport(obs, {
    gameStartMs,
    domainEndMs: domainEndS === null ? null : START + domainEndS * 1000,
    evidenceResolutionS: G,
  });
}
/** The same observations through the pre-contract heuristic, for contrast. */
function judgeHeuristic(points: ContractPoint[]) {
  const obs = points.map((p) => ({ atMs: Date.parse(p.timestamp), synthetic: p.live_edge === true }));
  return classifySeriesSupport(obs, { gameStartMs: START, domainEndMs: null });
}

describe("#7878 contract — reading the served contract", () => {
  test("the production shape is read; anything else keeps the heuristic", () => {
    expect(evidenceResolutionS({ v: "7878.v1", resolution_s: 300 })).toBe(300);
    expect(EVIDENCE_CONTRACT_V).toBe("7878.v1");
    expect(evidenceResolutionS(undefined)).toBeNull();
    expect(evidenceResolutionS(null)).toBeNull();
    expect(evidenceResolutionS({ v: "7878.v2", resolution_s: 300 })).toBeNull();
    expect(evidenceResolutionS({ v: "7878.v1" })).toBeNull();
    expect(evidenceResolutionS({ v: "7878.v1", resolution_s: "300" })).toBeNull();
    expect(evidenceResolutionS({ v: "7878.v1", resolution_s: 0 })).toBeNull();
    expect(evidenceResolutionS({ v: "7878.v1", resolution_s: Number.NaN })).toBeNull();
  });

  test("each served kind maps to what it can prove", () => {
    expect(contractObservation(pt(0))).toEqual({ atMs: START });
    expect(contractObservation(pt(0, { live_edge: true }))).toEqual({ atMs: START, synthetic: true });
    expect(contractObservation(pt(0, { evidence: { kind: "live_edge" } }))).toEqual({ atMs: START, synthetic: true });
    for (const kind of ["candle", "price_history", "terminal_row", "final", "something_new"]) {
      expect(contractObservation(pt(0, { evidence: { kind } }))).toEqual({ atMs: START, notEvidence: true });
    }
    // Malformed evidence fails closed, not open.
    expect(contractObservation(pt(0, { evidence: "observed" }))).toEqual({ atMs: START, notEvidence: true });
    expect(contractObservation(pt(0, { evidence: {} }))).toEqual({ atMs: START, notEvidence: true });
    expect(contractObservation({ timestamp: "not a time" })).toBeNull();
  });

  test("observed extends coverage to covered_through; a malformed or backwards span extends nothing", () => {
    expect(contractObservation(pt(0, { evidence: { kind: "observed", covered_through: iso(900) } }))).toEqual({
      atMs: START,
      observedUntilMs: START + 900_000,
    });
    expect(contractObservation(pt(0, { evidence: { kind: "observed", covered_through: "garbage" } }))).toEqual({ atMs: START });
    expect(contractObservation(pt(900, { evidence: { kind: "observed", covered_through: iso(0) } }))).toEqual({
      atMs: START + 900_000,
    });
  });

  test("valid_until is never read — Codex's 10:00 / 10:01 / 12:00 counterexample stays a hole", () => {
    const withValidUntil = { ...pt(60), valid_until: iso(7_200) } as ContractPoint;
    const r = judgeServed([pt(0), withValidUntil, pt(7_200)]);
    expect(r.unsupported).toEqual([{ fromMs: START + 60_000, toMs: START + 7_200_000, kind: "interior" }]);
  });
});

describe("#7878 contract — G is the whole rule", () => {
  test("exactly G is covered; one second over is a hole", () => {
    expect(judgeServed([pt(0), pt(G), pt(2 * G)]).unsupported).toEqual([]);
    expect(judgeServed([pt(0), pt(G + 1)]).unsupported).toEqual([
      { fromMs: START, toMs: START + (G + 1) * 1000, kind: "interior" },
    ]);
  });

  test("a 6-minute in-game hole breaks under the contract — the heuristic's 10-minute floor let it through", () => {
    const points = [pt(0), pt(120), pt(240), pt(600), pt(720)];
    expect(judgeHeuristic(points).unsupported).toEqual([]);
    expect(judgeServed(points).unsupported).toEqual([{ fromMs: START + 240_000, toMs: START + 600_000, kind: "interior" }]);
  });

  test("a single in-game reading and a live edge 3h later IS judged (no cadence needed)", () => {
    const r = judgeServed([pt(-600), pt(60), pt(12_437, { live_edge: true })]);
    expect(r.unsupported).toEqual([{ fromMs: START + 60_000, toMs: START + 12_437_000, kind: "trailing" }]);
    expect(r.inGameMedianS).toBeNull();
  });

  test("15316479's shape: five readings then the live edge ⇒ one trailing hole from the last reading", () => {
    const r = judgeServed([pt(141), pt(260), pt(380), pt(500), pt(619), pt(12_437, { live_edge: true })]);
    expect(r.unsupported).toEqual([{ fromMs: START + 619_000, toMs: START + 12_437_000, kind: "trailing" }]);
    expect(r.lastObservedMs).toBe(START + 619_000);
  });

  test("covered_through closes what would otherwise be a hole — and only as far as it reaches", () => {
    const covered = judgeServed([pt(0, { evidence: { kind: "observed", covered_through: iso(3_500) } }), pt(3_600)]);
    expect(covered.unsupported).toEqual([]);
    const short = judgeServed([pt(0, { evidence: { kind: "observed", covered_through: iso(1_000) } }), pt(3_600)]);
    expect(short.unsupported).toEqual([{ fromMs: START + 1_000_000, toMs: START + 3_600_000, kind: "interior" }]);
  });
});

describe("#7878 contract — drawn but proves nothing", () => {
  test("a live edge never counts as a reading, so a stale series gets its trailing hole", () => {
    const r = judgeServed([pt(0), pt(120), pt(7_200, { live_edge: true })]);
    expect(r.unsupported.map((iv) => iv.kind)).toEqual(["trailing"]);
    expect(r.lastObservedMs).toBe(START + 120_000);
  });

  test("a finished game's gap to its terminal row and result is a hole, not a solid line", () => {
    // Readings stop at 18:06; the terminal row is 3h later, the result after it.
    const r = judgeServed([
      pt(0),
      pt(120),
      pt(360),
      pt(11_400, { evidence: { kind: "terminal_row" } }),
      pt(11_460, { evidence: { kind: "final" } }),
    ]);
    expect(r.unsupported).toEqual([{ fromMs: START + 360_000, toMs: START + 11_400_000, kind: "interior" }]);
    expect(r.lastObservedMs).toBe(START + 360_000);
  });

  test("a terminal row one heartbeat after the last reading does not break the line", () => {
    const r = judgeServed([pt(0), pt(120), pt(240, { evidence: { kind: "terminal_row" } }), pt(250, { evidence: { kind: "final" } })]);
    expect(r.unsupported).toEqual([]);
  });

  test("candle endpoints are not continuous observation: two hourly candles in-game are a hole", () => {
    const r = judgeServed([pt(0, { evidence: { kind: "candle" } }), pt(3_600, { evidence: { kind: "candle" } })]);
    expect(r.unsupported).toEqual([{ fromMs: START, toMs: START + 3_600_000, kind: "interior" }]);
    expect(r.lastObservedMs).toBeNull();
  });

  test("a candle carrying a covered_through-shaped key still extends nothing", () => {
    const r = judgeServed([pt(0, { evidence: { kind: "candle", covered_through: iso(3_600) } }), pt(3_600)]);
    expect(r.unsupported).toHaveLength(1);
  });
});

describe("#7878 contract — the pre-match boundary", () => {
  test("pre-match intervals are still never judged, however long", () => {
    expect(judgeServed([pt(-172_800), pt(-86_400), pt(-3_600), pt(-600)], -600).unsupported).toEqual([]);
  });

  test("an interval straddling the start is judged from the start: the in-game stretch is in-game", () => {
    const r = judgeServed([pt(-7_200), pt(1_800), pt(1_920)]);
    expect(r.unsupported).toEqual([{ fromMs: START, toMs: START + 1_800_000, kind: "interior" }]);
    // …and one whose in-game part fits inside G is left joined.
    expect(judgeServed([pt(-7_200), pt(240), pt(360)]).unsupported).toEqual([]);
  });

  test("no scheduled start ⇒ nothing judged", () => {
    expect(judgeServed([pt(0), pt(12_437)], null, null).unsupported).toEqual([]);
  });

  test("the bucket rule is shared: the endpoint minutes keep their values", () => {
    const r = judgeServed([pt(0), pt(120), pt(1_200), pt(1_320)]);
    expect(bucketSupport(START + 120_000, r).kind).toBe("supported");
    expect(bucketSupport(START + 180_000, r).kind).toBe("gap");
    expect(bucketSupport(START + 1_200_000, r).kind).toBe("supported");
  });
});
