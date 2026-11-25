import React from "react";

interface Props {
  outcomes: readonly { key: string | number; name: string }[];
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
      <summary className="cursor-pointer select-none py-2 text-sm font-medium text-text-secondary">
        {summary}
      </summary>
      <ul className="mt-1 space-y-2 text-sm text-text-primary">
        {outcomes.map(({ key, name }) => <li key={key}>{name}</li>)}
      </ul>
    </details>
  );
}
