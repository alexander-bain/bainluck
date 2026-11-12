"use client";

/**
 * #12609 — The NFL Playoffs and Super Bowl Container Look Sheet (Step 1).
 *
 * Renders the 6 distinct sections + 1 full composed container preview for
 * Alex to grade on `/grade/groupings?slate=nfl-playoffs-look-sheet-2026-11`
 * (or `?view=nfl-look-sheet`) at 390 px on real live NFL numbers:
 *   1. Make the Playoffs % beside Win the Super Bowl % (with ESPN team crests,
 *      top 6 + full-width expander for all 12 clubs in the hunt).
 *   2. AFC & NFC Conference Championship Conversion Funnels (Reach Conference
 *      Final % → Win Conference %).
 *   3. Division Races Chosen by Distribution Shape (4-Way Scrambles vs 2-Team
 *      Duels vs 90% Locks).
 *   4. NFL MVP & Offensive Player of the Year Spotlight (Circular ESPN player
 *      headshots + Finalist % beside Winner %).
 *   5. This Week's Games That Move the Playoff Picture Most (Blended Win % +
 *      Playoff & Division Stakes).
 *   6. The "Too Many Props" Section on a Real Full NFL Prop Board (Pittsburgh
 *      Steelers at Cincinnati Bengals — 671 live game markets / 384 player prop
 *      lines: 3-lens first screen + category Milestone Ladder drawer behind a
 *      toggle).
 *   7. Full Composed Container Preview (all 6 sections in one 390 px vertical
 *      scroll where adjacent sections never share a form).
 *
 * Design-system compliance: light-mode tokens only (`bg-surface-*`, `text-text-*`,
 * `border-surface-border`, `text-accent-*`). Zero raw hexes, zero dark classes,
 * zero internal market IDs on card faces, and never calls a market a "question".
 */

import React, { useState } from "react";
import {
  NFL_CONFERENCE_PATH_ENTRIES,
  NFL_DIVISION_RACES_BY_SHAPE,
  NFL_MVP_CANDIDATES,
  NFL_OPOY_CANDIDATES,
  NFL_PLAYOFFS_LOOK_SHEET_ITEMS,
  NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS,
  NFL_SWING_GAMES_THIS_WEEK,
  STEELERS_BENGALS_PROP_BOARD,
  formatPct,
  resolveNflKidSafeArt,
  type NflArtAsset,
  type NflLookSheetContract,
  type NflLookSheetItemSpec,
  type NflPropDrawerCategoryKey,
} from "@/lib/discover/nflPlayoffsLookSheet";
import {
  GROUPING_GRADES,
  GROUPING_GRADE_LABELS,
  type GroupingGrade,
} from "@/lib/ranking/groupingGradeSession";
import { renderedPercent } from "@/lib/renderedPercent";

interface NflArtBadgeProps {
  subject: string;
  detail: string;
  art: NflArtAsset | null | undefined;
  fallbackText: string;
  kidSurface?: boolean;
  size?: "xs" | "sm" | "md" | "lg";
}

function NflArtBadge({
  subject,
  detail,
  art,
  fallbackText,
  kidSurface = false,
  size = "md",
}: NflArtBadgeProps) {
  const safeUrl = resolveNflKidSafeArt(subject, detail, art, { kidSurface });
  const isHeadshot = art?.kind === "espn_player_headshot";

  const dim =
    size === "lg"
      ? "h-12 w-12"
      : size === "sm"
        ? "h-7 w-7"
        : size === "xs"
          ? "h-5 w-5"
          : "h-9 w-9";

  if (safeUrl) {
    return (
      <img
        src={safeUrl}
        alt={subject}
        data-testid={isHeadshot ? "nfl-look-art-headshot" : "nfl-look-art-logo"}
        className={`${dim} shrink-0 rounded-full border border-surface-border bg-surface-elevated ${
          isHeadshot ? "object-cover" : "object-contain p-0.5"
        }`}
      />
    );
  }

  return (
    <div
      data-testid="nfl-look-art-fallback"
      className={`${dim} flex shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-xs font-bold text-text-secondary`}
    >
      {fallbackText.slice(0, 3).toUpperCase()}
    </div>
  );
}

function NflFormContractHeader({ form }: { form: NflLookSheetContract }) {
  return (
    <div
      className="mb-2 rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-xs"
      data-testid={`nfl-form-contract-${form.form_id}`}
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
// Section 1: Make Playoffs % beside Win Super Bowl % (Top 6 + Expander for 12)
// ============================================================================

export function NflPlayoffsToSuperBowlSectionCard({
  simulateSettled = false,
  kidSurface = false,
  defaultExpanded = false,
}: {
  simulateSettled?: boolean;
  kidSurface?: boolean;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const clubs = NFL_PLAYOFFS_TO_SUPER_BOWL_CLUBS;
  const visibleClubs = expanded ? clubs : clubs.slice(0, 6);
  const hiddenCount = clubs.length - 6;

  return (
    <div
      data-testid="nfl-section-1-playoffs-super-bowl"
      className="rounded-xl border border-surface-border bg-surface-card p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-1 text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>NFL PLAYOFFS &amp; SUPER BOWL LXI · PAIRED DUAL BARS</span>
        <span>RESOLVES FEB 14, 2027</span>
      </div>
      <h3 className="mt-1 text-lg font-bold text-text-primary">
        Make the Playoffs % beside Win the Super Bowl %
      </h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        All 12 NFL clubs at 4%+ Super Bowl chance, ordered by Super Bowl %. Top 6 shown first; Make Playoffs % and Win Super Bowl % are kept separate and never blended.
      </p>

      <div className="mt-3 divide-y divide-surface-border">
        {visibleClubs.map((club, idx) => {
          const playoffPct = renderedPercent(club.make_playoffs_probability) ?? 0;
          const sbPct = renderedPercent(club.win_super_bowl_probability) ?? 0;
          const clinched = club.make_playoffs_probability >= 0.70;
          return (
            <div
              key={club.club_key}
              data-testid={`nfl-paired-row-${idx + 1}`}
              className="flex items-center gap-3 py-2.5"
            >
              <NflArtBadge
                subject={club.team}
                detail={`${club.division} · ${club.record}`}
                art={club.logo}
                fallbackText={club.abbreviation}
                kidSurface={kidSurface}
                size="md"
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
                  <span className="text-xs font-bold text-text-primary sm:text-sm">
                    {club.team}
                  </span>
                  <span className="shrink-0 text-xs font-medium text-text-muted">
                    {club.division} · {club.record}
                  </span>
                </div>

                <div className="mt-1.5 space-y-1.5">
                  {/* Stage 1: Make Playoffs % (or ✓ Clinched / ✗ Eliminated) */}
                  <div className="flex items-center gap-2">
                    <span className="w-24 shrink-0 text-xs text-text-secondary">
                      Make Playoffs
                    </span>
                    {!simulateSettled ? (
                      <>
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-elevated">
                          <div
                            className="h-full rounded-full bg-text-muted"
                            style={{ width: `${Math.max(4, playoffPct)}%` }}
                          />
                        </div>
                        <span className="w-11 text-right text-xs font-semibold tabular-nums text-text-secondary">
                          {playoffPct}%
                        </span>
                      </>
                    ) : clinched ? (
                      <span
                        data-testid="nfl-settled-clinched"
                        className="inline-flex items-center rounded bg-surface-elevated px-2 py-0.5 text-xs font-semibold text-accent-positive"
                      >
                        ✓ Clinched playoff berth
                      </span>
                    ) : (
                      <span
                        data-testid="nfl-settled-eliminated"
                        className="inline-flex items-center rounded bg-surface-elevated px-2 py-0.5 text-xs font-medium text-text-muted line-through"
                      >
                        ✗ Missed playoffs
                      </span>
                    )}
                  </div>

                  {/* Stage 2: Win Super Bowl % */}
                  <div className="flex items-center gap-2">
                    <span className="w-24 shrink-0 text-xs font-medium text-text-primary">
                      Win Super Bowl
                    </span>
                    <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-elevated">
                      <div
                        className="h-full rounded-full bg-accent-brand"
                        style={{
                          width: `${
                            simulateSettled && !clinched ? 0 : Math.max(4, sbPct * 3)
                          }%`,
                        }}
                      />
                    </div>
                    <span className="w-11 text-right text-sm font-bold tabular-nums text-text-primary">
                      {simulateSettled && !clinched ? "0%" : `${sbPct}%`}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Prominent Full-Width Primary Expander Bar (#12600 pattern) */}
      <div className="mt-3 rounded-xl border border-accent-brand bg-surface-elevated p-2.5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-xs text-text-secondary">
            {expanded ? (
              <span>
                Showing <span className="font-semibold text-text-primary">all 12 NFL clubs</span> at 4%+ Super Bowl chance
              </span>
            ) : (
              <span>
                Showing <span className="font-semibold text-text-primary">top 6 of 12 clubs</span> · Next: Rams (46%/6%), Broncos (92%/5%), Seahawks (51%/5%), Lions (77%/4%)
              </span>
            )}
          </div>
          <button
            type="button"
            data-testid="nfl-section-1-expand-button"
            onClick={() => setExpanded((prev) => !prev)}
            className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-accent-brand px-3.5 py-2 text-xs font-bold text-text-inverse shadow-sm sm:w-auto"
          >
            <span>
              {expanded
                ? "Collapse to top 6 clubs"
                : `Show all 12 clubs in the hunt (+${hiddenCount} more)`}
            </span>
            <span aria-hidden="true">{expanded ? "▴" : "▾"}</span>
          </button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-surface-border pt-2.5 text-xs text-text-muted">
        <span>
          Playoff berth and Super Bowl winner are paired by club and kept separate.
        </span>
        <span>Updated Nov 11, 2026</span>
      </div>
    </div>
  );
}

// ============================================================================
// Section 2: AFC & NFC Conference Championship Conversion Funnels
// ============================================================================

export function NflConferencePathsSectionCard({
  simulateSettled = false,
  kidSurface = false,
}: {
  simulateSettled?: boolean;
  kidSurface?: boolean;
}) {
  const afc = NFL_CONFERENCE_PATH_ENTRIES.filter((e) => e.conference === "AFC");
  const nfc = NFL_CONFERENCE_PATH_ENTRIES.filter((e) => e.conference === "NFC");

  const renderConferenceColumn = (
    confLabel: string,
    subtitle: string,
    entries: typeof afc,
  ) => (
    <div
      key={confLabel}
      data-testid={`nfl-conference-funnel-${confLabel.toLowerCase()}`}
      className="rounded-xl border border-surface-border bg-surface-elevated p-3"
    >
      <div className="flex items-center justify-between border-b border-surface-border pb-2">
        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-accent-brand">
            {confLabel} PATH TO SUPER BOWL LXI
          </div>
          <div className="text-xs text-text-secondary">{subtitle}</div>
        </div>
        <span className="rounded border border-surface-border bg-surface-card px-2 py-0.5 text-xs font-semibold text-text-secondary">
          Reach → Win {confLabel}
        </span>
      </div>

      <div className="mt-2.5 space-y-2.5">
        {entries.map((entry) => {
          const reachPct = renderedPercent(entry.reach_conf_final_probability) ?? 0;
          const winPct = renderedPercent(entry.win_conference_probability) ?? 0;
          return (
            <div
              key={entry.club_key}
              className="rounded-lg border border-surface-border bg-surface-card p-2.5"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <NflArtBadge
                    subject={entry.team}
                    detail={entry.detail}
                    art={entry.logo}
                    fallbackText={entry.abbreviation}
                    kidSurface={kidSurface}
                    size="sm"
                  />
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-text-primary sm:text-sm">
                      {entry.team}
                    </div>
                    <div className="text-xs text-text-muted">
                      {entry.detail}
                    </div>
                  </div>
                </div>
                <div className="shrink-0 text-right tabular-nums">
                  <div className="text-sm font-bold text-text-primary">
                    {winPct}% win {confLabel}
                  </div>
                  <div className="text-xs text-text-secondary">
                    {simulateSettled && reachPct >= 34
                      ? `✓ In ${confLabel} Final`
                      : `${reachPct}% reach`}
                  </div>
                </div>
              </div>

              {/* Nested Funnel Bar: Outer = Reach Conference Final %, Inner = Win Conference % */}
              <div className="mt-2">
                <div className="relative h-3 w-full overflow-hidden rounded-full bg-surface-elevated">
                  <div
                    className="h-full rounded-full bg-surface-border"
                    style={{ width: `${Math.max(8, reachPct)}%` }}
                    title={`Reach ${confLabel} Championship: ${reachPct}%`}
                  />
                  <div
                    className="absolute inset-y-0 left-0 rounded-full bg-accent-brand"
                    style={{ width: `${Math.max(4, winPct)}%` }}
                    title={`Win ${confLabel} Championship: ${winPct}%`}
                  />
                </div>
                <div className="mt-1 flex items-center justify-between text-xs text-text-muted">
                  <span>Outer reach: {reachPct}%</span>
                  <span>
                    Converts {Math.round((winPct / Math.max(1, reachPct)) * 100)}% if in title game
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );

  return (
    <div
      data-testid="nfl-section-2-conference-paths"
      className="rounded-xl border border-surface-border bg-surface-card p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-1 text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>CONFERENCE CHAMPIONSHIPS · TWO-STEP CONVERSION FUNNELS</span>
        <span>JAN 31, 2027</span>
      </div>
      <h3 className="mt-1 text-lg font-bold text-text-primary">
        Who gets through the AFC &amp; NFC brackets?
      </h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        Outer bar shows chance to reach the Conference Championship Game; inner fill shows blended chance to win the conference trophy.
      </p>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        {renderConferenceColumn(
          "AFC",
          "Bills (25%) & Jaguars (21%) lead a 5-team pack",
          afc,
        )}
        {renderConferenceColumn(
          "NFC",
          "49ers (28%) & Bears (18%) pace the conference",
          nfc,
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Section 3: Division Races Chosen by Distribution Shape
// ============================================================================

export function NflDivisionRacesByShapeSectionCard({
  kidSurface = false,
}: {
  kidSurface?: boolean;
}) {
  const scrambles = NFL_DIVISION_RACES_BY_SHAPE.filter(
    (d) => d.shape === "four_way_scramble",
  );
  const duels = NFL_DIVISION_RACES_BY_SHAPE.filter(
    (d) => d.shape === "two_team_duel",
  );
  const locks = NFL_DIVISION_RACES_BY_SHAPE.filter(
    (d) => d.shape === "near_lock",
  );

  return (
    <div
      data-testid="nfl-section-3-division-races"
      className="rounded-xl border border-surface-border bg-surface-card p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-1 text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>DIVISION RACES · SHAPE-DRIVEN CONTRAST (#12523)</span>
        <span>4-WAY SCRAMBLES · 2-HORSE DUELS · 90% LOCKS</span>
      </div>
      <h3 className="mt-1 text-lg font-bold text-text-primary">
        The shape of the division race picks the visual form
      </h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        Wide-open 4-team scrambles get 4-club comparison grids, 2-horse races get head-to-head tug-of-war bars, and 89–90% division leaders compress into lock chips.
      </p>

      {/* Tier 1: Wide-Open 4-Way Scrambles (NFC North & NFC South) */}
      <div className="mt-3 space-y-2.5">
        <div className="text-xs font-bold uppercase tracking-wide text-accent-brand">
          1. Wide-Open Four-Team Scrambles (Leader &lt; 40%)
        </div>
        <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
          {scrambles.map((div) => (
            <div
              key={div.division}
              data-testid={`nfl-division-scramble-${div.division.toLowerCase().replace(/\s+/g, "-")}`}
              className="rounded-xl border border-surface-border bg-surface-elevated p-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-text-primary">
                  {div.division}
                </span>
                <span className="rounded border border-surface-border bg-surface-card px-2 py-0.5 text-xs font-semibold text-text-secondary">
                  4-Way Race
                </span>
              </div>
              <p className="mt-0.5 text-xs text-text-muted">{div.summary_note}</p>

              <div className="mt-2.5 grid grid-cols-2 gap-2">
                {div.candidates.map((c) => {
                  const pct = renderedPercent(c.probability) ?? 0;
                  return (
                    <div
                      key={c.abbreviation}
                      className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-card p-2"
                    >
                      <NflArtBadge
                        subject={c.team}
                        detail={div.division}
                        art={c.logo}
                        fallbackText={c.abbreviation}
                        kidSurface={kidSurface}
                        size="sm"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-semibold leading-tight text-text-primary">
                          {c.team.split(" ").slice(-1)[0]}
                        </div>
                        <div className="text-sm font-bold tabular-nums text-text-primary">
                          {pct}%
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tier 2: Two-Horse Division Duels (AFC West, NFC East, AFC North) */}
      <div className="mt-4 space-y-2.5">
        <div className="text-xs font-bold uppercase tracking-wide text-accent-brand">
          2. Two-Team Division Duels (Leader 55%–64%)
        </div>
        <div className="space-y-2">
          {duels.map((div) => {
            const c1 = div.candidates[0];
            const c2 = div.candidates[1];
            const c3 = div.candidates[2];
            const p1 = renderedPercent(c1.probability) ?? 0;
            const p2 = renderedPercent(c2.probability) ?? 0;
            const p3 = c3 ? renderedPercent(c3.probability) : null;
            const leftShare = Math.round((p1 / Math.max(1, p1 + p2)) * 100);
            return (
              <div
                key={div.division}
                data-testid={`nfl-division-duel-${div.division.toLowerCase().replace(/\s+/g, "-")}`}
                className="rounded-xl border border-surface-border bg-surface-elevated p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-1">
                  <span className="text-sm font-bold text-text-primary">
                    {div.division}
                  </span>
                  <span className="text-xs text-text-muted">{div.summary_note}</span>
                </div>

                <div className="mt-2 flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <NflArtBadge
                      subject={c1.team}
                      detail={div.division}
                      art={c1.logo}
                      fallbackText={c1.abbreviation}
                      kidSurface={kidSurface}
                      size="sm"
                    />
                    <div className="min-w-0">
                      <span className="block text-xs font-bold leading-tight text-text-primary">
                        {c1.team}
                      </span>
                      <span className="text-sm font-bold tabular-nums text-accent-brand">
                        {p1}%
                      </span>
                    </div>
                  </div>

                  <div className="flex min-w-0 items-center gap-2 text-right">
                    <div className="min-w-0">
                      <span className="block text-xs font-semibold leading-tight text-text-primary">
                        {c2.team}
                      </span>
                      <span className="text-sm font-bold tabular-nums text-text-secondary">
                        {p2}%
                      </span>
                    </div>
                    <NflArtBadge
                      subject={c2.team}
                      detail={div.division}
                      art={c2.logo}
                      fallbackText={c2.abbreviation}
                      kidSurface={kidSurface}
                      size="sm"
                    />
                  </div>
                </div>

                <div className="mt-2 flex h-2.5 w-full overflow-hidden rounded-full bg-surface-card">
                  <div
                    className="h-full bg-accent-brand"
                    style={{ width: `${leftShare}%` }}
                  />
                  <div
                    className="h-full bg-text-muted"
                    style={{ width: `${100 - leftShare}%` }}
                  />
                </div>
                {c3 && p3 !== null && (
                  <div className="mt-1 text-xs text-text-muted">
                    Also in {div.division}: {c3.team} ({p3}%)
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Tier 3: Division Near-Locks (Leader >= 88%) */}
      <div className="mt-4 space-y-2">
        <div className="text-xs font-bold uppercase tracking-wide text-accent-brand">
          3. Division Near-Locks (Leader &ge; 88%)
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {locks.map((div) => {
            const leader = div.candidates[0];
            const chaser = div.candidates[1];
            return (
              <div
                key={div.division}
                data-testid={`nfl-division-lock-${div.division.toLowerCase().replace(/\s+/g, "-")}`}
                className="flex items-center gap-2.5 rounded-xl border border-surface-border bg-surface-elevated p-2.5"
              >
                <NflArtBadge
                  subject={leader.team}
                  detail={div.division}
                  art={leader.logo}
                  fallbackText={leader.abbreviation}
                  kidSurface={kidSurface}
                  size="md"
                />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-semibold text-text-muted">
                    {div.division}
                  </div>
                  <div className="truncate text-sm font-bold text-text-primary">
                    {leader.team}
                  </div>
                  <div className="mt-0.5 flex items-baseline gap-2 text-xs tabular-nums">
                    <span className="text-sm font-bold text-accent-positive">
                      {formatPct(leader.probability)} division
                    </span>
                    {chaser && (
                      <span className="truncate text-text-muted">
                        · Next: {chaser.abbreviation} {formatPct(chaser.probability)}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Section 4: NFL MVP & Offensive Player of the Year (Player Headshots)
// ============================================================================

export function NflAwardsSpotlightSectionCard({
  simulateSettled = false,
  kidSurface = false,
}: {
  simulateSettled?: boolean;
  kidSurface?: boolean;
}) {
  const mvpPodium = NFL_MVP_CANDIDATES.slice(0, 3);
  const mvpChasers = NFL_MVP_CANDIDATES.slice(3);

  return (
    <div
      data-testid="nfl-section-4-awards-spotlight"
      className="rounded-xl border border-surface-border bg-surface-card p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-1 text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>NFL HONORS · PLAYER HEADSHOT PODIUM &amp; PAIRED FINALIST %</span>
        <span>FINALIST % BESIDE WIN %</span>
      </div>
      <h3 className="mt-1 text-lg font-bold text-text-primary">
        NFL MVP &amp; Offensive Player of the Year
      </h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        Circular ESPN player headshots pair AP Finalist % beside Winner %. Exposes finalist locks who are longshots to win the trophy (Jared Goff: 79% finalist · 1% win).
      </p>

      {/* MVP Top-3 Podium */}
      <div className="mt-3 grid grid-cols-3 gap-2">
        {mvpPodium.map((cand, idx) => {
          const winPct = renderedPercent(cand.winner_probability) ?? 0;
          const finPct = renderedPercent(cand.finalist_probability) ?? 0;
          const rankLabel = idx === 0 ? "#1 Favorite" : idx === 1 ? "#2 Contender" : "#3 Contender";
          return (
            <div
              key={cand.player_key}
              data-testid={`nfl-mvp-podium-${idx + 1}`}
              className={`flex flex-col items-center rounded-xl border p-2.5 text-center ${
                idx === 0
                  ? "border-accent-brand bg-surface-elevated"
                  : "border-surface-border bg-surface-elevated"
              }`}
            >
              <span className="text-xs font-bold uppercase tracking-wide text-accent-brand">
                {rankLabel}
              </span>
              <div className="mt-1.5">
                <NflArtBadge
                  subject={cand.player}
                  detail={`${cand.team_abbr} · ${cand.position}`}
                  art={cand.headshot}
                  fallbackText={cand.team_abbr}
                  kidSurface={kidSurface}
                  size="lg"
                />
              </div>
              <div className="mt-1.5 w-full text-xs font-bold leading-tight text-text-primary">
                {cand.player}
              </div>
              <div className="text-xs text-text-muted">
                {cand.team_abbr} · {cand.position}
              </div>
              <div className="mt-1.5 text-lg font-bold tabular-nums text-text-primary">
                {winPct}%
              </div>
              <div className="text-xs font-medium text-text-secondary">
                to win MVP
              </div>
              <div className="mt-1 rounded border border-surface-border bg-surface-card px-2 py-0.5 text-xs font-semibold tabular-nums text-text-secondary">
                {simulateSettled ? "✓ Finalist" : `${finPct}% finalist`}
              </div>
            </div>
          );
        })}
      </div>

      {/* MVP Finalist Chasers Strip */}
      <div className="mt-3 rounded-xl border border-surface-border bg-surface-elevated p-3">
        <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
          <span>IN THE MVP FINALIST HUNT (59%–79% TO MAKE TOP-5 BALLOT)</span>
          <span>FINALIST · WIN</span>
        </div>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {mvpChasers.map((cand) => {
            const winPct = renderedPercent(cand.winner_probability) ?? 0;
            const finPct = renderedPercent(cand.finalist_probability) ?? 0;
            return (
              <div
                key={cand.player_key}
                className="flex items-center justify-between gap-2 rounded-lg border border-surface-border bg-surface-card p-2"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <NflArtBadge
                    subject={cand.player}
                    detail={`${cand.team_abbr} · ${cand.position}`}
                    art={cand.headshot}
                    fallbackText={cand.team_abbr}
                    kidSurface={kidSurface}
                    size="sm"
                  />
                  <div className="min-w-0">
                    <div className="truncate text-xs font-bold text-text-primary">
                      {cand.player}
                    </div>
                    <div className="text-xs text-text-muted">
                      {cand.team_abbr} · {cand.position}
                    </div>
                  </div>
                </div>
                <div className="shrink-0 text-right text-xs tabular-nums">
                  <div className="font-semibold text-text-secondary">
                    {simulateSettled ? "✓ Finalist" : `${finPct}% finalist`}
                  </div>
                  <div className="font-bold text-text-primary">
                    {winPct}% win
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Offensive Player of the Year 2x2 Strip */}
      <div className="mt-3 rounded-xl border border-surface-border bg-surface-elevated p-3">
        <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-text-muted">
          <span>OFFENSIVE PLAYER OF THE YEAR · RB &amp; WR RACE</span>
          <span>BLENDED WIN %</span>
        </div>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {NFL_OPOY_CANDIDATES.map((cand) => {
            const winPct = renderedPercent(cand.winner_probability) ?? 0;
            const finPct = renderedPercent(cand.finalist_probability);
            return (
              <div
                key={cand.player_key}
                className="flex items-center justify-between gap-2 rounded-lg border border-surface-border bg-surface-card p-2"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <NflArtBadge
                    subject={cand.player}
                    detail={`${cand.team_abbr} · ${cand.position}`}
                    art={cand.headshot}
                    fallbackText={cand.team_abbr}
                    kidSurface={kidSurface}
                    size="sm"
                  />
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-text-primary">
                      {cand.player}
                    </div>
                    <div className="text-xs text-text-muted">
                      {cand.team_abbr} · {cand.position}
                    </div>
                  </div>
                </div>
                <div className="shrink-0 text-right text-xs tabular-nums">
                  <div className="font-bold text-accent-brand">
                    {winPct}% win OPOY
                  </div>
                  {finPct !== null && (
                    <div className="font-semibold text-text-secondary">
                      {finPct}% finalist
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Section 5: This Week's Games That Move the Playoff Picture Most
// ============================================================================

export function NflSwingGamesSectionCard({
  kidSurface = false,
}: {
  kidSurface?: boolean;
}) {
  return (
    <div
      data-testid="nfl-section-5-swing-games"
      className="rounded-xl border border-surface-border bg-surface-card p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-1 text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>THIS WEEK&apos;S SWING GAMES · BLENDED WIN % + PLAYOFF STAKES</span>
        <span>WEEK 10 / 11 SLATE</span>
      </div>
      <h3 className="mt-1 text-lg font-bold text-text-primary">
        Games this week that move the playoff picture most
      </h3>
      <p className="mt-0.5 text-xs text-text-secondary">
        Pairs each game&apos;s blended win probability (Kalshi, Polymarket &amp; Sportsbooks) with both clubs&apos; live playoff berth chance and division leverage.
      </p>

      <div className="mt-3 space-y-2.5">
        {NFL_SWING_GAMES_THIS_WEEK.map((game) => {
          const awayWin = renderedPercent(game.away_win_prob) ?? 50;
          const homeWin = renderedPercent(game.home_win_prob) ?? 50;
          const awayPlayoff = renderedPercent(game.away_playoff_prob) ?? 0;
          const homePlayoff = renderedPercent(game.home_playoff_prob) ?? 0;
          return (
            <div
              key={game.event_id}
              data-testid={`nfl-swing-game-${game.away_abbr.toLowerCase()}-${game.home_abbr.toLowerCase()}`}
              className="rounded-xl border border-surface-border bg-surface-elevated p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-1">
                <span className="rounded border border-surface-border bg-surface-card px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-accent-brand">
                  {game.stakes_tag}
                </span>
                <span className="text-xs font-medium text-text-muted">
                  {game.kickoff_label}
                </span>
              </div>

              <div className="mt-2 space-y-1.5">
                {/* Away Team Row */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <NflArtBadge
                      subject={game.away_team}
                      detail={game.away_record}
                      art={game.away_logo}
                      fallbackText={game.away_abbr}
                      kidSurface={kidSurface}
                      size="sm"
                    />
                    <div className="min-w-0">
                      <span className="text-xs font-bold text-text-primary sm:text-sm">
                        {game.away_team}
                      </span>
                      <span className="ml-1.5 text-xs text-text-muted">
                        ({game.away_record} · {awayPlayoff}% playoffs)
                      </span>
                    </div>
                  </div>
                  <span className="shrink-0 text-sm font-bold tabular-nums text-text-secondary">
                    {awayWin}% win
                  </span>
                </div>

                {/* Home Team Row */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <NflArtBadge
                      subject={game.home_team}
                      detail={game.home_record}
                      art={game.home_logo}
                      fallbackText={game.home_abbr}
                      kidSurface={kidSurface}
                      size="sm"
                    />
                    <div className="min-w-0">
                      <span className="text-xs font-bold text-text-primary sm:text-sm">
                        {game.home_team}
                      </span>
                      <span className="ml-1.5 text-xs text-text-muted">
                        ({game.home_record} · {homePlayoff}% playoffs)
                      </span>
                    </div>
                  </div>
                  <span className="shrink-0 text-sm font-bold tabular-nums text-accent-brand">
                    {homeWin}% win
                  </span>
                </div>
              </div>

              {/* Tug-of-war win probability bar */}
              <div className="mt-2 flex h-2 w-full overflow-hidden rounded-full bg-surface-card">
                <div
                  className="h-full bg-text-muted"
                  style={{ width: `${awayWin}%` }}
                />
                <div
                  className="h-full bg-accent-brand"
                  style={{ width: `${homeWin}%` }}
                />
              </div>
              <p className="mt-1.5 text-xs text-text-secondary">
                {game.stakes_note}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================================
// Section 6: The "Too Many Props" Section (Real NFL Game #14780578 — 671 Markets)
// ============================================================================

export function NflTooManyPropsSectionCard({
  kidSurface = false,
  defaultDrawerOpen = false,
}: {
  kidSurface?: boolean;
  defaultDrawerOpen?: boolean;
}) {
  const [drawerOpen, setDrawerOpen] = useState(defaultDrawerOpen);
  const [activeCategory, setActiveCategory] =
    useState<NflPropDrawerCategoryKey>("receiving");
  const board = STEELERS_BENGALS_PROP_BOARD;
  const categoryKeys: NflPropDrawerCategoryKey[] = [
    "receiving",
    "passing",
    "rushing",
    "touchdowns",
    "lines",
  ];
  const activeDrawer = board.drawer_categories[activeCategory];

  return (
    <div
      data-testid="nfl-section-6-too-many-props"
      className="rounded-xl border border-surface-border bg-surface-card p-4"
    >
      {/* Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-1 text-xs font-semibold uppercase tracking-wide text-text-muted">
        <span>LARGE-SET PROP CURATION (#12609) · 671 LIVE MARKETS → 11-NUMBER FIRST SCREEN</span>
        <span>{board.kickoff_label}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <NflArtBadge
            subject={board.away_team}
            detail={board.away_record}
            art={board.away_logo}
            fallbackText={board.away_abbr}
            kidSurface={kidSurface}
            size="sm"
          />
          <NflArtBadge
            subject={board.home_team}
            detail={board.home_record}
            art={board.home_logo}
            fallbackText={board.home_abbr}
            kidSurface={kidSurface}
            size="sm"
          />
          <h3 className="text-base font-bold leading-snug text-text-primary sm:text-lg">
            {board.matchup_title} · Prop Board
          </h3>
        </div>
        <span className="shrink-0 rounded-full border border-surface-border bg-surface-elevated px-2.5 py-0.5 text-xs font-bold tabular-nums text-text-primary">
          PIT 36% · CIN 64%
        </span>
      </div>
      <p className="mt-1 text-xs text-text-secondary">
        This game carries <span className="font-semibold text-text-primary">384 player prop lines</span>, <span className="font-semibold text-text-primary">261 spread/total/period lines</span>, and <span className="font-semibold text-text-primary">26 touchdown/novelty specials</span> (671 total). Instead of a 671-row wall, the first screen shows <span className="font-semibold text-text-primary">three scannable lenses</span>, and one toggle opens player milestone ladders for the rest.
      </p>

      {/* LENS 1: The Script (Likely Star Benchmarks >= 50%) */}
      <div className="mt-3 rounded-xl border border-surface-border bg-surface-elevated p-3">
        <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wide text-accent-brand">
          <span>1. THE SCRIPT · LIKELY STAR BENCHMARKS (50%+ CHANCE)</span>
          <span>4 STARS · 8 NUMBERS</span>
        </div>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {board.star_script.map((star) => (
            <div
              key={star.player}
              data-testid={`nfl-prop-script-${star.player.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
              className="flex items-center gap-2.5 rounded-lg border border-surface-border bg-surface-card p-2.5"
            >
              <NflArtBadge
                subject={star.player}
                detail={star.role}
                art={star.headshot}
                fallbackText={star.team_abbr}
                kidSurface={kidSurface}
                size="md"
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-1">
                  <span className="truncate text-sm font-bold text-text-primary">
                    {star.player}
                  </span>
                  <span className="text-xs font-semibold text-text-muted">
                    {star.role}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between text-xs tabular-nums">
                  <span className="text-text-secondary">{star.primary_label}</span>
                  <span className="font-bold text-accent-brand">
                    {formatPct(star.primary_probability)}
                  </span>
                </div>
                <div className="mt-0.5 flex items-center justify-between text-xs tabular-nums">
                  <span className="text-text-secondary">{star.secondary_label}</span>
                  <span className="font-bold text-text-primary">
                    {formatPct(star.secondary_probability)}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* LENS 2: 50/50 Coin-Flip Tension (Closest to 50%) */}
      <div className="mt-3 rounded-xl border border-surface-border bg-surface-elevated p-3">
        <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wide text-accent-brand">
          <span>2. COIN-FLIP TENSION · CLOSEST TO 50/50 ON THE BOARD</span>
          <span>48%–52% WINDOW</span>
        </div>
        <div className="mt-2 space-y-2">
          {board.coin_flips.map((flip) => {
            const leftPct = renderedPercent(flip.left_probability) ?? 50;
            const rightPct = renderedPercent(flip.right_probability) ?? 50;
            return (
              <div
                key={flip.label}
                className="rounded-lg border border-surface-border bg-surface-card p-2.5"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-1">
                  <span className="text-xs font-bold text-text-primary">
                    {flip.label}
                  </span>
                  <span className="text-xs text-text-muted">{flip.sublabel}</span>
                </div>
                <div className="mt-1.5 flex items-center justify-between text-xs font-semibold tabular-nums">
                  <span className="text-text-primary">
                    {flip.left_side} ({leftPct}%)
                  </span>
                  <span className="text-text-secondary">
                    {flip.right_side} ({rightPct}%)
                  </span>
                </div>
                <div className="mt-1 flex h-2 w-full overflow-hidden rounded-full bg-surface-elevated">
                  <div
                    className="h-full bg-accent-brand"
                    style={{ width: `${leftPct}%` }}
                  />
                  <div
                    className="h-full bg-text-muted"
                    style={{ width: `${rightPct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* LENS 3: First Touchdown & Specials Strip */}
      <div className="mt-3 rounded-xl border border-surface-border bg-surface-elevated p-3">
        <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wide text-accent-brand">
          <span>3. FIRST TOUCHDOWN LEADERS &amp; GAME SPECIALS</span>
          <span>TOP 4 + WEATHER</span>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {board.first_td_leaders.map((cand) => (
            <div
              key={cand.player}
              className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-card p-2"
            >
              <NflArtBadge
                subject={cand.player}
                detail={cand.team_abbr}
                art={cand.headshot}
                fallbackText={cand.team_abbr}
                kidSurface={kidSurface}
                size="sm"
              />
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-text-primary">
                  {cand.player.split(" ").slice(-1)[0]}
                </div>
                <div className="text-xs font-bold tabular-nums text-text-primary">
                  {formatPct(cand.probability)} 1st TD
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-2 flex items-center justify-between rounded-lg border border-surface-border bg-surface-card px-2.5 py-1.5 text-xs">
          <span className="font-medium text-text-secondary">
            Game Special · Weather Delay during Pittsburgh at Cincinnati
          </span>
          <span className="font-bold tabular-nums text-text-primary">
            {formatPct(board.weather_delay_probability)} chance
          </span>
        </div>
      </div>

      {/* ONE WAY TO REACH THE REST: Prominent Category Drawer Toggle */}
      <div className="mt-3 rounded-xl border border-accent-brand bg-surface-elevated p-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-xs font-bold text-text-primary">
              Want the rest of the 671 game &amp; player prop lines?
            </div>
            <div className="text-xs text-text-secondary">
              Grouped by category with 8–10 yardage thresholds collapsed into one Milestone Ladder per player.
            </div>
          </div>
          <button
            type="button"
            data-testid="nfl-too-many-props-drawer-toggle"
            onClick={() => setDrawerOpen((prev) => !prev)}
            className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-accent-brand px-3.5 py-2 text-xs font-bold text-text-inverse shadow-sm sm:w-auto"
          >
            <span>
              {drawerOpen
                ? "Hide full prop board drawer"
                : "Browse all 384 player props & 287 game lines"}
            </span>
            <span aria-hidden="true">{drawerOpen ? "▴" : "▾"}</span>
          </button>
        </div>

        {drawerOpen && (
          <div
            data-testid="nfl-too-many-props-drawer-content"
            className="mt-3 border-t border-surface-border pt-3"
          >
            {/* Category Tabs */}
            <div
              className="flex flex-wrap gap-1.5"
              data-testid="nfl-prop-drawer-category-tabs"
            >
              {categoryKeys.map((catKey) => {
                const cat = board.drawer_categories[catKey];
                const active = activeCategory === catKey;
                return (
                  <button
                    key={catKey}
                    type="button"
                    data-testid={`nfl-prop-tab-${catKey}`}
                    onClick={() => setActiveCategory(catKey)}
                    className={`rounded-lg border px-2.5 py-1 text-xs font-semibold ${
                      active
                        ? "border-accent-brand bg-accent-brand text-text-inverse"
                        : "border-surface-border bg-surface-card text-text-primary"
                    }`}
                  >
                    {cat.label}
                  </button>
                );
              })}
            </div>

            {/* Player Milestone Ladders */}
            <div className="mt-2.5 space-y-2">
              {activeDrawer.ladders.map((ladder) => (
                <div
                  key={`${ladder.player}-${ladder.stat_label}`}
                  className="rounded-lg border border-surface-border bg-surface-card p-2.5"
                >
                  <div className="flex items-center gap-2">
                    {ladder.headshot && (
                      <NflArtBadge
                        subject={ladder.player}
                        detail={ladder.stat_label}
                        art={ladder.headshot}
                        fallbackText={ladder.team_abbr}
                        kidSurface={kidSurface}
                        size="xs"
                      />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-bold text-text-primary">
                        {ladder.player} ({ladder.team_abbr})
                      </div>
                      <div className="text-xs text-text-muted">
                        {ladder.stat_label}
                      </div>
                    </div>
                  </div>

                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {ladder.milestones.map((m) => {
                      const pct = renderedPercent(m.probability) ?? 0;
                      return (
                        <span
                          key={m.threshold_label}
                          className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs tabular-nums ${
                            pct >= 50
                              ? "border-accent-brand bg-surface-elevated font-bold text-text-primary"
                              : "border-surface-border bg-surface-elevated font-medium text-text-secondary"
                          }`}
                        >
                          <span>{m.threshold_label}:</span>
                          <span>{pct}%</span>
                        </span>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Section 7: Full Composed Container Rhythm Preview (All 6 Sections Together)
// ============================================================================

export function NflFullComposedContainerPreview({
  simulateSettled = false,
  kidSurface = false,
}: {
  simulateSettled?: boolean;
  kidSurface?: boolean;
}) {
  const [seasonStage, setSeasonStage] = useState<
    "race_to_get_in" | "the_bracket" | "the_game"
  >("race_to_get_in");

  return (
    <section
      data-testid="nfl-section-7-full-composed-container"
      className="space-y-3 rounded-xl border border-surface-border bg-surface-elevated p-3.5"
    >
      <div className="rounded-xl border border-surface-border bg-surface-card p-3.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-xs font-bold uppercase tracking-wide text-accent-brand">
              SELF-BUILDING SEASON CONTAINER (#12609) · ADJACENT SECTIONS NEVER REPEAT A FORM
            </div>
            <h3 className="mt-0.5 text-base font-bold text-text-primary">
              NFL Playoffs &amp; Super Bowl LXI Hub · Resolves Feb 14, 2027
            </h3>
          </div>
          <span className="rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1 text-xs font-bold text-text-primary">
            Co-Favorites: 49ers 13% · Bills 13%
          </span>
        </div>

        {/* Selector Stage Switcher: shows how the container adapts across the calendar */}
        <div
          className="mt-2.5 flex flex-wrap gap-1.5"
          data-testid="nfl-container-stage-selector"
        >
          {[
            {
              id: "race_to_get_in" as const,
              label: "Stage 1 · The Race to Get In (Nov–Jan)",
            },
            {
              id: "the_bracket" as const,
              label: "Stage 2 · The Playoff Bracket (Mid-Jan)",
            },
            {
              id: "the_game" as const,
              label: "Stage 3 · Super Bowl LXI Week (Feb 14, 2027)",
            },
          ].map((st) => (
            <button
              key={st.id}
              type="button"
              onClick={() => setSeasonStage(st.id)}
              className={`rounded-lg border px-2.5 py-1 text-xs font-semibold ${
                seasonStage === st.id
                  ? "border-accent-brand bg-accent-brand text-text-inverse"
                  : "border-surface-border bg-surface-elevated text-text-primary"
              }`}
            >
              {st.label}
            </button>
          ))}
        </div>

        <p className="mt-2 text-xs text-text-secondary">
          {seasonStage === "race_to_get_in" &&
            "Active selector rule (Nov–Jan): leads with Make Playoffs % beside Win Super Bowl %, followed by AFC/NFC Conversion Funnels, Shape-Driven Division Races, MVP/OPOY Headshots, Swing Games, and the Curated Game Prop Board."}
          {seasonStage === "the_bracket" &&
            "Active selector rule (Mid-Jan): Playoff berths lock to ✓ Clinched / ✗ Eliminated; AFC & NFC Conference Conversion Funnels move to the top alongside Wild Card & Divisional Round matchup props."}
          {seasonStage === "the_game" &&
            "Active selector rule (Feb 14, 2027): AFC & NFC Champions lock to ✓; the container promotes the Super Bowl LXI Matchup Hero, the 3-Lens Curated Super Bowl Prop Board, and Super Bowl MVP."}
        </p>
      </div>

      <NflPlayoffsToSuperBowlSectionCard
        simulateSettled={simulateSettled || seasonStage !== "race_to_get_in"}
        kidSurface={kidSurface}
      />
      <NflConferencePathsSectionCard
        simulateSettled={simulateSettled || seasonStage === "the_game"}
        kidSurface={kidSurface}
      />
      <NflDivisionRacesByShapeSectionCard kidSurface={kidSurface} />
      <NflAwardsSpotlightSectionCard
        simulateSettled={simulateSettled || seasonStage !== "race_to_get_in"}
        kidSurface={kidSurface}
      />
      <NflSwingGamesSectionCard kidSurface={kidSurface} />
      <NflTooManyPropsSectionCard kidSurface={kidSurface} />
    </section>
  );
}

// ============================================================================
// Single Deck-Item Renderer for `/grade/groupings`
// ============================================================================

export function renderNflPlayoffsLookSheetDeckItem(
  itemKey: string,
  options?: {
    simulateSettled?: boolean;
    kidSurface?: boolean;
    defaultDrawerOpen?: boolean;
  },
): React.ReactNode | null {
  const spec = NFL_PLAYOFFS_LOOK_SHEET_ITEMS.find((i) => i.item_key === itemKey);
  if (!spec) return null;

  let body: React.ReactNode = null;
  switch (spec.item_key) {
    case "nfl-section-1-playoffs-to-super-bowl-paired-bars":
      body = (
        <NflPlayoffsToSuperBowlSectionCard
          simulateSettled={options?.simulateSettled}
          kidSurface={options?.kidSurface}
        />
      );
      break;
    case "nfl-section-2-afc-nfc-conference-paths":
      body = (
        <NflConferencePathsSectionCard
          simulateSettled={options?.simulateSettled}
          kidSurface={options?.kidSurface}
        />
      );
      break;
    case "nfl-section-3-division-races-by-shape":
      body = <NflDivisionRacesByShapeSectionCard kidSurface={options?.kidSurface} />;
      break;
    case "nfl-section-4-mvp-and-awards-spotlight":
      body = (
        <NflAwardsSpotlightSectionCard
          simulateSettled={options?.simulateSettled}
          kidSurface={options?.kidSurface}
        />
      );
      break;
    case "nfl-section-5-games-that-move-the-picture":
      body = <NflSwingGamesSectionCard kidSurface={options?.kidSurface} />;
      break;
    case "nfl-section-6-too-many-props-steelers-bengals":
      body = (
        <NflTooManyPropsSectionCard
          kidSurface={options?.kidSurface}
          defaultDrawerOpen={options?.defaultDrawerOpen}
        />
      );
      break;
    case "nfl-container-full-rhythm-preview":
      body = (
        <NflFullComposedContainerPreview
          simulateSettled={options?.simulateSettled}
          kidSurface={options?.kidSurface}
        />
      );
      break;
    default:
      return null;
  }

  return (
    <div className="space-y-2" data-testid={`nfl-look-sheet-item-${itemKey}`}>
      <NflFormContractHeader form={spec.form} />
      {body}
    </div>
  );
}

// ============================================================================
// Full NFL Playoffs & Super Bowl Look Sheet Gallery on `/grade/groupings`
// ============================================================================

export interface NflPlayoffsLookSheetGalleryProps {
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

export function NflPlayoffsLookSheetGallery({
  kidSurface = false,
  grader = null,
  existingGradesByItemKey = {},
  onGradeItem,
  savingItemKey = null,
}: NflPlayoffsLookSheetGalleryProps) {
  const [simulateSettled, setSimulateSettled] = useState(false);
  const [notesByKey, setNotesByKey] = useState<Record<string, string>>({});

  const renderGradableBlock = (spec: NflLookSheetItemSpec) => {
    const currentGrade = existingGradesByItemKey[spec.item_key];
    const itemNote = notesByKey[spec.item_key] ?? "";
    return (
      <div
        key={spec.item_key}
        data-testid={`nfl-look-sheet-block-${spec.section_number}`}
        className="rounded-xl border border-surface-border bg-surface-elevated p-3.5"
      >
        <div className="mb-1 flex items-baseline justify-between gap-2">
          <h4 className="text-sm font-bold text-text-primary">{spec.title}</h4>
          <span className="shrink-0 text-xs font-medium text-text-muted">
            Deck pos #{spec.position}
          </span>
        </div>
        <p className="mb-2 text-xs text-text-secondary">{spec.why_it_exists}</p>
        {renderNflPlayoffsLookSheetDeckItem(spec.item_key, {
          simulateSettled,
          kidSurface,
        })}

        {grader && onGradeItem && (
          <div className="mt-3 rounded-lg border border-surface-border bg-surface-card p-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <input
                type="text"
                placeholder={`Note on Section ${spec.section_number} (optional)`}
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
    <div className="space-y-6" data-testid="nfl-playoffs-look-sheet-gallery">
      {/* Header & Global Controls */}
      <div className="rounded-xl border border-surface-border bg-surface-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-accent-brand">
              #12609 · NFL PLAYOFFS &amp; SUPER BOWL LXI CONTAINER LOOK SHEET
            </div>
            <h2 className="mt-0.5 text-lg font-bold text-text-primary">
              Six non-repeating section forms on live NFL numbers + one &ldquo;too many props&rdquo; section on a 671-market NFL game
            </h2>
          </div>
          <button
            type="button"
            data-testid="toggle-nfl-simulate-settled"
            onClick={() => setSimulateSettled((prev) => !prev)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-semibold ${
              simulateSettled
                ? "border-accent-brand bg-accent-brand text-text-inverse"
                : "border-surface-border bg-surface-elevated text-text-primary"
            }`}
          >
            {simulateSettled
              ? "Showing: After regular season (✓ Clinched / ✗ Eliminated)"
              : "Preview after regular season (✓ / ✗)"}
          </button>
        </div>

        <ul className="mt-2.5 space-y-1 text-xs text-text-secondary">
          <li>
            • <span className="font-semibold text-text-primary">Adjacent sections never repeat a form (#12523):</span>{" "}
            Section 1 (Stacked Dual Bars + Expander) → Section 2 (Two-Step Conference Conversion Funnels) → Section 3 (Shape-Driven Division Grids, Duels &amp; Locks) → Section 4 (Player Headshot Podium &amp; Paired Finalist Strip) → Section 5 (Matchup Swing Cards) → Section 6 (3-Lens Curated Prop Digest + Milestone Drawer).
          </li>
          <li>
            • <span className="font-semibold text-text-primary">One unified Super Bowl number (#12530):</span>{" "}
            Stands on the verified Super Bowl LXI board (<span className="font-medium text-text-primary">San Francisco 49ers 13%</span>, <span className="font-medium text-text-primary">Buffalo Bills 13%</span>, <span className="font-medium text-text-primary">Jacksonville Jaguars 10%</span>, <span className="font-medium text-text-primary">Chicago Bears 9%</span> · Resolves Feb 14, 2027).
          </li>
          <li>
            • <span className="font-semibold text-text-primary">&ldquo;Too many props&rdquo; curation rule (Section 6):</span>{" "}
            Built on <span className="font-medium text-text-primary">Pittsburgh Steelers at Cincinnati Bengals</span> (671 live game markets / 384 player props) — curates an 11-number first screen (The Script, 50/50 Coin-Flips, First TD) with one toggle to browse player Milestone Ladders by category.
          </li>
        </ul>
      </div>

      {/* Sections 1..7 */}
      <div className="space-y-4">
        {NFL_PLAYOFFS_LOOK_SHEET_ITEMS.map(renderGradableBlock)}
      </div>
    </div>
  );
}
