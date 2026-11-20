"use client";

import Figure from "@/components/evals/Figure";
import ResultChip from "@/components/evals/ResultChip";
import TruthChip from "@/components/evals/TruthChip";
import {
  SIBLING_EXAM_GATE_WORDS,
  SIBLING_EXAM_PASSES,
  siblingFamilyExamTruth,
  type SiblingExamGate,
  type SiblingFamilyExam,
  type SiblingGateCell,
} from "@/lib/evals/siblingFamilyExam";
import type { MeasuredTruth } from "@/lib/evals/truth";

function SiblingCell({
  cell,
  truth,
  span,
}: {
  cell: SiblingGateCell;
  truth: MeasuredTruth;
  span?: boolean;
}) {
  const waitingForGrades =
    cell.gradedK !== undefined && cell.gradedK < cell.n;
  const ungradedCount =
    cell.ungradedK !== undefined
      ? cell.ungradedK
      : cell.gradedK !== undefined
        ? cell.n - cell.gradedK
        : 0;
  const toneClass =
    cell.result === "fail"
      ? "bg-accent-danger/5"
      : cell.result === "held"
        ? "bg-surface-hover/40"
        : "bg-green-500/5";

  return (
    <td
      colSpan={span ? SIBLING_EXAM_PASSES.length : undefined}
      data-sibling-gate-cell={span ? "across" : "pass"}
      data-result={cell.result}
      className={`border border-surface-border px-1.5 py-1.5 align-top text-micro ${toneClass}`}
    >
      <ResultChip result={cell.result} />
      {span && (
        <span className="mt-1 block text-text-tertiary" data-sibling-across="">
          Across all three tries
        </span>
      )}
      {waitingForGrades ? (
        <>
          <span className="mt-1 block" data-sibling-waiting-for-grades="">
            {(cell.gradedK ?? 0) === 0 ? "Not measured: " : "Waiting for grades: "}
            <Figure
              truth={truth}
              value={String(cell.gradedK)}
              className="text-text-primary"
            >
              {(cell.gradedK ?? 0).toLocaleString("en-US")}
            </Figure>
            {" of "}
            <Figure
              truth={truth}
              value={String(cell.n)}
              className="text-text-primary"
            >
              {cell.n.toLocaleString("en-US")}
            </Figure>
            {(cell.gradedK ?? 0) === 0 ? " test cards graded (" : " graded ("}
            <Figure
              truth={truth}
              value={String(ungradedCount)}
              className="text-text-secondary"
            >
              {ungradedCount.toLocaleString("en-US")}
            </Figure>
            {" ungraded)"}
          </span>
          {(cell.gradedK ?? 0) > 0 && (
            <span className="mt-0.5 block" data-sibling-graded-so-far="">
              {"Graded so far: "}
              <Figure
                truth={truth}
                value={`${cell.k}/${cell.gradedK}`}
                className="text-text-primary"
              >
                {`${cell.k.toLocaleString("en-US")}/${(cell.gradedK ?? 0).toLocaleString("en-US")}`}
              </Figure>
              {cell.betterPct !== undefined && cell.betterPct !== null && (
                <>
                  {" ("}
                  <Figure
                    truth={truth}
                    value={`${cell.betterPct}%`}
                    className="text-text-secondary"
                  >
                    {`${cell.betterPct.toFixed(1)}%`}
                  </Figure>
                  {cell.wilson95 && (
                    <>
                      {", "}
                      <Figure
                        truth={truth}
                        value={`${cell.wilson95[0]}–${cell.wilson95[1]}%`}
                        className="text-text-secondary"
                      >
                        {`${cell.wilson95[0].toFixed(1)}–${cell.wilson95[1].toFixed(1)}%`}
                      </Figure>
                    </>
                  )}
                  {")"}
                </>
              )}
            </span>
          )}
        </>
      ) : (
        <>
          <span className="mt-1 block">
            <Figure truth={truth} value={`${cell.k}/${cell.n}`} className="text-text-primary">
              {`${cell.k.toLocaleString("en-US")}/${cell.n.toLocaleString("en-US")}`}
            </Figure>
            {cell.wilson95 && (
              <>
                {" ("}
                <Figure
                  truth={truth}
                  value={`${cell.wilson95[0]}–${cell.wilson95[1]}%`}
                  className="text-text-secondary"
                >
                  {`${cell.wilson95[0].toFixed(1)}–${cell.wilson95[1].toFixed(1)}%`}
                </Figure>
                {")"}
              </>
            )}
          </span>
          {cell.strictAmazingK !== undefined && (
            <span className="mt-0.5 block text-text-secondary" data-sibling-strict-amazing="">
              {"Counting 'Amazing' and 'Fine' as better; strict 'Amazing' only: "}
              <Figure
                truth={truth}
                value={`${cell.strictAmazingK}/${cell.n}`}
                className="text-text-primary"
              >
                {`${cell.strictAmazingK.toLocaleString("en-US")}/${cell.n.toLocaleString("en-US")}`}
              </Figure>
              {cell.strictAmazingPct !== undefined && cell.strictAmazingPct !== null && (
                <>
                  {" ("}
                  <Figure
                    truth={truth}
                    value={`${cell.strictAmazingPct}%`}
                    className="text-text-secondary"
                  >
                    {`${cell.strictAmazingPct.toFixed(1)}%`}
                  </Figure>
                  {")"}
                </>
              )}
            </span>
          )}
          {cell.wilson95 && cell.gradedK !== undefined && cell.gradedK === cell.n && (
            <span className="mt-0.5 block text-text-tertiary" data-sibling-wilson-ceiling="">
              {"The interval's low end is "}
              <Figure
                truth={truth}
                value={`${cell.wilson95[0]}%`}
                className="text-text-secondary"
              >
                {`${cell.wilson95[0].toFixed(1)}%`}
              </Figure>
              {", which is what "}
              <Figure
                truth={truth}
                value={String(cell.n)}
                className="text-text-secondary"
              >
                {cell.n.toLocaleString("en-US")}
              </Figure>
              {" cards from one grader can show."}
            </span>
          )}
        </>
      )}
    </td>
  );
}

export default function SiblingFamilyExamSection({
  exam,
}: {
  exam: SiblingFamilyExam;
}) {
  const truth = siblingFamilyExamTruth(exam);
  const passed = exam.gates.filter((g) => g.result === "pass");
  const held = exam.gates.filter((g) => g.result === "held");
  const failed = exam.gates.filter((g) => g.result === "fail");
  const names = (list: SiblingExamGate[]) =>
    list.map((g) => SIBLING_EXAM_GATE_WORDS[g.id]?.name ?? g.id).join(", ");

  return (
    <section
      id="sibling-family-exam"
      data-sibling-exam=""
      data-truth-scope="last_run"
      className="rounded-xl border border-surface-border bg-surface-card p-5 space-y-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-heading-sm text-text-primary">
            Sibling-market card exam and its tests
          </h2>
          <p className="mt-1 text-caption text-text-secondary" data-testid="evals-sibling-exam-count">
            Before a grouped sibling-market card proposed by the model can publish on its own, it has to pass every test below on{" "}
            <Figure truth={truth} value={String(exam.splitCounts.test)} className="font-semibold">
              {String(exam.splitCounts.test)}
            </Figure>{" "}
            set-aside cards never used for tuning:{" "}
            <Figure truth={truth} value={String(passed.length)} className="font-semibold">
              {String(passed.length)}
            </Figure>{" "}
            passed
            {held.length > 0 && (
              <>
                {", "}
                <Figure truth={truth} value={String(held.length)} className="font-semibold">
                  {String(held.length)}
                </Figure>{" "}
                waiting for grades
              </>
            )}
            {failed.length > 0 && (
              <>
                {", "}
                <Figure truth={truth} value={String(failed.length)} className="font-semibold">
                  {String(failed.length)}
                </Figure>{" "}
                failed
              </>
            )}{" "}
            across{" "}
            <Figure truth={truth} value={String(exam.cost.replies)}>
              {String(exam.cost.replies)}
            </Figure>{" "}
            replies at{" "}
            <Figure truth={truth} value={String(exam.cost.actualUsd)}>
              {`$${exam.cost.actualUsd.toFixed(2)}`}
            </Figure>{" "}
            at published rates.
          </p>
        </div>
        <TruthChip truth={truth} />
      </div>

      <div
        data-testid="evals-sibling-exam-banner"
        data-result={exam.result}
        className={`rounded-lg border px-3 py-2.5 space-y-1 ${
          exam.result === "fail"
            ? "border-accent-danger/30 bg-accent-danger/5"
            : exam.result === "held"
              ? "border-surface-border bg-surface-hover/40"
              : "border-green-500/20 bg-green-500/5"
        }`}
      >
        <p className="flex flex-wrap items-center gap-2 text-caption-strong text-text-primary">
          <ResultChip result={exam.result} />
          {exam.licences.sibling_family === "pass" && exam.result === "pass"
            ? "All four tests passed; verified grouped sibling-market cards publish on Discover."
            : "It may not publish grouped sibling-market cards on its own yet, so every candidate waits for human grading."}
        </p>
        {passed.length > 0 && (
          <p
            className="text-caption text-text-secondary"
            data-sibling-gates-passed={passed.length}
          >
            Passed: {names(passed)}.
          </p>
        )}
        {held.length > 0 && (
          <p
            className="text-caption text-text-secondary"
            data-sibling-gates-held={held.length}
          >
            Waiting for grades: {names(held)}.
          </p>
        )}
        {failed.length > 0 && (
          <p
            className="text-caption text-text-secondary"
            data-sibling-gates-failed={failed.length}
          >
            Failed: {names(failed)}.
          </p>
        )}
      </div>

      <div className="-mx-1 overflow-x-auto">
        <table
          className="w-full table-fixed border-collapse text-left"
          data-testid="evals-sibling-gate-grid"
        >
          <colgroup>
            <col className="w-[40%]" />
            {SIBLING_EXAM_PASSES.map((p) => (
              <col key={p} className="w-[20%]" />
            ))}
          </colgroup>
          <thead>
            <tr className="text-micro uppercase tracking-wide text-text-tertiary">
              <th scope="col" className="px-2 py-1 font-semibold">
                Test
              </th>
              <th scope="col" className="px-1.5 py-1 font-semibold">
                First try
              </th>
              <th scope="col" className="px-1.5 py-1 font-semibold">
                Second try
              </th>
              <th scope="col" className="px-1.5 py-1 font-semibold">
                Third try
              </th>
            </tr>
          </thead>
          <tbody>
            {exam.gates.map((gate) => {
              const words = SIBLING_EXAM_GATE_WORDS[gate.id];
              return (
                <tr
                  key={gate.id}
                  data-sibling-gate={gate.id}
                  data-result={gate.result}
                >
                  <th
                    scope="row"
                    className="border border-surface-border px-2 py-1.5 align-top font-normal"
                  >
                    <details>
                      <summary className="cursor-pointer list-none text-caption-strong text-text-primary [&::-webkit-details-marker]:hidden">
                        {words?.name ?? gate.id}
                      </summary>
                      <span className="mt-1 block text-micro text-text-secondary">
                        {words?.checks}
                      </span>
                    </details>
                    <span className="mt-0.5 block text-micro text-text-tertiary">
                      {words?.unitLabel}
                    </span>
                  </th>
                  {gate.perPass ? (
                    SIBLING_EXAM_PASSES.map((p) => (
                      <SiblingCell
                        key={p}
                        cell={gate.perPass![p]}
                        truth={truth}
                      />
                    ))
                  ) : (
                    <SiblingCell
                      cell={gate.observed as SiblingGateCell}
                      truth={truth}
                      span
                    />
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div data-testid="evals-sibling-licences" className="space-y-1.5">
        <h3 className="text-caption-strong text-text-primary">
          May it publish on its own?
        </h3>
        <ul className="flex flex-wrap gap-2">
          <li
            data-sibling-licence="sibling_family"
            data-result={exam.licences.sibling_family}
            className="inline-flex items-center gap-1.5 rounded-lg border border-surface-border px-2 py-1 text-micro text-text-primary"
          >
            Sibling-market cards
            <ResultChip result={exam.licences.sibling_family} />
          </li>
        </ul>
      </div>
    </section>
  );
}
