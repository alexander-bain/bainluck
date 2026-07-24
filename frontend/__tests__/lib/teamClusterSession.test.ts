// L2-173 — Team-cluster adjudication velocity guard. jest env is 'node', so the
// session logic lives as pure functions (teamClusterSession.ts) and is asserted
// directly: keyboard bindings, verdict counts, undo → revert, optimistic
// rollback, arrow nav bounds, and merge-is-irreversible.

import {
  INITIAL_SESSION,
  keyToAction,
  isReversible,
  recordVerdict,
  reconcileVerdict,
  rollbackVerdict,
  undoLast,
  navigate,
  sessionTotals,
  progressLabel,
  type SessionState,
  type VerdictEntry,
} from "@/lib/teamClusterSession";

function entry(over: Partial<VerdictEntry>): VerdictEntry {
  return {
    uid: 1,
    clusterKey: "nba:1-2",
    verdict: "keep_separate",
    reversible: true,
    pending: false,
    ...over,
  };
}

describe("keyToAction — bindings", () => {
  it("m / M → merge", () => {
    for (const k of ["m", "M"]) expect(keyToAction(k)).toBe("merge");
  });
  it("k / K → keep_separate", () => {
    for (const k of ["k", "K"]) expect(keyToAction(k)).toBe("keep_separate");
  });
  it("d / D → defer", () => {
    for (const k of ["d", "D"]) expect(keyToAction(k)).toBe("defer");
  });
  it("u / U → undo", () => {
    expect(keyToAction("u")).toBe("undo");
    expect(keyToAction("U")).toBe("undo");
  });
  it("arrows → navigate", () => {
    expect(keyToAction("ArrowRight")).toBe("next");
    expect(keyToAction("ArrowLeft")).toBe("prev");
  });
  it("unbound keys → null", () => {
    for (const k of ["a", "r", "s", "Enter", "1", "Tab"]) expect(keyToAction(k)).toBeNull();
  });
});

describe("isReversible", () => {
  it("merge is terminal; keep/defer are reversible", () => {
    expect(isReversible("merge")).toBe(false);
    expect(isReversible("keep_separate")).toBe(true);
    expect(isReversible("defer")).toBe(true);
  });
});

describe("recordVerdict — optimistic advance", () => {
  it("appends the entry and steps the pointer forward", () => {
    const s = recordVerdict(INITIAL_SESSION, entry({ uid: 1 }));
    expect(s.index).toBe(1);
    expect(s.history).toHaveLength(1);
    // INITIAL_SESSION is not mutated
    expect(INITIAL_SESSION.index).toBe(0);
    expect(INITIAL_SESSION.history).toHaveLength(0);
  });
});

describe("verdict counts", () => {
  it("tallies merged / kept / deferred", () => {
    let s: SessionState = INITIAL_SESSION;
    let uid = 0;
    for (let i = 0; i < 3; i++) s = recordVerdict(s, entry({ uid: ++uid, verdict: "merge", reversible: false }));
    for (let i = 0; i < 2; i++) s = recordVerdict(s, entry({ uid: ++uid, verdict: "keep_separate" }));
    s = recordVerdict(s, entry({ uid: ++uid, verdict: "defer" }));
    const t = sessionTotals(s);
    expect(t.reviewed).toBe(6);
    expect(t.merged).toBe(3);
    expect(t.kept).toBe(2);
    expect(t.deferred).toBe(1);
    expect(progressLabel(s, 189)).toBe("6 of 189 · 3 merged · 2 kept · 1 deferred");
  });

  it("omits deferred from the strip when zero", () => {
    const s = recordVerdict(INITIAL_SESSION, entry({ uid: 1, verdict: "merge", reversible: false }));
    expect(progressLabel(s, 189)).toBe("1 of 189 · 1 merged · 0 kept");
  });
});

describe("reconcileVerdict — clears pending on the right entry", () => {
  it("only patches the matching uid", () => {
    let s = recordVerdict(INITIAL_SESSION, entry({ uid: 1, pending: true }));
    s = recordVerdict(s, entry({ uid: 2, clusterKey: "nba:3-4", pending: true }));
    s = reconcileVerdict(s, 2);
    expect(s.history.find((h) => h.uid === 1)?.pending).toBe(true);
    expect(s.history.find((h) => h.uid === 2)?.pending).toBe(false);
  });
});

describe("undoLast — revert", () => {
  it("pops the most recent verdict, steps the pointer back, and returns it", () => {
    let s = recordVerdict(INITIAL_SESSION, entry({ uid: 1, verdict: "merge", reversible: false }));
    s = recordVerdict(s, entry({ uid: 2, clusterKey: "nba:3-4", verdict: "keep_separate" }));
    expect(s.index).toBe(2);

    const { state, undone } = undoLast(s);
    expect(undone?.uid).toBe(2);
    expect(undone?.clusterKey).toBe("nba:3-4");
    expect(state.index).toBe(1);
    expect(state.history).toHaveLength(1);
    // the merge survives
    expect(sessionTotals(state).merged).toBe(1);
  });

  it("no-ops on an empty session", () => {
    const { state, undone } = undoLast(INITIAL_SESSION);
    expect(undone).toBeNull();
    expect(state).toBe(INITIAL_SESSION);
  });
});

describe("rollbackVerdict — optimistic error recovery", () => {
  it("drops a failed tail verdict and steps the pointer back for retry", () => {
    let s = recordVerdict(INITIAL_SESSION, entry({ uid: 1 }));
    s = recordVerdict(s, entry({ uid: 2, clusterKey: "nba:3-4" }));
    const rolled = rollbackVerdict(s, 2);
    expect(rolled.history.map((h) => h.uid)).toEqual([1]);
    expect(rolled.index).toBe(1);
  });

  it("drops a failed non-tail verdict without moving the pointer", () => {
    let s = recordVerdict(INITIAL_SESSION, entry({ uid: 1 }));
    s = recordVerdict(s, entry({ uid: 2, clusterKey: "nba:3-4" }));
    const rolled = rollbackVerdict(s, 1);
    expect(rolled.history.map((h) => h.uid)).toEqual([2]);
    expect(rolled.index).toBe(2);
  });

  it("is a no-op for an unknown uid", () => {
    const s = recordVerdict(INITIAL_SESSION, entry({ uid: 1 }));
    expect(rollbackVerdict(s, 99)).toBe(s);
  });
});

describe("navigate — arrow bounds", () => {
  it("prev clamps at 0", () => {
    expect(navigate(INITIAL_SESSION, "prev", 10).index).toBe(0);
  });
  it("next clamps at total (the completion sentinel)", () => {
    const s: SessionState = { index: 10, history: [] };
    expect(navigate(s, "next", 10).index).toBe(10);
  });
  it("moves the pointer without recording a verdict", () => {
    const s: SessionState = { index: 3, history: [] };
    const fwd = navigate(s, "next", 10);
    expect(fwd.index).toBe(4);
    expect(fwd.history).toHaveLength(0);
    expect(navigate(s, "prev", 10).index).toBe(2);
  });
});
