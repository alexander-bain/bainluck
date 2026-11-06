import exam from "../twin-exam-2026-11-05.json";
import confusion from "../twin-confusion-2026-11-05.json";

const heldOutDenominators = {
  twin: 25, same_number: 12, implies: 3, path_step: 2, by_when: 2,
  same_decision: 1, grouping: 1, related: 7, unrelated: 4, uncheckable: 3,
};

describe("the aggregate confusion record (#12102 S0b)", () => {
  it("uses the same frozen run and score as the report card", () => {
    expect(confusion.run_id).toBe(exam.run_id);
    expect(confusion.score_sha256).toBe(exam.hashes.score);
    expect(confusion.recorded_at_pt).toBe(exam.recorded_at_pt);
    expect(confusion.receipt_url).toBe(exam.receipt_url);
  });

  it.each(["1", "2", "3"] as const)("keeps every held-out denominator on pass %s", (pass) => {
    const section = confusion.per_pass[pass].test;
    expect(section.n).toBe(60);
    expect(Object.keys(section.rows).sort()).toEqual(Object.keys(heldOutDenominators).sort());
    for (const [relation, n] of Object.entries(heldOutDenominators)) {
      const row = section.rows[relation as keyof typeof section.rows];
      expect(row.n).toBe(n);
      expect(Object.values(row.counts).reduce((sum, count) => sum + count, 0)).toBe(n);
    }
  });

  it.each(["1", "2", "3"] as const)("agrees with recall and precision on pass %s in both splits", (pass) => {
    for (const split of ["test", "dev"] as const) {
      const section = confusion.per_pass[pass][split];
      const metrics = exam.per_pass[pass][split].per_relation;
      expect(Object.values(section.rows).reduce((sum, row) => sum + row.n, 0)).toBe(60);
      for (const relation of Object.keys(metrics) as Array<keyof typeof metrics>) {
        const row = section.rows[relation];
        const predictions = Object.values(section.rows).reduce((sum, truthRow) => sum + truthRow.counts[relation], 0);
        expect(row.n).toBe(metrics[relation].recall.n);
        expect(row.counts[relation]).toBe(metrics[relation].recall.k);
        expect(predictions).toBe(metrics[relation].precision.n);
        for (const count of Object.values(row.counts)) {
          expect(Number.isInteger(count)).toBe(true);
          expect(count).toBeGreaterThanOrEqual(0);
        }
      }
    }
  });

  it("retains wrong answers and contains no per-pair answer key", () => {
    expect(confusion.per_pass["1"].test.rows.uncheckable.counts.same_number).toBe(2);
    expect(confusion.per_pass["3"].test.rows.related.counts.path_step).toBe(1);
    const text = JSON.stringify(confusion);
    expect(text).not.toMatch(/pair-\d+-\d+/);
    for (const key of ["pair_id", "market_id", "outcome_id", "evidence", "messages", "title", "description"]) {
      expect(text).not.toContain(`"${key}":`);
    }
  });
});
