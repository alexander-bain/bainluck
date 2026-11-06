"use client";

import type { ReactNode } from "react";

import Figure, { Exhibit } from "@/components/evals/Figure";
import ResultChip from "@/components/evals/ResultChip";
import TruthChip from "@/components/evals/TruthChip";
import { DOT_CLASS, ReviewerMarks, WatcherAlarms, type Dot } from "@/components/evals/TopScreen";
import type { ForwardRecordState } from "@/components/evals/useForwardRecord";
import { TOPIC_COPY, TOP_COPY } from "@/lib/evals/copy";
import { barPointsText } from "@/lib/evals/forwardRecord";
import { reviewerTally, type ReviewerResults } from "@/lib/evals/reviewerResults";
import type { ReviewerStudy } from "@/lib/evals/reviewerStudy";
import { biteTruth, type Scoreboard } from "@/lib/evals/scoreboard";
import type { FigureTruth } from "@/lib/evals/truth";
import { acrossPasses, examTruth, type TwinExam } from "@/lib/evals/twinExam";
import { watcherHealth, type WatcherList } from "@/lib/evals/watchers";

/**
 * THE TOPICS BELOW THE TOP SCREEN (Alex, Nov 6): what this is and why it
 * matters, in plain words; a picture; then a "Show the details" fold holding
 * everything the page carried before, unchanged. Nothing outside the fold may
 * need the glossary (`topScreen.test.tsx`), and every number in a picture is a
 * labelled, linked figure.
 */
export function Topic({
  id,
  title,
  why,
  picture,
  children,
}: {
  id: string;
  title: string;
  why: ReactNode;
  picture?: ReactNode;
  /** The details: the sections as they stood, under the fold. */
  children?: ReactNode;
}) {
  return (
    <section id={`topic-${id}`} data-evals-topic={id} aria-labelledby={`topic-${id}-title`} className="space-y-3 scroll-mt-4">
      <h2 id={`topic-${id}-title`} className="text-title-3 text-text-primary">
        {title}
      </h2>
      <p className="text-body text-text-primary">{why}</p>
      {picture}
      {children && (
        <details data-evals-fold={id} className="group">
          <summary className="cursor-pointer list-none text-caption text-accent-brand [&::-webkit-details-marker]:hidden">
            <span aria-hidden="true" className="mr-1 inline-block transition-transform group-open:rotate-90">
              ›
            </span>
            {TOP_COPY.fold}
          </summary>
          <div className="mt-3 space-y-6">{children}</div>
        </details>
      )}
    </section>
  );
}

function PictureCard({ scope, children, footer }: { scope: FigureTruth["kind"]; children: ReactNode; footer: ReactNode }) {
  return (
    <div data-truth-scope={scope} data-topic-picture="" className="bg-surface-card rounded-xl border border-surface-border p-4 space-y-3">
      {children}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-micro text-text-secondary">{footer}</div>
    </div>
  );
}

/** Probabilities, kind by kind: one square per kind of market, green when it comes within the payload's own bar. */
export function KindsPicture({ state }: { state: ForwardRecordState }) {
  if (state.status !== "ready" || !state.view.categories) return null;
  const { truth } = state;
  const { atBar, total, barPp } = state.view.categories;
  const C = TOPIC_COPY.probabilities;
  const n = (value: number, text = String(value), className = "") => (
    <Figure truth={truth} value={String(value)} className={className}>
      {text}
    </Figure>
  );
  return (
    <PictureCard scope={truth.kind} footer={<TruthChip truth={truth} />}>
      <p className="text-caption text-text-secondary">{C.kindsBefore}</p>
      <Exhibit truth={truth} label={C.kindsLabel}>
        <div className="flex flex-wrap gap-1.5" aria-hidden="true" data-kinds-at-bar={atBar} data-kinds-total={total}>
          {Array.from({ length: total }, (_, i) => (
            <span
              key={i}
              data-kind-square={i < atBar ? "inside" : "outside"}
              className={`h-7 w-7 rounded-md ${i < atBar ? "bg-accent-brand" : "bg-accent-danger"}`}
            />
          ))}
        </div>
      </Exhibit>
      <p className="text-body text-text-primary">
        {n(atBar, String(atBar), "text-title-3")} {C.kindsOf} {n(total)} {C.kindsInsideBefore} {n(barPp, barPointsText(barPp))}{" "}
        {C.kindsInsideAfter}
      </p>
    </PictureCard>
  );
}

/** The matcher's exam, as two bars, under its result: FAIL stays FAIL. */
export function ExamPicture({ exam }: { exam: TwinExam }) {
  const truth = examTruth(exam);
  const C = TOPIC_COPY.matching;
  const [foundLo, foundHi] = acrossPasses(exam, (p) => p.test.perRelation.twin.recall.k);
  const [wrongLo, wrongHi] = acrossPasses(exam, (p) => p.test.wrongMerges);
  const real = exam.perPass["1"].test.perRelation.twin.recall.n;
  const pairs = exam.perPass["1"].test.expected;
  const n = (value: number, className = "") => (
    <Figure truth={truth} value={String(value)} className={className}>
      {value.toLocaleString("en-US")}
    </Figure>
  );
  const range = (lo: number, hi: number) =>
    lo === hi ? (
      n(lo, "text-title-3")
    ) : (
      <>
        {n(lo, "text-title-3")} {C.wrongTo} {n(hi, "text-title-3")}
      </>
    );
  const bar = (part: number, whole: number, tone: string, kind: string) => (
    <div className="h-3 w-full overflow-hidden rounded-full bg-surface-elevated" data-exam-bar={kind}>
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${whole > 0 ? (100 * part) / whole : 0}%` }} />
    </div>
  );
  return (
    <PictureCard scope={truth.kind} footer={<TruthChip truth={truth} />}>
      <div className="flex items-center gap-2">
        <ResultChip result={exam.result} />
        <span className="text-body text-text-primary">{exam.result === "pass" ? C.passed : C.failed}</span>
      </div>
      <Exhibit truth={truth} label={C.label}>
        <div className="space-y-3">
          <div className="space-y-1">
            <p className="text-caption text-text-secondary">
              {C.foundBefore} {range(foundLo, foundHi)} {C.foundOf} {n(real)} {C.foundAfter}
            </p>
            {bar(foundLo, real, "bg-accent-brand", "found")}
          </div>
          <div className="space-y-1">
            <p className="text-caption text-text-secondary">
              {C.wrongBefore} {range(wrongLo, wrongHi)} {C.wrongOf} {n(pairs)} {C.wrongAfter}
            </p>
            {bar(wrongHi, pairs, "bg-accent-danger", "wrong")}
          </div>
        </div>
      </Exhibit>
    </PictureCard>
  );
}

/** Our own tests: one block per planted breakage, green when a test caught it, and the honest limit beside it. */
export function BreakagesPicture({ board }: { board: Scoreboard }) {
  const truth = biteTruth(board);
  if (!truth.asOf) return null;
  const C = TOPIC_COPY.tests;
  const { total, caught, realCode } = board.bite;
  const n = (value: number, className = "") => (
    <Figure truth={truth} value={String(value)} className={className}>
      {value.toLocaleString("en-US")}
    </Figure>
  );
  return (
    <PictureCard scope={truth.kind} footer={<TruthChip truth={truth} />}>
      <p className="text-body text-text-primary">
        {C.caughtBefore} {n(caught, "text-title-3")} {C.caughtOf} {n(total)} {C.caughtAfter}
      </p>
      <Exhibit truth={truth} label={C.label}>
        {/* Rows of ten, so the count can be read off the picture. */}
        <div className="grid w-fit grid-cols-10 gap-1" aria-hidden="true">
          {Array.from({ length: total }, (_, i) => (
            <span
              key={i}
              data-breakage={i < caught ? "caught" : "missed"}
              className={`h-5 w-5 rounded-sm ${i < caught ? "bg-accent-brand" : "bg-accent-danger"}`}
            />
          ))}
        </div>
      </Exhibit>
      {/* The limit is said only while it is true, as the meter in the fold says it. */}
      <p className="text-caption text-text-secondary" data-breakages-limit="">
        {realCode === 0 ? (
          C.honest
        ) : (
          <>
            {n(realCode)} {C.realOf} {n(total)} {C.realAfter}
          </>
        )}
      </p>
    </PictureCard>
  );
}

/** The checks, larger: one alarm per check, the working count, and a legend with counts. */
export function ChecksPicture({ list }: { list: WatcherList }) {
  const health = watcherHealth(list);
  const truth: FigureTruth = { kind: "reviewed", asOf: list.reviewedAt, source: list.scheduleSource };
  const C = TOPIC_COPY.checks;
  const n = (value: number, className = "") => (
    <Figure truth={truth} value={String(value)} className={className}>
      {String(value)}
    </Figure>
  );
  const counts: Record<Dot, number> = {
    problems: health.foundProblems,
    fixed: health.foundFixed,
    stopped: health.stopped,
    unknown: health.unknown,
  };
  const order: Dot[] = ["problems", "fixed", "stopped", "unknown"];
  return (
    <PictureCard scope={truth.kind} footer={<TruthChip truth={truth} />}>
      <p className="text-body text-text-primary">
        {n(health.working, "text-title-3")} {C.of} {n(health.total)} {C.workingAfter}
      </p>
      <WatcherAlarms list={list} large />
      <ul className="space-y-1 text-caption text-text-primary" data-checks-legend="">
        {order
          .filter((d) => counts[d] > 0)
          .map((d) => (
            <li key={d} className="flex items-center gap-2" data-checks-legend-row={d}>
              <span aria-hidden="true" className={`inline-block h-3 w-3 shrink-0 rounded-full bg-current ${DOT_CLASS[d]}`} />
              <span>
                {n(counts[d])} {C.legend[d]}
              </span>
            </li>
          ))}
      </ul>
    </PictureCard>
  );
}

/** The reviewer study, larger: the bugs and decoys, and what it has caught so far. */
export function ReviewerPicture({ results, study }: { results: ReviewerResults; study: ReviewerStudy }) {
  const tally = reviewerTally(results, study);
  const truth: FigureTruth = { kind: "last_run", asOf: results.asOf, source: results.receipt };
  const C = TOPIC_COPY.reviewer;
  const n = (value: number, className = "") => (
    <Figure truth={truth} value={String(value)} className={className}>
      {String(value)}
    </Figure>
  );
  return (
    <PictureCard scope={truth.kind} footer={<TruthChip truth={truth} showClock />}>
      <p className="text-body text-text-primary" data-review-kind="mistakes">
        {tally.mistakes.reviewed > 0 ? (
          <>
            {TOP_COPY.reviewerCaughtBefore} {n(tally.mistakes.right, "text-title-3")} {TOP_COPY.reviewerCaughtMiddle}{" "}
            {n(tally.mistakes.reviewed, "text-title-3")} {TOP_COPY.reviewerCaughtAfter}
          </>
        ) : (
          TOP_COPY.reviewerNoneChecked
        )}
      </p>
      <ReviewerMarks results={results} study={study} large />
      <p className="text-caption text-text-secondary">
        {C.legendBefore}{" "}
        <Figure truth={{ kind: "last_run", asOf: results.asOf, source: results.planReceipt }} value={String(results.planned / study.cases.length)}>
          {String(results.planned / study.cases.length)}
        </Figure>{" "}
        {C.legendAfter}
      </p>
    </PictureCard>
  );
}
