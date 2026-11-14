"use client";

/**
 * #12577 / #12523 — Visual Forms Look Sheet (Sheet 1 + Sheet 2) & Oscars Container Diversity Options.
 *
 * Renders the Bain Luck Visual Form Library on live paired-metric data:
 * - Sheet 1: 6 baseline forms (Best Picture 2027, NHL Playoff Berth → Stanley Cup,
 *   and Post-Nominations Settled Gate) + 3 Oscars 2027 container layouts (#12523).
 * - Sheet 2 (Alex's 8:33 PM PT reaction + Fable's 8:20 PM / 9:09 PM / 9:34 PM notes):
 *   3 shorter versions of Card 1 (`paired_bars_top5_expandable`,
 *   `paired_bars_single_line`, `paired_bars_top3_plus_strip`) and 3 wilder visual
 *   forms (`podium_and_tiers`, `barbell_race_track`, `ballot_quadrant_map`).
 *
 * Design-system compliance: light-mode tokens only (`bg-surface-*`, `text-text-*`,
 * `border-surface-border`, `text-accent-*`). Zero raw hexes, zero dark classes.
 */

import React, { useState } from "react";
import {
  OSCARS_CONTAINER_LOOK_SHEET_OPTIONS,
  PAIRED_METRIC_REGISTER,
  TMDB_ATTRIBUTION_LINE,
  TMDB_ATTRIBUTION_URL,
  TMDB_OFFICIAL_LOGO_PATH,
  VISUAL_FORM_LOOK_SHEET_CARDS,
  VISUAL_FORM_SHEET_2_CARDS,
  formatStage1Display,
  formatStage2Display,
  resolveKidSafeVisualArt,
  sortPairedEntries,
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
import { renderedPercent } from "@/lib/renderedPercent";

interface ArtThumbProps {
  entry: PairedSubjectEntry;
  kidSurface?: boolean;
  size?: "xs" | "sm" | "md" | "lg";
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
    const dim =
      size === "lg"
        ? "h-10 w-10"
        : size === "sm"
          ? "h-6 w-6"
          : size === "xs"
            ? "h-5 w-5"
            : "h-8 w-8";
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
    const dim =
      size === "lg"
        ? "h-12 w-12"
        : size === "sm"
          ? "h-8 w-8"
          : size === "xs"
            ? "h-6 w-6"
            : "h-10 w-10";
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
        : size === "xs"
          ? "h-9 w-6"
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

function TMDBAttributionNote({ set }: { set: PairedMetricSet }) {
  const usesTmdb = set.entries.some(
    (e) => e.art?.kind === "tmdb_poster" || e.art?.kind === "tmdb_headshot",
  );
  if (!usesTmdb) return null;
  return (
    <span
      data-testid="tmdb-attribution-line"
      className="inline-flex flex-wrap items-center gap-2 text-xs text-text-muted"
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
          width={85}
          height={11}
          data-testid="tmdb-official-logo"
          className="inline-block h-[11px] w-auto shrink-0"
        />
      </a>
      <span>{TMDB_ATTRIBUTION_LINE}</span>
    </span>
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
        <span className="rounded border border-surface-border bg-surface-card px-2 py-0.5 font-medium text-text-secondary">
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
// Shared Dual-Bar Row (Used by Card 1, Card 1A, Card 1C, and Card 5)
// ============================================================================

function DualBarRow({
  entry,
  set,
  idx,
  simulateSettled,
  kidSurface,
}: {
  entry: PairedSubjectEntry;
  set: PairedMetricSet;
  idx: number;
  simulateSettled: boolean;
  kidSurface: boolean;
}) {
  const s1 = formatStage1Display(entry, set, {
    simulateSettledStage1: simulateSettled,
  });
  const s2 = formatStage2Display(entry, set, {
    simulateSettledStage1: simulateSettled,
  });
  return (
    <div
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
  const rows = sortPairedEntries(set.entries).slice(0, maxRows);
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
          <span className="inline-block h-2.5 w-2.5 rounded-sm border border-surface-border bg-surface-hover" />
          <span className="font-medium text-text-primary">
            {simulateSettled
              ? `${set.stage_1_label} (✓ / ✗ settled)`
              : `${set.stage_1_label} %`}
          </span>
          <span className="text-text-muted">
            (
            {set.stage_1_market.companion_polymarket_id
              ? `average of two venues: #${set.stage_1_market.id} + #${set.stage_1_market.companion_polymarket_id}`
              : `#${set.stage_1_market.id}`}
            )
          </span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-accent-brand" />
          <span className="font-medium text-text-primary">{set.stage_2_label} %</span>
          <span className="text-text-muted">(#{set.stage_2_market.id})</span>
        </span>
      </div>

      <div className="mt-2 divide-y divide-surface-border">
        {rows.map((entry, idx) => (
          <DualBarRow
            key={entry.subject_key}
            entry={entry}
            set={set}
            idx={idx}
            simulateSettled={simulateSettled}
            kidSurface={kidSurface}
          />
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-surface-border pt-2 text-xs text-text-muted">
        <span>
          Paired in register · Kept separate · Sorted by {set.stage_2_label.toLowerCase()}
        </span>
        <TMDBAttributionNote set={set} />
      </div>
    </article>
  );
}

// ============================================================================
// Shorter Card 1A: Top 5 Dual Bars + 'Show All 10' Expander (`paired_bars_top5_expandable`)
// ============================================================================

function PairedBarsTop5ExpandableCard({
  set,
  simulateSettled = false,
  kidSurface = false,
}: {
  set: PairedMetricSet;
  simulateSettled?: boolean;
  kidSurface?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const sorted = sortPairedEntries(set.entries);
  const visibleRows = expanded ? sorted : sorted.slice(0, 5);
  const hiddenCount = Math.max(0, sorted.length - 5);
  const unpricedInHidden = sorted
    .slice(5)
    .find((e) => e.stage_2_probability === null);

  return (
    <article
      data-testid="visual-form-card-paired-bars-top5-expandable"
      className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>{set.kicker} · SHORTER VERSION 1A</span>
        <span>TOP 5 + EXPANDER</span>
      </div>
      <h3 className="mt-1 text-lg font-semibold text-text-primary">{set.title}</h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        From the {sorted.length} films most likely to be nominated, shows the top 5 by {set.stage_2_label} % in full two-bar rows; the remaining {hiddenCount} expand in place on tap.
      </p>

      <div className="mt-2 divide-y divide-surface-border">
        {visibleRows.map((entry, idx) => (
          <DualBarRow
            key={entry.subject_key}
            entry={entry}
            set={set}
            idx={idx}
            simulateSettled={simulateSettled}
            kidSurface={kidSurface}
          />
        ))}
      </div>

      {hiddenCount > 0 && (
        <div className="mt-2.5">
          <button
            type="button"
            data-testid="toggle-expand-all-rows"
            onClick={() => setExpanded((prev) => !prev)}
            className="flex w-full items-center justify-between rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-xs font-semibold text-text-primary hover:bg-surface-hover"
          >
            <span>
              {expanded
                ? "Show top 5 by Wins % only"
                : `Show all ${sorted.length} most likely nominees (+${hiddenCount} more)`}
            </span>
            {!expanded && unpricedInHidden && (
              <span
                data-testid="missing-probability-notice"
                className="font-normal text-text-muted"
              >
                incl. {unpricedInHidden.subject} (49% nom · Not listed to win)
              </span>
            )}
          </button>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-surface-border pt-2 text-xs text-text-muted">
        <span>Nominee % (average of two venues: #5165726 + #27988771) · Winner #6173044</span>
        <TMDBAttributionNote set={set} />
      </div>
    </article>
  );
}

// ============================================================================
// Shorter Card 1B: Compact One-Line-Per-Film Table (`paired_bars_single_line`)
// ============================================================================

function PairedBarsSingleLineCard({
  set,
  simulateSettled = false,
  kidSurface = false,
}: {
  set: PairedMetricSet;
  simulateSettled?: boolean;
  kidSurface?: boolean;
}) {
  const rows = sortPairedEntries(set.entries);
  return (
    <article
      data-testid="visual-form-card-paired-bars-single-line"
      className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>{set.kicker} · SHORTER VERSION 1B</span>
        <span>ONE LINE PER FILM (ALL 10)</span>
      </div>
      <h3 className="mt-1 text-lg font-semibold text-text-primary">{set.title}</h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        All {rows.length} films most likely to be nominated visible at once on single compact rows (ordered by {set.stage_2_label} %): mini poster, film title, inline dual micro-bars, {set.stage_1_label} % and {set.stage_2_label} %.
      </p>

      {/* Column Headers */}
      <div className="mt-3 flex items-center justify-between border-b border-surface-border pb-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>Film (Top 10 by Nom %)</span>
        <div className="flex items-center gap-3">
          <span className="w-16 text-right">{set.stage_1_label}</span>
          <span className="w-24 text-right text-text-primary">{set.stage_2_label}</span>
        </div>
      </div>

      <div className="divide-y divide-surface-border">
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
              data-testid={`single-line-row-${idx + 1}`}
              className="flex items-center gap-2.5 py-1.5"
            >
              <ArtThumb entry={entry} kidSurface={kidSurface} size="xs" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-text-primary">
                  {entry.subject}
                </div>
                {/* Stacked 3px micro-bars */}
                <div className="mt-1 space-y-0.5">
                  <div className="h-1 w-full overflow-hidden rounded-full bg-surface-elevated">
                    {s1.kind === "percent" && s1.percent !== null && (
                      <div
                        className="h-full rounded-full bg-text-muted"
                        style={{ width: `${Math.max(4, s1.percent)}%` }}
                      />
                    )}
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-elevated">
                    {s2.kind === "percent" && s2.percent !== null && (
                      <div
                        className="h-full rounded-full bg-accent-brand"
                        style={{ width: `${Math.max(4, s2.percent)}%` }}
                      />
                    )}
                  </div>
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-2 tabular-nums">
                <span
                  className={`w-14 text-right text-xs font-semibold ${
                    s1.kind === "tick"
                      ? "text-accent-positive"
                      : s1.kind === "cross"
                        ? "text-text-muted line-through"
                        : "text-text-secondary"
                  }`}
                >
                  {s1.kind === "tick" ? "✓ Nom" : s1.kind === "cross" ? "✗ Out" : s1.label}
                </span>
                {s2.kind === "percent" ? (
                  <span className="w-24 text-right text-xs font-bold text-text-primary">
                    {s2.label}
                  </span>
                ) : (
                  <span
                    data-testid="missing-probability-notice"
                    className="w-24 text-right text-xs font-medium text-text-muted"
                  >
                    {s2.label}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 border-t border-surface-border pt-2 text-xs text-text-muted">
        <span>Top bar = {set.stage_1_label} % · Bottom green bar = {set.stage_2_label} %</span>
        <TMDBAttributionNote set={set} />
      </div>
    </article>
  );
}

// ============================================================================
// Shorter Card 1C: Top 3 Dual-Bar Rows + 2-Up Contender Strip (`paired_bars_top3_plus_strip`)
// ============================================================================

function PairedBarsTop3PlusStripCard({
  set,
  simulateSettled = false,
  kidSurface = false,
}: {
  set: PairedMetricSet;
  simulateSettled?: boolean;
  kidSurface?: boolean;
}) {
  const sorted = sortPairedEntries(set.entries);
  const top3 = sorted.slice(0, 3);
  const rest = sorted.slice(3);

  return (
    <article
      data-testid="visual-form-card-paired-bars-top3-plus-strip"
      className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>{set.kicker} · SHORTER VERSION 1C</span>
        <span>TOP 3 ROWS + 2-UP STRIP</span>
      </div>
      <h3 className="mt-1 text-lg font-semibold text-text-primary">{set.title}</h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        From the {sorted.length} films most likely to be nominated, the top 3 by {set.stage_2_label} % get full poster + dual-bar rows; the other 7 sit in a compact 2-column grid below.
      </p>

      <div className="mt-2 divide-y divide-surface-border">
        {top3.map((entry, idx) => (
          <DualBarRow
            key={entry.subject_key}
            entry={entry}
            set={set}
            idx={idx}
            simulateSettled={simulateSettled}
            kidSurface={kidSurface}
          />
        ))}
      </div>

      <div className="mt-3 border-t border-surface-border pt-2.5">
        <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
          <span>Other 7 of Top {sorted.length} Most Likely Nominees</span>
          <span>
            {set.stage_1_label} · {set.stage_2_label}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {rest.map((entry) => {
            const s1 = formatStage1Display(entry, set, {
              simulateSettledStage1: simulateSettled,
            });
            const s2 = formatStage2Display(entry, set, {
              simulateSettledStage1: simulateSettled,
            });
            return (
              <div
                key={entry.subject_key}
                className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-elevated p-2"
              >
                <ArtThumb entry={entry} kidSurface={kidSurface} size="xs" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-semibold text-text-primary">
                    {entry.subject}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-baseline justify-between gap-1 text-xs tabular-nums">
                    <span className="text-text-secondary">
                      {s1.kind === "percent" ? `${s1.label} nom` : s1.label}
                    </span>
                    {s2.kind === "percent" ? (
                      <span className="font-bold text-text-primary">
                        {s2.label} win
                      </span>
                    ) : (
                      <span
                        data-testid="missing-probability-notice"
                        className="font-medium text-text-muted"
                      >
                        {s2.label}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-surface-border pt-2 text-xs text-text-muted">
        <span>Top 10 most likely nominees · Top 3 bars + 7 compact tiles</span>
        <TMDBAttributionNote set={set} />
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
  const sorted = sortPairedEntries(set.entries);
  const topFive = sorted.slice(0, 5);
  const unpricedRow = sorted.find((e) => e.stage_2_probability === null);
  const tiles =
    unpricedRow && !topFive.includes(unpricedRow)
      ? [...topFive, unpricedRow]
      : sorted.slice(0, 6);

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
        {set.title}
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

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
        <span>
          Showing 6 of {set.entries.length} most likely nominees · {set.stage_1_label} and {set.stage_2_label} kept separate.
        </span>
        <TMDBAttributionNote set={set} />
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
  const sorted = sortPairedEntries(set.entries);
  const baseRows = sorted.slice(0, maxRows - 1);
  const unpricedRow = sorted.find(
    (e) => e.stage_2_probability === null || e.stage_1_probability === null,
  );
  const rows =
    unpricedRow && !baseRows.includes(unpricedRow)
      ? [...baseRows, unpricedRow]
      : sorted.slice(0, maxRows);

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
        {set.title}
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

      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
        <span>Light bar = {set.stage_1_label} % · Green bar = {set.stage_2_label} %</span>
        <TMDBAttributionNote set={set} />
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
  const sorted = sortPairedEntries(set.entries);
  const leader = sorted[0];
  const chasers = sorted.slice(1, 6);
  const unpriced = sorted.find((e) => e.stage_2_probability === null);
  const chaserList =
    unpriced && !chasers.includes(unpriced)
      ? [...chasers.slice(0, 4), unpriced]
      : chasers;

  const leaderS1 = formatStage1Display(leader, set, {
    simulateSettledStage1: simulateSettled,
  });
  const leaderS2 = formatStage2Display(leader, set, {
    simulateSettledStage1: simulateSettled,
  });
  const runnerUpS2 = sorted[1]?.stage_2_probability ?? 0;
  const leadMarginPts =
    renderedPercent((leader.stage_2_probability ?? 0) - runnerUpS2) ?? 0;

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

      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 border-t border-surface-border pt-2 text-xs text-text-muted">
        <span>Leader spotlight + compact chasers</span>
        <TMDBAttributionNote set={set} />
      </div>
    </article>
  );
}

// ============================================================================
// Wild Form A: Three-Spot Trophy Podium + Tier Chips (`podium_and_tiers`)
// ============================================================================

function PodiumAndTiersCard({
  set,
  simulateSettled = false,
  kidSurface = false,
}: {
  set: PairedMetricSet;
  simulateSettled?: boolean;
  kidSurface?: boolean;
}) {
  const sorted = sortPairedEntries(set.entries);
  const first = sorted[0];
  const second = sorted[1];
  const third = sorted[2];
  const remaining = sorted.slice(3);

  const lockTier = remaining.filter(
    (e) => (renderedPercent(e.stage_1_probability) ?? 0) >= 70,
  );
  const bubbleTier = remaining.filter(
    (e) => (renderedPercent(e.stage_1_probability) ?? 0) < 70,
  );

  // Order podium visual columns as #2 (left) · #1 (center, elevated) · #3 (right)
  const podiumSpots = [
    { rank: 2, badge: "#2 CHASER", entry: second, elevated: false },
    { rank: 1, badge: "#1 LEADER", entry: first, elevated: true },
    { rank: 3, badge: "#3 CONTENDER", entry: third, elevated: false },
  ];

  return (
    <article
      data-testid="visual-form-card-podium-and-tiers"
      className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>{set.kicker} · WILD FORM A</span>
        <span>PODIUM + BALLOT TIERS</span>
      </div>
      <h3 className="mt-1 text-lg font-semibold text-text-primary">{set.title}</h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        From the {sorted.length} films most likely to be nominated, the top 3 by {set.stage_2_label} % stand on a visual podium; the other 7 group into 70%+ vs &lt;70% to be nominated.
      </p>

      {/* 3-Column Podium */}
      <div className="mt-3 grid grid-cols-3 items-end gap-2">
        {podiumSpots.map(({ rank, badge, entry, elevated }) => {
          const s1 = formatStage1Display(entry, set, {
            simulateSettledStage1: simulateSettled,
          });
          const s2 = formatStage2Display(entry, set, {
            simulateSettledStage1: simulateSettled,
          });
          return (
            <div
              key={entry.subject_key}
              data-testid={`podium-spot-${rank}`}
              className={`flex flex-col items-center rounded-xl border p-2.5 text-center ${
                elevated
                  ? "border-accent-brand bg-surface-elevated pb-3.5 pt-3 shadow-sm"
                  : "border-surface-border bg-surface-elevated"
              }`}
            >
              <span
                className={`rounded px-1.5 py-0.5 text-xs font-bold ${
                  elevated
                    ? "bg-accent-brand text-text-inverse"
                    : "bg-surface-card text-text-secondary"
                }`}
              >
                {badge}
              </span>
              <div className="mt-2">
                <ArtThumb
                  entry={entry}
                  kidSurface={kidSurface}
                  size={elevated ? "lg" : "md"}
                />
              </div>
              <div className="mt-1.5 line-clamp-2 text-xs font-bold leading-tight text-text-primary">
                {entry.subject}
              </div>
              <div className="mt-1 text-base font-bold tabular-nums text-text-primary">
                {s2.label}{" "}
                <span className="text-xs font-normal text-text-muted">win</span>
              </div>
              <div className="text-xs font-medium tabular-nums text-text-secondary">
                {s1.kind === "percent" ? `${s1.label} nom` : s1.label}
              </div>
            </div>
          );
        })}
      </div>

      {/* Tier 1: Nomination Locks (70%+ Nominated, Longshot to Win) */}
      <div className="mt-3 space-y-2">
        <div className="rounded-lg border border-surface-border bg-surface-elevated p-2.5">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
            <span>Likely Nominees (70%+ to be nominated · longshot to win)</span>
            <span>NOM · WIN</span>
          </div>
          <div className="mt-2 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {lockTier.map((entry) => {
              const s1 = formatStage1Display(entry, set, {
                simulateSettledStage1: simulateSettled,
              });
              const s2 = formatStage2Display(entry, set, {
                simulateSettledStage1: simulateSettled,
              });
              return (
                <div
                  key={entry.subject_key}
                  className="flex items-center justify-between gap-2 rounded border border-surface-border bg-surface-card px-2 py-1.5"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <ArtThumb entry={entry} kidSurface={kidSurface} size="xs" />
                    <span className="truncate text-xs font-semibold text-text-primary">
                      {entry.subject}
                    </span>
                  </div>
                  <span className="shrink-0 text-xs tabular-nums text-text-secondary">
                    {s1.label} →{" "}
                    <strong className="text-text-primary">{s2.label}</strong>
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Tier 2: Bubble Watch (<70% Nominated) */}
        <div className="rounded-lg border border-surface-border bg-surface-elevated p-2.5">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
            <span>On the Nomination Bubble (&lt;70% to be nominated)</span>
            <span>NOM · WIN</span>
          </div>
          <div className="mt-2 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {bubbleTier.map((entry) => {
              const s1 = formatStage1Display(entry, set, {
                simulateSettledStage1: simulateSettled,
              });
              const s2 = formatStage2Display(entry, set, {
                simulateSettledStage1: simulateSettled,
              });
              return (
                <div
                  key={entry.subject_key}
                  className="flex items-center justify-between gap-2 rounded border border-surface-border bg-surface-card px-2 py-1.5"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <ArtThumb entry={entry} kidSurface={kidSurface} size="xs" />
                    <span className="truncate text-xs font-semibold text-text-primary">
                      {entry.subject}
                    </span>
                  </div>
                  {s2.kind === "percent" ? (
                    <span className="shrink-0 text-xs tabular-nums text-text-secondary">
                      {s1.label} →{" "}
                      <strong className="text-text-primary">{s2.label}</strong>
                    </span>
                  ) : (
                    <span
                      data-testid="missing-probability-notice"
                      className="shrink-0 text-xs font-medium text-text-muted"
                    >
                      {s1.label} · {s2.label}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-surface-border pt-2 text-xs text-text-muted">
        <span>3-spot podium + 2 ballot tiers</span>
        <TMDBAttributionNote set={set} />
      </div>
    </article>
  );
}

// ============================================================================
// Wild Form B: 0–100% Barbell Gap Track (`barbell_race_track`)
// ============================================================================

function BarbellRaceTrackCard({
  set,
  simulateSettled = false,
  kidSurface = false,
}: {
  set: PairedMetricSet;
  simulateSettled?: boolean;
  kidSurface?: boolean;
}) {
  const rows = sortPairedEntries(set.entries);
  return (
    <article
      data-testid="visual-form-card-barbell-race-track"
      className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>{set.kicker} · WILD FORM B</span>
        <span>0–100% BARBELL GAP TRACK</span>
      </div>
      <h3 className="mt-1 text-lg font-semibold text-text-primary">{set.title}</h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        For the {rows.length} films most likely to be nominated, each film&apos;s {set.stage_2_label} % (green dot) and {set.stage_1_label} % (dark dot) sit on one 0–100% axis; the connecting span shows the ballot-to-trophy gap.
      </p>

      {/* Scale Header */}
      <div className="mt-3 flex items-center justify-between border-b border-surface-border pb-1 text-xs font-medium tabular-nums text-text-muted">
        <span>0%</span>
        <span>25%</span>
        <span>50%</span>
        <span>75%</span>
        <span>100%</span>
      </div>

      <div className="divide-y divide-surface-border">
        {rows.map((entry, idx) => {
          const s1 = formatStage1Display(entry, set, {
            simulateSettledStage1: simulateSettled,
          });
          const s2 = formatStage2Display(entry, set, {
            simulateSettledStage1: simulateSettled,
          });
          const s1Pos =
            s1.kind === "tick"
              ? 100
              : s1.kind === "percent" && s1.percent !== null
                ? s1.percent
                : null;
          const s2Pos =
            s2.kind === "percent" && s2.percent !== null ? s2.percent : null;
          const leftPos =
            s1Pos !== null && s2Pos !== null ? Math.min(s1Pos, s2Pos) : null;
          const spanWidth =
            s1Pos !== null && s2Pos !== null ? Math.abs(s1Pos - s2Pos) : null;

          return (
            <div
              key={entry.subject_key}
              data-testid={`barbell-row-${idx + 1}`}
              className="py-2"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <ArtThumb entry={entry} kidSurface={kidSurface} size="xs" />
                  <span className="truncate text-xs font-semibold text-text-primary">
                    {entry.subject}
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-1.5 text-xs tabular-nums">
                  {s2.kind === "percent" ? (
                    <span className="font-bold text-text-primary">
                      {s2.label} win
                    </span>
                  ) : (
                    <span
                      data-testid="missing-probability-notice"
                      className="font-medium text-text-muted"
                    >
                      {s2.label}
                    </span>
                  )}
                  <span className="text-text-muted">·</span>
                  <span className="text-text-secondary">
                    {s1.kind === "percent" ? `${s1.label} nom` : s1.label}
                  </span>
                </div>
              </div>

              {/* 0–100% Barbell Axis */}
              <div className="relative mt-1.5 h-3 w-full rounded-full bg-surface-elevated">
                {leftPos !== null && spanWidth !== null && (
                  <div
                    className="absolute top-1 h-1 rounded-full bg-text-muted"
                    style={{
                      left: `${leftPos}%`,
                      width: `${Math.max(2, spanWidth)}%`,
                    }}
                  />
                )}
                {s2Pos !== null && (
                  <div
                    data-testid="barbell-win-dot"
                    className="absolute top-0.5 h-2 w-2 -translate-x-1/2 rounded-full bg-accent-brand"
                    style={{ left: `${Math.max(2, Math.min(98, s2Pos))}%` }}
                  />
                )}
                {s1Pos !== null && (
                  <div
                    data-testid="barbell-nom-dot"
                    className="absolute top-0.5 h-2 w-2 -translate-x-1/2 rounded-full border border-surface-card bg-text-primary"
                    style={{ left: `${Math.max(2, Math.min(98, s1Pos))}%` }}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 border-t border-surface-border pt-2 text-xs text-text-muted">
        <span>Green dot = {set.stage_2_label} % · Dark dot = {set.stage_1_label} %</span>
        <TMDBAttributionNote set={set} />
      </div>
    </article>
  );
}

// ============================================================================
// Wild Form C: 2×2 Ballot Quadrant Board (`ballot_quadrant_map`)
// ============================================================================

function BallotQuadrantMapCard({
  set,
  simulateSettled = false,
  kidSurface = false,
}: {
  set: PairedMetricSet;
  simulateSettled?: boolean;
  kidSurface?: boolean;
}) {
  const sorted = sortPairedEntries(set.entries);
  const s1Printed = (e: PairedSubjectEntry) =>
    renderedPercent(e.stage_1_probability) ?? 0;
  const s2Printed = (e: PairedSubjectEntry) =>
    renderedPercent(e.stage_2_probability) ?? 0;

  const favorites = sorted.filter(
    (e) => s1Printed(e) >= 75 && s2Printed(e) >= 10,
  );
  const safeNominees = sorted.filter(
    (e) => s1Printed(e) >= 75 && s2Printed(e) < 10,
  );
  const likelyNominees = sorted.filter(
    (e) => s1Printed(e) >= 65 && s1Printed(e) < 75,
  );
  const bubbleWatch = sorted.filter((e) => s1Printed(e) < 65);

  const quadrants = [
    {
      key: "favorites",
      title: "Trophy Favorites",
      rule: "75%+ nom · 10%+ win",
      items: favorites,
    },
    {
      key: "safe-nominees",
      title: "Safe Nominees · Longshot Win",
      rule: "75%+ nom · <10% win",
      items: safeNominees,
    },
    {
      key: "likely-nominees",
      title: "Likely Nominees",
      rule: "65–74% nom",
      items: likelyNominees,
    },
    {
      key: "bubble-watch",
      title: "On the Bubble",
      rule: "<65% nom",
      items: bubbleWatch,
    },
  ];

  return (
    <article
      data-testid="visual-form-card-ballot-quadrant-map"
      className="rounded-xl border border-surface-border bg-surface-card p-4 shadow-sm"
    >
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>{set.kicker} · WILD FORM C</span>
        <span>2×2 BALLOT QUADRANT BOARD</span>
      </div>
      <h3 className="mt-1 text-lg font-semibold text-text-primary">{set.title}</h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        Maps the {sorted.length} films most likely to be nominated into four spatial zones by their printed ({set.stage_1_label} %, {set.stage_2_label} %) numbers.
      </p>

      <div className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {quadrants.map((q) => (
          <div
            key={q.key}
            data-testid={`quadrant-${q.key}`}
            className="rounded-lg border border-surface-border bg-surface-elevated p-2.5"
          >
            <div className="flex items-baseline justify-between border-b border-surface-border pb-1.5">
              <span className="text-xs font-bold text-text-primary">
                {q.title}
              </span>
              <span className="text-xs text-text-muted">{q.rule}</span>
            </div>
            <div className="mt-2 space-y-1.5">
              {q.items.map((entry) => {
                const s1 = formatStage1Display(entry, set, {
                  simulateSettledStage1: simulateSettled,
                });
                const s2 = formatStage2Display(entry, set, {
                  simulateSettledStage1: simulateSettled,
                });
                return (
                  <div
                    key={entry.subject_key}
                    className="flex items-center justify-between gap-2 rounded border border-surface-border bg-surface-card p-1.5"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <ArtThumb entry={entry} kidSurface={kidSurface} size="xs" />
                      <div className="min-w-0">
                        <div className="truncate text-xs font-semibold text-text-primary">
                          {entry.subject}
                        </div>
                        <div className="truncate text-xs text-text-muted">
                          {entry.detail}
                        </div>
                      </div>
                    </div>
                    <div className="shrink-0 text-right text-xs tabular-nums">
                      {s2.kind === "percent" ? (
                        <div className="font-bold text-text-primary">
                          {s2.label} win
                        </div>
                      ) : (
                        <div
                          data-testid="missing-probability-notice"
                          className="font-medium text-text-muted"
                        >
                          {s2.label}
                        </div>
                      )}
                      <div className="text-text-secondary">
                        {s1.kind === "percent" ? `${s1.label} nom` : s1.label}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-surface-border pt-2 text-xs text-text-muted">
        <span>2×2 spatial quadrant classification</span>
        <TMDBAttributionNote set={set} />
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
      ...set.entries[5], // Artificial (was 58% nom)
      stage_1_settled_state: "no",
    },
    {
      ...set.entries[9], // I Play Rocky (was 49% nom)
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

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-surface-border pt-2 text-xs text-text-muted">
        <span>Settled step 1 preview</span>
        <TMDBAttributionNote set={set} />
      </div>
    </article>
  );
}

// ============================================================================
// Single Look-Sheet Card Renderer (Used by both Gallery and 1-by-1 Grading)
// ============================================================================

export const renderLookSheetCardBySpec = (
  spec: LookSheetCardSpec,
  options?: {
    simulateSettled?: boolean;
    kidSurface?: boolean;
    pairedMetricSet?: PairedMetricSet | null;
    pairedMetricSets?: Record<string, PairedMetricSet> | null;
  },
) => {
  const set =
    options?.pairedMetricSet ??
    options?.pairedMetricSets?.[spec.set_id] ??
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
          maxRows={spec.set_id === "oscars-2027-best-picture" ? 10 : 9}
        />
      );
    case "paired_bars_top5_expandable":
      return (
        <PairedBarsTop5ExpandableCard
          set={set}
          simulateSettled={settled}
          kidSurface={kid}
        />
      );
    case "paired_bars_single_line":
      return (
        <PairedBarsSingleLineCard
          set={set}
          simulateSettled={settled}
          kidSurface={kid}
        />
      );
    case "paired_bars_top3_plus_strip":
      return (
        <PairedBarsTop3PlusStripCard
          set={set}
          simulateSettled={settled}
          kidSurface={kid}
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
    case "podium_and_tiers":
      return (
        <PodiumAndTiersCard
          set={set}
          simulateSettled={settled}
          kidSurface={kid}
        />
      );
    case "barbell_race_track":
      return (
        <BarbellRaceTrackCard
          set={set}
          simulateSettled={settled}
          kidSurface={kid}
        />
      );
    case "ballot_quadrant_map":
      return (
        <BallotQuadrantMapCard
          set={set}
          simulateSettled={settled}
          kidSurface={kid}
        />
      );
    case "settled_gate_after_nominations":
      return <SettledGateAfterNominationsCard set={set} kidSurface={kid} />;
  }
};

// ============================================================================
// Part 2: Three Oscars Container Layouts (#12523)
// ============================================================================

export function OscarsContainerLayoutPreview({
  spec,
  simulateSettled = false,
  kidSurface = false,
  pairedMetricSets = null,
}: {
  spec: ContainerLookSheetSpec;
  simulateSettled?: boolean;
  kidSurface?: boolean;
  pairedMetricSets?: Record<string, PairedMetricSet> | null;
}) {
  const picSet =
    pairedMetricSets?.["oscars-2027-best-picture"] ??
    PAIRED_METRIC_REGISTER["oscars-2027-best-picture"];
  const dirSet =
    pairedMetricSets?.["oscars-2027-best-director"] ??
    PAIRED_METRIC_REGISTER["oscars-2027-best-director"];
  const actSet =
    pairedMetricSets?.["oscars-2027-best-actor"] ??
    PAIRED_METRIC_REGISTER["oscars-2027-best-actor"];
  const actressSet =
    pairedMetricSets?.["oscars-2027-best-actress"] ??
    PAIRED_METRIC_REGISTER["oscars-2027-best-actress"];
  const animSet =
    pairedMetricSets?.["oscars-2027-best-animated"] ??
    PAIRED_METRIC_REGISTER["oscars-2027-best-animated"];

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
              {
                cat: "Best Animated Feature",
                entry: animSet.entries[0],
                set: animSet,
                chaser: "Toy Story 5 (5% win · 85% nom)",
              },
              {
                cat: "Best Actress",
                entry: actressSet.entries[0],
                set: actressSet,
                chaser: "Inde Navarrette (17% win · 78% nom)",
              },
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

        {/* Tier 3: Top-5 Expandable Best Picture Board */}
        <PairedBarsTop5ExpandableCard
          set={picSet}
          simulateSettled={simulateSettled}
          kidSurface={kidSurface}
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
    { label: "John Malkovich", cat: "Actor", pct: "96%", entry: actSet.entries[0] },
    { label: "The Black Ball", cat: "Picture", pct: "95%", entry: picSet.entries[2] },
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
  options?: {
    simulateSettled?: boolean;
    kidSurface?: boolean;
    pairedMetricSet?: PairedMetricSet | null;
    pairedMetricSets?: Record<string, PairedMetricSet> | null;
  },
): React.ReactNode | null => {
  const allCards = [...VISUAL_FORM_LOOK_SHEET_CARDS, ...VISUAL_FORM_SHEET_2_CARDS];
  const cardSpec = allCards.find((c) => c.item_key === itemKey);
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
          pairedMetricSets={options?.pairedMetricSets ?? null}
        />
      </div>
    );
  }
  return null;
};

// ============================================================================
// Full Look Sheet Gallery View (Sheet 2 + Sheet 1 + 3 Containers on One Page)
// ============================================================================

export interface VisualFormLookSheetGalleryProps {
  kidSurface?: boolean;
  grader?: string | null;
  existingGradesByItemKey?: Record<string, GroupingGrade>;
  pairedMetricSets?: Record<string, PairedMetricSet> | null;
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
  pairedMetricSets = null,
  onGradeItem,
  savingItemKey = null,
}: VisualFormLookSheetGalleryProps) {
  const [simulateSettled, setSimulateSettled] = useState(false);
  const [notesByKey, setNotesByKey] = useState<Record<string, string>>({});

  const renderGradableCardBlock = (spec: LookSheetCardSpec) => {
    const currentGrade = existingGradesByItemKey[spec.item_key];
    const itemNote = notesByKey[spec.item_key] ?? "";
    return (
      <div
        key={spec.item_key}
        data-testid={`look-sheet-card-block-${spec.block_id}`}
        className="rounded-xl border border-surface-border bg-surface-elevated p-3.5"
      >
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <h4 className="text-sm font-bold text-text-primary">{spec.label}</h4>
          <span className="text-xs font-medium text-text-muted">
            Deck pos #{spec.position}
          </span>
        </div>
        <p className="mb-2 text-xs text-text-secondary">{spec.why_it_exists}</p>
        <FormContractHeader form={spec.form} />
        {renderLookSheetCardBySpec(spec, {
          simulateSettled,
          kidSurface,
          pairedMetricSets,
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
  };

  return (
    <div className="space-y-6" data-testid="visual-forms-look-sheet-gallery">
      {/* Header & Global Controls */}
      <div className="rounded-xl border border-surface-border bg-surface-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-accent-brand">
              #12577 / #12523 · VISUAL FORM LIBRARY LOOK SHEET (SHEET 1 + SHEET 2)
            </div>
            <h2 className="mt-0.5 text-lg font-bold text-text-primary">
              Shorter versions of Card 1, three wilder visual forms, baseline forms, and three Oscars container rhythms
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
            • <span className="font-semibold text-text-primary">Two distinct numbers per film (server-computed venue average):</span>{" "}
            Best Picture Nominee % averages #5165726 and #27988771 across venues on the server via <code className="font-mono">futures_source_merge.blend_with_verdict</code> (<code className="font-mono">backend/app/services/paired_metric_register.py</code>); Nominee % and Winner % (#6173044) are paired in <code className="font-mono">paired_metric_register.json</code> as two separate propositions.
          </li>
          <li>
            • <span className="font-semibold text-text-primary">One rounding rule &amp; selection-carrying titles:</span>{" "}
            Uses <code className="font-mono">renderedPercent</code> (#1933 / #3867) so half-percents (<span className="font-medium text-text-primary">0.955 → 96%</span>, <span className="font-medium text-text-primary">0.935 → 94%</span>) always round half-up; NHL includes all 9 clubs at 5%+ (<span className="font-medium text-text-primary">Dallas Stars 84%/5%</span> alongside <span className="font-medium text-text-primary">Tampa Bay Lightning 82%/5%</span>).
          </li>
          <li>
            • <span className="font-semibold text-text-primary">Sourced TMDB credits, verified headshots &amp; official TMDB notice + logo:</span>{" "}
            Film credits and person headshots are verified against TMDB (<span className="font-medium text-text-primary">Jesse Eisenberg</span> on <em>The Debut</em>, <span className="font-medium text-text-primary">Nathan Fielder #1212667</span> on <em>You Can See Everything</em>) and carry the required TMDB attribution notice and official TMDB logo mark linked to <code className="font-mono">themoviedb.org</code>.
          </li>
        </ul>
      </div>

      {/* Sheet 2 Section: 3 Shorter Versions of Card 1 + 3 Wilder Visual Forms */}
      <div className="space-y-4" data-testid="visual-forms-sheet-2-section">
        <h3 className="text-base font-bold text-text-primary">
          Sheet 2 · Three Shorter Versions of Card 1 (1A–1C) + Three Wilder Visual Forms (Podium, Barbell Track, 2×2 Quadrant Board)
        </h3>
        {VISUAL_FORM_SHEET_2_CARDS.map(renderGradableCardBlock)}
      </div>

      {/* Sheet 1 Section: Original 6 Visual Form Cards */}
      <div className="space-y-4" data-testid="visual-forms-sheet-1-section">
        <h3 className="text-base font-bold text-text-primary">
          Sheet 1 · Six Baseline Visual Forms for &ldquo;Two Related Numbers per Subject&rdquo;
        </h3>
        {VISUAL_FORM_LOOK_SHEET_CARDS.map(renderGradableCardBlock)}
      </div>

      {/* Part 2: 3 Oscars Container Layouts (#12523) */}
      <div className="space-y-4">
        <h3 className="text-base font-bold text-text-primary">
          Containers (#12523) · Three Ways an Oscars Container Can Look When Rows Don&apos;t All Look the Same
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
                pairedMetricSets={pairedMetricSets}
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
