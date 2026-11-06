/**
 * #12102 S3 — the exams on the record say what their receipts say.
 *
 * Every figure and verdict in `data/runs-2026-11.json` is copied from a public
 * receipt, and `data/runs-2026-11.receipts.json` keeps the receipt's own words
 * beside it. This suite holds each value to its quote, so a slip in the copy
 * fails here instead of printing on the page. Where the receipt is a document
 * in this repo, it is cited at a fixed commit: a row is a dated record, so a
 * later edit to the document (a re-run of the same exam, say) cannot change
 * what the row's receipt said. (The quotes were checked against those commits
 * when transcribed — `git show <sha>:<path>`, or the GitHub contents API for the
 * audit on the still-open #11956; CI's shallow checkout cannot read old
 * commits, and reading today's file would break on a legitimate edit.)
 */

import RUNS_JSON from "@/lib/evals/data/runs-2026-11.json";
import RECEIPTS from "@/lib/evals/data/runs-2026-11.receipts.json";
import { formatUsd, loadRuns, modelName, notePieces, noteSlots, runProblem } from "@/lib/evals/runs";

type Quote = { quote: string; from: string };
const QUOTES = RECEIPTS.quotes as Record<string, Record<string, Quote>>;
const AUDIT_AT_COMMIT = "https://github.com/alexander-bain/bainluck/blob/a555441130/docs/calibration/AUDIT-2026-11.md";

/** A number as a receipt might print it: "1285", "1,285" or "1285.0". */
function spellings(value: number): string[] {
  return [String(value), value.toLocaleString("en-US")];
}

describe("the runs record", () => {
  const runs = loadRuns();

  it("loads every row, oldest first, and every row passes the shape check", () => {
    const raw = (RUNS_JSON as { runs: unknown[] }).runs;
    expect(runs).toHaveLength(raw.length);
    expect(raw.map(runProblem)).toEqual(raw.map(() => null));
    const dates = runs.map((r) => r.date);
    expect([...dates].sort()).toEqual(dates);
  });

  it("every figure appears in its receipt's own words", () => {
    for (const run of runs) {
      for (const [slot, figure] of Object.entries(run.figures)) {
        const q = QUOTES[run.id]?.[slot];
        expect({ run: run.id, slot, quoted: !!q }).toEqual({ run: run.id, slot, quoted: true });
        expect(spellings(figure.value).some((s) => q.quote.includes(s))).toBe(true);
      }
    }
  });

  it("every cost appears in its receipt, to the digit", () => {
    for (const run of runs.filter((r) => r.cost)) {
      const q = QUOTES[run.id]?.cost;
      expect(q?.quote).toContain(`$${String(run.cost?.value)}`);
    }
  });

  it("every verdict is the receipt's word, translated to a chip and never re-graded", () => {
    const words: Record<string, RegExp> = {
      fail: /\bFAIL\b|\bfailed\b|never passed/,
      not_eligible: /NO BASELINE MEASURABLE/,
      pass: /\bPASS\b|\bpassed\b/,
    };
    for (const run of runs) {
      const q = QUOTES[run.id]?.result;
      expect(q).toBeDefined();
      expect(q.quote).toMatch(words[run.result]);
    }
  });

  it("an AI run names the model its receipt names", () => {
    for (const run of runs.filter((r) => r.by === "ai_model")) {
      expect(QUOTES[run.id]?.model?.quote).toContain(run.model as string);
    }
  });

  it("a quote from a document in this repo cites the document at a fixed commit", () => {
    const fromRepo = Object.values(QUOTES)
      .flatMap((slots) => Object.values(slots))
      .filter((q) => q.from.startsWith("https://github.com/alexander-bain/bainluck/blob/"));
    expect(fromRepo.length).toBeGreaterThan(0);
    for (const q of fromRepo) {
      expect(q.from).toMatch(/\/blob\/[0-9a-f]{10,40}\/docs\/[\w./-]+\.md$/);
    }
  });

  it("a repeated run says it is not a fresh blind test, as its receipt discloses (Decide 39-A)", () => {
    const disclosed = runs.filter((r) => QUOTES[r.id]?.disclosure);
    expect(disclosed.map((r) => r.id)).toEqual(["twin-judge-exam-run-2"]);
    for (const run of disclosed) {
      expect(QUOTES[run.id].disclosure.quote).toMatch(/not fresh blind validation/);
      expect(run.note).toContain("not a fresh blind test");
    }
  });

  it("each run links the receipt its figures came from", () => {
    for (const run of runs) {
      for (const q of Object.values(QUOTES[run.id] ?? {})) {
        // A figure's quote comes from the row's receipt, or from the audit that
        // states the row's verdict (the calibration exit exam's), cited at the
        // audit's commit on #11956.
        expect([run.receipt.href, AUDIT_AT_COMMIT]).toContain(q.from);
      }
    }
  });
});

describe("a malformed row is dropped, never half-shown", () => {
  const good = (RUNS_JSON as { runs: Record<string, unknown>[] }).runs[2];

  it.each([
    ["no receipt link", { ...good, receipt: { label: "x", href: "" } }, /receipt/],
    ["an AI run with no model", { ...good, model: undefined }, /model/],
    ["a note slot with no figure", { ...good, note: "{missing} of them" }, /\{missing\}/],
    ["a cost with no basis", { ...good, cost: { value: 1 } }, /basis/],
    ["an unknown verdict", { ...good, result: "great" }, /result/],
  ])("%s", (_label, row, why) => {
    expect(runProblem(row)).toMatch(why);
    expect(loadRuns({ runs: [row] })).toEqual([]);
  });
});

describe("the row's words", () => {
  it("formats cents and names models the way a reader reads them", () => {
    expect(formatUsd(0.177876)).toBe("$0.18");
    expect(formatUsd(6.807833)).toBe("$6.81");
    expect(formatUsd(0.51)).toBe("$0.51");
    expect(modelName("claude-sonnet-5-5")).toBe("Claude Sonnet 5.5");
    expect(modelName("gpt-x")).toBe("gpt-x");
  });

  it("splits a note into words and figure slots", () => {
    expect(noteSlots("{a} of its {b} replies")).toEqual(["a", "b"]);
    expect(notePieces("{a} of its {b} replies")).toEqual([
      { slot: "a" },
      { text: " of its " },
      { slot: "b" },
      { text: " replies" },
    ]);
  });
});
