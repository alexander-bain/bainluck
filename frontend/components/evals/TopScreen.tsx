"use client";

import type { ReactNode } from "react";

import Figure, { Exhibit } from "@/components/evals/Figure";
import ResultChip from "@/components/evals/ResultChip";
import TruthChip from "@/components/evals/TruthChip";
import type { ForwardRecordState } from "@/components/evals/useForwardRecord";
import { EVALS_PAGE_TITLE, TOP_COPY as COPY } from "@/lib/evals/copy";
import { CHART_THIN_FLOOR } from "@/lib/evals/forwardRecord";
import { reviewerTally, type ReviewerResults } from "@/lib/evals/reviewerResults";
import type { ReviewerStudy } from "@/lib/evals/reviewerStudy";
import {
  TRUTH_PLOT,
  plotX,
  plotY,
  reviewBlocks,
  truthDots,
  truthReading,
  type ReviewBlock,
} from "@/lib/evals/topScreen";
import type { FigureTruth } from "@/lib/evals/truth";
import { watcherHealth, type WatcherList } from "@/lib/evals/watchers";

/**
 * THE TOP SCREEN OF /evals (Alex, Nov 6): one plain answer, then three pictures
 * a reader takes in without reading a number — do our probabilities come true,
 * does the AI reviewer catch planted mistakes, are the automatic checks
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
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" role="img" aria-label={COPY.truthChartLabel}>
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
        {reading === "close" ? COPY.truthClose : reading === "far" ? COPY.truthFar : COPY.truthPlain}
      </p>
    </Card>
  );
}

const BLOCK_TONE: Record<ReviewBlock, string> = {
  caught: "bg-accent-brand",
  passed: "bg-accent-brand",
  missed: "bg-accent-danger",
  flagged: "bg-accent-danger",
  not_yet: "bg-surface-elevated",
};

function BlockRow({ blocks, kind }: { blocks: ReviewBlock[]; kind: string }) {
  return (
    <div className="flex gap-[2px]" aria-hidden="true" data-review-blocks={kind}>
      {blocks.map((b, i) => (
        <span key={i} data-review-block={b} className={`h-3 flex-1 rounded-sm ${BLOCK_TONE[b]}`} />
      ))}
    </div>
  );
}

/** "Does our AI reviewer catch planted mistakes?" — one block per planned review, filled as results come in. */
function ReviewerCard({ results, study }: { results: ReviewerResults; study: ReviewerStudy }) {
  const tally = reviewerTally(results, study);
  const truth: FigureTruth = { kind: "last_run", asOf: results.asOf, source: results.receipt };
  const n = (value: number) => (
    <Figure truth={truth} value={String(value)}>
      {String(value)}
    </Figure>
  );
  const done = tally.mistakes.reviewed + tally.harmless.reviewed;
  const row = (kind: "mistakes" | "harmless") => {
    const t = tally[kind];
    return (
      <div className="space-y-0.5" data-review-kind={kind}>
        <p className="flex flex-wrap items-baseline justify-between gap-x-2 text-caption">
          <span className="text-text-primary">{kind === "mistakes" ? COPY.reviewerMistakes : COPY.reviewerHarmless}</span>
          <span className="text-text-secondary">
            {t.reviewed > 0 ? (
              <>
                {n(kind === "mistakes" ? t.right : t.wrong)}{" "}
                {kind === "mistakes" ? COPY.reviewerCaughtAfter : COPY.reviewerAlarmsAfter} {n(t.reviewed)}{" "}
                {COPY.reviewerSoFar}
              </>
            ) : (
              <>
                <ResultChip result="unknown" /> {COPY.reviewerNoneYet}
              </>
            )}
          </span>
        </p>
        <BlockRow blocks={reviewBlocks(results, study, kind === "mistakes" ? "defect" : "control")} kind={kind} />
      </div>
    );
  };
  return (
    <Card id="reviewer" title={COPY.reviewerTitle} scope={truth.kind} footer={<TruthChip truth={truth} showClock />}>
      <Exhibit truth={truth} label={COPY.reviewerChartLabel}>
        <div className="space-y-1.5">
          {row("mistakes")}
          {row("harmless")}
        </div>
      </Exhibit>
      <p className="text-caption text-text-primary">
        {COPY.reviewerSentence}
        {done < results.planned && <> {COPY.reviewerUnderWay}</>}
      </p>
    </Card>
  );
}

type Dot = "problems" | "fixed" | "stopped" | "unknown";

const DOT_CLASS: Record<Dot, string> = {
  problems: "bg-accent-danger border-accent-danger",
  fixed: "bg-accent-brand border-accent-brand",
  stopped: "bg-surface-elevated border-text-muted",
  unknown: "bg-surface-card border-dashed border-text-muted",
};

const DOT_WORDS: Record<Dot, string> = {
  problems: COPY.watchersProblems,
  fixed: COPY.watchersFixed,
  stopped: COPY.watchersStopped,
  unknown: COPY.watchersUnknown,
};

/** "Are our automatic checks working?" — one circle per check, marked by what its newest run found. */
function WatchersCard({ list }: { list: WatcherList }) {
  const health = watcherHealth(list);
  const truth: FigureTruth = { kind: "reviewed", asOf: list.reviewedAt, source: list.scheduleSource };
  const n = (value: number) => (
    <Figure truth={truth} value={String(value)}>
      {String(value)}
    </Figure>
  );
  const dotOf = (state: string | null): Dot =>
    state === "red_reporting" ? "problems" : state === "closed_fixed" ? "fixed" : state === "red_stopped" ? "stopped" : "unknown";
  const dots = list.watchers.map((w) => ({ id: w.id, dot: dotOf(w.verdict?.state ?? null) }));
  // The sentence names only the kinds of circle the picture has.
  const present = (["problems", "fixed", "stopped", "unknown"] as Dot[]).filter((k) => dots.some((d) => d.dot === k));
  return (
    <Card id="watchers" title={COPY.watchersTitle} scope={truth.kind} footer={<TruthChip truth={truth} />}>
      <p className="text-caption text-text-secondary" data-watchers-working={health.working}>
        <span className="text-title-3 text-text-primary">{n(health.working)}</span> {COPY.watchersOf}{" "}
        <span className="text-title-3 text-text-primary">{n(health.total)}</span> {COPY.watchersWorkingAfter}
      </p>
      <Exhibit truth={truth} label={COPY.watchersChartLabel}>
        <div className="flex gap-1" aria-hidden="true">
          {dots.map((d) => (
            <span key={d.id} data-watcher-dot={d.dot} className={`h-6 w-6 shrink-0 rounded-full border-2 ${DOT_CLASS[d.dot]}`} />
          ))}
        </div>
      </Exhibit>
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
    <header data-evals-top="" className="space-y-2">
      <h1 className="text-title-3 text-text-primary">{EVALS_PAGE_TITLE}</h1>
      <p className="text-body text-text-primary">{COPY.answer}</p>
      <div className="grid gap-2 md:grid-cols-3">
        <TruthCard state={forward} />
        {results && study && <ReviewerCard results={results} study={study} />}
        {watchers && <WatchersCard list={watchers} />}
      </div>
    </header>
  );
}
