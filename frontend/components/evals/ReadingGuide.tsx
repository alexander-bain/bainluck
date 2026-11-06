import { CHIP_SHAPE, TRUTH_TONE } from "@/components/evals/chipStyles";
import ResultChip from "@/components/evals/ResultChip";
import {
  CHIP_COPY,
  READING_COPY,
  RESULT_CHIP_MEANING,
  TERMS,
  TRUTH_CHIP_MEANING,
} from "@/lib/evals/copy";
import { RESULT_KINDS, TRUTH_KINDS, type TruthKind } from "@/lib/evals/truth";

/**
 * The chip's shape with the word "date" where a run's date goes. A sample with a
 * real date would read as a record of something that ran on that day.
 */
const SAMPLE_LABEL: Record<TruthKind, string> = {
  live: "LIVE",
  last_run: `LAST RUN · ${CHIP_COPY.sampleDate}`,
  reviewed: `LAST REVIEWED · ${CHIP_COPY.sampleDate}`,
  planned: "PLANNED",
};

/** "How to read this page": the chip legend and the terms the page uses. */
export default function ReadingGuide() {
  return (
    <div className="space-y-5" data-testid="evals-reading-guide">
      <div>
        <h3 className="text-caption-strong text-text-primary">{READING_COPY.labelsHeading}</h3>
        <dl className="mt-2 space-y-2">
          {TRUTH_KINDS.map((kind) => (
            <div key={kind} className="flex flex-col gap-1 sm:flex-row sm:gap-3" data-legend={kind}>
              <dt className="sm:w-44 flex-none">
                <span className={`${CHIP_SHAPE} ${TRUTH_TONE[kind]}`}>{SAMPLE_LABEL[kind]}</span>
              </dt>
              <dd className="text-caption text-text-secondary">{TRUTH_CHIP_MEANING[kind]}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div>
        <h3 className="text-caption-strong text-text-primary">{READING_COPY.resultsHeading}</h3>
        <dl className="mt-2 space-y-2">
          {RESULT_KINDS.map((kind) => (
            <div key={kind} className="flex flex-col gap-1 sm:flex-row sm:gap-3" data-legend={kind}>
              <dt className="sm:w-44 flex-none">
                <ResultChip result={kind} />
              </dt>
              <dd className="text-caption text-text-secondary">{RESULT_CHIP_MEANING[kind]}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div>
        <h3 className="text-caption-strong text-text-primary">{READING_COPY.termsHeading}</h3>
        <div className="mt-2 divide-y divide-surface-border border-y border-surface-border">
          {TERMS.map(({ term, meaning }) => (
            <details key={term} className="group py-2" data-term={term}>
              <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden text-caption-strong text-text-primary flex items-center justify-between">
                {term}
                <span aria-hidden="true" className="text-text-muted transition-transform group-open:rotate-90">
                  ›
                </span>
              </summary>
              <p className="mt-1 text-caption text-text-secondary">{meaning}</p>
            </details>
          ))}
        </div>
      </div>
    </div>
  );
}
