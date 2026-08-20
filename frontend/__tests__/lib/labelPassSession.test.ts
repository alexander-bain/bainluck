// L2-168 — Label Speed Pass velocity guard. jest env is 'node', so the session
// logic lives as pure functions (labelPassSession.ts) and is asserted directly:
// keyboard bindings, accept → applied-count bump, kill-switch-off leaves the
// applied count unchanged, undo → revert, optimistic rollback, arrow nav bounds.

import {
  INITIAL_SESSION,
  keyToAction,
  recordVerdict,
  reconcileVerdict,
  rollbackVerdict,
  undoLast,
  navigate,
  sessionTotals,
  progressLabel,
  verdictRefusal,
  refusalMessage,
  type SessionState,
  type VerdictEntry,
} from "@/lib/labelPassSession";

function entry(over: Partial<VerdictEntry>): VerdictEntry {
  return { uid: 1, id: 100, verdict: "accept", applied: false, pending: false, ...over };
}

describe("keyToAction — bindings", () => {
  it("a / A / j / J → accept", () => {
    for (const k of ["a", "A", "j", "J"]) expect(keyToAction(k)).toBe("accept");
  });
  it("r / R / k / K → reject", () => {
    for (const k of ["r", "R", "k", "K"]) expect(keyToAction(k)).toBe("reject");
  });
  it("s / S / space → skip", () => {
    for (const k of ["s", "S", " "]) expect(keyToAction(k)).toBe("skip");
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
    for (const k of ["x", "Enter", "Escape", "1", "Tab"]) expect(keyToAction(k)).toBeNull();
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

describe("accept → applied count bump", () => {
  it("an accept whose POST reports applied bumps the live applied count", () => {
    let s = recordVerdict(INITIAL_SESSION, entry({ uid: 1, verdict: "accept", applied: false, pending: true }));
    // still pending — not yet counted as applied
    expect(sessionTotals(s).applied).toBe(0);
    // POST resolves with applied=true (kill switch on, promote proposal)
    s = reconcileVerdict(s, 1, { newId: 555, applied: true });
    const t = sessionTotals(s);
    expect(t.accepted).toBe(1);
    expect(t.applied).toBe(1);
    expect(s.history[0].pending).toBe(false);
    expect(s.history[0].newId).toBe(555);
    expect(progressLabel(s, 354)).toContain("1 applied");
  });
});

describe("kill-switch-off — applied count unchanged", () => {
  it("an accept whose POST reports applied=false still counts as accepted but not applied", () => {
    let s = recordVerdict(INITIAL_SESSION, entry({ uid: 1, verdict: "accept", pending: true }));
    s = reconcileVerdict(s, 1, { newId: 777, applied: false });
    const t = sessionTotals(s);
    expect(t.accepted).toBe(1);
    expect(t.applied).toBe(0);
    expect(progressLabel(s, 354)).toBe("1 of 354 · 0 applied · 0 rejected");
  });
});

describe("undoLast — revert", () => {
  it("pops the most recent verdict, steps the pointer back, and returns it for server undo", () => {
    let s = recordVerdict(INITIAL_SESSION, entry({ uid: 1, verdict: "accept", newId: 900, applied: true }));
    s = recordVerdict(s, entry({ uid: 2, id: 101, verdict: "reject", newId: 901 }));
    expect(s.index).toBe(2);

    const { state, undone } = undoLast(s);
    expect(undone?.uid).toBe(2);
    expect(undone?.newId).toBe(901); // caller uses this to DELETE the row
    expect(state.index).toBe(1);
    expect(state.history).toHaveLength(1);
    // the applied accept survives
    expect(sessionTotals(state).applied).toBe(1);
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
    s = recordVerdict(s, entry({ uid: 2, id: 101 }));
    const rolled = rollbackVerdict(s, 2);
    expect(rolled.history.map((h) => h.uid)).toEqual([1]);
    expect(rolled.index).toBe(1); // stepped back
  });

  it("drops a failed non-tail verdict without moving the pointer", () => {
    let s = recordVerdict(INITIAL_SESSION, entry({ uid: 1 }));
    s = recordVerdict(s, entry({ uid: 2, id: 101 }));
    const rolled = rollbackVerdict(s, 1);
    expect(rolled.history.map((h) => h.uid)).toEqual([2]);
    expect(rolled.index).toBe(2); // unchanged — user already moved on
  });

  it("is a no-op for an unknown uid", () => {
    const s = recordVerdict(INITIAL_SESSION, entry({ uid: 1 }));
    expect(rollbackVerdict(s, 99)).toBe(s);
  });
});

describe("reconcileVerdict — targets the right entry", () => {
  it("only patches the matching uid", () => {
    let s = recordVerdict(INITIAL_SESSION, entry({ uid: 1, verdict: "accept", pending: true }));
    s = recordVerdict(s, entry({ uid: 2, id: 101, verdict: "accept", pending: true }));
    s = reconcileVerdict(s, 2, { applied: true });
    expect(s.history.find((h) => h.uid === 1)?.applied).toBe(false);
    expect(s.history.find((h) => h.uid === 2)?.applied).toBe(true);
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

describe("progressLabel — strip format", () => {
  it('renders "14 of 354 · 9 applied · 2 rejected"', () => {
    let s: SessionState = INITIAL_SESSION;
    let uid = 0;
    // 9 applied accepts
    for (let i = 0; i < 9; i++) s = recordVerdict(s, entry({ uid: ++uid, id: uid, verdict: "accept", applied: true }));
    // 3 accepts that did not apply (kill switch off / non-applied)
    for (let i = 0; i < 3; i++) s = recordVerdict(s, entry({ uid: ++uid, id: uid, verdict: "accept", applied: false }));
    // 2 rejects
    for (let i = 0; i < 2; i++) s = recordVerdict(s, entry({ uid: ++uid, id: uid, verdict: "reject" }));
    expect(sessionTotals(s).reviewed).toBe(14);
    expect(progressLabel(s, 354)).toBe("14 of 354 · 9 applied · 2 rejected");
  });

  it("appends skipped only when non-zero", () => {
    let s = recordVerdict(INITIAL_SESSION, entry({ uid: 1, verdict: "skip" }));
    expect(progressLabel(s, 354)).toBe("1 of 354 · 0 applied · 0 rejected · 1 skipped");
  });
});

// ── #1542/#1873: the refusal reader ────────────────────────────────────────
// `adminFetchJSON` throws `Admin API error <status>: <body slice>`, so the typed
// 409 reason has to be recovered from a string. These pin the two ways that goes
// wrong: reading a reason out of a NON-409 (a 500 mentioning a market is not a
// refusal), and reaching for JSON.parse on a body the helper already truncated.
describe("verdictRefusal", () => {
  const body = (reason: string) =>
    new Error(
      `Admin API error 409: {"detail":{"status":"conflict","reason":"${reason}","applied":false,"writes":0,"expected":"ab12`
    );

  it("reads the typed reason out of a truncated 409 body", () => {
    expect(verdictRefusal(body("card_drifted"))).toBe("card_drifted");
    expect(verdictRefusal(body("card_fingerprint_missing"))).toBe("card_fingerprint_missing");
    expect(verdictRefusal(body("lifecycle_terminal"))).toBe("lifecycle_terminal");
    expect(verdictRefusal(body("duplicate_verdict"))).toBe("duplicate_verdict");
  });

  it("does not parse the body as JSON", () => {
    // The truncation above cuts mid-object; JSON.parse would throw and a
    // catch-all would return null in exactly the case this exists for.
    expect(() => JSON.parse(body("card_drifted").message.split(": ").slice(1).join(": "))).toThrow();
    expect(verdictRefusal(body("card_drifted"))).toBe("card_drifted");
  });

  it("is not fooled by a non-409 that happens to mention a reason", () => {
    expect(verdictRefusal(new Error("Admin API error 500: market_missing in log line"))).toBeNull();
    expect(verdictRefusal(new Error("NetworkError when attempting to fetch"))).toBeNull();
    expect(verdictRefusal(null)).toBeNull();
    expect(verdictRefusal(undefined)).toBeNull();
  });

  it("returns null for a 409 whose reason is not one we know", () => {
    expect(verdictRefusal(new Error('Admin API error 409: {"reason":"something_new"}'))).toBeNull();
  });
});

describe("refusalMessage", () => {
  it("tells the reader nothing was recorded, in every branch", () => {
    for (const r of [
      "card_drifted",
      "card_fingerprint_missing",
      "duplicate_verdict",
      "lifecycle_terminal",
      "market_missing",
    ] as const) {
      expect(refusalMessage(r).toLowerCase()).toContain("nothing was recorded");
    }
  });

  it("names the re-price for the drift case, since that is the one Alex can act on", () => {
    expect(refusalMessage("card_drifted")).toMatch(/re-priced/i);
  });
});
