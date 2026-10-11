"use client";

import { useState } from "react";
import type { GameMarketsResponse } from "@/lib/api";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { buildQuestionCatalog, type CatalogGroup } from "@/lib/questionCatalog";
import { formatSourceStamp } from "@/lib/sourceAge";
import MarketBrowser from "./MarketBrowser";

/** Outcomes a group shows before the reader asks for the rest (Atlas v6). */
export const GROUP_PREVIEW = 6;

/**
 * #10809 / #10868 — one venue question with its outcomes. Whether it is opened
 * is held by the catalog, not the card: switching family unmounts the card, and
 * the reader's opened group must still be open when they come back.
 */
function QuestionGroupCard({
  group,
  expanded,
  onToggle,
}: {
  group: CatalogGroup;
  expanded: boolean;
  onToggle: () => void;
}) {
  const shown = expanded ? group.outcomes : group.outcomes.slice(0, GROUP_PREVIEW);
  const thresholds = Array.from(
    new Set(group.outcomes.flatMap((o) => (o.threshold == null ? [] : [o.threshold]))),
  );
  // Only a price the card prints has a "seen" time worth stating.
  const seen = group.outcomes
    .filter((o) => o.probability != null)
    .map((o) => o.observedAt)
    .filter((t): t is string => typeof t === "string")
    .sort()
    .pop();
  const seenStamp = formatSourceStamp(seen ?? null);
  return (
    <div className="py-3 border-b border-surface-border" data-question-group={group.key}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium min-w-0">{group.question}</span>
        {group.source && (
          <span className="text-xs text-text-secondary shrink-0">{group.source}</span>
        )}
      </div>
      <ul className="mt-1">
        {shown.map((outcome, index) => (
          <li key={`${outcome.label}-${index}`} className="flex justify-between gap-4 text-sm py-0.5">
            <span className="min-w-0">{outcome.label}</span>
            {outcome.probability != null && (
              <strong className="font-mono tabular-nums whitespace-nowrap">
                {formatProbabilityPercent(outcome.probability)}
              </strong>
            )}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-x-4">
        {group.outcomes.length > GROUP_PREVIEW && (
          <button
            type="button"
            aria-expanded={expanded}
            onClick={onToggle}
            className="min-h-11 text-sm font-semibold text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
          >
            {expanded ? "Show fewer outcomes" : `Show all ${group.outcomes.length} outcomes`}
          </button>
        )}
        <details className="text-xs text-text-secondary">
          <summary className="cursor-pointer min-h-11 flex items-center">About this question</summary>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 pb-2">
            <dt>Question</dt>
            <dd className="text-text-primary">{group.question}</dd>
            {group.source && (
              <>
                <dt>Venue</dt>
                <dd>{group.source}</dd>
              </>
            )}
            {group.period && (
              <>
                <dt>Period</dt>
                <dd>{group.period}</dd>
              </>
            )}
            {thresholds.length > 0 && (
              <>
                <dt>{thresholds.length === 1 ? "Line" : "Lines"}</dt>
                <dd>{thresholds.join(", ")}</dd>
              </>
            )}
            {seenStamp && (
              <>
                <dt>Price seen</dt>
                <dd>{seenStamp}</dd>
              </>
            )}
          </dl>
        </details>
      </div>
    </div>
  );
}

/**
 * Every question the game page serves, behind one fold. `<details>` keeps the
 * browser mounted while closed, so search, family, page and opened groups all
 * survive closing it and every live refresh; opened groups also survive a
 * family switch.
 */
export default function QuestionCatalog({
  data,
  status,
}: {
  data: GameMarketsResponse;
  status?: string;
}) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const groups = buildQuestionCatalog(data, status, Date.now());
  if (!groups.length) return null;
  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  return (
    <details className="rounded-xl border border-surface-border bg-surface-card p-4">
      <summary className="cursor-pointer min-h-11 text-sm font-semibold">
        All questions
      </summary>
      <MarketBrowser
        label="All questions"
        items={groups.map((group) => ({
          key: group.key,
          group: group.family,
          search: [
            group.question,
            group.source ?? "",
            ...group.outcomes.map((o) => o.label),
          ].join(" "),
          content: (
            <QuestionGroupCard
              group={group}
              expanded={expanded.has(group.key)}
              onToggle={() => toggle(group.key)}
            />
          ),
        }))}
      />
    </details>
  );
}
