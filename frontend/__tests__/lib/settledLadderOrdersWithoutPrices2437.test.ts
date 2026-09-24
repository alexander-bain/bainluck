// #2437 — a settled quantity ladder needs an ordering signal that survives
// settlement. The first block documents what #4568's chronological tiebreak
// already buys (price-free order for date rungs); the second pins the settled
// builder's contract: label chronology is the WHOLE order (never the grade,
// never the price), and a refusal everywhere it cannot order honestly.
import {
  buildOutcomeLadderRungs,
  buildSettledOutcomeLadderRungs,
  type SettledLadderOutcome,
} from "@/lib/futuresLadder";

// The real 109349 serve order (fixture verbatim: 2027, October, April, July),
// settled the way its own rungs would settle: iPhone ships in September, so
// October + 2027 true, April + July false, probabilities collapsed to 1/0.
const SETTLED_109349 = [
  { id: 1596638, name: "Before 2027", probability: 1 },
  { id: 1596639, name: "Before October", probability: 1 },
  { id: 1596641, name: "Before April", probability: 0 },
  { id: 1596640, name: "Before July", probability: 0 },
];

describe("#2437 probe: settled date ladder order on current source", () => {
  test("collapsed 1/0 prices in backwards serve order still ladder chronologically", () => {
    const rungs = buildOutcomeLadderRungs(SETTLED_109349, "cumulative");
    expect(rungs.map((r) => r.label)).toEqual([
      "Before April",
      "Before July",
      "Before October",
      "Before 2027",
    ]);
  });

  test("all-one-probability (total collapse) still ladders chronologically", () => {
    const rows = SETTLED_109349.map((o) => ({ ...o, probability: 1 }));
    const rungs = buildOutcomeLadderRungs(rows, "cumulative");
    expect(rungs.map((r) => r.label)).toEqual([
      "Before April",
      "Before July",
      "Before October",
      "Before 2027",
    ]);
  });

  test("non-date cumulative rungs keep serve order (the remaining gap)", () => {
    const rows = [
      { id: 1, name: "Over 9000", probability: 1 },
      { id: 2, name: "Over 7000", probability: 1 },
      { id: 3, name: "Over 5000", probability: 0 },
    ];
    const rungs = buildOutcomeLadderRungs(rows, "cumulative");
    // Price groups partition (0s before 1s) but WITHIN each group there is no
    // signal — serve order stands, which may be wrong. Documented, not fixed.
    expect(rungs.map((r) => r.label)).toEqual(["Over 5000", "Over 9000", "Over 7000"]);
  });
});

const GRADED_109349: SettledLadderOutcome[] = [
  { id: 1596638, name: "Before 2027", probability: 1, verdict: "won" },
  { id: 1596639, name: "Before October", probability: 1, verdict: "won" },
  { id: 1596641, name: "Before April", probability: 0, verdict: "lost" },
  { id: 1596640, name: "Before July", probability: 0, verdict: "lost" },
];

describe("#2437 settled builder: chronological order, refusal everywhere else", () => {
  test("a fully graded ladder reads as its timeline, April to 2027", () => {
    const rungs = buildSettledOutcomeLadderRungs(GRADED_109349, "cumulative");
    expect(rungs!.map((r) => r.label)).toEqual([
      "Before April",
      "Before July",
      "Before October",
      "Before 2027",
    ]);
    expect(rungs!.map((r) => r.verdict)).toEqual(["lost", "lost", "won", "won"]);
  });

  test("a frozen price that contradicts the grade cannot re-scramble the timeline", () => {
    // The winner's last recorded price never repriced to 1.0 — price-ascending
    // would bury it among the losers. The labels are the order, not the price.
    const rows = GRADED_109349.map((o) =>
      o.name === "Before October" ? { ...o, probability: 0.01 } : o,
    );
    const rungs = buildSettledOutcomeLadderRungs(rows, "cumulative");
    expect(rungs!.map((r) => r.label)).toEqual([
      "Before April",
      "Before July",
      "Before October",
      "Before 2027",
    ]);
  });

  test("graded rungs print 100%/0%; an ungraded rung keeps its served price", () => {
    const rows = GRADED_109349.map((o) =>
      o.name === "Before April" ? { ...o, verdict: null, probability: 0.42 } : o,
    );
    const rungs = buildSettledOutcomeLadderRungs(rows, "cumulative");
    expect(rungs!.map((r) => r.probability)).toEqual([0.42, 0, 1, 1]);
  });

  test("CODEX COUNTEREXAMPLE: an ungraded rung keeps its place in time", () => {
    // April lost, July won, October null, 2027 won — a permitted partial grade
    // (the retracted/withheld rung reaches here as `verdict: null`). The first
    // version partitioned by grade and rendered April, OCTOBER, JULY, 2027: the
    // ungraded rung jumped ahead of a known winner. The timeline must hold.
    const rows: SettledLadderOutcome[] = [
      { id: 1, name: "Before April", probability: 0, verdict: "lost" },
      { id: 2, name: "Before July", probability: 1, verdict: "won" },
      { id: 3, name: "Before October", probability: null, verdict: null },
      { id: 4, name: "Before 2027", probability: 1, verdict: "won" },
    ];
    const rungs = buildSettledOutcomeLadderRungs(rows, "cumulative");
    expect(rungs!.map((r) => r.label)).toEqual([
      "Before April",
      "Before July",
      "Before October",
      "Before 2027",
    ]);
    // The null rung states nothing and keeps its served (null) price.
    expect(rungs!.map((r) => r.verdict)).toEqual(["lost", "won", null, "won"]);
    expect(rungs![2].probability).toBeNull();
    expect(rungs!.map((r) => r.value)).toEqual([0, 1, 2, 3]);
  });

  test("the same partial grade in scrambled serve order still reads chronologically", () => {
    const rows: SettledLadderOutcome[] = [
      { id: 4, name: "Before 2027", probability: 1, verdict: "won" },
      { id: 3, name: "Before October", probability: 0.37, verdict: null },
      { id: 2, name: "Before July", probability: 1, verdict: "won" },
      { id: 1, name: "Before April", probability: 0, verdict: "lost" },
    ];
    const rungs = buildSettledOutcomeLadderRungs(rows, "cumulative");
    expect(rungs!.map((r) => r.label)).toEqual([
      "Before April",
      "Before July",
      "Before October",
      "Before 2027",
    ]);
    expect(rungs![2].probability).toBe(0.37);
  });

  test("a LOST rung after a WON one is a contradiction — refuse, the table renders", () => {
    // On a cumulative "before X" ladder a later deadline contains every earlier
    // one: July true and October false cannot both hold. No timeline is honest.
    const rows: SettledLadderOutcome[] = [
      { id: 1, name: "Before April", probability: 0, verdict: "lost" },
      { id: 2, name: "Before July", probability: 1, verdict: "won" },
      { id: 3, name: "Before October", probability: 0, verdict: "lost" },
      { id: 4, name: "Before 2027", probability: 1, verdict: "won" },
    ];
    expect(buildSettledOutcomeLadderRungs(rows, "cumulative")).toBeNull();
  });

  test("zero stated winners refuses (gotcha #53: graded-losers vs never-graded)", () => {
    const rows = GRADED_109349.map((o) => ({ ...o, verdict: "lost" as const }));
    expect(buildSettledOutcomeLadderRungs(rows, "cumulative")).toBeNull();
  });

  test("non-date cumulative rungs refuse — no settlement-proof fine order", () => {
    const rows = [
      { id: 1, name: "Over 9000", probability: 1, verdict: "won" as const },
      { id: 2, name: "Over 7000", probability: 1, verdict: "won" as const },
      { id: 3, name: "Over 5000", probability: 0, verdict: "lost" as const },
    ];
    expect(buildSettledOutcomeLadderRungs(rows, "cumulative")).toBeNull();
  });

  test("a forward-pointing rung refuses the whole ladder", () => {
    const rows = [
      { id: 1, name: "After March", probability: 0, verdict: "lost" as const },
      { id: 2, name: "After June", probability: 1, verdict: "won" as const },
    ];
    expect(buildSettledOutcomeLadderRungs(rows, "cumulative")).toBeNull();
  });

  test("disjoint bins refuse — a bin set has no ladder order at all", () => {
    expect(buildSettledOutcomeLadderRungs(GRADED_109349, "served")).toBeNull();
  });
});
