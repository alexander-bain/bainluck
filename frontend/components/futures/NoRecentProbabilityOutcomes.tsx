import React from "react";

interface Props {
  outcomes: readonly {
    key: string | number;
    name: string;
    history?: { selected: boolean; toggle: () => void };
  }[];
  testId: string;
  className?: string;
  resolved?: boolean;
}

export function NoRecentProbabilityOutcomes({ outcomes, testId, className, resolved = false }: Props) {
  if (outcomes.length === 0) return null;
  const summary = resolved
    ? `More outcomes (${outcomes.length})`
    : `${outcomes.length} others: no recent probability`;
  return (
    <details data-testid={testId} className={className}>
      <summary className="cursor-pointer select-none py-3 text-sm font-medium text-text-secondary">
        {summary}
      </summary>
      <ul className="mt-1 space-y-2 text-sm text-text-primary">
        {outcomes.map(({ key, name, history }) => (
          <li key={key}>
            {history ? (
              <button
                type="button"
                data-testid="futures-folded-outcome-history"
                data-outcome-name={name}
                aria-label={`Show history for ${name}`}
                aria-pressed={history.selected}
                onClick={history.toggle}
                className="text-left underline decoration-surface-border underline-offset-4 hover:decoration-text-primary"
              >
                {name}
              </button>
            ) : name}
          </li>
        ))}
      </ul>
    </details>
  );
}
