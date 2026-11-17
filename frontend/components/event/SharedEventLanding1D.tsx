"use client";

import React from "react";
import Link from "next/link";
import useSWR from "swr";
import EventCard183A, { buildUnifiedCardFromFeed } from "@/components/EventCard183A";
import { PinIcon, pinTitle } from "@/components/PinButton";
import { fetchFeed } from "@/lib/api";
import { formatProbabilityPercent, movementPoints } from "@/lib/probabilityDisplay";
import type { FeedEventData, FeedFuturesData, FeedItem } from "@/lib/types";

/**
 * Ruling 212-A (`#11934` Step 1D) — Web landing additions when a reader arrives
 * from a shared game link (`/events/[id]?utm_source=share` or `?shared=1`).
 *
 * Applies Fable's Ruling 212-A rules + 4:09 PM PT look updates:
 * 1. Every game on the screen uses the shipped components (`EventPageHeadline199`
 *    above, `OddsChart` for the chart, and `EventCard183A` for any game teaser
 *    in "More of what the world thinks now").
 * 2. Charts follow Ruling 201 (the page's shipped `OddsChart`, never a custom
 *    0–100 mini-chart).
 * 3. No clutter line under the arrival chart (no `"pregame (61%) Projected: ..."`).
 * 4. Plain words: `"points"`, never `"pts"`, and never raw `"Will ..."` question
 *    titles or `"from pregame"` before kickoff.
 * 5. Apple's standard Smart App Banner (`apple-itunes-app` meta tag site-wide)
 *    replaces any custom `"Get the app"` button, and `SharedLinkPinBanner` stays
 *    off behind `NEXT_PUBLIC_SHARED_LINK_PIN_ALERTS=1` until web-pin alerts and
 *    1.0.8 app handoff exist end to end.
 */

export function isSharedLinkPinBannerEnabled(
  envFlag: string | undefined = process.env.NEXT_PUBLIC_SHARED_LINK_PIN_ALERTS,
): boolean {
  return envFlag === "1";
}

export function normalizeSharedTeaserCopy(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const cleaned = raw
    .replace(/\b([+-]?\d+(?:\.\d+)?)\s*pts\b/gi, "$1 points")
    .replace(/\bpts\b/gi, "points")
    .trim();
  if (!cleaned) return null;
  if (/^will\s+/i.test(cleaned)) return null;
  return cleaned;
}

function cleanFuturesTitle(name: string): string {
  const trimmed = name.trim();
  if (!/^will\s+/i.test(trimmed)) return trimmed;
  return trimmed
    .replace(/^will\s+(?:the\s+)?/i, "")
    .replace(/\?+$/, "")
    .trim();
}

function futuresCategoryLabel(data: FeedFuturesData): string {
  const cat = (data.llm_sport_category || data.sport_name || data.sport || "").trim();
  if (!cat) return "Market";
  const lower = cat.toLowerCase();
  if (lower.includes("econom") || lower.includes("fed") || lower.includes("finance")) return "Economy";
  if (lower.includes("entertain") || lower.includes("oscar") || lower.includes("award") || lower.includes("culture")) {
    return "Entertainment";
  }
  if (lower.includes("politic") || lower.includes("election")) return "Politics";
  if (lower.includes("tech") || /\bai\b/.test(lower)) return "Tech";
  if (lower.includes("weather") || lower.includes("climate")) return "Weather";
  return cat.replace(/_/g, " ");
}

function SharedFuturesTeaserCard({ item }: { item: FeedItem }) {
  const data = item.data as FeedFuturesData;
  const outcomes = Array.isArray(data.top_outcomes) ? data.top_outcomes : [];
  const leader = outcomes[0] ?? null;
  if (!leader || leader.probability == null) return null;

  const pctLabel =
    typeof leader.rendered_percent === "number"
      ? `${leader.rendered_percent}%`
      : formatProbabilityPercent(leader.probability);
  if (!pctLabel) return null;

  const isBinaryYesNo =
    outcomes.length <= 2 &&
    /^(yes|no)$/i.test(leader.name.trim());
  const title = cleanFuturesTitle(data.name);
  const subtitle = !isBinaryYesNo
    ? leader.name
    : normalizeSharedTeaserCopy(item.context_summary || item.headline || item.reason);

  let moveChip: string | null = null;
  let movePositive = true;
  const movePts = movementPoints(leader.movement);
  if (movePts !== null) {
    const pts = Math.round(Math.abs(movePts));
    if (pts >= 2) {
      movePositive = movePts > 0;
      moveChip = `${movePositive ? "up" : "down"} ${pts} points`;
    }
  }

  return (
    <Link
      href={`/futures/${data.id}`}
      className="block rounded-xl border border-surface-border bg-surface-card px-3.5 py-3 shadow-card transition-colors hover:border-text-muted/30"
      data-testid="shared-landing-futures-teaser"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            <span>{futuresCategoryLabel(data)}</span>
            {moveChip && (
              <span
                className={`normal-case font-semibold ${
                  movePositive ? "text-accent-green" : "text-accent-danger"
                }`}
              >
                · {moveChip}
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-[14px] font-semibold text-text-primary">
            {title}
          </p>
          {subtitle && (
            <p className="mt-0.5 truncate text-[12px] text-text-secondary">
              {subtitle}
            </p>
          )}
        </div>
        <div className="shrink-0 text-right tabular-nums">
          <div className="text-[19px] font-bold leading-none text-text-primary">
            {pctLabel}
          </div>
          <div className="mt-1 text-[11px] text-text-muted">
            {isBinaryYesNo ? "chance" : "to win"}
          </div>
        </div>
      </div>
    </Link>
  );
}

export interface SharedMoreFromDiscoverProps {
  currentEventId: number;
  /** Optional injected items for deterministic server/static rendering tests. */
  seedItems?: FeedItem[];
}

export function SharedMoreFromDiscoverSection({
  currentEventId,
  seedItems,
}: SharedMoreFromDiscoverProps) {
  const { data } = useSWR(
    seedItems ? null : ["shared-landing-discover-teasers", currentEventId],
    () =>
      fetchFeed(
        { limit: 10 },
        { sharedAnonEligible: true, authenticated: false, hasInMemoryInteraction: false },
      ),
    { revalidateOnFocus: false, dedupingInterval: 120_000 },
  );

  const rawItems = seedItems ?? data?.items ?? [];
  const selected: FeedItem[] = [];
  for (const item of rawItems) {
    if (selected.length >= 4) break;
    if (item.type === "event") {
      const ev = item.data as FeedEventData;
      if (!ev || ev.id === currentEventId) continue;
      selected.push(item);
    } else if (item.type === "futures") {
      const fut = item.data as FeedFuturesData;
      if (!fut || !Array.isArray(fut.top_outcomes) || fut.top_outcomes.length === 0) continue;
      selected.push(item);
    }
  }

  return (
    <section
      aria-label="More of what the world thinks now"
      className="space-y-2.5"
      data-testid="shared-landing-more-discover"
    >
      <div className="flex items-center justify-between px-0.5">
        <h2 className="text-[14px] font-bold text-text-primary">
          More of what the world thinks now
        </h2>
        <Link
          href="/discover"
          className="text-[13px] font-semibold text-accent-brand hover:opacity-80 transition-opacity"
        >
          Discover &rarr;
        </Link>
      </div>

      {selected.length > 0 && (
        <div className="space-y-2.5">
          {selected.map((item) => {
            if (item.type === "event") {
              const ev = item.data as FeedEventData;
              const unified = buildUnifiedCardFromFeed(item, ev);
              return (
                <div key={`ev-${ev.id}`} data-testid="shared-landing-event-teaser">
                  <EventCard183A card={unified} surface="standard" />
                </div>
              );
            }
            const fut = item.data as FeedFuturesData;
            return <SharedFuturesTeaserCard key={`fut-${fut.id}`} item={item} />;
          })}
        </div>
      )}

      <Link
        href="/discover"
        className="flex items-center justify-between rounded-xl border border-surface-border bg-surface-card px-3.5 py-2.5 text-[13px] font-semibold text-text-primary shadow-card transition-colors hover:border-text-muted/30"
        data-testid="shared-landing-discover-footer"
      >
        <span>See sports, awards, tech &amp; economy</span>
        <span className="text-accent-brand">Discover &rarr;</span>
      </Link>
    </section>
  );
}

export interface SharedLinkPinBannerProps {
  isPinned: boolean;
  pinDisabled: boolean;
  onPinToggle: () => void;
  /** When true (consent banner open), renders inline rather than stacking two fixed bottom bars. */
  inline?: boolean;
  /** Feature switch override (defaults to `NEXT_PUBLIC_SHARED_LINK_PIN_ALERTS === "1"`, off in 1.0.7). */
  enabled?: boolean;
}

export function SharedLinkPinBanner({
  isPinned,
  pinDisabled,
  onPinToggle,
  inline = false,
  enabled = isSharedLinkPinBannerEnabled(),
}: SharedLinkPinBannerProps) {
  if (!enabled) {
    return null;
  }

  return (
    <div
      className={
        inline
          ? "w-full"
          : "fixed inset-x-0 bottom-[62px] md:bottom-0 z-40 pointer-events-none px-3 pb-2.5 pt-1"
      }
      data-testid="shared-link-pin-banner"
    >
      <div className="pointer-events-auto mx-auto flex max-w-xl items-center justify-between gap-2 rounded-2xl bg-text-primary px-3.5 py-2.5 text-surface-card shadow-lg">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[12.5px] font-bold leading-snug text-surface-card">
            {isPinned ? "Pinned on this browser" : "Pin for swing alerts"}
          </p>
          <p className="truncate text-[11px] leading-snug text-surface-card/75">
            {isPinned
              ? "Carries into the Bain Luck app"
              : "Pick up your pin in the app"}
          </p>
        </div>

        <button
          type="button"
          disabled={pinDisabled}
          onClick={onPinToggle}
          title={pinTitle(isPinned, pinDisabled)}
          aria-label={isPinned ? "Unpin game" : "Pin game"}
          aria-pressed={isPinned}
          data-testid="shared-link-pin-button"
          className="inline-flex shrink-0 items-center gap-1 rounded-xl border border-surface-card/20 bg-surface-card/10 px-3 py-1.5 text-[12px] font-semibold text-surface-card transition-colors hover:bg-surface-card/20 disabled:opacity-40"
        >
          <PinIcon filled={isPinned} className="h-3.5 w-3.5" />
          <span>{isPinned ? "Pinned" : "Pin"}</span>
        </button>
      </div>
    </div>
  );
}
