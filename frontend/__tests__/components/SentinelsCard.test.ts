// L2-153 — Sentinels card. The row rendering is a pure function
// (`evaluateSentinel`), so the three required states — fresh-green, red-verdict,
// silent-red — are asserted deterministically here (jest env is 'node', no DOM).
// Plus a module-load SSR guard: the real SSR-crash vector is module-scope browser
// access, and this proves the module has none.

import SentinelsCard, {
  evaluateSentinel,
  SENTINELS,
  SILENCE_MULTIPLIER,
  type SentinelSpec,
} from "@/components/admin/SentinelsCard";

const NOW = Date.parse("2026-07-22T14:00:00Z");
const HOUR = 3_600_000;

const flow = SENTINELS.find((s) => s.key === "flow")!;
const grid = SENTINELS.find((s) => s.key === "grid")!;
const settled = SENTINELS.find((s) => s.key === "settled")!;
const board = SENTINELS.find((s) => s.key === "board")!;

function iso(msAgo: number): string {
  return new Date(NOW - msAgo).toISOString();
}

describe("SentinelsCard specs", () => {
  it("covers the four sentinels with daily beats", () => {
    expect(SENTINELS).toHaveLength(4);
    expect(SENTINELS.map((s) => s.key).sort()).toEqual([
      "board",
      "flow",
      "grid",
      "settled",
    ]);
    for (const s of SENTINELS) {
      expect(s.beatIntervalHours).toBe(24);
      expect(s.endpoint).toMatch(/\/api\/admin\/.*-sentinel\/last$/);
    }
    expect(SILENCE_MULTIPLIER).toBe(1.5);
  });
});

describe("evaluateSentinel — board sentinel (Queue #258)", () => {
  it("board: clean run reads GREEN", () => {
    const payload = {
      generated_at: iso(1 * HOUR),
      verdict: "green",
      real: [],
      unknown: [],
      counts: { open_issues_scanned: 90, open_project_items: 90, open_alert_intake: 12 },
    };
    const v = evaluateSentinel(board, payload, false, NOW);
    expect(v.status).toBe("green");
    expect(v.headline).toBe("GREEN");
    expect(v.detail).toContain("board clean");
    expect(v.detail).toContain("90 open");
    expect(v.detail).toContain("90 on board");
    expect(v.detail).toContain("12 alert-intake");
  });

  it("board: real defects read RED and name the check kinds", () => {
    const payload = {
      generated_at: iso(1 * HOUR),
      verdict: "red",
      real: [
        { check: "duplicate_fingerprint", detail: "x" },
        { check: "stale_inbox", detail: "y" },
      ],
      unknown: [],
      counts: { open_alert_intake: 12 },
    };
    const v = evaluateSentinel(board, payload, false, NOW);
    expect(v.status).toBe("red");
    expect(v.headline).toBe("RED");
    expect(v.detail).toContain("duplicate_fingerprint");
    expect(v.detail).toContain("stale_inbox");
  });

  it("board: UNKNOWN verdict reads AMBER, never GREEN", () => {
    const payload = {
      generated_at: iso(1 * HOUR),
      verdict: "unknown",
      real: [],
      unknown: [{ check: "inbox_column_checks", detail: "z" }],
      counts: { open_alert_intake: 12 },
    };
    const v = evaluateSentinel(board, payload, false, NOW);
    expect(v.status).toBe("amber");
    expect(v.headline).toBe("UNKNOWN");
    expect(v.detail).toContain("not asserting clean");
    expect(v.detail).toContain("inbox_column_checks");
  });

  it("board: no_run_cached still reads SILENT-RED (guard-of-the-guards)", () => {
    const v = evaluateSentinel(board, { status: "no_run_cached" }, false, NOW);
    expect(v.status).toBe("red");
    expect(v.headline).toBe("SILENT");
  });
});

describe("evaluateSentinel — fresh-green", () => {
  it("settled: fresh clean run reads GREEN with age", () => {
    const payload = {
      generated_at: iso(2 * HOUR),
      as_of: "2026-07-22",
      targets: 2,
      green: 2,
      red: 0,
      concepts: [],
    };
    const v = evaluateSentinel(settled, payload, false, NOW);
    expect(v.status).toBe("green");
    expect(v.headline).toBe("GREEN");
    expect(v.ageText).toBe("ran 2h ago");
    expect(v.detail).toContain("2 green");
    expect(v.detail).toContain("0 red");
  });

  it("flow: clean run with no timestamp reads GREEN with 'age unknown' fallback", () => {
    // Pre-#232 transition state: a flow payload with no generated_at still reads
    // GREEN (never a false RED); age degrades to "age unknown", not "ran (cached)".
    const payload = {
      scorecard: { flows_total: 8, flows_passed: 8, flows_failed: 0, per_flow: [] },
    };
    const v = evaluateSentinel(flow, payload, false, NOW);
    expect(v.status).toBe("green");
    expect(v.headline).toBe("GREEN");
    expect(v.detail).toBe("8/8 flows passing");
    expect(v.ageText).toBe("age unknown");
  });

  it("flow: post-#232 payload with generated_at reads a real age", () => {
    // #232 adds generated_at to flow + grid too; the generic lastRunMs picks it
    // up so precise ages + stale-RED now apply to all three rows.
    const payload = {
      generated_at: iso(6 * HOUR),
      scorecard: { flows_total: 8, flows_passed: 8, flows_failed: 0, per_flow: [] },
    };
    const v = evaluateSentinel(flow, payload, false, NOW);
    expect(v.status).toBe("green");
    expect(v.ageText).toBe("ran 6h ago");
  });

  it("grid: post-#232 stale run (older than 1.5× beat) overrides to SILENT-RED", () => {
    // The stale-RED logic now applies to grid as well once it carries a timestamp.
    const payload = {
      generated_at: iso(40 * HOUR),
      scorecard: { leagues_total: 5, leagues_green: 5, leagues_red: 0, per_league: [] },
    };
    const v = evaluateSentinel(grid, payload, false, NOW);
    expect(v.status).toBe("red");
    expect(v.headline).toBe("SILENT");
    expect(v.ageText).toBe("ran 40h ago");
    expect(v.detail).toContain("older than 1.5×");
  });
});

describe("evaluateSentinel — red-verdict", () => {
  it("settled: a RED concept reads RED and names it", () => {
    const payload = {
      generated_at: iso(2 * HOUR),
      targets: 2,
      green: 1,
      red: 1,
      concepts: [
        { concept_key: "event:soccer:world-cup-2026", name: "FIFA World Cup 2026", verdict: "RED", n_real: 1 },
        { concept_key: "event:golf:the-open-championship", name: "The Open", verdict: "GREEN" },
      ],
    };
    const v = evaluateSentinel(settled, payload, false, NOW);
    expect(v.status).toBe("red");
    expect(v.headline).toBe("RED");
    expect(v.detail).toContain("1 RED of 2 concepts");
    expect(v.detail).toContain("FIFA World Cup 2026");
  });

  it("flow: failing flows read RED and name them", () => {
    const payload = {
      scorecard: {
        flows_total: 8,
        flows_passed: 6,
        flows_failed: 2,
        per_flow: [
          { flow: "duplicate_events", passed: false, skipped: false },
          { flow: "unlinked_held", passed: false, skipped: false },
          { flow: "search_gold_set", passed: true, skipped: false },
        ],
      },
    };
    const v = evaluateSentinel(flow, payload, false, NOW);
    expect(v.status).toBe("red");
    expect(v.headline).toBe("RED");
    expect(v.detail).toContain("2 of 8 flows failing");
    expect(v.detail).toContain("duplicate events");
    expect(v.detail).toContain("unlinked held");
  });

  it("grid: a RED league reads RED and names it", () => {
    const payload = {
      scorecard: {
        leagues_total: 5,
        leagues_green: 4,
        leagues_red: 1,
        per_league: [
          { league: "nba", verdict: "red" },
          { league: "mlb", verdict: "green" },
        ],
      },
    };
    const v = evaluateSentinel(grid, payload, false, NOW);
    expect(v.status).toBe("red");
    expect(v.headline).toBe("RED");
    expect(v.detail).toContain("1 of 5 leagues RED");
    expect(v.detail).toContain("nba");
  });
});

describe("evaluateSentinel — silent-red (the r236 state)", () => {
  it("no_run_cached reads SILENT-RED", () => {
    const payload = { status: "no_run_cached", key: "bainluck:flow_sentinel:last" };
    const v = evaluateSentinel(flow, payload, false, NOW);
    expect(v.status).toBe("red");
    expect(v.headline).toBe("SILENT");
    expect(v.ageText).toBe("no run cached");
    expect(v.detail).toContain("has not run");
  });

  it("null payload reads SILENT-RED", () => {
    const v = evaluateSentinel(grid, null, false, NOW);
    expect(v.status).toBe("red");
    expect(v.headline).toBe("SILENT");
    expect(v.ageText).toBe("no run cached");
  });

  it("a run older than 1.5× the beat overrides a clean verdict to SILENT-RED", () => {
    // 40h > 36h (1.5 × 24h). Even though the verdict is clean, staleness wins.
    const payload = {
      generated_at: iso(40 * HOUR),
      targets: 2,
      green: 2,
      red: 0,
      concepts: [],
    };
    const v = evaluateSentinel(settled, payload, false, NOW);
    expect(v.status).toBe("red");
    expect(v.headline).toBe("SILENT");
    expect(v.ageText).toBe("ran 40h ago");
    expect(v.detail).toContain("older than 1.5×");
  });

  it("a run just inside 1.5× the beat is NOT silent", () => {
    const payload = {
      generated_at: iso(30 * HOUR),
      targets: 2,
      green: 2,
      red: 0,
      concepts: [],
    };
    const v = evaluateSentinel(settled, payload, false, NOW);
    expect(v.status).toBe("green");
    expect(v.headline).toBe("GREEN");
    expect(v.ageText).toBe("ran 30h ago");
  });
});

describe("evaluateSentinel — unreachable (never hides)", () => {
  it("a fetch error reads amber UNREACHABLE, not a false green or red", () => {
    const v = evaluateSentinel(settled, null, true, NOW);
    expect(v.status).toBe("amber");
    expect(v.headline).toBe("UNREACHABLE");
    expect(v.ageText).toBe("unreachable");
    expect(v.detail).toContain("can't confirm");
  });
});

describe("SSR guard", () => {
  it("module loads under node with no browser access; default export is a component", () => {
    expect(typeof SentinelsCard).toBe("function");
    const spec: SentinelSpec = SENTINELS[0];
    expect(spec.label).toBeTruthy();
  });
});
