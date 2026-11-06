import exam from "../twin-exam-2026-11-05.json";

describe("the frozen baseline exam record (#12102 S0a)", () => {
  it("pins the five figures in the published run-1 receipt", () => {
    for (const pass of Object.values(exam.per_pass)) {
      expect(pass.test.per_relation.twin.recall).toMatchObject({ k: 24, n: 25 });
      expect(pass.test.false_twins).toMatchObject({ k: 0, n: 35 });
    }
    expect(Object.values(exam.per_pass).map((pass) => pass.test.wrong_merges)).toEqual([2, 2, 3]);
    expect(exam.consistency).toMatchObject({ k: 114, n: 120 });
    expect(exam.cost.total_usd).toBe(6.807833);
    expect(exam.cost.total_microusd).toBe(6807833);
  });

  it("preserves the failed verdict and held licences under the partial passes", () => {
    expect(exam.result).toBe("FAIL");
    expect(exam.activation).toBe("NONE");
    expect(exam.licences.twin).toBe("HELD");
    expect(exam.licences.same_number).toBe("HELD");
    expect(exam.gate_results).toHaveLength(9);
    for (const pass of ["1", "2", "3"] as const) {
      const results = exam.gate_results.map((gate) =>
        gate.by_pass ? gate.by_pass[pass].result : gate.observed?.result,
      );
      expect(results.filter((result) => result === "PASS")).toHaveLength(4);
      expect(results.filter((result) => result === "FAIL")).toHaveLength(5);
    }
  });

  it("keeps each split, denominator and observed failure rather than pooling passes", () => {
    expect(exam.expected_results).toBe(360);
    expect(exam.received_results).toBe(360);
    for (const pass of Object.values(exam.per_pass)) {
      expect(pass.test.expected).toBe(60);
      expect(pass.dev.expected).toBe(60);
      expect(pass.all.expected).toBe(120);
      for (const split of Object.values(pass)) {
        const relationRows: Record<string, {
          recall: { k: number; n: number };
          precision: { k: number; n: number };
        }> = split.per_relation;
        expect(Object.values(relationRows).reduce((n, row) => n + row.recall.n, 0)).toBe(split.expected);
        for (const row of Object.values(relationRows)) {
          expect(row.recall.k).toBeLessThanOrEqual(row.recall.n);
          expect(row.precision.k).toBeLessThanOrEqual(row.precision.n);
        }
      }
    }
    expect(exam.per_pass["2"].test.flags.nonverbatim_or_wrong_field_quote).toBe(1);
    expect(exam.per_pass["1"].test.per_relation.uncheckable.precision.wilson95).toBeNull();
  });

  it("carries phased usage-rated costs and source hashes", () => {
    let total = 0;
    for (const phase of ["pilot", "exam"] as const) {
      const usage = exam.cost.token_usage[phase];
      const microusd = usage.input_tokens * exam.cost.rates_usd_per_million.input
        + usage.output_tokens * exam.cost.rates_usd_per_million.output;
      expect(Math.round(exam.cost[`${phase}_usd`] * 1e6)).toBe(microusd);
      total += microusd;
    }
    expect(total).toBe(exam.cost.total_microusd);
    for (const hash of Object.values(exam.hashes)) expect(hash).toMatch(/^[a-f0-9]{64}$/);
    expect(exam.recorded_at_pt).toMatch(/^2026-11-05T.*-08:00$/);
  });

  it("exports aggregate identifiers and numbers, with no private pair rows or narrative", () => {
    function check(value: unknown): void {
      if (typeof value === "string") {
        expect(value).not.toMatch(/pair-\d+-\d+/);
        expect(value).toMatch(/^[A-Za-z0-9_.\/:#=+?%\-]+$/);
      } else if (value !== null && typeof value === "object") {
        for (const [key, child] of Object.entries(value)) {
          expect(["pair_id", "market_id", "outcome_id", "evidence", "messages", "content", "description", "title"]).not.toContain(key);
          check(child);
        }
      }
    }
    check(exam);
  });
});
