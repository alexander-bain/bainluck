"use client";

/**
 * #12577 / #12523 — Visual Forms Look Sheet & Oscars Container Diversity Options.
 *
 * Renders the first entries of the Bain Luck Visual Form Library on live
 * paired-metric data (Best Picture 2027, NHL Playoff Berth → Stanley Cup,
 * and three Oscars 2027 multi-category container rhythms).
 *
 * Design-system compliance: light-mode tokens only (`bg-surface-*`, `text-text-*`,
 * `border-surface-border`, `text-accent-*`). Zero raw hexes, zero dark classes.
 */

import React, { useState } from "react";
import {
  OSCARS_CONTAINER_LOOK_SHEET_OPTIONS,
  PAIRED_METRIC_REGISTER,
  VISUAL_FORM_LOOK_SHEET_CARDS,
  formatStage1Display,
  formatStage2Display,
  resolveKidSafeVisualArt,
  type ContainerLookSheetSpec,
  type LookSheetCardSpec,
  type PairedMetricSet,
  type PairedSubjectEntry,
  type VisualFormContract,
} from "@/lib/discover/visualForms";
import {
  GROUPING_GRADES,
  GROUPING_GRADE_LABELS,
  type GroupingGrade,
} from "@/lib/ranking/groupingGradeSession";

interface ArtThumbProps {
  entry: PairedSubjectEntry;
  kidSurface?: boolean;
  size?: "sm" | "md" | "lg";
}

function ArtThumb({ entry, kidSurface = false, size = "md" }: ArtThumbProps) {
  const safeUrl = resolveKidSafeVisualArt(entry, { kidSurface });
  const kind = entry.art?.kind ?? "tmdb_poster";
  const initials = entry.subject
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0] || "")
    .join("")
    .toUpperCase();

  if (kind === "espn_team_logo") {
    const dim = size === "lg" ? "h-10 w-10" : size === "sm" ? "h-6 w-6" : "h-8 w-8";
    return safeUrl ? (
      <img
        src={safeUrl}
        alt={entry.subject}
        data-testid="visual-form-art-logo"
        className={`${dim} shrink-0 rounded-full border border-surface-border bg-surface-elevated object-contain p-0.5`}
      />
    ) : (
      <div
        data-testid="visual-form-art-fallback"
        className={`${dim} flex shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-xs font-bold text-text-secondary`}
      >
        {initials}
      </div>
    );
  }

  if (kind === "tmdb_headshot") {
    const dim = size === "lg" ? "h-12 w-12" : size === "sm" ? "h-8 w-8" : "h-10 w-10";
    return safeUrl ? (
      <img
        src={safeUrl}
        alt={entry.subject}
        data-testid="visual-form-art-headshot"
        className={`${dim} shrink-0 rounded-full border border-surface-border bg-surface-elevated object-cover`}
      />
    ) : (
      <div
        data-testid="visual-form-art-fallback"
        className={`${dim} flex shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-xs font-bold text-text-secondary`}
      >
        {initials}
      </div>
    );
  }

  // tmdb_poster (2:3 aspect ratio)
  const dim =
    size === "lg"
      ? "h-20 w-14"
      : size === "sm"
        ? "h-11 w-8"
        : "h-14 w-10";
  return safeUrl ? (
    <img
      src={safeUrl}
      alt={entry.subject}
      data-testid="visual-form-art-poster"
      className={`${dim} shrink-0 rounded-md border border-surface-border bg-surface-elevated object-cover`}
    />
  ) : (
    <div
      data-testid="visual-form-art-fallback"
      className={`${dim} flex shrink-0 items-center justify-center rounded-md border border-surface-border bg-surface-elevated text-xs font-bold text-text-secondary`}
    >
      {initials}
    </div>
  );
}

function FormContractHeader({ form }: { form: VisualFormContract }) {
  return (
    <div
      className="mb-2 rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-xs"
      data-testid={`form-contract-${form.form_id}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-1">
        <span className="font-semibold text-text-primary">
          Form: <code className="font-mono text-accent-brand">{form.form_id}</code> ({form.form_name})
        </span>
        <span className="rounded bg-surface-card px-2 py-0.5 font-medium text-text-secondary border border-surface-border">
          Parts: {form.parts_vocabulary.join(" · ")}
        </span>
      </div>
      <div className="mt-1 text-text-secondary">
        <span className="font-medium text-text-primary">Data shape:</span> &ldquo;{form.data_shape}&rdquo;
      </div>
    </div>
  );
}

// ============================================================================
// Form 1 & Form 5: Stacked Dual Bars with Art (`paired_bars_with_art`)
// ============================================================================

function PairedBarsWithArtCard({
  set,
  simulateSettled = false,
  kidSurface = false,
  maxRows = 10,
}: {
  set: PairedMetricSet;
  simulateSettled?: boolean;
  kidSurface?: boolean;
  maxRows?: number;
}) {
  const rows = set.entries.slice(0, maxRows);
  return (
    <article
      data-testid={`visual-form-card-paired-bars-${set.set_id}`}
      className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>{set.kicker}</span>
        <span>
          {set.stage_1_label} · {set.stage_2_label}
        </span>
      </div>
      <h3 className="mt-1 text-lg font-semibold text-text-primary">{set.title}</h3>
      <p className="mt-0.5 text-xs text-text-secondary">{set.subtitle}</p>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap items-center gap-4 border-b border-surface-border pb-2 text-xs text-text-secondary">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-surface-hover border border-surface-border" />
          <span className="font-medium text-text-primary">
            {simulateSettled ? `${set.stage_1_label} (✓ / ✗ settled)` : `${set.stage_1_label} %`}
          </span>
          <span className="text-text-muted">(#{set.stage_1_market.id})</span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-accent-brand" />
          <span className="font-medium text-text-primary">{set.stage_2_label} %</span>
          <span className="text-text-muted">(#{set.stage_2_market.id})</span>
        </span>
      </div>

      <div className="mt-2 divide-y divide-surface-border">
        {rows.map((entry, idx) => {
          const s1 = formatStage1Display(entry, set, {
            simulateSettledStage1: simulateSettled,
          });
          const s2 = formatStage2Display(entry, set, {
            simulateSettledStage1: simulateSettled,
          });
          return (
            <div
              key={entry.subject_key}
              data-testid={`paired-bars-row-${idx + 1}`}
              className="flex items-center gap-3 py-2.5"
            >
              <ArtThumb entry={entry} kidSurface={kidSurface} size="md" />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <div className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-text-primary">
                      {entry.subject}
                    </span>
                    <span className="block truncate text-xs text-text-muted">
                      {entry.detail}
                    </span>
                  </div>
                </div>

                {/* Two bars stacked together in one column (Alex Nov 4 / Nov 10 design) */}
                <div className="mt-1.5 space-y-1.5">
                  {/* Bar 1: Stage 1 (Nominated % / Make Playoffs % or ✓ / ✗) */}
                  <div className="flex items-center gap-2">
                    <span className="w-20 shrink-0 text-xs text-text-secondary">
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
                        <span className="w-12 text-right text-xs font-semibold tabular-nums text-text-secondary">
                          {s1.label}
                        </span>
                      </>
                    ) : s1.kind === "tick" ? (
                      <div className="flex flex-1 items-center justify-between">
                        <span
                          data-testid="settled-stage-1-tick"
                          className="inline-flex items-center rounded bg-surface-elevated px-2 py-0.5 text-xs font-semibold text-accent-positive"
                        >
                          {s1.label}
                        </span>
                      </div>
                    ) : s1.kind === "cross" ? (
                      <div className="flex flex-1 items-center justify-between">
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

                  {/* Bar 2: Stage 2 (Wins % / Win Cup %) */}
                  <div className="flex items-center gap-2">
                    <span className="w-20 shrink-0 text-xs font-medium text-text-primary">
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
                        <span className="w-12 text-right text-sm font-bold tabular-nums text-text-primary">
                          {s2.label}
                        </span>
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
        })}
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-surface-border pt-2 text-xs text-text-muted">
        <span>
          Paired by hand in register · Kept separate · Sorted by {set.stage_2_label.toLowerCase()}
        </span>
        <span>as of {set.as_of}</span>
      </div>
    </article>
  );
}

// ============================================================================
// Form 2: Art-Led 2-Up Spotlight Tiles (`poster_spotlight_tiles`)
// ============================================================================

function PosterSpotlightTilesCard({
  set,
  simulateSettled = false,
  kidSurface = false,
}: {
  set: PairedMetricSet;
  simulateSettled?: boolean;
  kidSurface?: boolean;
}) {
  // Show top 5 by wins + the unpriced-win contender (I Play Rocky) so missing-number rule is visible
  const topFive = set.entries.slice(0, 5);
  const unpricedRow = set.entries.find((e) => e.stage_2_probability === null);
  const tiles = unpricedRow && !topFive.includes(unpricedRow) ? [...topFive, unpricedRow] : set.entries.slice(0, 6);

  return (
    <article
      data-testid="visual-form-card-poster-tiles"
      className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>{set.kicker}</span>
        <span>POSTER-LED TILES</span>
      </div>
      <h3 className="mt-1 text-lg font-semibold text-text-primary">
        {set.title} (Tile Grid)
      </h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        Each contender&apos;s poster anchors its tile; {set.stage_2_label} % stays the headline and {set.stage_1_label} % sits beside it.
      </p>

      <div className="mt-3 grid grid-cols-2 gap-2.5">
        {tiles.map((entry) => {
          const s1 = formatStage1Display(entry, set, {
            simulateSettledStage1: simulateSettled,
          });
          const s2 = formatStage2Display(entry, set, {
            simulateSettledStage1: simulateSettled,
          });
          return (
            <div
              key={entry.subject_key}
              className="flex flex-col justify-between rounded-lg border border-surface-border bg-surface-elevated p-2.5"
            >
              <div className="flex items-start gap-2.5">
                <ArtThumb entry={entry} kidSurface={kidSurface} size="md" />
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-2 text-xs font-semibold leading-snug text-text-primary">
                    {entry.subject}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-text-muted">
                    {entry.detail}
                  </div>
                </div>
              </div>

              <div className="mt-2.5 border-t border-surface-border pt-2">
                <div className="flex items-baseline justify-between gap-1">
                  <div>
                    <div className="text-xs text-text-muted">{set.stage_2_label}</div>
                    {s2.kind === "percent" ? (
                      <div className="text-lg font-bold tabular-nums text-text-primary">
                        {s2.label}
                      </div>
                    ) : (
                      <div
                        data-testid="missing-probability-notice"
                        className="text-xs font-medium text-text-muted"
                      >
                        {s2.label}
                      </div>
                    )}
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-text-muted">{set.stage_1_label}</div>
                    {s1.kind === "tick" ? (
                      <div className="text-xs font-semibold text-accent-positive">
                        {s1.label}
                      </div>
                    ) : s1.kind === "cross" ? (
                      <div className="text-xs font-medium text-text-muted line-through">
                        {s1.label}
                      </div>
                    ) : (
                      <div className="text-sm font-semibold tabular-nums text-text-secondary">
                        {s1.label}
                      </div>
                    )}
                  </div>
                </div>
                {s1.kind === "percent" && s1.percent !== null && (
                  <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-card">
                    {s2.kind === "percent" && s2.percent !== null && s2.percent > 0 && (
                      <div
                        className="h-full rounded-full bg-accent-brand"
                        style={{
                          width: `${Math.max(4, s2.percent)}%`,
                        }}
                      />
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-3 text-xs text-text-muted">
        Showing 6 of {set.entries.length} paired contenders · {set.stage_1_label} and {set.stage_2_label} kept separate.
      </div>
    </article>
  );
}

// ============================================================================
// Form 3: Two-Step Conversion Funnel Track (`step_conversion_path`)
// ============================================================================

function StepConversionPathCard({
  set,
  simulateSettled = false,
  kidSurface = false,
  maxRows = 8,
}: {
  set: PairedMetricSet;
  simulateSettled?: boolean;
  kidSurface?: boolean;
  maxRows?: number;
}) {
  const baseRows = set.entries.slice(0, maxRows - 1);
  const unpricedRow = set.entries.find((e) => e.stage_2_probability === null || e.stage_1_probability === null);
  const rows =
    unpricedRow && !baseRows.includes(unpricedRow)
      ? [...baseRows, unpricedRow]
      : set.entries.slice(0, maxRows);

  return (
    <article
      data-testid="visual-form-card-step-conversion"
      className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>{set.kicker}</span>
        <span>STEP 1 → STEP 2 PATH</span>
      </div>
      <h3 className="mt-1 text-lg font-semibold text-text-primary">
        From {set.stage_1_label.toLowerCase()} lock to {set.stage_2_label.toLowerCase()}
      </h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        Outer track shows {set.stage_1_label} % reach; solid inner fill shows {set.stage_2_label} % on the same 0–100% scale.
      </p>

      <div className="mt-3 divide-y divide-surface-border">
        {rows.map((entry) => {
          const s1 = formatStage1Display(entry, set, {
            simulateSettledStage1: simulateSettled,
          });
          const s2 = formatStage2Display(entry, set, {
            simulateSettledStage1: simulateSettled,
          });
          const outerWidth =
            s1.kind === "tick"
              ? 100
              : s1.kind === "percent" && s1.percent !== null
                ? Math.max(6, s1.percent)
                : 0;
          const innerWidth =
            s2.kind === "percent" && s2.percent !== null ? Math.max(3, s2.percent) : 0;

          return (
            <div key={entry.subject_key} className="flex items-center gap-3 py-2.5">
              <ArtThumb entry={entry} kidSurface={kidSurface} size="sm" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
                  <span className="text-sm font-semibold text-text-primary">
                    {entry.subject}
                  </span>
                  <div className="flex shrink-0 items-center gap-1.5 text-xs tabular-nums">
                    <span
                      className={
                        s1.kind === "tick"
                          ? "font-semibold text-accent-positive"
                          : s1.kind === "cross"
                            ? "text-text-muted line-through"
                            : "font-medium text-text-secondary"
                      }
                    >
                      {s1.kind === "percent" ? `${s1.label} nom` : s1.label}
                    </span>
                    <span className="text-text-muted">→</span>
                    {s2.kind === "percent" ? (
                      <span className="font-bold text-text-primary">
                        {s2.label} win
                      </span>
                    ) : (
                      <span
                        data-testid="missing-probability-notice"
                        className="rounded border border-surface-border bg-surface-elevated px-1.5 py-0.5 text-xs font-medium text-text-muted"
                      >
                        {s2.label}
                      </span>
                    )}
                  </div>
                </div>

                {/* Single nested funnel bar */}
                <div className="relative mt-1.5 h-3 w-full overflow-hidden rounded-full bg-surface-elevated">
                  {outerWidth > 0 && (
                    <div
                      className="absolute inset-y-0 left-0 rounded-full border border-surface-border bg-surface-hover"
                      style={{ width: `${outerWidth}%` }}
                    />
                  )}
                  {innerWidth > 0 && (
                    <div
                      className="absolute inset-y-0 left-0 rounded-full bg-accent-brand"
                      style={{ width: `${innerWidth}%` }}
                    />
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-2.5 flex items-center justify-between gap-2 text-xs text-text-muted">
        <span>Light bar = {set.stage_1_label} % · Green bar = {set.stage_2_label} %</span>
        <span className="shrink-0">Kept separate</span>
      </div>
    </article>
  );
}

// ============================================================================
// Form 4: One Leader Hero + Chasers Strip (`leader_and_chasers_split`)
// ============================================================================

function LeaderAndChasersSplitCard({
  set,
  simulateSettled = false,
  kidSurface = false,
}: {
  set: PairedMetricSet;
  simulateSettled?: boolean;
  kidSurface?: boolean;
}) {
  const leader = set.entries[0];
  const chasers = set.entries.slice(1, 6);
  const unpriced = set.entries.find((e) => e.stage_2_probability === null);
  const chaserList =
    unpriced && !chasers.includes(unpriced) ? [...chasers.slice(0, 4), unpriced] : chasers;

  const leaderS1 = formatStage1Display(leader, set, {
    simulateSettledStage1: simulateSettled,
  });
  const leaderS2 = formatStage2Display(leader, set, {
    simulateSettledStage1: simulateSettled,
  });
  const runnerUpS2 = set.entries[1]?.stage_2_probability ?? 0;
  const leadMarginPts = Math.round(
    ((leader.stage_2_probability ?? 0) - runnerUpS2) * 100,
  );

  return (
    <article
      data-testid="visual-form-card-leader-chasers"
      className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>{set.kicker}</span>
        <span>LEADER + CHASERS</span>
      </div>

      {/* Leader Spotlight Banner */}
      <div className="mt-2.5 flex items-center gap-3.5 rounded-lg border border-surface-border bg-surface-elevated p-3">
        <ArtThumb entry={leader} kidSurface={kidSurface} size="lg" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="rounded bg-accent-brand px-1.5 py-0.5 text-xs font-bold text-text-inverse">
              #1 FAVORITE
            </span>
            {leadMarginPts > 0 && (
              <span className="text-xs font-medium text-text-secondary">
                +{leadMarginPts} pts ahead of #2
              </span>
            )}
          </div>
          <h3 className="mt-1 truncate text-base font-bold text-text-primary">
            {leader.subject}
          </h3>
          <p className="truncate text-xs text-text-muted">{leader.detail}</p>

          <div className="mt-2 flex items-center gap-4">
            <div>
              <div className="text-xs text-text-muted">{set.stage_2_label}</div>
              <div className="text-xl font-bold tabular-nums text-text-primary">
                {leaderS2.label}
              </div>
            </div>
            <div className="h-7 w-px bg-surface-border" />
            <div>
              <div className="text-xs text-text-muted">{set.stage_1_label}</div>
              <div className="text-base font-semibold tabular-nums text-text-secondary">
                {leaderS1.label}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Chasers Strip */}
      <div className="mt-3">
        <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
          <span>Chasing pack</span>
          <span>
            {set.stage_1_label} · {set.stage_2_label}
          </span>
        </div>
        <div className="mt-1.5 divide-y divide-surface-border">
          {chaserList.map((entry) => {
            const s1 = formatStage1Display(entry, set, {
              simulateSettledStage1: simulateSettled,
            });
            const s2 = formatStage2Display(entry, set, {
              simulateSettledStage1: simulateSettled,
            });
            return (
              <div
                key={entry.subject_key}
                className="flex items-center gap-2.5 py-2"
              >
                <ArtThumb entry={entry} kidSurface={kidSurface} size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
                    <div className="text-sm font-medium text-text-primary">
                      {entry.subject}
                    </div>
                    <div className="flex shrink-0 items-center gap-2 text-right tabular-nums">
                      <span className="rounded bg-surface-elevated px-2 py-0.5 text-xs font-medium text-text-secondary">
                        {s1.kind === "percent" ? `${s1.label} nom` : s1.label}
                      </span>
                      {s2.kind === "percent" ? (
                        <span className="w-10 text-sm font-bold text-text-primary">
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
                  <div className="truncate text-xs text-text-muted">
                    {entry.detail}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </article>
  );
}

// ============================================================================
// Form 6: Settled Gate After Nominations (`settled_gate_after_nominations`)
// ============================================================================

function SettledGateAfterNominationsCard({
  set,
  kidSurface = false,
}: {
  set: PairedMetricSet;
  kidSurface?: boolean;
}) {
  const nominatedRows = set.entries.slice(0, 5);
  const snubbedRows: PairedSubjectEntry[] = [
    {
      ...set.entries[5], // Artificial (was 57% nom)
      stage_1_settled_state: "no",
    },
    {
      ...set.entries[9], // I Play Rocky (was 48% nom)
      stage_1_settled_state: "no",
    },
  ];

  return (
    <article
      data-testid="visual-form-card-settled-gate"
      className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      <div
        data-testid="settled-gate-illustration-banner"
        className="mb-2.5 flex items-center justify-between rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1.5 text-xs font-semibold text-text-secondary"
      >
        <span>Illustration: nominations aren&apos;t out</span>
        <span className="text-text-muted">Jan 2027 preview</span>
      </div>
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>{set.kicker} · AFTER NOMINATIONS</span>
        <span>SETTLED STEP 1 (✓ / ✗)</span>
      </div>
      <h3 className="mt-1 text-lg font-semibold text-text-primary">
        Best Picture: ✓ nominated vs ✗ missed
      </h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        Illustration: nominations aren&apos;t out. Once nominations are announced, the first bar becomes ✓ or ✗ (&ldquo;settled means settled&rdquo;); only confirmed nominees keep a live Winner % bar.
      </p>

      <div className="mt-3 divide-y divide-surface-border">
        {nominatedRows.map((raw) => {
          const entry: PairedSubjectEntry = {
            ...raw,
            stage_1_settled_state: "yes",
          };
          const s1 = formatStage1Display(entry, set);
          const s2 = formatStage2Display(entry, set);
          return (
            <div key={entry.subject_key} className="flex items-center gap-3 py-2">
              <ArtThumb entry={entry} kidSurface={kidSurface} size="sm" />
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <span className="line-clamp-2 text-sm font-semibold leading-snug text-text-primary">
                    {entry.subject}
                  </span>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <span
                      data-testid="settled-stage-1-tick"
                      className="whitespace-nowrap rounded bg-surface-elevated px-1.5 py-0.5 text-xs font-semibold text-accent-positive"
                    >
                      {s1.label}
                    </span>
                    <span className="w-9 text-right text-sm font-bold tabular-nums text-text-primary">
                      {s2.label}
                    </span>
                  </div>
                </div>
                {s2.kind === "percent" && s2.percent !== null && (
                  <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-surface-elevated">
                    <div
                      className="h-full rounded-full bg-accent-brand"
                      style={{ width: `${Math.max(4, s2.percent)}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {snubbedRows.map((entry) => {
          const s1 = formatStage1Display(entry, set);
          return (
            <div
              key={entry.subject_key}
              className="flex items-center justify-between gap-2 py-2 opacity-75"
            >
              <div className="flex min-w-0 items-center gap-2.5">
                <ArtThumb entry={entry} kidSurface={kidSurface} size="sm" />
                <span className="line-clamp-2 text-sm font-medium leading-snug text-text-muted line-through">
                  {entry.subject}
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-1.5 whitespace-nowrap text-xs text-text-muted">
                <span data-testid="settled-stage-1-cross" className="font-semibold">
                  {s1.label}
                </span>
                {s1.sublabel && <span>({s1.sublabel})</span>}
              </div>
            </div>
          );
        })}
      </div>
    </article>
  );
}

// ============================================================================
// Single Look-Sheet Card Renderer (Used by both Gallery and 1-by-1 Grading)
// ============================================================================

export const renderLookSheetCardBySpec = (
  spec: LookSheetCardSpec,
  options?: { simulateSettled?: boolean; kidSurface?: boolean },
) => {
  const set =
    PAIRED_METRIC_REGISTER[spec.set_id] ??
    PAIRED_METRIC_REGISTER["oscars-2027-best-picture"];
  const settled = Boolean(spec.force_settled_stage_1 || options?.simulateSettled);
  const kid = Boolean(options?.kidSurface);

  switch (spec.form.form_id) {
    case "paired_bars_with_art":
      return (
        <PairedBarsWithArtCard
          set={set}
          simulateSettled={settled}
          kidSurface={kid}
          maxRows={spec.set_id === "oscars-2027-best-picture" ? 10 : 8}
        />
      );
    case "poster_spotlight_tiles":
      return (
        <PosterSpotlightTilesCard
          set={set}
          simulateSettled={settled}
          kidSurface={kid}
        />
      );
    case "step_conversion_path":
      return (
        <StepConversionPathCard
          set={set}
          simulateSettled={settled}
          kidSurface={kid}
        />
      );
    case "leader_and_chasers_split":
      return (
        <LeaderAndChasersSplitCard
          set={set}
          simulateSettled={settled}
          kidSurface={kid}
        />
      );
    case "settled_gate_after_nominations":
      return <SettledGateAfterNominationsCard set={set} kidSurface={kid} />;
  }
}

// ============================================================================
// Part 2: Three Oscars Container Layouts (#12523)
// ============================================================================

export function OscarsContainerLayoutPreview({
  spec,
  simulateSettled = false,
  kidSurface = false,
}: {
  spec: ContainerLookSheetSpec;
  simulateSettled?: boolean;
  kidSurface?: boolean;
}) {
  const picSet = PAIRED_METRIC_REGISTER["oscars-2027-best-picture"];
  const dirSet = PAIRED_METRIC_REGISTER["oscars-2027-best-director"];
  const actSet = PAIRED_METRIC_REGISTER["oscars-2027-best-actor"];
  const actressSet = PAIRED_METRIC_REGISTER["oscars-2027-best-actress"];
  const animSet = PAIRED_METRIC_REGISTER["oscars-2027-best-animated"];

  if (spec.option_code === "A") {
    return (
      <section
        data-testid="oscars-container-option-A"
        className="space-y-3 rounded-xl border border-surface-border bg-surface-elevated p-3.5"
      >
        <div className="border-b border-surface-border pb-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-accent-brand">
            OSCARS 2027 CONTAINER · OPTION A (MAGAZINE RHYTHM)
          </div>
          <h3 className="mt-0.5 text-base font-bold text-text-primary">
            Adjacent sections never use the same visual form
          </h3>
          <p className="text-xs text-text-secondary">{spec.rule_summary}</p>
        </div>

        {/* Section 1: Best Picture as Leader + Chasers */}
        <LeaderAndChasersSplitCard
          set={picSet}
          simulateSettled={simulateSettled}
          kidSurface={kidSurface}
        />

        {/* Section 2: Best Director as 2x2 Circular Headshot Tiles */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-3.5">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
            <span>BEST DIRECTOR · HEADSHOT TILES</span>
            <span>NOMINATED · WINS</span>
          </div>
          <div className="mt-2.5 grid grid-cols-2 gap-2">
            {dirSet.entries.slice(0, 6).map((entry) => {
              const s1 = formatStage1Display(entry, dirSet, {
                simulateSettledStage1: simulateSettled,
              });
              const s2 = formatStage2Display(entry, dirSet, {
                simulateSettledStage1: simulateSettled,
              });
              return (
                <div
                  key={entry.subject_key}
                  className="flex items-center gap-2.5 rounded-lg border border-surface-border bg-surface-elevated p-2"
                >
                  <ArtThumb entry={entry} kidSurface={kidSurface} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-semibold text-text-primary">
                      {entry.subject}
                    </div>
                    <div className="truncate text-xs text-text-muted">
                      {entry.detail}
                    </div>
                    <div className="mt-1 flex items-center justify-between text-xs tabular-nums">
                      <span className="text-text-secondary">
                        {s1.kind === "percent" ? `${s1.label} nom` : s1.label}
                      </span>
                      <span className="font-bold text-text-primary">
                        {s2.label} win
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Section 3: Best Actress as Step Conversion Funnel */}
        <StepConversionPathCard
          set={actressSet}
          simulateSettled={simulateSettled}
          kidSurface={kidSurface}
          maxRows={4}
        />

        {/* Section 4: Best Animated Feature as 4-Poster Strip */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-3.5">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
            <span>BEST ANIMATED FEATURE · POSTER STRIP</span>
            <span>NOMINATED · WINS</span>
          </div>
          <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {animSet.entries.map((entry) => {
              const s1 = formatStage1Display(entry, animSet, {
                simulateSettledStage1: simulateSettled,
              });
              const s2 = formatStage2Display(entry, animSet, {
                simulateSettledStage1: simulateSettled,
              });
              return (
                <div
                  key={entry.subject_key}
                  className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-elevated p-2"
                >
                  <ArtThumb entry={entry} kidSurface={kidSurface} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-semibold text-text-primary">
                      {entry.subject}
                    </div>
                    <div className="mt-0.5 text-xs font-bold tabular-nums text-text-primary">
                      {s2.label} win
                    </div>
                    <div className="text-xs tabular-nums text-text-secondary">
                      {s1.kind === "percent" ? `${s1.label} nom` : s1.label}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>
    );
  }

  if (spec.option_code === "B") {
    return (
      <section
        data-testid="oscars-container-option-B"
        className="space-y-3 rounded-xl border border-surface-border bg-surface-elevated p-3.5"
      >
        <div className="border-b border-surface-border pb-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-accent-brand">
            OSCARS 2027 CONTAINER · OPTION B (SHAPE-DRIVEN CONTRAST)
          </div>
          <h3 className="mt-0.5 text-base font-bold text-text-primary">
            Distribution shape picks the form: Locks vs Open Duels vs 10-Slot Field
          </h3>
          <p className="text-xs text-text-secondary">{spec.rule_summary}</p>
        </div>

        {/* Tier 1: Runaway Locks (>= 70% to win) */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-3.5">
          <div className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            RUNAWAY FAVORITES (LEADER &ge; 70% TO WIN)
          </div>
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {[
              { cat: "Best Animated Feature", entry: animSet.entries[0], set: animSet, chaser: "Toy Story 5 (6% win · 92% nom)" },
              { cat: "Best Actress", entry: actressSet.entries[0], set: actressSet, chaser: "Inde Navarrette (17% win · 78% nom)" },
            ].map(({ cat, entry, set, chaser }) => {
              const s1 = formatStage1Display(entry, set, {
                simulateSettledStage1: simulateSettled,
              });
              const s2 = formatStage2Display(entry, set, {
                simulateSettledStage1: simulateSettled,
              });
              return (
                <div
                  key={cat}
                  className="flex items-center gap-3 rounded-lg border border-surface-border bg-surface-elevated p-2.5"
                >
                  <ArtThumb entry={entry} kidSurface={kidSurface} size="md" />
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-semibold text-text-muted">{cat}</div>
                    <div className="truncate text-sm font-bold text-text-primary">
                      {entry.subject}
                    </div>
                    <div className="mt-1 flex items-baseline gap-2 text-xs tabular-nums">
                      <span className="text-base font-bold text-text-primary">
                        {s2.label} win
                      </span>
                      <span className="text-text-secondary">· {s1.label} nom</span>
                    </div>
                    <div className="mt-0.5 truncate text-xs text-text-muted">
                      Next: {chaser}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Tier 2: Open 3-Way Race (Best Actor) */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-3.5">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
            <span>OPEN THREE-WAY RACE · BEST ACTOR</span>
            <span>NOMINATED · WINS</span>
          </div>
          <div className="mt-2.5 divide-y divide-surface-border">
            {actSet.entries.slice(0, 4).map((entry) => {
              const s1 = formatStage1Display(entry, actSet, {
                simulateSettledStage1: simulateSettled,
              });
              const s2 = formatStage2Display(entry, actSet, {
                simulateSettledStage1: simulateSettled,
              });
              return (
                <div
                  key={entry.subject_key}
                  className="flex items-center justify-between gap-3 py-2"
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <ArtThumb entry={entry} kidSurface={kidSurface} size="sm" />
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-text-primary">
                        {entry.subject}
                      </div>
                      <div className="truncate text-xs text-text-muted">
                        {entry.detail}
                      </div>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2 tabular-nums">
                    <span className="rounded bg-surface-elevated px-2 py-0.5 text-xs text-text-secondary">
                      {s1.kind === "percent" ? `${s1.label} nom` : s1.label}
                    </span>
                    <span className="w-12 text-right text-sm font-bold text-text-primary">
                      {s2.label}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Tier 3: Full 10-Film Best Picture Board */}
        <PairedBarsWithArtCard
          set={picSet}
          simulateSettled={simulateSettled}
          kidSurface={kidSurface}
          maxRows={6}
        />
      </section>
    );
  }

  // Option C: Two-Act Ballot (90%+ Nomination Locks Rail + Category Forms)
  const locks = [
    { label: "Christopher Nolan", cat: "Director", pct: "99%", entry: dirSet.entries[0] },
    { label: "The Odyssey", cat: "Picture", pct: "98%", entry: picSet.entries[0] },
    { label: "Julianne Moore", cat: "Actress", pct: "98%", entry: actressSet.entries[0] },
    { label: "Wildwood", cat: "Animated", pct: "97%", entry: animSet.entries[0] },
    { label: "John Malkovich", cat: "Actor", pct: "95%", entry: actSet.entries[0] },
    { label: "The Black Ball", cat: "Picture", pct: "94%", entry: picSet.entries[2] },
  ];

  return (
    <section
      data-testid="oscars-container-option-C"
      className="space-y-3 rounded-xl border border-surface-border bg-surface-elevated p-3.5"
    >
      <div className="border-b border-surface-border pb-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-accent-brand">
          OSCARS 2027 CONTAINER · OPTION C (TWO-ACT BALLOT)
        </div>
        <h3 className="mt-0.5 text-base font-bold text-text-primary">
          Act I: 90%+ Nomination Locks · Act II: Film Posters vs Acting Headshots
        </h3>
        <p className="text-xs text-text-secondary">{spec.rule_summary}</p>
      </div>

      {/* Act I: 90%+ Nomination Locks Rail */}
      <div className="rounded-xl border border-surface-border bg-surface-card p-3.5">
        <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
          <span>
            {simulateSettled
              ? "ACT I · CONFIRMED NOMINEES (✓ SETTLED)"
              : "ACT I · THE 90%+ NOMINATION LOCKS"}
          </span>
          <span>JAN 2027 NOMINATIONS</span>
        </div>
        <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {locks.map((item) => (
            <div
              key={`${item.cat}-${item.label}`}
              className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-elevated p-2"
            >
              <ArtThumb entry={item.entry} kidSurface={kidSurface} size="sm" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-text-primary">
                  {item.label}
                </div>
                <div className="text-xs text-text-muted">{item.cat}</div>
                <div className="text-xs font-bold tabular-nums text-accent-positive">
                  {simulateSettled ? "✓ Nominated" : `${item.pct} nom`}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Act II: Best Picture Poster Tiles + Best Director Headshot Funnel */}
      <PosterSpotlightTilesCard
        set={picSet}
        simulateSettled={simulateSettled}
        kidSurface={kidSurface}
      />
      <StepConversionPathCard
        set={dirSet}
        simulateSettled={simulateSettled}
        kidSurface={kidSurface}
        maxRows={6}
      />
    </section>
  );
}

// ============================================================================
// Single Deck-Item Renderer for `/grade/groupings`
// ============================================================================

export const renderVisualLookSheetDeckItem = (
  itemKey: string,
  options?: { simulateSettled?: boolean; kidSurface?: boolean },
): React.ReactNode | null => {
  const cardSpec = VISUAL_FORM_LOOK_SHEET_CARDS.find((c) => c.item_key === itemKey);
  if (cardSpec) {
    return (
      <div className="space-y-2" data-testid={`look-sheet-item-${itemKey}`}>
        <FormContractHeader form={cardSpec.form} />
        {renderLookSheetCardBySpec(cardSpec, options)}
      </div>
    );
  }
  const containerSpec = OSCARS_CONTAINER_LOOK_SHEET_OPTIONS.find(
    (c) => c.item_key === itemKey,
  );
  if (containerSpec) {
    return (
      <div className="space-y-2" data-testid={`look-sheet-item-${itemKey}`}>
        <OscarsContainerLayoutPreview
          spec={containerSpec}
          simulateSettled={options?.simulateSettled}
          kidSurface={options?.kidSurface}
        />
      </div>
    );
  }
  return null;
}

// ============================================================================
// Full Look Sheet Gallery View (All 6 Cards + All 3 Containers on One Page)
// ============================================================================

export interface VisualFormLookSheetGalleryProps {
  kidSurface?: boolean;
  grader?: string | null;
  existingGradesByItemKey?: Record<string, GroupingGrade>;
  onGradeItem?: (
    position: number,
    itemKey: string,
    grade: GroupingGrade,
    note: string,
  ) => Promise<void>;
  savingItemKey?: string | null;
}

export function VisualFormLookSheetGallery({
  kidSurface = false,
  grader = null,
  existingGradesByItemKey = {},
  onGradeItem,
  savingItemKey = null,
}: VisualFormLookSheetGalleryProps) {
  const [simulateSettled, setSimulateSettled] = useState(false);
  const [notesByKey, setNotesByKey] = useState<Record<string, string>>({});

  return (
    <div className="space-y-6" data-testid="visual-forms-look-sheet-gallery">
      {/* Header & Global Controls */}
      <div className="rounded-xl border border-surface-border bg-surface-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-accent-brand">
              #12577 / #12523 · VISUAL FORM LIBRARY LOOK SHEET (DECISION 132-A)
            </div>
            <h2 className="mt-0.5 text-lg font-bold text-text-primary">
              Six visual forms for &ldquo;two related numbers per subject&rdquo; + three Oscars container rhythms
            </h2>
          </div>
          <button
            type="button"
            data-testid="toggle-simulate-settled-nominations"
            onClick={() => setSimulateSettled((prev) => !prev)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
              simulateSettled
                ? "border-accent-brand bg-accent-brand text-text-inverse"
                : "border-surface-border bg-surface-elevated text-text-primary"
            }`}
          >
            {simulateSettled
              ? "Showing: After nominations (✓ / ✗)"
              : "Preview after nominations (✓ / ✗)"}
          </button>
        </div>

        <ul className="mt-2.5 space-y-1 text-xs text-text-secondary">
          <li>
            • <span className="font-semibold text-text-primary">Kept separate:</span>{" "}
            Nominee (#5165726) and Winner (#6173044) are paired by film in a hand-kept register; NHL Playoffs (#63068142) and Stanley Cup (#52755659) are paired by club.
          </li>
          <li>
            • <span className="font-semibold text-text-primary">Settled means settled:</span>{" "}
            Once step 1 settles, the first bar becomes <span className="font-semibold text-accent-positive">✓</span> or <span className="font-semibold text-text-muted">✗</span>.
          </li>
          <li>
            • <span className="font-semibold text-text-primary">Missing probability says so:</span>{" "}
            Contenders not in one market or without a recent probability say why (<span className="font-medium text-text-primary">&ldquo;Not listed to win&rdquo;</span> on <em>I Play Rocky</em>, <span className="font-medium text-text-primary">&ldquo;Not listed to be nominated&rdquo;</span> on <em>Alejandro G. Iñárritu</em>).
          </li>
          <li>
            • <span className="font-semibold text-text-primary">Kid-safe gate (#7461):</span>{" "}
            All posters, headshots, and team logos pass <code className="font-mono">resolveKidSafeVisualArt</code> (no schema migration required).
          </li>
        </ul>
      </div>

      {/* Section 1: 6 Visual Form Cards */}
      <div className="space-y-4">
        <h3 className="text-base font-bold text-text-primary">
          Part 1 · Six Visual Forms for &ldquo;Two Related Numbers per Subject&rdquo;
        </h3>
        {VISUAL_FORM_LOOK_SHEET_CARDS.map((spec) => {
          const currentGrade = existingGradesByItemKey[spec.item_key];
          const itemNote = notesByKey[spec.item_key] ?? "";
          return (
            <div
              key={spec.item_key}
              data-testid={`look-sheet-card-block-${spec.position}`}
              className="rounded-xl border border-surface-border bg-surface-elevated p-3.5"
            >
              <div className="mb-2 flex items-baseline justify-between gap-2">
                <h4 className="text-sm font-bold text-text-primary">{spec.label}</h4>
                <span className="text-xs font-medium text-text-muted">
                  Item #{spec.position} of 9
                </span>
              </div>
              <p className="mb-2 text-xs text-text-secondary">{spec.why_it_exists}</p>
              <FormContractHeader form={spec.form} />
              {renderLookSheetCardBySpec(spec, {
                simulateSettled,
                kidSurface,
              })}

              {grader && onGradeItem && (
                <div className="mt-3 rounded-lg border border-surface-border bg-surface-card p-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <input
                      type="text"
                      placeholder="Note on this form (optional)"
                      value={itemNote}
                      maxLength={300}
                      onChange={(e) =>
                        setNotesByKey((prev) => ({
                          ...prev,
                          [spec.item_key]: e.target.value,
                        }))
                      }
                      className="min-w-0 flex-1 rounded border border-surface-border bg-surface-elevated px-2.5 py-1.5 text-xs text-text-primary"
                    />
                    <div className="flex flex-wrap gap-1.5">
                      {GROUPING_GRADES.map((g) => (
                        <button
                          key={g}
                          type="button"
                          disabled={savingItemKey === spec.item_key}
                          onClick={() =>
                            void onGradeItem(spec.position, spec.item_key, g, itemNote)
                          }
                          className={`rounded border px-2.5 py-1.5 text-xs font-semibold ${
                            currentGrade === g
                              ? "border-accent-brand bg-accent-brand text-text-inverse"
                              : "border-surface-border bg-surface-elevated text-text-primary"
                          }`}
                        >
                          {GROUPING_GRADE_LABELS[g]}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Section 2: 3 Oscars Container Layouts (#12523) */}
      <div className="space-y-4">
        <h3 className="text-base font-bold text-text-primary">
          Part 2 · Three Ways an Oscars Container Can Look When Rows Don&apos;t All Look the Same (#12523)
        </h3>
        {OSCARS_CONTAINER_LOOK_SHEET_OPTIONS.map((spec) => {
          const currentGrade = existingGradesByItemKey[spec.item_key];
          const itemNote = notesByKey[spec.item_key] ?? "";
          return (
            <div
              key={spec.item_key}
              data-testid={`look-sheet-container-block-${spec.option_code}`}
              className="space-y-2"
            >
              <OscarsContainerLayoutPreview
                spec={spec}
                simulateSettled={simulateSettled}
                kidSurface={kidSurface}
              />
              {grader && onGradeItem && (
                <div className="rounded-lg border border-surface-border bg-surface-card p-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <input
                      type="text"
                      placeholder={`Note on Container ${spec.option_code} (optional)`}
                      value={itemNote}
                      maxLength={300}
                      onChange={(e) =>
                        setNotesByKey((prev) => ({
                          ...prev,
                          [spec.item_key]: e.target.value,
                        }))
                      }
                      className="min-w-0 flex-1 rounded border border-surface-border bg-surface-elevated px-2.5 py-1.5 text-xs text-text-primary"
                    />
                    <div className="flex flex-wrap gap-1.5">
                      {GROUPING_GRADES.map((g) => (
                        <button
                          key={g}
                          type="button"
                          disabled={savingItemKey === spec.item_key}
                          onClick={() =>
                            void onGradeItem(spec.position, spec.item_key, g, itemNote)
                          }
                          className={`rounded border px-2.5 py-1.5 text-xs font-semibold ${
                            currentGrade === g
                              ? "border-accent-brand bg-accent-brand text-text-inverse"
                              : "border-surface-border bg-surface-elevated text-text-primary"
                          }`}
                        >
                          {GROUPING_GRADE_LABELS[g]}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
