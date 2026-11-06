"use client";

import Link from "next/link";

import CalibrationChart from "@/components/CalibrationChart";
import EvalsSection from "@/components/evals/EvalsSection";
import Figure, { Exhibit } from "@/components/evals/Figure";
import type { ForwardRecordState } from "@/components/evals/useForwardRecord";
import { FORWARD_COPY } from "@/lib/evals/copy";
import { CHART_THIN_FLOOR, DEFAULT_CURVE_COLOR, barPointsText } from "@/lib/evals/forwardRecord";
import { stalenessHeadline, stalenessInputSentence, type CalibrationStalenessNotice } from "@/lib/calibrationStaleness";
import { pacificClockLabel, pacificDayLabel } from "@/lib/evals/truth";

/** A payload timestamp as "Oct 27, 1:54 PM PT", or null when it cannot be read. */
function pacificMoment(iso: string | null): string | null {
  if (!iso) return null;
  const day = pacificDayLabel(iso);
  const clock = pacificClockLabel(iso);
  return day && clock ? `${day}, ${clock}` : day;
}

/**
 * The staleness line: the accuracy page's own headline, then the date the
 * notice names. The banner may describe, never predict — so no schedule or
 * recovery is promised here either.
 */
function StalenessLine({ notice }: { notice: CalibrationStalenessNotice }) {
  const staged = pacificMoment(notice.stagedAt);
  const built = pacificMoment(notice.generatedAt);
  return (
    <p
      role="status"
      data-testid="evals-forward-staleness"
      data-staleness-kind={notice.kind}
      className="rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-caption text-text-secondary"
    >
      <strong className="text-text-primary">{stalenessHeadline(notice)}</strong>{" "}
      {notice.kind === "frozen-inputs" && staged && (
        <>
          {FORWARD_COPY.stagedBefore} <time dateTime={notice.stagedAt ?? undefined}>{staged}</time>.
        </>
      )}
      {notice.kind === "last-good" && built && (
        <>
          {FORWARD_COPY.builtBefore} <time dateTime={notice.generatedAt ?? undefined}>{built}</time>.
        </>
      )}
      {notice.kind === "undisclosed" && stalenessInputSentence(notice)}
    </p>
  );
}

/** "Do market probabilities come true?" — the live forward record. */
export default function ForwardRecordSection({ state }: { state: ForwardRecordState }) {
  const ready = state.status === "ready" ? state : null;
  return (
    <EvalsSection
      id="forward-record"
      title={FORWARD_COPY.title}
      lead={FORWARD_COPY.lead}
      detail={FORWARD_COPY.detail}
      truth={ready?.truth}
    >
      <div data-forward-status={state.status} className="space-y-4">
        {state.status === "loading" && (
          <p className="text-caption text-text-secondary">{FORWARD_COPY.loading}</p>
        )}
        {state.status === "unavailable" && (
          <p className="text-caption text-text-secondary" data-testid="evals-forward-unavailable">
            {FORWARD_COPY.unavailable}
          </p>
        )}
        {ready && (
          <>
            {ready.view.proof && (
              <p className="text-body text-text-primary" data-testid="evals-forward-proof">
                {FORWARD_COPY.proofBefore}{" "}
                <Figure truth={ready.truth} value={String(ready.view.proof.outcomes)}>
                  {ready.view.proof.outcomesText}
                </Figure>{" "}
                {FORWARD_COPY.proofMiddle}{" "}
                <Figure
                  truth={ready.truth}
                  value={String(ready.view.proof.errorPp)}
                  className="font-semibold"
                >
                  {ready.view.proof.errorText}
                </Figure>{" "}
                {FORWARD_COPY.proofAfter}
              </p>
            )}
            {ready.view.categories && (
              <div data-testid="evals-forward-categories">
                <p className="text-caption text-text-primary">
                  <Figure truth={ready.truth} value={String(ready.view.categories.atBar)}>
                    {String(ready.view.categories.atBar)}
                  </Figure>{" "}
                  {FORWARD_COPY.categoriesOf}{" "}
                  <Figure truth={ready.truth} value={String(ready.view.categories.total)}>
                    {String(ready.view.categories.total)}
                  </Figure>{" "}
                  {FORWARD_COPY.categoriesInside}{" "}
                  <Figure truth={ready.truth} value={String(ready.view.categories.barPp)}>
                    {barPointsText(ready.view.categories.barPp)}
                  </Figure>
                  -{FORWARD_COPY.categoriesBar}
                </p>
                <div
                  aria-hidden="true"
                  className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-surface-elevated"
                >
                  <div
                    className="h-full rounded-full bg-green-600"
                    style={{
                      width: `${(100 * ready.view.categories.atBar) / ready.view.categories.total}%`,
                    }}
                  />
                </div>
              </div>
            )}
            {ready.view.staleness && <StalenessLine notice={ready.view.staleness} />}
            {ready.view.curve && (
              <Exhibit truth={ready.truth} label={FORWARD_COPY.chartLabel}>
                <CalibrationChart
                  series={[
                    { data: ready.view.curve.data, color: DEFAULT_CURVE_COLOR, label: ready.view.curve.label },
                  ]}
                  width={700}
                  height={400}
                  thinFloor={CHART_THIN_FLOOR}
                />
              </Exhibit>
            )}
          </>
        )}
        <Link href="/calibration" className="inline-block text-caption text-accent-brand hover:underline">
          {FORWARD_COPY.more}
        </Link>
      </div>
    </EvalsSection>
  );
}
