"use client";

/**
 * #12577 — Production Award Category Paired-Metric Card (`Nominated %` + `Wins %`, with posters).
 *
 * Implements Alex's `amazing`-graded Shorter Card 1A (`paired_bars_top5_expandable`):
 * - Poster or portrait per contender from TMDB enrichment, behind the kid-safe gate (#7461).
 * - Two separate horizontal bars per contender (`Nominated %` neutral grey bar + `Wins %`
 *   emerald bar, sorted by `Wins %`, ties broken by `Nominated %`) — never combining
 *   distinct propositions (Ruling 196-A).
 * - Post-nominations transition ("settled means settled"): once `stage_1_settled` is true,
 *   the first bar becomes `✓ Nominated` or `✗ Not nominated`.
 * - Top 5 contenders shown by default on Discover & Collection surfaces with a full-width
 *   in-place `"Show all N most likely nominees (+M more)"` expander (`defaultExpanded` on
 *   the category's own `/futures/[id]` page).
 * - Traceable one-tap source links to both the Winner market and the Nominees market, plus
 *   official TMDB attribution (`/tmdb-blue-short.svg`).
 */

import Link from "next/link";
import React, { useState } from "react";
import { QuietFillPercentBox } from "@/components/discover/QuietFillPercentBox";
import {
  TMDB_ATTRIBUTION_LINE,
  TMDB_ATTRIBUTION_URL,
  TMDB_OFFICIAL_LOGO_PATH,
  formatStage1Display,
  formatStage2Display,
  resolveKidSafeVisualArt,
  sortPairedEntries,
  type PairedMetricSet,
  type PairedSubjectEntry,
} from "@/lib/discover/visualForms";

export function cleanPairedCardSubtitle(subtitle: string | null | undefined): string {
  return String(subtitle ?? "")
    .replace(/\s*·\s*Nominee\s*%.*$/i, "")
    .replace(/\s*·\s*Paired by club.*$/i, "")
    .replace(/\s*·\s*Verified [A-Za-z0-9\s]+$/i, "")
    .replace(/\s*\(ordered by [^)]*\)/gi, "")
    .replace(/\s*\([^)]*#\d+[^)]*\)/g, "")
    .trim();
}

function PairedArtThumb({
  entry,
  kidSurface = false,
  reservesSlotWidthWhenMissing = false,
  fallbackArtKind = "tmdb_poster",
}: {
  entry: PairedSubjectEntry;
  kidSurface?: boolean;
  reservesSlotWidthWhenMissing?: boolean;
  fallbackArtKind?: string;
}) {
  const safeUrl = resolveKidSafeVisualArt(entry, { kidSurface });
  const kind = entry.art?.kind ?? fallbackArtKind;

  if (!safeUrl) {
    if (!reservesSlotWidthWhenMissing) return null;
    const widthClass =
      kind === "espn_team_logo"
        ? "w-9"
        : kind === "tmdb_headshot"
          ? "w-11"
          : "w-10";
    return (
      <span
        aria-hidden="true"
        data-testid="award-paired-art-spacer"
        className={`inline-block h-1 ${widthClass} shrink-0`}
      />
    );
  }

  if (kind === "espn_team_logo") {
    return (
      <img
        src={safeUrl}
        alt={entry.subject}
        data-testid="award-paired-art-logo"
        className="h-9 w-9 shrink-0 rounded-full border border-surface-border bg-surface-elevated object-contain p-0.5"
      />
    );
  }

  if (kind === "tmdb_headshot") {
    return (
      <img
        src={safeUrl}
        alt={entry.subject}
        data-testid="award-paired-art-headshot"
        className="h-11 w-11 shrink-0 rounded-full border border-surface-border bg-surface-elevated object-cover"
      />
    );
  }

  return (
    <img
      src={safeUrl}
      alt={entry.subject}
      data-testid="award-paired-art-poster"
      className="h-14 w-10 shrink-0 rounded-md border border-surface-border bg-surface-elevated object-cover"
    />
  );
}

function PairedDualBarRow({
  entry,
  set,
  idx,
  kidSurface,
  reservesArtSlotWidth,
  fallbackArtKind,
}: {
  entry: PairedSubjectEntry;
  set: PairedMetricSet;
  idx: number;
  kidSurface: boolean;
  reservesArtSlotWidth: boolean;
  fallbackArtKind: string;
}) {
  const s1 = formatStage1Display(entry, set);
  const s2 = formatStage2Display(entry, set);

  return (
    <div
      data-testid={`award-paired-row-${idx + 1}`}
      className="flex items-center gap-3 py-2.5"
    >
      <PairedArtThumb
        entry={entry}
        kidSurface={kidSurface}
        reservesSlotWidthWhenMissing={reservesArtSlotWidth}
        fallbackArtKind={fallbackArtKind}
      />
      <div className="min-w-0 flex-1">
        <div className="min-w-0">
          <span className="block truncate text-sm font-semibold text-text-primary">
            {entry.subject}
          </span>
          {entry.detail && (
            <span className="block truncate text-xs text-text-muted">
              {entry.detail}
            </span>
          )}
        </div>

        <div className="mt-1.5 space-y-1.5">
          {/* Stage 1: Nominated % (neutral grey bar, or ✓ / ✗ once settled) */}
          <div className="flex items-center gap-2">
            <span className="w-[4.5rem] shrink-0 text-xs text-text-secondary">
              {set.stage_1_label}
            </span>
            {s1.kind === "percent" && s1.percent !== null ? (
              <>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-elevated">
                  <div
                    className="h-full rounded-full bg-text-muted"
                    style={{ width: `${Math.max(4, s1.percent)}%` }}
                  />
                </div>
                <QuietFillPercentBox
                  percent={s1.percent}
                  tone="slate"
                  widthClass="w-12"
                  alignClass="justify-end"
                >
                  <span className="text-xs font-semibold tabular-nums text-text-primary">
                    {s1.label}
                  </span>
                </QuietFillPercentBox>
              </>
            ) : s1.kind === "tick" ? (
              <div className="flex flex-1 items-center">
                <span
                  data-testid="settled-stage-1-tick"
                  className="inline-flex items-center rounded bg-surface-elevated px-2 py-0.5 text-xs font-semibold text-accent-positive"
                >
                  {s1.label}
                </span>
              </div>
            ) : s1.kind === "cross" ? (
              <div className="flex flex-1 items-center gap-2">
                <span
                  data-testid="settled-stage-1-cross"
                  className="inline-flex items-center rounded bg-surface-elevated px-2 py-0.5 text-xs font-medium text-text-muted line-through"
                >
                  {s1.label}
                </span>
                {s1.sublabel && (
                  <span className="text-xs text-text-muted">{s1.sublabel}</span>
                )}
              </div>
            ) : (
              <span
                data-testid="missing-probability-notice"
                className="rounded border border-surface-border bg-surface-elevated px-2 py-0.5 text-xs font-medium text-text-muted"
              >
                {s1.label}
              </span>
            )}
          </div>

          {/* Stage 2: Wins % (emerald bar) */}
          <div className="flex items-center gap-2">
            <span className="w-[4.5rem] shrink-0 text-xs font-medium text-text-primary">
              {set.stage_2_label}
            </span>
            {s2.kind === "percent" && s2.percent !== null ? (
              <>
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-elevated">
                  <div
                    className="h-full rounded-full bg-accent-brand"
                    style={{ width: `${Math.max(4, s2.percent)}%` }}
                  />
                </div>
                <QuietFillPercentBox
                  percent={s2.percent}
                  tone="emerald"
                  widthClass="w-12"
                  alignClass="justify-end"
                >
                  <span className="text-sm font-bold tabular-nums text-text-primary">
                    {s2.label}
                  </span>
                </QuietFillPercentBox>
              </>
            ) : s2.kind === "cross" ? (
              <span className="text-xs font-medium text-text-muted">
                {s2.label}
              </span>
            ) : (
              <span
                data-testid="missing-probability-notice"
                className="rounded border border-surface-border bg-surface-elevated px-2 py-0.5 text-xs font-medium text-text-muted"
              >
                {s2.label}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export interface AwardCategoryPairedCardProps {
  set: PairedMetricSet;
  surface?: "discover" | "collection" | "category";
  defaultExpanded?: boolean;
  initialLimit?: number;
  kidSurface?: boolean;
  currentMarketId?: number | null;
  showHeader?: boolean;
}

export function AwardCategoryPairedCard({
  set,
  surface = "discover",
  defaultExpanded = false,
  initialLimit = 5,
  kidSurface = false,
  currentMarketId = null,
  showHeader,
}: AwardCategoryPairedCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const sorted = sortPairedEntries(set.entries);
  const visibleRows = expanded ? sorted : sorted.slice(0, initialLimit);
  const hiddenCount = Math.max(0, sorted.length - initialLimit);
  const subtitle = cleanPairedCardSubtitle(set.subtitle);
  const suppressedByPayload = Boolean(
    (set as PairedMetricSet & { suppress_card_header_in_section?: boolean })
      .suppress_card_header_in_section,
  );
  const effectiveShowHeader = showHeader ?? !suppressedByPayload;
  const listHasAnyArt = visibleRows.some((e) =>
    Boolean(resolveKidSafeVisualArt(e, { kidSurface })),
  );
  const listArtKind =
    visibleRows.find((e) => Boolean(resolveKidSafeVisualArt(e, { kidSurface })))?.art
      ?.kind ?? "tmdb_poster";

  const stage1Id = set.stage_1_market?.id ?? null;
  const stage2Id = set.stage_2_market?.id ?? null;
  const primaryHref = stage2Id ? `/futures/${stage2Id}` : "/collections/oscars-2027";
  const isOscars = set.set_id.startsWith("oscars-");
  const usesTmdb = set.entries.some(
    (e) => e.art?.kind === "tmdb_poster" || e.art?.kind === "tmdb_headshot",
  );

  return (
    <article
      data-testid={`award-category-paired-card-${set.set_id}`}
      data-paired-surface={surface}
      className="rounded-2xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      {effectiveShowHeader && (
        <>
          <div className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            {set.kicker}
          </div>

          {surface === "category" ? (
            <h2 className="mt-1 text-lg font-semibold leading-snug text-text-primary">
              {set.title}
            </h2>
          ) : (
            <h3 className="mt-1 text-lg font-semibold leading-snug text-text-primary">
              <Link href={primaryHref} className="hover:underline">
                {set.title}
              </Link>
            </h3>
          )}

          {subtitle && (
            <p className="mt-0.5 text-xs text-text-secondary">{subtitle}</p>
          )}
        </>
      )}

      {/* Legend */}
      <div
        className={`${
          effectiveShowHeader ? "mt-2.5" : "mt-0"
        } flex flex-wrap items-center gap-4 border-b border-surface-border pb-2 text-xs text-text-secondary`}
      >
        <span className="inline-flex items-center gap-1.5">
          <span
            data-testid="legend-swatch-stage-1"
            className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm bg-text-muted"
          />
          <span className="font-medium text-text-primary">
            {set.stage_1_settled
              ? `${set.stage_1_label} (✓ / ✗ settled)`
              : `${set.stage_1_label} %`}
          </span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            data-testid="legend-swatch-stage-2"
            className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm bg-accent-brand"
          />
          <span className="font-medium text-text-primary">
            {set.stage_2_label} %
          </span>
        </span>
      </div>

      <div className="mt-1 divide-y divide-surface-border">
        {visibleRows.map((entry, idx) => (
          <PairedDualBarRow
            key={entry.subject_key}
            entry={entry}
            set={set}
            idx={idx}
            kidSurface={kidSurface}
            reservesArtSlotWidth={listHasAnyArt}
            fallbackArtKind={listArtKind}
          />
        ))}
      </div>

      {hiddenCount > 0 && (
        <div className="mt-2.5">
          <button
            type="button"
            data-testid="toggle-expand-all-rows"
            onClick={() => setExpanded((prev) => !prev)}
            className="flex w-full items-center justify-between rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-left text-xs font-semibold text-text-primary hover:bg-surface-hover"
          >
            <span>
              {expanded
                ? `Show top ${initialLimit} by ${set.stage_2_label} %`
                : `Show all ${sorted.length} contenders (+${hiddenCount} more)`}
            </span>
            <span aria-hidden="true" className="text-text-muted">
              {expanded ? "▴" : "▾"}
            </span>
          </button>
        </div>
      )}

      {/* Traceable source market links + TMDB attribution */}
      <div className="mt-3 space-y-2 border-t border-surface-border pt-2.5 text-xs text-text-muted">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>Several contenders are nominated; one wins.</span>
          <div className="flex flex-wrap items-center gap-3 font-semibold text-accent-brand">
            {stage2Id && currentMarketId !== stage2Id && (
              <Link
                href={`/futures/${stage2Id}`}
                data-testid="paired-card-winner-market-link"
                className="hover:underline"
              >
                {set.stage_2_label} market ›
              </Link>
            )}
            {stage1Id && currentMarketId !== stage1Id && (
              <Link
                href={`/futures/${stage1Id}`}
                data-testid="paired-card-nominee-market-link"
                className="hover:underline"
              >
                {set.stage_1_label} market ›
              </Link>
            )}
            {isOscars && surface !== "collection" && (
              <Link
                href="/collections/oscars-2027"
                data-testid="paired-card-oscars-collection-link"
                className="hover:underline"
              >
                All Oscars categories ›
              </Link>
            )}
          </div>
        </div>

        {usesTmdb && (
          <div
            data-testid="tmdb-attribution-line"
            className="flex flex-wrap items-center gap-2 text-[11px] text-text-muted"
          >
            <a
              href={TMDB_ATTRIBUTION_URL}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="tmdb-attribution-link"
              aria-label="The Movie Database (TMDB)"
              className="inline-flex shrink-0 items-center rounded border border-surface-border bg-surface-elevated px-1.5 py-0.5"
            >
              <img
                src={TMDB_OFFICIAL_LOGO_PATH}
                alt="The Movie Database (TMDB)"
                width={76}
                height={10}
                data-testid="tmdb-official-logo"
                className="inline-block h-[10px] w-auto shrink-0"
              />
            </a>
            <span>{TMDB_ATTRIBUTION_LINE}</span>
          </div>
        )}
      </div>
    </article>
  );
}
export default AwardCategoryPairedCard;
