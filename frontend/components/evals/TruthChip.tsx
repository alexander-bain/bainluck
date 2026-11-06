"use client";

import { CHIP_SHAPE, TRUTH_TONE } from "@/components/evals/chipStyles";
import RepoRefLink from "@/components/evals/RepoRefLink";
import { useNow } from "@/components/evals/useNow";
import { CHIP_COPY } from "@/lib/evals/copy";
import {
  ageInDays,
  ageLabel,
  isAgeAmber,
  pacificClockLabel,
  truthChipLabel,
  type Truth,
} from "@/lib/evals/truth";

/**
 * LIVE · LAST RUN · NOV 5 · LAST REVIEWED · NOV 5 · PLANNED.
 *
 * Everything inside `data-truth-chip` — the date, the age, the issue a PLANNED
 * item waits on — is a label rather than a figure, and the page test exempts it
 * by that attribute. A figure never goes in here.
 */
export default function TruthChip({
  truth,
  linked = true,
}: {
  truth: Truth;
  /** False inside something that is already a link (a hero tile), where a nested `<a>` is invalid. */
  linked?: boolean;
}) {
  const now = useNow();
  const dated = truth.kind === "last_run" || truth.kind === "reviewed";
  const days = dated && now ? ageInDays(truth.asOf, now) : null;
  const clock = truth.kind === "live" ? pacificClockLabel(truth.asOf) : null;
  const source = truth.kind === "planned" ? undefined : truth.source;

  const chip = (
    <span className={`${CHIP_SHAPE} ${TRUTH_TONE[truth.kind]}`}>{truthChipLabel(truth)}</span>
  );

  return (
    <span
      data-truth-chip=""
      data-truth={truth.kind}
      data-as-of={truth.kind === "planned" ? undefined : truth.asOf}
      className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-1"
    >
      {source && linked ? (
        <a href={source.href} target="_blank" rel="noopener noreferrer" title={source.label}>
          {chip}
        </a>
      ) : (
        chip
      )}
      {clock && (
        <span className="text-micro text-text-secondary">
          {CHIP_COPY.asOf} {clock}
        </span>
      )}
      {days !== null && (
        <span
          className={`text-micro ${isAgeAmber(days) ? "text-yellow-700" : "text-text-secondary"}`}
          data-age-days={days}
          data-age-amber={isAgeAmber(days) ? "true" : "false"}
        >
          {ageLabel(days)}
        </span>
      )}
      {truth.kind === "planned" && (
        <span className="text-micro text-text-secondary">
          {CHIP_COPY.waitingOn} {truth.waitingOn}
          {truth.ref && (
            <>
              {" "}
              <RepoRefLink repoRef={truth.ref} />
            </>
          )}
        </span>
      )}
    </span>
  );
}
