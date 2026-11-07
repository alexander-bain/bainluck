"use client";

import { AlarmSmoke, Bug, CircleHelp, FileCheck } from "lucide-react";
import type { ReactNode } from "react";

import Figure, { Exhibit } from "@/components/evals/Figure";
import TruthChip from "@/components/evals/TruthChip";
import type { ForwardRecordState } from "@/components/evals/useForwardRecord";
import { EVALS_PAGE_TITLE, TOP_COPY as COPY } from "@/lib/evals/copy";
import { CHART_THIN_FLOOR } from "@/lib/evals/forwardRecord";
import { stalenessHeadline } from "@/lib/calibrationStaleness";
import { reviewerTally, type ReviewerResults } from "@/lib/evals/reviewerResults";
import type { ReviewerStudy } from "@/lib/evals/reviewerStudy";
import {
  TRUTH_PLOT,
  caseMarks,
  plotX,
  plotY,
  truthDots,
  truthExample,
  truthReading,
  wholePercent,
  type CaseMark,
} from "@/lib/evals/topScreen";
import type { FigureTruth } from "@/lib/evals/truth";
import { watcherHealth, type WatcherList } from "@/lib/evals/watchers";

/**
 * THE TOP SCREEN OF /evals (Alex, Nov 6): one plain answer, then three pictures
 * a reader takes in without reading a number — do our probabilities come true,
 * does the AI reviewer catch planted mistakes, are the site watchers
 * working — all on one phone screen. Every figure is still a `Figure` with its
 * label and its link, and every picture is an `Exhibit` under the label of the
 * record it draws; each card's label sits on its last line.
 *
 * A picture whose record cannot be read is absent, never drawn empty.
 */

function Card({
  id,
  title,
  scope,
  footer,
  children,
}: {
  id: string;
  title: string;
  /** The label every figure in the card is under. */
  scope?: FigureTruth["kind"];
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      data-evals-top-card={id}
      data-truth-scope={scope}
      aria-labelledby={`evals-top-${id}`}
      className="bg-surface-card rounded-xl border border-surface-border px-3 py-2 space-y-1"
    >
      <h2 id={`evals-top-${id}`} className="text-body-strong text-text-primary">
        {title}
      </h2>
      {children}
      {footer && <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-micro text-text-secondary">{footer}</div>}
    </section>
  );
}

/** "Do our probabilities come true?" — the live curve as dots on the grey line where said equals happened. */
function TruthCard({ state }: { state: ForwardRecordState }) {
  const ready = state.status === "ready" ? state : null;
  const curve = ready?.view.curve ?? null;
  if (!ready || !curve) {
    return (
      <Card id="truth" title={COPY.truthTitle}>
        <p className="text-caption text-text-secondary" data-top-status={state.status}>
          {state.status === "loading" ? COPY.truthLoading : COPY.truthUnavailable}
        </p>
      </Card>
    );
  }
  const { view, truth } = ready;
  const dots = truthDots(curve.data, CHART_THIN_FLOOR);
  const reading = truthReading(view);
  const example = truthExample(dots);
  const { width, height, left, bottom } = TRUTH_PLOT;
  return (
    <Card
      id="truth"
      title={COPY.truthTitle}
      scope={truth.kind}
      footer={
        <>
          <TruthChip truth={truth} />
          {view.proof && (
            <span>
              <Figure truth={truth} value={String(view.proof.errorPp)}>
                {view.proof.errorText}
              </Figure>{" "}
              {COPY.truthPointsAfter}
            </span>
          )}
        </>
      }
    >
      <Exhibit truth={truth} label={COPY.truthChartLabel}>
        {/* The exhibit around it carries the label, so the drawing itself is not announced twice. */}
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" aria-hidden="true">
          {[0, 100].map((t) => (
            <g key={t}>
              <text x={left - 4} y={plotY(t) + 3} textAnchor="end" className="fill-text-muted" fontSize={9}>
                {`${t}%`}
              </text>
              <text
                x={plotX(t)}
                y={height - bottom + 11}
                textAnchor={t === 0 ? "start" : "end"}
                className="fill-text-muted"
                fontSize={9}
              >
                {`${t}%`}
              </text>
            </g>
          ))}
          <rect
            x={plotX(0)}
            y={plotY(100)}
            width={plotX(100) - plotX(0)}
            height={plotY(0) - plotY(100)}
            className="fill-none stroke-surface-border"
            strokeWidth={1}
          />
          <line
            data-truth-line=""
            x1={plotX(0)}
            y1={plotY(0)}
            x2={plotX(100)}
            y2={plotY(100)}
            className="stroke-surface-elevated"
            strokeWidth={9}
            strokeLinecap="round"
          />
          {example && (
            <circle
              data-truth-example=""
              cx={example.cx}
              cy={example.cy}
              r={8}
              className="fill-none stroke-text-primary"
              strokeWidth={1.5}
            />
          )}
          {dots.map((d) => (
            <circle
              key={`${d.said}-${d.happened}`}
              data-truth-dot=""
              data-said={d.said}
              data-happened={d.happened}
              cx={d.cx}
              cy={d.cy}
              r={4}
              strokeWidth={1.5}
              className={d.thin ? "fill-surface-card stroke-accent-brand" : "fill-accent-brand stroke-surface-card"}
            />
          ))}
          <text x={plotX(0) + 4} y={plotY(100) + 10} className="fill-text-secondary" fontSize={10}>
            {COPY.truthHappened}
          </text>
          <text x={plotX(100) - 4} y={plotY(0) - 5} textAnchor="end" className="fill-text-secondary" fontSize={10}>
            {COPY.truthSaid}
          </text>
        </svg>
      </Exhibit>
      <p className="text-caption text-text-primary" data-truth-reading={reading}>
        {example ? (
          <>
            {COPY.truthExampleBefore}{" "}
            <Figure truth={truth} value={String(example.said)} className="font-semibold">
              {wholePercent(example.said)}
            </Figure>
            {COPY.truthExampleMiddle}{" "}
            <Figure truth={truth} value={String(example.happened)} className="font-semibold">
              {wholePercent(example.happened)}
            </Figure>{" "}
            {reading === "close" ? COPY.truthExampleClose : reading === "far" ? COPY.truthExampleFar : COPY.truthExamplePlain}
          </>
        ) : (
          COPY.truthPlain
        )}
      </p>
      {view.staleness && (
        // LIVE is the curve's label; when its inputs are older, the first
        // screen says so in the accuracy page's own words (Fable on #12124).
        <p className="text-micro text-yellow-700" data-testid="evals-top-forward-staleness">
          {stalenessHeadline(view.staleness)}
        </p>
      )}
    </Card>
  );
}

const MARK_TONE: Record<CaseMark, string> = {
  right: "text-accent-brand",
  wrong: "text-accent-danger",
  not_yet: "text-text-muted",
};

/**
 * One bug per hidden mistake and one page per harmless decoy, coloured by what
 * the reviewer did with each: the top screen's picture, and, larger, its topic's.
 */
export function ReviewerMarks({
  results,
  study,
  large = false,
}: {
  results: ReviewerResults;
  study: ReviewerStudy;
  large?: boolean;
}) {
  const truth: FigureTruth = { kind: "last_run", asOf: results.asOf, source: results.receipt };
  const bug = large ? "h-8 w-8" : "h-5 w-5";
  const page = large ? "h-7 w-7" : "h-[18px] w-[18px]";
  return (
    <Exhibit truth={truth} label={COPY.reviewerChartLabel}>
      <div className={`flex items-center ${large ? "flex-wrap gap-x-4 gap-y-2" : "gap-x-2.5"}`} aria-hidden="true">
        {/* Large, the bugs sit in rows of five, so ten read as two even rows instead of nine and a straggler. */}
        <span className={large ? "grid w-fit grid-cols-5 gap-1.5" : "flex gap-0.5"} data-review-marks="mistakes">
          {caseMarks(results, study, "defect").map((m, i) => (
            <Bug key={i} data-review-mark={m} className={`${bug} shrink-0 ${MARK_TONE[m]}`} strokeWidth={2.25} />
          ))}
        </span>
        <span className={`flex items-center ${large ? "gap-1" : "gap-0.5"}`} data-review-marks="harmless">
          {caseMarks(results, study, "control").map((m, i) => (
            <FileCheck key={i} data-review-mark={m} className={`${page} shrink-0 ${MARK_TONE[m]}`} strokeWidth={2} />
          ))}
        </span>
      </div>
    </Exhibit>
  );
}

/** "Does our AI reviewer spot mistakes?" — one bug per hidden mistake, coloured by what the reviewer did with it. */
function ReviewerCard({ results, study }: { results: ReviewerResults; study: ReviewerStudy }) {
  const tally = reviewerTally(results, study);
  const truth: FigureTruth = { kind: "last_run", asOf: results.asOf, source: results.receipt };
  const caseTruth: FigureTruth = { kind: "last_run", asOf: study.asOf, source: study.receipt };
  const n = (value: number, t: FigureTruth = truth, className = "") => (
    <Figure truth={t} value={String(value)} className={className}>
      {String(value)}
    </Figure>
  );
  const bugs = caseMarks(results, study, "defect");
  const decoys = caseMarks(results, study, "control");
  return (
    <Card id="reviewer" title={COPY.reviewerTitle} scope={truth.kind} footer={<TruthChip truth={truth} showClock />}>
      <p className="text-caption text-text-secondary" data-review-kind="mistakes">
        {tally.mistakes.reviewed > 0 ? (
          <>
            {COPY.reviewerCaughtBefore} <span className="text-title-3 text-text-primary">{n(tally.mistakes.right)}</span>{" "}
            {COPY.reviewerCaughtMiddle} <span className="text-title-3 text-text-primary">{n(tally.mistakes.reviewed)}</span>{" "}
            {COPY.reviewerCaughtAfter}
          </>
        ) : (
          COPY.reviewerNoneChecked
        )}
      </p>
      <ReviewerMarks results={results} study={study} />
      <p className="text-caption text-text-primary" data-review-kind="harmless">
        {COPY.reviewerHidBefore} {n(bugs.length, caseTruth)} {COPY.reviewerHidMiddle} {n(decoys.length, caseTruth)}{" "}
        {COPY.reviewerHidAfter}
      </p>
    </Card>
  );
}

export type Dot = "problems" | "fixed" | "stopped" | "unknown";

export const DOT_CLASS: Record<Dot, string> = {
  problems: "text-accent-danger",
  fixed: "text-accent-brand",
  stopped: "text-text-secondary",
  unknown: "text-text-muted",
};

const DOT_WORDS: Record<Dot, string> = {
  problems: COPY.watchersProblems,
  fixed: COPY.watchersFixed,
  stopped: COPY.watchersStopped,
  unknown: COPY.watchersUnknown,
};

const dotOf = (state: string | null): Dot =>
  state === "red_reporting" ? "problems" : state === "closed_fixed" ? "fixed" : state === "red_stopped" ? "stopped" : "unknown";

/** One smoke alarm per watcher, or a question mark where there is no public record: the top screen's picture, and its topic's. */
export function WatcherAlarms({ list, large = false }: { list: WatcherList; large?: boolean }) {
  const truth: FigureTruth = { kind: "reviewed", asOf: list.reviewedAt, source: list.scheduleSource };
  const size = large ? "h-9 w-9" : "h-6 w-6";
  return (
    <Exhibit truth={truth} label={COPY.watchersChartLabel}>
      {/* Large, the alarms sit in rows of six, so a dozen read as two even rows. */}
      <div className={large ? "grid w-fit grid-cols-6 gap-2" : "flex gap-1"} aria-hidden="true">
        {list.watchers.map((w) => {
          const dot = dotOf(w.verdict?.state ?? null);
          return dot === "unknown" ? (
            <CircleHelp key={w.id} data-watcher-dot={dot} className={`${size} shrink-0 ${DOT_CLASS[dot]}`} strokeWidth={2} />
          ) : (
            <AlarmSmoke key={w.id} data-watcher-dot={dot} className={`${size} shrink-0 ${DOT_CLASS[dot]}`} strokeWidth={2.25} />
          );
        })}
      </div>
    </Exhibit>
  );
}

/** "Are our site watchers working?" — one alarm per watcher, marked by what its newest run found. */
function WatchersCard({ list }: { list: WatcherList }) {
  const health = watcherHealth(list);
  const truth: FigureTruth = { kind: "reviewed", asOf: list.reviewedAt, source: list.scheduleSource };
  const n = (value: number) => (
    <Figure truth={truth} value={String(value)}>
      {String(value)}
    </Figure>
  );
  const dots = list.watchers.map((w) => ({ id: w.id, dot: dotOf(w.verdict?.state ?? null) }));
  // The sentence names only the kinds of circle the picture has.
  const present = (["problems", "fixed", "stopped", "unknown"] as Dot[]).filter((k) => dots.some((d) => d.dot === k));
  return (
    <Card id="watchers" title={COPY.watchersTitle} scope={truth.kind} footer={<TruthChip truth={truth} />}>
      <p className="text-caption text-text-secondary" data-watchers-working={health.working}>
        <span className="text-title-3 text-text-primary">{n(health.working)}</span> {COPY.watchersOf}{" "}
        <span className="text-title-3 text-text-primary">{n(health.total)}</span> {COPY.watchersWorkingAfter}
      </p>
      <WatcherAlarms list={list} />
      <p className="text-caption text-text-primary">
        {COPY.watchersSentenceStart}: {present.map((k) => DOT_WORDS[k]).join("; ")}.
      </p>
    </Card>
  );
}

export default function TopScreen({
  forward,
  study,
  results,
  watchers,
}: {
  forward: ForwardRecordState;
  study: ReviewerStudy | null;
  results: ReviewerResults | null;
  watchers: WatcherList | null;
}) {
  return (
    // On a phone the gaps are 6 px, not 8, for the same room as TRUTH_PLOT's height.
    <header data-evals-top="" className="space-y-1.5 md:space-y-2">
      <h1 className="text-title-3 text-text-primary">{EVALS_PAGE_TITLE}</h1>
      <p className="text-body text-text-primary">{COPY.answer}</p>
      <div className="grid gap-1.5 md:gap-2 md:grid-cols-3">
        <TruthCard state={forward} />
        {results && study && <ReviewerCard results={results} study={study} />}
        {watchers && <WatchersCard list={watchers} />}
      </div>
    </header>
  );
}
