"use client";

import { useState } from "react";

import EvalsSection from "@/components/evals/EvalsSection";
import Figure from "@/components/evals/Figure";
import RepoRefLink from "@/components/evals/RepoRefLink";
import ResultChip from "@/components/evals/ResultChip";
import TruthChip from "@/components/evals/TruthChip";
import { TESTS_FOR_TESTS_COPY as COPY } from "@/lib/evals/copy";
import type { ReviewerCase, ReviewerStudy } from "@/lib/evals/reviewerStudy";
import { biteTruth, type Scoreboard } from "@/lib/evals/scoreboard";
import { issueRef, type MeasuredTruth } from "@/lib/evals/truth";

function Meter({ part, whole, tone, testId }: { part: number; whole: number; tone: string; testId: string }) {
  return (
    <div aria-hidden="true" data-testid={testId} className="mt-1 h-2 w-full overflow-hidden rounded-full bg-surface-elevated">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${whole > 0 ? (100 * part) / whole : 0}%` }} />
    </div>
  );
}

/** Two bars, never one: how many planted changes were caught, and how many of those cases run the site's own code. */
function BiteMeter({ board }: { board: Scoreboard }) {
  const truth = biteTruth(board);
  const { total, caught, realCode } = board.bite;
  const n = (value: number) => (
    <Figure truth={truth} value={String(value)}>
      {value.toLocaleString("en-US")}
    </Figure>
  );
  return (
    <div data-testid="evals-bite" data-truth-scope="last_run" className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-caption-strong text-text-primary">{COPY.biteTitle}</h3>
        <TruthChip truth={truth} />
      </div>
      <div data-bite="caught">
        <p className="text-caption text-text-primary">
          {n(caught)} {COPY.biteOf} {n(total)} {COPY.biteCaught}
        </p>
        <Meter part={caught} whole={total} tone="bg-green-600" testId="evals-bite-caught-bar" />
      </div>
      <div data-bite="real-code">
        <p className="text-caption text-text-primary">
          {n(realCode)} {COPY.biteOf} {n(total)} {COPY.biteReal}
        </p>
        <Meter part={realCode} whole={total} tone="bg-yellow-500" testId="evals-bite-real-bar" />
      </div>
      <p className="text-caption text-text-secondary">
        {COPY.biteExplain} {realCode === 0 && COPY.biteNoneReal}
      </p>
    </div>
  );
}

function Tile({ c, selected, onSelect }: { c: ReviewerCase; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-controls="evals-reviewer-detail"
      data-reviewer-case={c.id}
      data-case-kind={c.kind}
      data-reviewer-result={c.reviewer}
      className={`flex h-full flex-col items-start justify-between gap-1.5 rounded-lg border p-2 text-left transition-colors ${
        selected
          ? "border-accent-brand bg-surface-elevated"
          : "border-surface-border bg-surface-card hover:bg-surface-elevated"
      }`}
    >
      <span className="text-caption-strong text-text-primary">{c.label}</span>
      <ResultChip result={c.reviewer} />
    </button>
  );
}

function CaseDetail({ c }: { c: ReviewerCase }) {
  return (
    <div
      id="evals-reviewer-detail"
      role="region"
      aria-live="polite"
      data-testid="evals-reviewer-detail"
      data-detail-case={c.id}
      className="rounded-lg border border-surface-border bg-surface-elevated px-3 py-2.5 space-y-1.5"
    >
      <p className="text-micro uppercase tracking-wide text-text-tertiary">
        {c.kind === "defect" ? COPY.bug : COPY.healthy}
      </p>
      <p className="text-caption-strong text-text-primary">{c.label}</p>
      <p className="text-caption text-text-secondary">{c.text}</p>
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-text-primary">
        <span data-our-tests={c.ourTests}>
          {COPY.ourTests}: {c.ourTests === "caught" ? COPY.caught : COPY.passedIt}{" "}
          <span aria-hidden="true" className="text-green-700">
            ✓
          </span>
        </span>
        <span className="flex items-center gap-1.5">
          {COPY.reviewer}: <ResultChip result={c.reviewer} />
        </span>
      </p>
    </div>
  );
}

/** The planted-bug grid: ten bugs and five healthy changes, each with the AI reviewer's result. */
function ReviewerGrid({ study }: { study: ReviewerStudy }) {
  const [selectedId, setSelectedId] = useState(study.cases[0].id);
  const truth: MeasuredTruth = { kind: "last_run", asOf: study.asOf, source: study.receipt };
  const bugs = study.cases.filter((c) => c.kind === "defect");
  const healthy = study.cases.filter((c) => c.kind === "control");
  const selected = study.cases.find((c) => c.id === selectedId) ?? study.cases[0];
  const allOurs =
    bugs.every((c) => c.ourTests === "caught") && healthy.every((c) => c.ourTests === "pass");
  const noneReviewed = study.cases.every((c) => c.reviewer === "not_run");
  const n = (value: number) => (
    <Figure truth={truth} value={String(value)}>
      {value.toLocaleString("en-US")}
    </Figure>
  );
  const grid = (cases: ReviewerCase[], heading: string, kind: string) => (
    <div>
      <h4 className="text-micro uppercase tracking-wide text-text-tertiary mb-1.5">{heading}</h4>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2" data-reviewer-grid={kind}>
        {cases.map((c) => (
          <Tile key={c.id} c={c} selected={c.id === selected.id} onSelect={() => setSelectedId(c.id)} />
        ))}
      </div>
    </div>
  );

  return (
    <div data-testid="evals-reviewer" data-truth-scope="last_run" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-caption-strong text-text-primary">{COPY.reviewerTitle}</h3>
        <TruthChip truth={truth} />
      </div>
      <p className="text-caption text-text-secondary">
        {COPY.reviewerLeadBefore} {n(bugs.length)} {COPY.reviewerLeadMiddle} {n(healthy.length)} {COPY.reviewerLeadAfter}
      </p>
      {allOurs && noneReviewed && <p className="text-caption text-text-primary">{COPY.reviewerOursAll}</p>}
      <p className="text-micro text-text-tertiary">{COPY.pickHint}</p>
      {grid(bugs, COPY.bugsHeading, "defect")}
      {grid(healthy, COPY.healthyHeading, "control")}
      <CaseDetail c={selected} />
      {study.dropped && (
        <p className="text-caption text-text-secondary">
          {COPY.droppedBefore} <RepoRefLink repoRef={issueRef(study.dropped.issue)} />.
        </p>
      )}
    </div>
  );
}

/** "Tests for the tests" — the bite audit and the AI code reviewer's study. */
export default function TestsForTheTests({ board, study }: { board: Scoreboard | null; study: ReviewerStudy | null }) {
  return (
    <EvalsSection id="tests-for-tests" title={COPY.title} lead={COPY.lead} detail={COPY.detail}>
      <div className="space-y-6">
        {board && <BiteMeter board={board} />}
        {study && <ReviewerGrid study={study} />}
      </div>
    </EvalsSection>
  );
}
