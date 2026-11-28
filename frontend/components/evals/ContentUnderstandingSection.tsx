"use client";

import EvalsSection from "@/components/evals/EvalsSection";
import Figure from "@/components/evals/Figure";
import TruthChip from "@/components/evals/TruthChip";
import { CU_SCORECARD_COPY as COPY } from "@/lib/evals/copy";
import {
  CU_SLICE_ORDER,
  CU_SLICE_WORDS,
  cuRepeatabilityTruth,
  cuScorecardTruth,
  formatCuCostUsd,
  plainCuSliceGroupLabel,
  type CuCountBucket,
  type CuRepeatabilityResult,
  type CuScorecard,
} from "@/lib/evals/contentUnderstanding";
import { pacificDayLabel, type MeasuredTruth } from "@/lib/evals/truth";

function RepeatabilityCard({ repeatability }: { repeatability: CuRepeatabilityResult }) {
  const truth = cuRepeatabilityTruth(repeatability);
  const measuredDay = pacificDayLabel(repeatability.asOf);
  return (
    <div
      data-testid="evals-cu-repeatability"
      data-truth-scope="last_run"
      className="rounded-lg border border-surface-border bg-surface-elevated p-4 space-y-2"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-caption-strong text-text-primary">{COPY.repeatabilityHeading}</h3>
        <TruthChip truth={truth} />
      </div>
      <p className="text-body text-text-primary">
        {COPY.repeatabilityBefore}{" "}
        <Figure truth={truth} value={String(repeatability.changedMarkets)}>
          {repeatability.changedMarkets.toLocaleString("en-US")}
        </Figure>{" "}
        {COPY.repeatabilityOf}{" "}
        <Figure truth={truth} value={String(repeatability.totalMarkets)}>
          {repeatability.totalMarkets.toLocaleString("en-US")}
        </Figure>{" "}
        {COPY.repeatabilityAfter}{" "}
        <time dateTime={repeatability.asOf}>{measuredDay ?? repeatability.asOf}</time>
        {COPY.repeatabilityCostBefore}{" "}
        <Figure truth={truth} value={String(repeatability.costCents)}>
          {repeatability.costCents.toLocaleString("en-US")}
        </Figure>{" "}
        {COPY.repeatabilityCostAfter}
      </p>
      <a
        href={truth.source.href}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-block text-caption text-accent-brand hover:underline"
      >
        {COPY.repeatabilityLink}
      </a>
    </div>
  );
}

function BucketCell({
  bucket,
  truth,
  field,
  decider,
}: {
  bucket: CuCountBucket;
  truth: MeasuredTruth;
  field: string;
  decider: "code" | "model";
}) {
  if (bucket.total === 0) {
    return (
      <td className="border-b border-surface-border px-2 py-1.5 text-caption text-text-tertiary">
        <span data-none="">—</span>
      </td>
    );
  }
  return (
    <td
      data-cu-field={field}
      data-cu-decider={decider}
      className="border-b border-surface-border px-2 py-1.5 text-caption text-text-primary whitespace-nowrap"
    >
      <Figure truth={truth} value={String(bucket.right)}>
        {String(bucket.right)}
      </Figure>
      <span className="text-text-tertiary"> / </span>
      <Figure truth={truth} value={String(bucket.wrong)}>
        {String(bucket.wrong)}
      </Figure>
      <span className="text-text-tertiary"> / </span>
      <Figure truth={truth} value={String(bucket.blank)}>
        {String(bucket.blank)}
      </Figure>
      <span className="text-text-tertiary"> / </span>
      <Figure truth={truth} value={String(bucket.said_not_known)}>
        {String(bucket.said_not_known)}
      </Figure>
    </td>
  );
}

export default function ContentUnderstandingSection({ scorecard }: { scorecard: CuScorecard }) {
  const truth = cuScorecardTruth(scorecard);
  const measuredTruth: MeasuredTruth | null = truth.kind === "last_run" ? truth : null;
  const day = pacificDayLabel(scorecard.asOf);
  const codeFields = scorecard.fields.filter(
    (f) => f.decided_by === "code" || f.decided_by === "code_and_model"
  );
  const modelFields = scorecard.fields.filter(
    (f) => f.decided_by === "model" || f.decided_by === "code_and_model"
  );

  return (
    <EvalsSection
      id="market-understanding"
      title={COPY.title}
      lead={COPY.lead}
      detail={COPY.detail}
      truth={truth}
    >
      <div className="space-y-4">
        {scorecard.repeatability && <RepeatabilityCard repeatability={scorecard.repeatability} />}
        {!measuredTruth ? (
        <div className="space-y-4">
          <div
            data-testid="evals-cu-unmeasured"
            className="rounded-lg border border-surface-border bg-surface-elevated p-4 space-y-2"
          >
            <p className="text-body font-medium text-text-primary">
              {COPY.notMeasuredYet}{" "}
              <time dateTime={scorecard.asOf}>{day ?? scorecard.asOf}</time>.
            </p>
            <p className="text-caption text-text-secondary">{COPY.notMeasuredDetail}</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-surface-border bg-surface-card p-3 space-y-1.5">
              <h3 className="text-caption-strong text-text-primary">{COPY.rulesHeading}</h3>
              <ul className="space-y-1 text-caption text-text-secondary" data-cu-group="code">
                {codeFields.map((f) => (
                  <li key={f.field} data-cu-planned-field={f.field}>
                    {f.label}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-lg border border-surface-border bg-surface-card p-3 space-y-1.5">
              <h3 className="text-caption-strong text-text-primary">{COPY.aiHeading}</h3>
              <ul className="space-y-1 text-caption text-text-secondary" data-cu-group="model">
                {modelFields.map((f) => (
                  <li key={f.field} data-cu-planned-field={f.field}>
                    {f.label}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <p className="text-caption text-text-secondary">{COPY.slicesSummary}</p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-x-6 gap-y-2 rounded-lg border border-surface-border bg-surface-elevated p-3 text-caption text-text-secondary">
            <span>
              {COPY.recordedOn}{" "}
              <time dateTime={scorecard.asOf}>{day ?? scorecard.asOf}</time>
            </span>
            <span>
              {COPY.marketsScored}{" "}
              <Figure truth={measuredTruth} value={String(scorecard.marketCount)} className="text-text-primary">
                {scorecard.marketCount.toLocaleString("en-US")}
              </Figure>
            </span>
            {scorecard.writerRev !== null && (
              <span>
                {COPY.revisionLabel}{" "}
                <Figure truth={measuredTruth} value={String(scorecard.writerRev)} className="text-text-primary">
                  {String(scorecard.writerRev)}
                </Figure>
              </span>
            )}
            {scorecard.cost.totalUsd !== null && (
              <span>
                {COPY.costLabel}{" "}
                <Figure
                  truth={measuredTruth}
                  value={formatCuCostUsd(scorecard.cost.totalUsd)}
                  className="text-text-primary"
                >
                  {formatCuCostUsd(scorecard.cost.totalUsd)}
                </Figure>
              </span>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left" data-testid="evals-cu-table">
              <thead>
                <tr className="border-b border-surface-border text-micro text-text-secondary">
                  <th className="py-2 pr-3 font-medium">{COPY.fieldCol}</th>
                  <th className="px-2 py-2 font-medium">
                    {COPY.rulesCol} ({COPY.countsLegend})
                  </th>
                  <th className="px-2 py-2 font-medium">
                    {COPY.aiCol} ({COPY.countsLegend})
                  </th>
                </tr>
              </thead>
              <tbody>
                {scorecard.fields.map((row) => (
                  <tr key={row.field} data-cu-row={row.field}>
                    <th scope="row" className="border-b border-surface-border py-1.5 pr-3 text-caption font-normal text-text-primary">
                      {row.label}
                    </th>
                    <BucketCell bucket={row.code} truth={measuredTruth} field={row.field} decider="code" />
                    <BucketCell bucket={row.model} truth={measuredTruth} field={row.field} decider="model" />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid gap-3 sm:grid-cols-2" data-testid="evals-cu-slices">
            {CU_SLICE_ORDER.map((sliceKey) => {
              const groups = Object.entries(scorecard.slices[sliceKey] ?? {});
              if (groups.length === 0) return null;
              return (
                <div
                  key={sliceKey}
                  data-cu-slice={sliceKey}
                  className="rounded-lg border border-surface-border bg-surface-card p-3 space-y-1.5"
                >
                  <h3 className="text-caption-strong text-text-primary">{CU_SLICE_WORDS[sliceKey]}</h3>
                  <ul className="space-y-1 text-micro text-text-secondary">
                    {groups.map(([groupKey, group]) => (
                      <li key={groupKey} className="flex items-baseline justify-between gap-2">
                        <span>{plainCuSliceGroupLabel(groupKey)}</span>
                        <span className="whitespace-nowrap">
                          <Figure truth={measuredTruth} value={String(group.market_count)} className="text-text-primary">
                            {group.market_count.toLocaleString("en-US")}
                          </Figure>{" "}
                          {COPY.sliceMarkets}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      )}
      </div>
    </EvalsSection>
  );
}
