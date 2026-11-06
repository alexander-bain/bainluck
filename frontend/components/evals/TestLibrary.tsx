"use client";

import EvalsSection from "@/components/evals/EvalsSection";
import Figure from "@/components/evals/Figure";
import ResultChip from "@/components/evals/ResultChip";
import { LIBRARY_COPY } from "@/lib/evals/copy";
import { familyView, libraryTruth, recordedClock, type Scoreboard } from "@/lib/evals/scoreboard";
import { sourceLink } from "@/lib/evals/sources";
import { pacificDayLabel, type MeasuredTruth } from "@/lib/evals/truth";

const REPO = "https://github.com/alexander-bain/bainluck";

/**
 * "The test library" — the scoreboard's families in plain words, with the
 * recorded run's time and commit, and the golden set's count and floor.
 *
 * A family's recorded run shows passed and failed always (skipped only when
 * there are skips), and how many of its checks have no recorded run, so a
 * family that is mostly unrecorded never reads as all green. A failure would
 * also put a FAIL chip beside its name.
 */
export default function TestLibrary({ board }: { board: Scoreboard }) {
  const truth = libraryTruth(board);
  const golden: MeasuredTruth = { ...truth, source: sourceLink("golden-baseline") };
  const day = pacificDayLabel(truth.asOf);
  const clock = recordedClock(board.recordedAtPt);
  const shortSha = board.recordedSourceSha.slice(0, 10);
  const families = board.families.map(familyView);
  const n = (value: number, t: MeasuredTruth = truth) => (
    <Figure truth={t} value={String(value)}>
      {value.toLocaleString("en-US")}
    </Figure>
  );

  return (
    <EvalsSection
      id="test-library"
      title={LIBRARY_COPY.title}
      lead={LIBRARY_COPY.lead}
      detail={LIBRARY_COPY.detail}
      truth={truth}
    >
      <div className="space-y-4">
        <div className="space-y-1 text-caption text-text-secondary">
          <p data-testid="evals-library-recorded">
            {LIBRARY_COPY.recordedBefore}{" "}
            <time dateTime={truth.asOf}>{clock && day ? `${day}, ${clock}` : day}</time>{" "}
            {LIBRARY_COPY.recordedAt}{" "}
            <a
              href={`${REPO}/commit/${board.recordedSourceSha}`}
              target="_blank"
              rel="noopener noreferrer"
              data-evals-ref=""
              data-recorded-sha={board.recordedSourceSha}
              className="font-mono text-micro text-accent-brand hover:underline"
            >
              {shortSha}
            </a>
            .
          </p>
          <p>
            {n(board.registry.registered)} {LIBRARY_COPY.checksIn} {n(families.length)} {LIBRARY_COPY.families}{" "}
            {n(board.registry.grandfathered)} {LIBRARY_COPY.olderAfter}
          </p>
        </div>

        <ul className="divide-y divide-surface-border border-y border-surface-border" data-testid="evals-library-families">
          {families.map((f) => (
            <li key={f.canonical} data-family={f.canonical} data-failed={f.failed} className="py-2.5">
              <details className="group">
                <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden">
                  <span className="flex items-baseline justify-between gap-3">
                    <span className="flex flex-wrap items-center gap-2 text-caption-strong text-text-primary">
                      <span className="text-text-tertiary group-open:rotate-90 transition-transform" aria-hidden="true">
                        ›
                      </span>
                      {f.name}
                      {f.failed > 0 && <ResultChip result="fail" />}
                    </span>
                    <span className="text-caption text-text-secondary whitespace-nowrap">
                      {n(f.cases)} {f.casesAtLeast ? LIBRARY_COPY.casesAtLeast : LIBRARY_COPY.cases}
                    </span>
                  </span>
                  <span className="mt-0.5 block pl-4 text-micro text-text-secondary">
                    {LIBRARY_COPY.recordedRun} {n(f.passed)} {LIBRARY_COPY.passed}, {n(f.failed)} {LIBRARY_COPY.failed}
                    {f.skipped > 0 && (
                      <>
                        , {n(f.skipped)} {LIBRARY_COPY.skipped}
                      </>
                    )}
                    .
                    {f.unrecorded > 0 && (
                      <>
                        {" "}
                        {n(f.unrecorded)} {LIBRARY_COPY.unrecordedOf} {n(f.evals)}{" "}
                        {f.unrecorded === 1 ? LIBRARY_COPY.unrecordedAfterOne : LIBRARY_COPY.unrecordedAfter}
                      </>
                    )}
                  </span>
                </summary>
                <p className="mt-1.5 pl-4 text-caption text-text-secondary">
                  {f.checks} {n(f.evals)} {LIBRARY_COPY.checks}.
                </p>
              </details>
            </li>
          ))}
        </ul>

        <div
          data-testid="evals-golden"
          className="rounded-lg border border-surface-border bg-surface-elevated px-3 py-2.5 text-caption text-text-secondary space-y-1"
        >
          <p className="text-caption-strong text-text-primary">{LIBRARY_COPY.goldenTitle}</p>
          <p>
            {LIBRARY_COPY.goldenGets} {n(board.golden.passing, golden)} {LIBRARY_COPY.goldenOf}{" "}
            {n(board.golden.total, golden)} {LIBRARY_COPY.goldenAfter}
          </p>
          <p>
            {LIBRARY_COPY.floorBefore} {n(board.golden.floor, golden)}
            {LIBRARY_COPY.floorAfter}
          </p>
        </div>
      </div>
    </EvalsSection>
  );
}
