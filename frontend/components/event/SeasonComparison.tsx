import type { AdvancementStage } from "./AdvancementPath";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { risingIsGood } from "@/lib/gridColumnPolarity";

function StageValue({ stage }: { stage?: AdvancementStage }) {
  if (!stage || (stage.prob == null && !stage.resolved)) return <span />;
  return (
    <div className="min-w-0 text-right">
      <strong className="text-sm font-mono tabular-nums">
        {stage.resolved ? "✓ clinched" : formatProbabilityPercent(stage.prob!)}
      </strong>
      {stage.prob != null && !stage.resolved && (
        <div
          aria-hidden="true"
          className="mt-1 h-1 rounded-full bg-surface-elevated overflow-hidden"
        >
          <div
            className="h-full bg-accent-futures"
            style={{ width: `${stage.prob * 100}%` }}
          />
        </div>
      )}
      {stage.change != null && Math.abs(stage.change) >= 0.005 && (
        <span
          className={`text-xs font-mono ${stage.change > 0 === risingIsGood(stage.columnKey) ? "text-accent-brand" : "text-accent-danger"}`}
        >
          {stage.change > 0 ? "↑" : "↓"}{" "}
          {(Math.abs(stage.change) * 100).toFixed(1)}%
        </span>
      )}
    </div>
  );
}

export default function SeasonComparison({
  home,
  away,
  homeName,
  awayName,
}: {
  home: AdvancementStage[];
  away: AdvancementStage[];
  homeName: string;
  awayName: string;
}) {
  const key = (stage: AdvancementStage) => stage.columnKey || stage.label;
  const keys = Array.from(new Set([...home, ...away].map(key)));
  if (!keys.length) return null;
  return (
    <div
      className="rounded-xl border border-surface-border bg-surface-card p-4 mb-4"
      data-testid="season-comparison"
    >
      <div className="grid grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3 pb-3 text-xs font-semibold">
        <span className="text-text-secondary">Season outcomes</span>
        <span className="text-right">{homeName}</span>
        <span className="text-right">{awayName}</span>
      </div>
      {keys.map((id) => {
        const h = home.find((stage) => key(stage) === id);
        const a = away.find((stage) => key(stage) === id);
        return (
          <div
            key={id}
            className="grid grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)] items-center gap-3 py-3 border-t border-surface-border"
          >
            <span className="text-sm text-text-secondary">
              {h?.label ?? a?.label}
            </span>
            <StageValue stage={h} />
            <StageValue stage={a} />
          </div>
        );
      })}
    </div>
  );
}
