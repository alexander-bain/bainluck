import { Fragment } from "react";

import Figure from "@/components/evals/Figure";
import ResultChip from "@/components/evals/ResultChip";
import { TIMELINE_COPY } from "@/lib/evals/copy";
import { formatCount, formatUsd, modelName, notePieces, type Run } from "@/lib/evals/runs";
import { pacificDayLabel, type MeasuredTruth, type ResultKind } from "@/lib/evals/truth";

/** The dot repeats the result chip's colour; the chip carries the word. */
const DOT: Record<ResultKind, string> = {
  pass: "bg-green-600",
  fail: "bg-accent-danger",
  held: "bg-yellow-500",
  not_run: "bg-text-muted",
  not_eligible: "bg-text-muted",
  unknown: "bg-text-muted",
};

function RunRow({ run }: { run: Run }) {
  // Every figure on a row is from that row's run, dated by it and sourced to
  // its receipt. The row is the truth scope; its date is the label.
  const truth: MeasuredTruth = { kind: "last_run", asOf: run.date, source: run.receipt };
  const replies = run.figures.replies;
  return (
    <li
      className="relative pl-5"
      data-run-id={run.id}
      data-result={run.result}
      data-truth-scope="last_run"
    >
      <span
        aria-hidden="true"
        className={`absolute -left-[6.5px] top-1.5 h-3 w-3 rounded-full ring-4 ring-surface-card ${DOT[run.result]}`}
      />
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <time dateTime={run.date} className="text-micro font-semibold uppercase tracking-wide text-text-secondary">
          {pacificDayLabel(run.date)}
        </time>
        <ResultChip result={run.result} />
      </div>
      <p className="mt-1 text-body-strong text-text-primary">{run.title}</p>
      <p className="mt-0.5 text-caption text-text-secondary">
        {run.by === "by_hand" ? (
          TIMELINE_COPY.byHand
        ) : (
          <>
            {run.model && (
              <span data-evals-ref="" data-model={run.model}>
                {modelName(run.model)}
              </span>
            )}
            {replies && (
              <>
                {" · "}
                <Figure truth={truth} value={String(replies.value)}>
                  {formatCount(replies.value)}
                </Figure>{" "}
                {TIMELINE_COPY.replies}
              </>
            )}
            {run.cost && (
              <>
                {" · "}
                <Figure truth={truth} value={String(run.cost.value)}>
                  {formatUsd(run.cost.value)}
                </Figure>{" "}
                {TIMELINE_COPY.usageRated}
                {run.cost.includes === "pilot" && `, ${TIMELINE_COPY.includesPilot}`}
              </>
            )}
          </>
        )}
      </p>
      <p className="mt-1 text-caption text-text-primary">
        {notePieces(run.note).map((piece, i) =>
          "slot" in piece ? (
            <Figure key={i} truth={truth} value={String(run.figures[piece.slot].value)}>
              {formatCount(run.figures[piece.slot].value)}
            </Figure>
          ) : (
            <Fragment key={i}>{piece.text}</Fragment>
          )
        )}
      </p>
      <a
        href={run.receipt.href}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1 inline-block text-caption text-accent-brand hover:underline"
        title={run.receipt.label}
      >
        {TIMELINE_COPY.receipt}: {run.receipt.label}
      </a>
    </li>
  );
}

/** "Exams on the record": one row per run, oldest first, each linked to its receipt. */
export default function RunTimeline({ runs }: { runs: readonly Run[] }) {
  return (
    <ol className="relative space-y-5 border-l border-surface-border ml-1.5 pl-0" data-testid="evals-run-timeline">
      {runs.map((run) => (
        <RunRow key={run.id} run={run} />
      ))}
    </ol>
  );
}
