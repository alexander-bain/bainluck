/**
 * @jest-environment jsdom
 */

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import SiblingFamilyExamSection from "@/components/evals/SiblingFamilyExamSection";
import RAW_SIBLING_EXAM from "@/lib/evals/data/sibling-family-exam-2026-11.json";
import { scanEvalsDom } from "@/lib/evals/scanEvalsDom";
import {
  SIBLING_EXAM_GATE_IDS,
  loadSiblingFamilyExam,
  siblingFamilyExamProblem,
} from "@/lib/evals/siblingFamilyExam";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | null = null;
let host: HTMLElement | null = null;

async function mount(node: React.ReactElement): Promise<HTMLElement> {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root?.render(node);
  });
  return host;
}

afterEach(async () => {
  await act(async () => root?.unmount());
  host?.remove();
  root = null;
  host = null;
});

describe("#12374: sibling-family exam data and /evals section", () => {
  it("loads the committed sibling-family exam record with 20 set-aside test cards and all 4 gates PASS under Decide 117-A", async () => {
    expect(siblingFamilyExamProblem(RAW_SIBLING_EXAM)).toBeNull();
    const exam = loadSiblingFamilyExam();
    expect(exam).not.toBeNull();
    expect(exam?.splitCounts).toEqual({ test: 20, dev: 12, all: 32 });
    expect(exam?.result).toBe("pass");
    expect(exam?.licences).toEqual({ sibling_family: "pass" });
    expect(exam?.cost.estimatedUsd).toBeLessThan(5.0);
    expect(exam?.cost.actualUsd).toBeLessThan(5.0);
    expect(exam?.cost.replies).toBe(96);
    expect(exam?.hashes.datasetSha256).toMatch(/^[0-9a-f]{64}$/);
    expect(exam?.hashes.scorerSha256).toMatch(/^[0-9a-f]{64}$/);

    expect(exam?.gates.map((g) => g.id)).toEqual([...SIBLING_EXAM_GATE_IDS]);
    const byId = Object.fromEntries(exam!.gates.map((g) => [g.id, g.result]));
    expect(byId).toEqual({
      card_vs_single_member: "pass",
      relation_truth: "pass",
      freshness_and_count: "pass",
      run_to_run_stability: "pass",
    });

    const el = await mount(<SiblingFamilyExamSection exam={exam!} />);
    const gate1Row = el.querySelector('[data-sibling-gate="card_vs_single_member"]');
    expect(gate1Row?.getAttribute("data-result")).toBe("pass");
    expect(gate1Row?.textContent).toContain("20/20 (83.9–100.0%)");
    expect(gate1Row?.textContent).toContain(
      "Counting 'Amazing' and 'Fine' as better; strict 'Amazing' only: 20/20 (100.0%)"
    );
    expect(gate1Row?.textContent).toContain(
      "The interval's low end is 83.9%, which is what 20 cards from one grader can show."
    );
    const scan = scanEvalsDom(el);
    expect(scan).toEqual({
      bareNumbers: [],
      figuresInPlanned: [],
      figuresOutsideScope: [],
    });
  });

  it("renders a graded Gate 1 under 109-A (19/20 better, 9/20 strict Amazing) with zero bare numbers", async () => {
    const gradedRaw = JSON.parse(JSON.stringify(RAW_SIBLING_EXAM)) as Record<string, unknown>;
    gradedRaw.result = "PASS";
    const gates = gradedRaw.gate_results as Record<string, unknown>[];
    gates[0] = {
      ...gates[0],
      result: "PASS",
      observed: {
        k: 19,
        n: 20,
        better_k: 19,
        worse_k: 1,
        graded_k: 20,
        ungraded_k: 0,
        better_pct: 95.0,
        worse_pct: 5.0,
        better_wilson95: [76.4, 99.1],
        worse_wilson95: [0.9, 23.6],
        strict_amazing_k: 9,
        strict_amazing_pct: 45.0,
        strict_amazing_wilson95: [25.8, 65.8],
        result: "PASS",
      },
    };
    const exam = loadSiblingFamilyExam(gradedRaw)!;
    const el = await mount(<SiblingFamilyExamSection exam={exam} />);
    const gate1Row = el.querySelector('[data-sibling-gate="card_vs_single_member"]');
    expect(gate1Row?.getAttribute("data-result")).toBe("pass");
    expect(gate1Row?.textContent).toContain("19/20 (76.4–99.1%)");
    expect(gate1Row?.textContent).toContain(
      "Counting 'Amazing' and 'Fine' as better; strict 'Amazing' only: 9/20 (45.0%)"
    );
    const scan = scanEvalsDom(el);
    expect(scan).toEqual({
      bareNumbers: [],
      figuresInPlanned: [],
      figuresOutsideScope: [],
    });
  });

  it("refuses malformed exam records (fewer than 20 test cards, missing gate verdict, or unknown licence)", () => {
    expect(
      siblingFamilyExamProblem({
        ...RAW_SIBLING_EXAM,
        split_counts: { test: 19, dev: 12, all: 31 },
      })
    ).toMatch(/test >= 20/);

    expect(
      siblingFamilyExamProblem({
        ...RAW_SIBLING_EXAM,
        licences: { sibling_family: "UNKNOWN" },
      })
    ).toMatch(/licences\.sibling_family/);

    expect(
      loadSiblingFamilyExam({
        ...RAW_SIBLING_EXAM,
        result: "MAYBE",
      })
    ).toBeNull();
  });

  it("renders ungraded Gate 1 as HELD ('Not measured: 0 of 20 test cards graded') rather than FAIL 0/20, with zero bare numbers", async () => {
    const ungradedRaw = JSON.parse(JSON.stringify(RAW_SIBLING_EXAM)) as Record<string, unknown>;
    ungradedRaw.result = "HELD";
    ungradedRaw.licences = { sibling_family: "HELD" };
    const gates = ungradedRaw.gate_results as Record<string, unknown>[];
    gates[0] = {
      ...gates[0],
      result: "HELD",
      observed: {
        k: 0,
        n: 20,
        better_k: 0,
        worse_k: 0,
        graded_k: 0,
        ungraded_k: 20,
        better_pct: null,
        worse_pct: null,
        better_wilson95: null,
        worse_wilson95: null,
        result: "HELD",
      },
    };
    const exam = loadSiblingFamilyExam(ungradedRaw)!;
    const el = await mount(<SiblingFamilyExamSection exam={exam} />);

    const banner = el.querySelector('[data-testid="evals-sibling-exam-banner"]');
    expect(banner?.getAttribute("data-result")).toBe("held");
    expect(
      banner?.querySelector("[data-sibling-gates-passed]")?.getAttribute("data-sibling-gates-passed")
    ).toBe("3");
    expect(
      banner?.querySelector("[data-sibling-gates-held]")?.getAttribute("data-sibling-gates-held")
    ).toBe("1");
    expect(banner?.querySelector("[data-sibling-gates-failed]")).toBeNull();
    expect(banner?.textContent).toContain(
      "It may not publish grouped sibling-market cards on its own yet, so every candidate waits for human grading."
    );

    const rows = Array.from(el.querySelectorAll("[data-sibling-gate]"));
    expect(rows.map((r) => r.getAttribute("data-sibling-gate"))).toEqual([
      ...SIBLING_EXAM_GATE_IDS,
    ]);
    expect(rows.map((r) => r.getAttribute("data-result"))).toEqual([
      "held",
      "pass",
      "pass",
      "pass",
    ]);

    const gate1Row = el.querySelector('[data-sibling-gate="card_vs_single_member"]');
    expect(gate1Row?.textContent).toContain("Not measured: 0 of 20 test cards graded (20 ungraded)");
    expect(gate1Row?.textContent).not.toContain("0/20");
    expect(gate1Row?.textContent).not.toContain("0.0–16.1%");

    const licence = el.querySelector('[data-sibling-licence="sibling_family"]');
    expect(licence?.getAttribute("data-result")).toBe("held");

    const scan = scanEvalsDom(el);
    expect(scan).toEqual({
      bareNumbers: [],
      figuresInPlanned: [],
      figuresOutsideScope: [],
    });
  });

  it("shows rate and Wilson interval over graded cards only alongside ungraded count when partially graded", async () => {
    const partialRaw = JSON.parse(JSON.stringify(RAW_SIBLING_EXAM)) as Record<string, unknown>;
    partialRaw.result = "HELD";
    const gates = partialRaw.gate_results as Record<string, unknown>[];
    gates[0] = {
      ...gates[0],
      result: "HELD",
      observed: {
        ...(gates[0].observed as Record<string, unknown>),
        k: 9,
        n: 20,
        better_k: 9,
        worse_k: 0,
        graded_k: 10,
        ungraded_k: 10,
        better_pct: 90.0,
        worse_pct: 0.0,
        better_wilson95: [59.6, 98.2],
        worse_wilson95: [0.0, 27.8],
        result: "HELD",
      },
    };
    const exam = loadSiblingFamilyExam(partialRaw)!;
    expect(exam).not.toBeNull();
    expect(exam.result).toBe("held");

    const el = await mount(<SiblingFamilyExamSection exam={exam} />);
    const gate1Row = el.querySelector('[data-sibling-gate="card_vs_single_member"]');
    expect(gate1Row?.getAttribute("data-result")).toBe("held");
    expect(gate1Row?.textContent).toContain("Waiting for grades: 10 of 20 graded (10 ungraded)");
    expect(gate1Row?.textContent).toContain("Graded so far: 9/10 (90.0%, 59.6–98.2%)");

    const scan = scanEvalsDom(el);
    expect(scan).toEqual({
      bareNumbers: [],
      figuresInPlanned: [],
      figuresOutsideScope: [],
    });
  });
});
