"use client";

import Figure from "@/components/evals/Figure";
import ResultChip from "@/components/evals/ResultChip";
import TruthChip from "@/components/evals/TruthChip";
import type { ForwardRecordState } from "@/components/evals/useForwardRecord";
import { HERO_TILE_COPY } from "@/lib/evals/copy";
import { stalenessHeadline } from "@/lib/calibrationStaleness";
import { biteTruth, type Scoreboard } from "@/lib/evals/scoreboard";
import { acrossPasses, examTruth, type TwinExam } from "@/lib/evals/twinExam";

const TILE =
  "block rounded-xl border border-surface-border bg-surface-card p-4 hover:bg-surface-elevated transition-colors";

/**
 * The hero's tiles. Each jumps to its section and carries its own truth label;
 * a tile whose section is not on the page is absent: the AI exam's (S2), the
 * forward record's (S3) and the tests-for-the-tests' (S4).
 */
export default function HeroTiles({
  exam,
  forward,
  board,
}: {
  exam: TwinExam | null;
  forward: ForwardRecordState;
  board: Scoreboard | null;
}) {
  const ready = forward.status === "ready" ? forward : null;
  const proof = ready?.view.proof ?? null;
  const bite = board ? biteTruth(board) : null;
  return (
    <div className="grid gap-3 sm:grid-cols-3 text-left" data-testid="evals-hero-tiles">
      {exam && <ExamTile exam={exam} />}
      <a href="#forward-record" data-hero-tile="forward-record" data-truth-scope={ready ? "live" : undefined} className={TILE}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-caption-strong text-text-primary">{HERO_TILE_COPY.forwardTitle}</span>
          {ready && <TruthChip truth={ready.truth} linked={false} />}
        </div>
        <p className="mt-2 text-caption text-text-secondary">
          {ready && proof ? (
            <>
              <Figure truth={ready.truth} value={String(proof.errorPp)} className="text-prob-sm text-text-primary">
                {proof.errorText}
              </Figure>{" "}
              {HERO_TILE_COPY.forwardPointsAfter}{" "}
              <Figure truth={ready.truth} value={String(proof.outcomes)}>
                {proof.outcomesText}
              </Figure>{" "}
              {HERO_TILE_COPY.forwardOutcomesAfter}
            </>
          ) : forward.status === "loading" ? (
            HERO_TILE_COPY.loading
          ) : (
            HERO_TILE_COPY.unavailable
          )}
        </p>
        {ready?.view.staleness && (
          // The chip says LIVE for the curve; when its inputs are older, the
          // first screen says so in the accuracy page's own words (Fable on #12124).
          <p className="mt-1.5 text-micro text-yellow-700" data-testid="evals-hero-forward-staleness">
            {stalenessHeadline(ready.view.staleness)}
          </p>
        )}
      </a>
      {board && bite && (
        <a href="#tests-for-tests" data-hero-tile="tests-for-tests" data-truth-scope="last_run" className={TILE}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-caption-strong text-text-primary">{HERO_TILE_COPY.testsTitle}</span>
            <TruthChip truth={bite} linked={false} />
          </div>
          <p className="mt-2 text-caption text-text-secondary">
            <Figure truth={bite} value={String(board.bite.caught)} className="text-prob-sm text-text-primary">
              {board.bite.caught.toLocaleString("en-US")}
            </Figure>{" "}
            {HERO_TILE_COPY.testsOf}{" "}
            <Figure truth={bite} value={String(board.bite.total)}>
              {board.bite.total.toLocaleString("en-US")}
            </Figure>{" "}
            {HERO_TILE_COPY.testsCaughtAfter}{" "}
            <Figure truth={bite} value={String(board.bite.realCode)} className="text-prob-sm text-text-primary">
              {board.bite.realCode.toLocaleString("en-US")}
            </Figure>{" "}
            {HERO_TILE_COPY.testsOf}{" "}
            <Figure truth={bite} value={String(board.bite.total)}>
              {board.bite.total.toLocaleString("en-US")}
            </Figure>{" "}
            {HERO_TILE_COPY.testsRealAfter}
          </p>
        </a>
      )}
    </div>
  );
}

/** The AI exam's verdict, FAIL as FAIL, with what it got right and what it got wrong on held-out pairs. */
function ExamTile({ exam }: { exam: TwinExam }) {
  const truth = examTruth(exam);
  const [foundLo, foundHi] = acrossPasses(exam, (p) => p.test.perRelation.twin.recall.k);
  const [mergedLo, mergedHi] = acrossPasses(exam, (p) => p.test.wrongMerges);
  const twins = exam.perPass["1"].test.perRelation.twin.recall.n;
  const heldOut = exam.perPass["1"].test.expected;
  const n = (value: number, className = "") => (
    <Figure truth={truth} value={String(value)} className={className}>
      {value.toLocaleString("en-US")}
    </Figure>
  );
  const range = (lo: number, hi: number, className = "") =>
    lo === hi ? (
      n(lo, className)
    ) : (
      <>
        {n(lo, className)} {HERO_TILE_COPY.examTo} {n(hi, className)}
      </>
    );
  return (
    <a href="#exam" data-hero-tile="exam" data-truth-scope="last_run" className={TILE}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-caption-strong text-text-primary">
          {HERO_TILE_COPY.examTitle}
          <ResultChip result={exam.result} />
        </span>
        <TruthChip truth={truth} linked={false} />
      </div>
      <p className="mt-2 text-caption text-text-secondary">
        {HERO_TILE_COPY.examFoundBefore} {range(foundLo, foundHi, "text-prob-sm text-text-primary")} {HERO_TILE_COPY.examOf}{" "}
        {n(twins)} {HERO_TILE_COPY.examFoundAfter} {range(mergedLo, mergedHi, "text-prob-sm text-text-primary")}{" "}
        {HERO_TILE_COPY.examOf} {n(heldOut)} {HERO_TILE_COPY.examCombinedAfter}
      </p>
    </a>
  );
}
