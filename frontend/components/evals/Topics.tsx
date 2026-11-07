"use client";

import type { ReactNode } from "react";

import Figure, { Example, Exhibit } from "@/components/evals/Figure";
import ResultChip from "@/components/evals/ResultChip";
import TruthChip from "@/components/evals/TruthChip";
import { DOT_CLASS, ReviewerMarks, WatcherAlarms, type Dot } from "@/components/evals/TopScreen";
import type { ForwardRecordState } from "@/components/evals/useForwardRecord";
import { STORY_COPY, TOPIC_COPY, TOP_COPY } from "@/lib/evals/copy";
import { EXAMPLE_AMERICAN_ODDS, EXAMPLE_CONTRACT_CENTS, americanOddsText, americanToPercent } from "@/lib/evals/example";
import { barPointsText } from "@/lib/evals/forwardRecord";
import { reviewerTally, type ReviewerResults } from "@/lib/evals/reviewerResults";
import type { ReviewerStudy } from "@/lib/evals/reviewerStudy";
import { biteTruth, type Scoreboard } from "@/lib/evals/scoreboard";
import type { FigureTruth } from "@/lib/evals/truth";
import { acrossPasses, examTruth, type TwinExam } from "@/lib/evals/twinExam";
import { watcherHealth, type WatcherList } from "@/lib/evals/watchers";

/**
 * THE STORY BELOW THE TOP SCREEN (Alex, Nov 6, 2:04 PM: "tell our ENTIRE story
 * to an interested party in approachable language"). One chapter per step of
 * the stack: a title, a few plain sentences, and at most a picture. No word
 * that needs the glossary appears in a chapter (`topScreen.test.tsx`); the
 * records behind every number sit in one fold at the bottom of the page.
 */
export function Chapter({
  id,
  title,
  paragraphs,
  children,
}: {
  id: string;
  title: string;
  paragraphs: readonly string[];
  /** The chapter's picture, if it has one. */
  children?: ReactNode;
}) {
  return (
    <section id={`chapter-${id}`} data-evals-chapter={id} aria-labelledby={`chapter-${id}-title`} className="space-y-3 scroll-mt-4">
      <h2 id={`chapter-${id}-title`} className="text-title-3 text-text-primary">
        {title}
      </h2>
      {paragraphs.map((text, i) => (
        <p key={i} className="text-body text-text-primary">
          {text}
        </p>
      ))}
      {children}
    </section>
  );
}

/** One view written two ways, and the one probability we show for both. Illustrative: see `lib/evals/example.ts`. */
export function OddsExample() {
  const C = STORY_COPY;
  const chance = americanToPercent(EXAMPLE_AMERICAN_ODDS);
  const odds = americanOddsText(EXAMPLE_AMERICAN_ODDS);
  const label = `${C.exampleAriaBefore} ${odds} ${C.exampleAriaMiddle} ${EXAMPLE_CONTRACT_CENTS} ${C.exampleAriaCents} ${C.exampleAriaAfter} ${chance}%.`;
  const source = (who: string, what: string) => (
    <div className="rounded-lg border border-surface-border bg-surface-elevated px-3 py-2">
      <p className="text-micro text-text-secondary">{who}</p>
      <p className="text-title-3 text-text-primary">{what}</p>
    </div>
  );
  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4" data-chapter-picture="example">
      <Example caption={C.exampleLabel} label={label}>
        <div className="flex items-center gap-3" aria-hidden="true">
          <div className="grid flex-1 gap-2">
            {source(C.exampleBetting, odds)}
            {source(C.exampleMarket, `${EXAMPLE_CONTRACT_CENTS}¢`)}
          </div>
          <span className="text-title-3 text-text-secondary">→</span>
          <div className="rounded-lg bg-accent-brand/15 px-4 py-3 text-center">
            <p className="text-micro text-text-secondary">{C.exampleUs}</p>
            <p className="text-title-1 font-semibold text-accent-brand">{chance}%</p>
          </div>
        </div>
      </Example>
    </div>
  );
}

function PictureCard({ name, scope, children, footer }: { name: string; scope: FigureTruth["kind"]; children: ReactNode; footer: ReactNode }) {
  return (
    <div data-truth-scope={scope} data-chapter-picture={name} className="bg-surface-card rounded-xl border border-surface-border p-4 space-y-3">
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
    <PictureCard name="kinds" scope={truth.kind} footer={<TruthChip truth={truth} />}>
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

/**
 * The matcher's exam, as two bars, under its result: FAIL stays FAIL. The bars
 * name their three tries, and the rule the red one counts is said in words,
 * since a short red bar under FAIL reads as a contradiction without it.
 */
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
        {n(lo, "text-title-3")} {C.or} {n(hi, "text-title-3")}
      </>
    );
  const bar = (part: number, whole: number, tone: string, kind: string) => (
    <div className="h-3 w-full overflow-hidden rounded-full bg-surface-elevated" data-exam-bar={kind}>
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${whole > 0 ? (100 * part) / whole : 0}%` }} />
    </div>
  );
  return (
    <PictureCard name="exam" scope={truth.kind} footer={<TruthChip truth={truth} />}>
      <div className="flex items-center gap-2">
        <ResultChip result={exam.result} />
        <span className="text-body text-text-primary">{exam.result === "pass" ? C.passed : C.failed}</span>
      </div>
      <p className="text-caption text-text-secondary" data-exam-tries="">
        {C.triesBefore} {n(pairs)} {C.triesAfter}
      </p>
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
              {C.wrongBefore} {range(wrongLo, wrongHi)} {C.wrongAfter}
            </p>
            {bar(wrongHi, pairs, "bg-accent-danger", "wrong")}
          </div>
        </div>
      </Exhibit>
      <p className="text-caption text-text-secondary" data-exam-why="">
        {C.why}
      </p>
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
    <PictureCard name="breakages" scope={truth.kind} footer={<TruthChip truth={truth} />}>
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
    <PictureCard name="checks" scope={truth.kind} footer={<TruthChip truth={truth} />}>
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
    <PictureCard name="reviewer" scope={truth.kind} footer={<TruthChip truth={truth} showClock />}>
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
