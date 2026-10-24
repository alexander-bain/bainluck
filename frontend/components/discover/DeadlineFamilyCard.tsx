"use client";

import { useState } from "react";
import Link from "next/link";
import { trackEvent } from "@/lib/analytics";
import {
  getDiscoverItemAnalytics,
  recordDiscoverInteraction,
  sendDiscoverInteraction,
} from "@/lib/discoverInteractions";
import type { DeadlineFamilyCardModel } from "@/lib/discover/deadlineFamilyCard";
import type { FeedItem } from "@/lib/types";
import { BundleActionBar } from "./BundleActionBar";
import { BundleHeader } from "./BundleHeader";
import { MovementBadge } from "./shared";

export interface DeadlineFamilyCardProps {
  model: DeadlineFamilyCardModel;
  items?: FeedItem[];
  title?: string;
  sharedQuestion?: string | null;
  storyKey?: string | null;
  positionIndex?: number;
  defaultExpanded?: boolean;
}

/**
 * Movement-led cumulative deadline-family card — Slice 1 (#9878 / #11040).
 *
 * - Renders one card for a verified single-provider cumulative deadline family.
 * - Leads with the selected representative deadline (largest supported dated move
 *   >= 2 pts, or nearest 50% fallback with deterministic tie-break).
 * - Uses the 5-percentage-point local hero chip threshold (Q7) and reader-local
 *   calendar-date wording ("since yesterday" vs truthful same-day time, Q4).
 * - Expands in place (Q2) to inspect all represented deadlines in ascending
 *   deadline_instant order without losing context, preserving original questions,
 *   outcome-bound probabilities, and `/futures/{id}` links.
 */
export function DeadlineFamilyCard({
  model,
  items = [],
  positionIndex,
  defaultExpanded = false,
}: DeadlineFamilyCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const primary = items[0];
  const analytics = primary ? getDiscoverItemAnalytics(primary) : null;
  const category = analytics?.category ?? model.category ?? "politics";
  const rep = model.representative;

  const toggleExpanded = () => {
    const next = !expanded;
    setExpanded(next);
    if (next) {
      trackEvent("theme_bundle_expand", {
        ...(analytics ?? { category }),
        story_key: model.storyKey,
        member_count: model.representedCount,
        position: positionIndex,
        surface: "discover",
      });
      recordDiscoverInteraction(category, "group_expand");
      if (analytics) {
        sendDiscoverInteraction(analytics, "group_expand", positionIndex);
      }
    }
  };

  return (
    <article
      className="rounded-2xl border border-surface-border bg-surface-card shadow-lg overflow-hidden"
      aria-label={`${model.title} — ${rep.accessibleLabel}`}
      data-testid="deadline-family-card"
      data-story-key={model.storyKey}
      data-group-id={model.groupId}
      data-source={model.source}
      data-family-state={model.familyState}
      data-rule-template-hash={model.ruleTemplateHash}
      data-cutoff-timezone={model.cutoffTimezone}
      data-cutoff-local-time={model.cutoffLocalTime}
      data-selection-reason={model.selectionReason}
      data-representative-market-id={rep.marketId}
      data-representative-outcome-id={rep.yesOutcomeId}
      data-represented-count={model.representedCount}
      data-verified-family-count={model.verifiedFamilyCount ?? ""}
      data-provider-market-count={model.providerMarketCount ?? ""}
      data-inventory-complete={
        model.inventoryComplete == null ? "unknown" : String(model.inventoryComplete)
      }
    >
      <BundleHeader
        title={model.title}
        sharedQuestion={model.sharedQuestion}
        fallbackCount={`· ${model.representedCount} deadlines`}
        category={model.category}
        expanded={expanded}
        canExpand
        onToggle={toggleExpanded}
      />

      {/* Selected representative deadline hero (kept visible when expanded so context is never lost) */}
      <div
        className="px-4 py-3.5 border-t border-surface-border"
        data-testid="deadline-family-hero"
        data-market-id={rep.marketId}
        data-outcome-id={rep.yesOutcomeId}
      >
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-2 min-w-0">
            <span
              className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-surface-elevated text-text-primary border border-surface-border"
              data-testid="deadline-family-hero-deadline"
            >
              {rep.deadlineLabel}
            </span>
            <span
              className="text-[11px] font-medium text-text-muted truncate"
              data-testid="deadline-family-selection-badge"
            >
              {model.selectionBadgeText}
            </span>
          </div>
          <span className="text-[11px] font-semibold uppercase tracking-[0.04em] text-text-muted shrink-0">
            Yes outcome
          </span>
        </div>

        {model.familyState === "settled" || rep.isSettled ? (
          <div
            className="mb-2.5"
            data-testid="deadline-family-settled-hero"
            data-outcome-id={rep.yesOutcomeId}
          >
            <div className="text-lg font-bold text-text-primary">
              {rep.settledText ?? "Resolved"}
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-end gap-3 mb-2">
              <span
                className="font-mono font-bold text-4xl tracking-tight leading-none text-text-primary tabular-nums"
                data-testid="deadline-family-hero-probability"
                data-outcome-id={rep.yesOutcomeId}
                data-probability={rep.yesProbability ?? ""}
              >
                {rep.yesPercentText}
              </span>
              {rep.showHeroMovementChip && rep.heroMovementChipText && (
                <div
                  className="pb-0.5"
                  data-testid="deadline-family-hero-movement-block"
                >
                  <div
                    className={`font-mono font-bold text-[15px] whitespace-nowrap ${
                      rep.heroMovementUp
                        ? "text-accent-live"
                        : "text-accent-danger"
                    }`}
                    title={rep.heroMovementAriaLabel ?? undefined}
                    aria-label={rep.heroMovementAriaLabel ?? undefined}
                    data-testid="deadline-family-hero-movement"
                    data-outcome-id={rep.yesOutcomeId}
                    data-movement-points={rep.supportedMovePoints ?? ""}
                  >
                    {rep.heroMovementChipText}
                  </div>
                  {rep.heroTimeframeText && (
                    <div
                      className="text-[10px] font-semibold tracking-[0.02em] text-text-muted mt-0.5"
                      data-testid="deadline-family-hero-timeframe"
                    >
                      {rep.heroTimeframeText}
                    </div>
                  )}
                </div>
              )}
            </div>

            {rep.yesProbability != null && (
              <div
                className="flex h-[7px] gap-0.5 mb-3"
                role="img"
                aria-label={`Yes (${rep.deadlineLabel}): ${rep.yesPercentText}`}
                data-testid="deadline-family-hero-bar"
                data-outcome-id={rep.yesOutcomeId}
              >
                <div
                  className="rounded-full bg-accent-brand shadow-inner"
                  style={{ width: `${rep.barWidthPercent}%` }}
                  data-testid="deadline-family-hero-bar-fill"
                />
                <div className="rounded-full bg-text-muted/30 flex-1" />
              </div>
            )}
          </>
        )}

        <Link
          href={rep.detailHref}
          className="block group"
          data-testid="deadline-family-hero-link"
        >
          <h4
            className="text-[15px] font-semibold leading-snug text-text-primary group-hover:text-accent-brand transition-colors"
            data-testid="deadline-family-hero-question"
          >
            {rep.name}
          </h4>
        </Link>

        <div
          className="text-[13px] leading-relaxed text-text-secondary mt-1"
          data-testid="deadline-family-hero-caption"
          data-movement-status={rep.movementStatus}
        >
          {rep.narrativeCaption}
        </div>
      </div>

      {/* In-place expansion of all represented family deadlines in ascending deadline_instant order (Q2) */}
      {expanded && (
        <div
          className="divide-y divide-surface-border border-t border-surface-border bg-surface-elevated/30"
          data-testid="deadline-family-member-list"
        >
          {model.members.map((member) => (
            <Link
              key={member.marketId}
              href={member.detailHref}
              className="flex items-center justify-between gap-3 px-4 py-3 group hover:bg-surface-elevated/60 transition-colors"
              aria-label={member.accessibleLabel}
              data-testid="deadline-family-member-row"
              data-market-id={member.marketId}
              data-outcome-id={member.yesOutcomeId}
              data-deadline-instant={member.deadlineInstant}
              data-representative={member.isRepresentative ? "true" : "false"}
              data-settlement-state={member.settlementState}
              data-settled={member.isSettled ? "true" : "false"}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span
                    className="text-xs font-semibold text-text-secondary"
                    data-testid="deadline-family-member-deadline"
                  >
                    {member.deadlineLabel}
                  </span>
                  {member.isRepresentative && (
                    <span
                      className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-surface-elevated text-text-secondary border border-surface-border"
                      data-testid="deadline-family-member-selected-pill"
                    >
                      Selected
                    </span>
                  )}
                </div>
                <div
                  className="text-sm font-semibold text-text-primary break-words group-hover:text-accent-brand transition-colors"
                  data-testid="deadline-family-member-question"
                >
                  {member.name}
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {member.isSettled ? (
                  <span
                    className="text-xs font-semibold text-text-secondary"
                    data-testid="deadline-family-member-settled"
                  >
                    {member.settledText ?? "Resolved"}
                  </span>
                ) : member.isTradingClosed ? (
                  <span
                    className="text-xs font-semibold text-text-secondary"
                    data-testid="deadline-family-member-trading-closed"
                  >
                    Trading closed
                  </span>
                ) : member.isDeadlinePassed ? (
                  <span
                    className="text-xs font-semibold text-text-secondary"
                    data-testid="deadline-family-member-deadline-passed"
                  >
                    Deadline passed
                  </span>
                ) : (
                  <>
                    {member.showRowMovementBadge && (
                      <MovementBadge
                        m={member.rowMovementFraction}
                        prob={member.yesProbability}
                      />
                    )}
                    <span
                      className="font-mono tabular-nums text-base font-bold text-text-primary"
                      data-testid="deadline-family-member-percent"
                      data-outcome-id={member.yesOutcomeId}
                    >
                      {member.yesPercentText}
                    </span>
                  </>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={toggleExpanded}
        aria-expanded={expanded}
        className="w-full text-center py-2.5 text-xs font-medium text-accent-brand hover:text-accent-brand/80 border-t border-surface-border"
        data-testid="deadline-family-expand-toggle"
      >
        {expanded ? model.collapseLabel : model.expandLabel}
      </button>

      <BundleActionBar
        items={items}
        title={model.title}
        sharedQuestion={model.sharedQuestion}
        storyKey={model.storyKey}
        positionIndex={positionIndex}
      />
    </article>
  );
}
