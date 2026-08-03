// L2-241 Item 2 — the foreground failure terminal, case for case against C132
// (backend/tests/evals/fixtures/first_card_client_contract.json).
//
// The bug this locks down: a slow or aborted INITIAL feed request keeps the
// loading skeleton on screen through a generic retry sequence, with no honest
// terminal (C132 RETRIES_HOLD_SKELETON). The fix reaches a terminal — last-good
// if present, otherwise a retry — but a SLOW-but-not-failed request may only do
// so against an APPROVED budget (C132 FOREGROUND_BUDGET_NEEDS_APPROVAL), so with
// no approved budget a slow request stays loading rather than inventing a
// timeout.

import {
  decideForegroundTerminal,
  shouldApplyResponse,
  FOREGROUND_FEED_BUDGET_MS,
} from "@/lib/discover/foregroundTerminal";

describe("decideForegroundTerminal — no approved budget", () => {
  it("keeps a slow, pending request in loading — never invents a timeout", () => {
    const d = decideForegroundTerminal({
      elapsedMs: 60_000,
      budgetMs: null,
      aborted: false,
      failed: false,
      hasLastGood: false,
    });
    expect(d.state).toBe("loading");
    expect(d.showSkeleton).toBe(true);
    expect(d.allowBackgroundRetry).toBe(false);
    expect(d.reason).toBe("no-approved-budget:waiting");
  });

  it("still terminates on an ABORT with no budget (the RETRIES_HOLD_SKELETON fix)", () => {
    const d = decideForegroundTerminal({
      elapsedMs: 1_200,
      budgetMs: null,
      aborted: true,
      hasLastGood: false,
    });
    expect(d.state).toBe("terminal-retry");
    expect(d.showSkeleton).toBe(false);
    expect(d.allowBackgroundRetry).toBe(true);
    expect(d.reason).toBe("aborted:retry");
  });

  it("still terminates on an outright FAILURE with no budget", () => {
    const d = decideForegroundTerminal({
      elapsedMs: 800,
      budgetMs: null,
      aborted: false,
      failed: true,
      hasLastGood: false,
    });
    expect(d.state).toBe("terminal-retry");
    expect(d.showSkeleton).toBe(false);
  });
});

describe("decideForegroundTerminal — approved budget", () => {
  it("within budget stays loading", () => {
    const d = decideForegroundTerminal({
      elapsedMs: 1_000,
      budgetMs: 3_000,
      aborted: false,
      hasLastGood: false,
    });
    expect(d.state).toBe("loading");
    expect(d.showSkeleton).toBe(true);
    expect(d.reason).toBe("within-budget");
  });

  it("past budget terminates honestly with a retry when there is no last-good", () => {
    const d = decideForegroundTerminal({
      elapsedMs: 3_000,
      budgetMs: 3_000,
      aborted: false,
      hasLastGood: false,
    });
    expect(d.state).toBe("terminal-retry");
    expect(d.showSkeleton).toBe(false);
    expect(d.allowBackgroundRetry).toBe(true);
    expect(d.reason).toBe("budget-exceeded:retry");
  });

  it("a non-positive or non-finite budget is treated as no budget", () => {
    for (const bad of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
      const d = decideForegroundTerminal({
        elapsedMs: 99_999,
        budgetMs: bad,
        aborted: false,
        hasLastGood: false,
      });
      expect(d.state).toBe("loading");
    }
  });
});

describe("decideForegroundTerminal — last-good is preserved, never cleared", () => {
  it("a budget-exceeded terminal keeps last-good on screen", () => {
    const d = decideForegroundTerminal({
      elapsedMs: 5_000,
      budgetMs: 3_000,
      aborted: false,
      hasLastGood: true,
    });
    expect(d.state).toBe("terminal-last-good");
    expect(d.showSkeleton).toBe(false);
    expect(d.allowBackgroundRetry).toBe(true);
    expect(d.reason).toBe("budget-exceeded:last-good");
  });

  it("an aborted request with last-good preserves it rather than showing a bare retry", () => {
    const d = decideForegroundTerminal({
      elapsedMs: 400,
      budgetMs: null,
      aborted: true,
      hasLastGood: true,
    });
    expect(d.state).toBe("terminal-last-good");
    expect(d.reason).toBe("aborted:last-good");
  });
});

describe("shouldApplyResponse — no stale/foreign overwrite (STALE_PRINCIPAL_OVERWRITE)", () => {
  it("applies a response for the current generation and principal", () => {
    expect(
      shouldApplyResponse({
        responseGeneration: 4,
        currentGeneration: 4,
        responsePrincipal: "anon",
        currentPrincipal: "anon",
      })
    ).toBe(true);
  });

  it("rejects a superseded generation", () => {
    expect(
      shouldApplyResponse({
        responseGeneration: 3,
        currentGeneration: 4,
        responsePrincipal: "anon",
        currentPrincipal: "anon",
      })
    ).toBe(false);
  });

  it("rejects a late anonymous response landing on a signed-in generation", () => {
    expect(
      shouldApplyResponse({
        responseGeneration: 4,
        currentGeneration: 4,
        responsePrincipal: "anon",
        currentPrincipal: "user-123",
      })
    ).toBe(false);
  });
});

describe("the approved budget is unset — the rail ships inert, awaiting Alex", () => {
  it("FOREGROUND_FEED_BUDGET_MS is null until a product value is approved", () => {
    expect(FOREGROUND_FEED_BUDGET_MS).toBeNull();
  });
});
