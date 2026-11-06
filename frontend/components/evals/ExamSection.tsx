"use client";

import EvalsSection from "@/components/evals/EvalsSection";
import Figure from "@/components/evals/Figure";
import ResultChip from "@/components/evals/ResultChip";
import { EXAM_COPY as COPY } from "@/lib/evals/copy";
import { sourceLink } from "@/lib/evals/sources";
import type { MeasuredTruth } from "@/lib/evals/truth";
import {
  GATE_WORDS,
  PASSES,
  RELATIONS,
  RELATION_WORDS,
  examTruth,
  type Gate,
  type GateCell,
  type TwinExam,
} from "@/lib/evals/twinExam";

/** A cell's counts in the order its gate's words list them, so each line matches the legend under the gate's name. */
function orderedCounts(gate: Gate, cell: GateCell) {
  const order = Object.keys(GATE_WORDS[gate.id]?.units ?? {});
  return [...cell.counts].sort((x, y) => order.indexOf(x.key) - order.indexOf(y.key));
}

function Cell({ gate, cell, truth, span }: { gate: Gate; cell: GateCell; truth: MeasuredTruth; span?: boolean }) {
  return (
    <td
      colSpan={span ? PASSES.length : undefined}
      data-gate-cell={span ? "across" : "pass"}
      data-result={cell.result}
      className={`border border-surface-border px-1.5 py-1.5 align-top text-micro ${
        cell.result === "fail" ? "bg-accent-danger/5" : "bg-green-500/5"
      }`}
    >
      <ResultChip result={cell.result} />
      {orderedCounts(gate, cell).map((c) => (
        <span key={c.key} className="mt-1 block">
          <Figure truth={truth} value={`${c.k}/${c.n}`} className="text-text-primary">
            {`${c.k.toLocaleString("en-US")}/${c.n.toLocaleString("en-US")}`}
          </Figure>
        </span>
      ))}
    </td>
  );
}

/**
 * The gate grid: a row per gate, a cell per pass for gates measured in each
 * pass, and one spanning cell for gates measured across the three. Each row's
 * verdict is the record's; tapping a gate's name shows what it checks.
 */
function GateGrid({ exam, truth }: { exam: TwinExam; truth: MeasuredTruth }) {
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full table-fixed border-collapse text-left" data-testid="evals-gate-grid">
        <colgroup>
          <col className="w-[40%]" />
          {PASSES.map((p) => (
            <col key={p} className="w-[20%]" />
          ))}
        </colgroup>
        <thead>
          <tr className="text-micro uppercase tracking-wide text-text-tertiary">
            <th scope="col" className="px-2 py-1 font-semibold">
              {COPY.gateHeading}
            </th>
            {COPY.passHeadings.map((h) => (
              <th key={h} scope="col" className="px-1.5 py-1 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {exam.gates.map((gate) => {
            const words = GATE_WORDS[gate.id];
            return (
              <tr key={gate.id} data-gate={gate.id} data-result={gate.result}>
                <th scope="row" className="border border-surface-border px-2 py-1.5 align-top font-normal">
                  <details>
                    <summary className="cursor-pointer list-none text-caption-strong text-text-primary [&::-webkit-details-marker]:hidden">
                      {words?.name ?? gate.id}
                    </summary>
                    <span className="mt-1 block text-micro text-text-secondary">
                      {words?.checks} {gate.scope === "test" ? COPY.heldOutScope : COPY.allScope}.
                    </span>
                  </details>
                  <span className="mt-0.5 block text-micro text-text-tertiary" data-gate-units="">
                    {Object.values(words?.units ?? {}).join(" · ")}
                  </span>
                </th>
                {gate.perPass ? (
                  PASSES.map((p) => <Cell key={p} gate={gate} cell={gate.perPass![p]} truth={truth} />)
                ) : (
                  <Cell gate={gate} cell={gate.observed as GateCell} truth={truth} span />
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** The verdict on top, with what passed and what failed under it — never instead of it. */
function ExamBanner({ exam }: { exam: TwinExam }) {
  const passed = exam.gates.filter((g) => g.result === "pass");
  const failed = exam.gates.filter((g) => g.result === "fail");
  const anyLicense = Object.values(exam.licences).some((l) => l === "pass");
  const names = (gates: Gate[]) => gates.map((g) => GATE_WORDS[g.id]?.name ?? g.id).join(", ");
  return (
    <div
      data-testid="evals-exam-banner"
      data-result={exam.result}
      className={`rounded-lg border px-3 py-2.5 space-y-1 ${
        exam.result === "fail" ? "border-accent-danger/30 bg-accent-danger/5" : "border-green-500/20 bg-green-500/5"
      }`}
    >
      <p className="flex flex-wrap items-center gap-2 text-caption-strong text-text-primary">
        <ResultChip result={exam.result} />
        {!anyLicense && COPY.noLicense}
      </p>
      {passed.length > 0 && (
        <p className="text-caption text-text-secondary" data-gates-passed={passed.length}>
          {COPY.passedPrefix} {names(passed)}.
        </p>
      )}
      {failed.length > 0 && (
        <p className="text-caption text-text-secondary" data-gates-failed={failed.length}>
          {COPY.failedPrefix} {names(failed)}.
        </p>
      )}
    </div>
  );
}

function Licenses({ exam }: { exam: TwinExam }) {
  return (
    <div data-testid="evals-licenses" className="space-y-1.5">
      <h3 className="text-caption-strong text-text-primary">{COPY.licensesTitle}</h3>
      <ul className="flex flex-wrap gap-2">
        {RELATIONS.map((r) => (
          <li
            key={r}
            data-licence={r}
            data-result={exam.licences[r]}
            className="inline-flex items-center gap-1.5 rounded-lg border border-surface-border px-2 py-1 text-micro text-text-primary"
          >
            {RELATION_WORDS[r]}
            <ResultChip result={exam.licences[r]} />
          </li>
        ))}
      </ul>
      <p className="text-micro text-text-secondary">{COPY.licensesNote}</p>
    </div>
  );
}

/** "The twin exam and its gates" — the record's verdict, its gates pass by pass, and a license per kind of pair. */
export default function ExamSection({ exam }: { exam: TwinExam }) {
  const truth = examTruth(exam);
  const passed = exam.gates.filter((g) => g.result === "pass").length;
  const failed = exam.gates.length - passed;
  const ruling = sourceLink("ruling-24a");
  return (
    <EvalsSection
      id="exam"
      title={COPY.title}
      lead={
        <span data-testid="evals-exam-count">
          {COPY.leadBefore}{" "}
          <Figure truth={truth} value={String(passed)} className="font-semibold">
            {String(passed)}
          </Figure>{" "}
          {COPY.leadMiddle}{" "}
          <Figure truth={truth} value={String(failed)} className="font-semibold">
            {String(failed)}
          </Figure>
          {COPY.leadAfter}
        </span>
      }
      detail={COPY.detail}
      truth={truth}
    >
      <div className="space-y-4">
        <ExamBanner exam={exam} />
        <GateGrid exam={exam} truth={truth} />
        <p className="text-micro text-text-secondary">
          {COPY.barBefore}{" "}
          <a href={ruling.href} target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">
            {COPY.barLink}
          </a>
          .
        </p>
        <Licenses exam={exam} />
      </div>
    </EvalsSection>
  );
}

