"use client";

import Link from "next/link";
import FeedCard from "@/components/FeedCard";
import ErrorBoundary from "@/components/ErrorBoundary";
import { outcomeRowVerdict, type GradedRow } from "@/components/futures/OutcomeRow";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import type { FeedFuturesData, FeedFuturesOutcome } from "@/lib/types";
import type { CollectionMember } from "@/lib/collections";

export function CollectionMemberCard({ member }: { member: CollectionMember }) {
  const market = member.type === "market" ? member.item.data as FeedFuturesData : null;
  const outcomes = market?.top_outcomes as (FeedFuturesOutcome & GradedRow)[] | undefined;
  const resolved = !!market && ["resolved", "closed", "settled", "finalized", "final"].includes(market.status);
  const hasVerdict = outcomes?.some((outcome) => outcomeRowVerdict(outcome, resolved) !== null) ?? false;
  const missingPrices = !!market && (!outcomes?.length || outcomes.some((outcome) => outcome.probability == null));
  // The existing sports card owns game lifecycle and probabilities. A missing
  // price or served result uses the existing verdict/format rule, never nil -> 0%.
  const card = market && (resolved || hasVerdict || missingPrices) ? (
    <Link href={member.href} className="block rounded-card border border-surface-border bg-surface-card p-4 hover:bg-surface-elevated transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand">
      <h3 className="font-semibold text-text-primary mb-3">{market.name}</h3>
      <div className="space-y-2 text-sm">
        {outcomes?.map((outcome, index) => {
          const verdict = outcomeRowVerdict(outcome, resolved);
          const label = verdict === "won" ? "Won" : verdict === "lost" ? "Lost" : resolved ? "Result unavailable" : outcome.probability == null ? "Probability unavailable" : formatProbabilityPercent(outcome.probability);
          return <div key={`${outcome.id ?? index}:${outcome.name}`} className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 text-text-secondary">{outcome.name}</span>
            <span className={`shrink-0 font-semibold ${verdict === "won" ? "text-accent-brand" : "text-text-primary"}`}>{label}</span>
          </div>;
        })}
        {!outcomes?.length && <p className="text-text-secondary">{resolved ? "Result unavailable" : "Probabilities aren't available right now."}</p>}
      </div>
    </Link>
  ) : <FeedCard item={member.item} />;
  return <ErrorBoundary resetKey={member.item.data} fallback={<p role="status" className="rounded-card border border-surface-border bg-surface-card p-4 text-text-secondary">This game or question isn&apos;t available right now.</p>}>{card}</ErrorBoundary>;
}
