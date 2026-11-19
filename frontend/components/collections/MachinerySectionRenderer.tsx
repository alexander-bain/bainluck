/* eslint-disable @next/next/no-img-element */
"use client";

import { useState } from "react";
import Link from "next/link";
import AwardCategoryPairedCard from "@/components/discover/forms/AwardCategoryPairedCard";
import EventCard183A, { buildUnifiedCardFromEvent } from "@/components/EventCard183A";
import type {
  CollectionMember,
  MachineryOutcomeVisual,
  MachinerySubjectArt,
  MachineryVisualBlock,
} from "@/lib/collections";
import type { Event } from "@/lib/types";

export function isMachinerySlice1Enabled(): boolean {
  return process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1 === "true";
}

export interface MachineryHistorySeriesPoint {
  t: string;
  pct: number;
}

export interface MachineryHistorySeries {
  outcome_id: number;
  name: string;
  current_pct: number;
  color: string;
  art?: MachinerySubjectArt;
  points: MachineryHistorySeriesPoint[];
}

export interface MachineryHistoryChartItem {
  market_id: number;
  title: string;
  href: string;
  scale_ordered?: boolean;
  start_iso: string;
  end_iso: string;
  y_min: number;
  y_max: number;
  series: MachineryHistorySeries[];
}

export interface MachineryCardContract {
  slug: string;
  form_id: string;
  kicker: string;
  title: string;
  subtitle: string;
  footer: string;
  scale_ordered?: boolean;
  section_count: number;
  destination_href: string;
  rows: Record<string, unknown>[];
  mini_chart?: MachineryHistoryChartItem | null;
}

const CHART_SERIES_FALLBACK_PALETTE = [
  "#0D9488",
  "#2563EB",
  "#D97706",
  "#7C3AED",
  "#DC2626",
  "#0891B2",
] as const;

export function resolveDistinctChartSeries(
  series: readonly MachineryHistorySeries[],
): MachineryHistorySeries[] {
  const used = new Set<string>();
  return series.map((s, idx) => {
    const raw = (s.color ?? "").trim();
    const norm = raw.toLowerCase();
    let chosen = raw;
    if (!chosen || used.has(norm)) {
      const nextUnused = CHART_SERIES_FALLBACK_PALETTE.find(
        (c) => !used.has(c.toLowerCase()),
      );
      chosen =
        nextUnused ??
        CHART_SERIES_FALLBACK_PALETTE[idx % CHART_SERIES_FALLBACK_PALETTE.length];
    }
    used.add(chosen.toLowerCase());
    return chosen === s.color ? s : { ...s, color: chosen };
  });
}

function SubjectAvatar({
  art,
  label,
  sizeClass = "h-9 w-9",
  widthClass,
  poster = false,
  reserveSlotWhenMissing = false,
}: {
  art?: MachinerySubjectArt | null;
  label: string;
  sizeClass?: string;
  widthClass?: string;
  poster?: boolean;
  reserveSlotWhenMissing?: boolean;
}) {
  const url = art?.url;
  if (!url) {
    if (!reserveSlotWhenMissing) return null;
    return (
      <span
        aria-hidden="true"
        data-testid="machinery-avatar-spacer"
        className={`inline-block shrink-0 ${widthClass ?? sizeClass}`}
      />
    );
  }
  const kind = art?.kind ?? "person";
  const isLogo = kind === "team_logo";
  const shapeClass = poster ? "rounded-md" : "rounded-full";
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center overflow-hidden border border-surface-border bg-surface-elevated ${shapeClass} ${sizeClass}`}
    >
      <img
        src={url}
        alt={label}
        className={isLogo ? "h-4/5 w-4/5 object-contain" : "h-full w-full object-cover object-top"}
      />
    </span>
  );
}

function ShowAllButton({
  expanded,
  totalCount,
  visibleLimit,
  noun,
  onToggle,
}: {
  expanded: boolean;
  totalCount: number;
  visibleLimit: number;
  noun: string;
  onToggle: () => void;
}) {
  if (totalCount <= visibleLimit) return null;
  return (
    <button
      type="button"
      onClick={onToggle}
      data-testid="machinery-show-all-toggle"
      className="w-full rounded-lg border border-surface-border bg-surface-elevated/70 px-3 py-2 text-xs font-semibold text-accent-brand transition-colors hover:bg-surface-elevated"
    >
      {expanded
        ? `Show top ${visibleLimit}`
        : `Show all ${totalCount} ${noun} (+${totalCount - visibleLimit} more)`}
    </button>
  );
}

function formatShortKickoff(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatShortSpanDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function CoinFlipMatchupsBlock({
  items,
  limit = 3,
}: {
  items: Record<string, unknown>[];
  limit?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? items : items.slice(0, limit);
  const anyAwayArt = shown.some((r) =>
    Boolean((r.away_art as MachinerySubjectArt | undefined)?.url),
  );
  const anyHomeArt = shown.some((r) =>
    Boolean((r.home_art as MachinerySubjectArt | undefined)?.url),
  );
  return (
    <div className="space-y-2.5" data-machinery-form="coin_flip_matchups">
      <div className="grid grid-cols-1 gap-2.5">
        {shown.map((raw) => {
          const eid = Number(raw.event_id ?? 0);
          const awayShort = String(raw.away_short ?? raw.away_team ?? "");
          const homeShort = String(raw.home_short ?? raw.home_team ?? "");
          const awayPct = Number(raw.away_pct ?? 50);
          const homePct = Number(raw.home_pct ?? 50);
          const awayArt = raw.away_art as MachinerySubjectArt | undefined;
          const homeArt = raw.home_art as MachinerySubjectArt | undefined;
          const when = formatShortKickoff(String(raw.commence_time ?? ""));
          return (
            <Link
              key={eid}
              href={`/events/${eid}`}
              className="block rounded-card border border-surface-border bg-surface-card p-3 transition-colors hover:bg-surface-elevated"
            >
              <div className="mb-2 flex items-center justify-between text-xs text-text-muted">
                <span className="font-semibold uppercase tracking-wide text-accent-brand">Toss-up</span>
                <span>{when}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <SubjectAvatar
                    art={awayArt}
                    label={awayShort}
                    sizeClass="h-8 w-8"
                    widthClass="w-8 h-1"
                    reserveSlotWhenMissing={anyAwayArt}
                  />
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-text-primary">{awayShort}</div>
                    <div className="text-xs font-bold tabular-nums text-text-secondary">{awayPct}%</div>
                  </div>
                </div>
                <span className="text-xs font-medium text-text-muted">at</span>
                <div className="flex min-w-0 items-center gap-2 text-right">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-text-primary">{homeShort}</div>
                    <div className="text-xs font-bold tabular-nums text-text-secondary">{homePct}%</div>
                  </div>
                  <SubjectAvatar
                    art={homeArt}
                    label={homeShort}
                    sizeClass="h-8 w-8"
                    widthClass="w-8 h-1"
                    reserveSlotWhenMissing={anyHomeArt}
                  />
                </div>
              </div>
              <div className="mt-2.5 flex h-2 w-full overflow-hidden rounded-full bg-surface-elevated">
                <div
                  className="h-full bg-accent-brand transition-all"
                  style={{
                    width: `${Math.max(8, Math.min(92, awayPct))}%`,
                    backgroundColor: awayArt?.accent_color || undefined,
                  }}
                />
                <div
                  className="h-full flex-1 bg-slate-400 transition-all"
                  style={{ backgroundColor: homeArt?.accent_color || undefined }}
                />
              </div>
            </Link>
          );
        })}
      </div>
      <ShowAllButton
        expanded={expanded}
        totalCount={items.length}
        visibleLimit={limit}
        noun="games"
        onToggle={() => setExpanded((v) => !v)}
      />
    </div>
  );
}

function MatchupSlateBlock({
  members,
  limit = 3,
}: {
  members: CollectionMember[];
  limit?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const eventMembers = members.filter((m) => m.type === "event");
  const shown = expanded ? eventMembers : eventMembers.slice(0, limit);
  return (
    <div className="space-y-2.5" data-machinery-form="matchup_slate">
      <div className="grid grid-cols-1 gap-3">
        {shown.map((m) => (
          <EventCard183A
            key={m.key}
            card={buildUnifiedCardFromEvent(m.item.data as unknown as Event)}
            surface="standard"
          />
        ))}
      </div>
      <ShowAllButton
        expanded={expanded}
        totalCount={eventMembers.length}
        visibleLimit={limit}
        noun="games"
        onToggle={() => setExpanded((v) => !v)}
      />
    </div>
  );
}

function DuelBarBlock({ items }: { items: Record<string, unknown>[] }) {
  const lead = items[0];
  if (!lead) return null;
  const outcomes = (lead.outcomes as MachineryOutcomeVisual[] | undefined) ?? [];
  if (outcomes.length < 2) return null;
  const left = outcomes[0];
  const right = outcomes[1];
  const href = String(lead.href ?? "/discover");
  return (
    <Link
      href={href}
      data-machinery-form="duel_bar"
      className="block rounded-card border border-surface-border bg-surface-card p-4 transition-colors hover:bg-surface-elevated"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          {left.art?.url ? (
            <SubjectAvatar art={left.art} label={left.name} sizeClass="h-10 w-10" />
          ) : null}
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-sm font-semibold text-text-primary">
              {!left.art?.url && (
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-full bg-accent-brand"
                  style={{ backgroundColor: left.art?.accent_color || undefined }}
                />
              )}
              <span>{left.name}</span>
            </div>
            <div className="text-xl font-extrabold tabular-nums text-text-primary">
              {left.rendered_percent}%
            </div>
          </div>
        </div>
        <div className="flex min-w-0 items-center gap-2.5 text-right">
          <div className="min-w-0">
            <div className="flex items-center justify-end gap-1.5 text-sm font-semibold text-text-primary">
              <span>{right.name}</span>
              {!right.art?.url && (
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-full bg-slate-400"
                  style={{ backgroundColor: right.art?.accent_color || undefined }}
                />
              )}
            </div>
            <div className="text-xl font-extrabold tabular-nums text-text-primary">
              {right.rendered_percent}%
            </div>
          </div>
          {right.art?.url ? (
            <SubjectAvatar art={right.art} label={right.name} sizeClass="h-10 w-10" />
          ) : null}
        </div>
      </div>
      <div className="mt-3 flex h-3 w-full overflow-hidden rounded-full bg-surface-elevated">
        <div
          className="h-full bg-accent-brand"
          style={{
            width: `${Math.max(6, Math.min(94, left.rendered_percent))}%`,
            backgroundColor: left.art?.accent_color || undefined,
          }}
        />
        <div
          className="h-full flex-1 bg-slate-400"
          style={{ backgroundColor: right.art?.accent_color || undefined }}
        />
      </div>
    </Link>
  );
}

function ContenderSpotlightBlock({
  items,
  limit = 3,
}: {
  items: Record<string, unknown>[];
  limit?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const lead = items[0];
  if (!lead) return null;
  const outcomes = (lead.outcomes as MachineryOutcomeVisual[] | undefined) ?? [];
  const href = String(lead.href ?? "/discover");
  const scaleOrdered = Boolean(lead.scale_ordered);
  const leaderOutcomeId = Number(lead.leader_outcome_id ?? 0);

  // Direction 228 (#12885): numerical-scale markets run ascending by value with NO #1/#2/#3 podium badges.
  if (scaleOrdered) {
    const shownScale = expanded ? outcomes : outcomes.slice(0, limit);
    return (
      <div
        className="space-y-2.5"
        data-machinery-form="contender_spotlight"
        data-scale-ordered="true"
      >
        <div className="divide-y divide-surface-border rounded-card border border-surface-border bg-surface-card">
          {shownScale.map((o) => {
            const isFav = leaderOutcomeId > 0 && o.outcome_id === leaderOutcomeId;
            return (
              <Link
                key={o.outcome_id}
                href={href}
                className="flex items-center gap-3 px-3.5 py-2.5 transition-colors hover:bg-surface-elevated"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span
                      className={`truncate text-sm ${
                        isFav ? "font-bold text-text-primary" : "font-medium text-text-secondary"
                      }`}
                    >
                      {o.name}
                    </span>
                    <span
                      className={`tabular-nums text-sm ${
                        isFav ? "font-extrabold text-text-primary" : "font-semibold text-text-secondary"
                      }`}
                    >
                      {o.rendered_percent}%
                    </span>
                  </div>
                  <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-surface-elevated">
                    <div
                      className={`h-full rounded-full ${isFav ? "bg-accent-brand" : "bg-slate-400"}`}
                      style={{ width: `${Math.max(3, Math.min(100, o.rendered_percent))}%` }}
                    />
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
        <ShowAllButton
          expanded={expanded}
          totalCount={outcomes.length}
          visibleLimit={limit}
          noun="outcomes"
          onToggle={() => setExpanded((v) => !v)}
        />
      </div>
    );
  }

  const topThree = outcomes.slice(0, 3);
  const chasers = outcomes.slice(3);
  const podiumHasAnyArt = topThree.some((o) => Boolean(o.art?.url));
  const podiumAnyPoster = topThree.some((o) => o.art?.kind === "tmdb_poster");
  const chasersHaveAnyArt = chasers.some((o) => Boolean(o.art?.url));

  return (
    <div className="space-y-2.5" data-machinery-form="contender_spotlight">
      <div className="grid grid-cols-3 gap-2">
        {topThree.map((o, idx) => {
          const isPoster = o.art?.kind === "tmdb_poster";
          return (
            <Link
              key={o.outcome_id}
              href={href}
              className="flex flex-col items-center rounded-card border border-surface-border bg-surface-card p-2.5 text-center transition-colors hover:bg-surface-elevated"
            >
              <div className="mb-1.5 flex w-full items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-text-muted">
                <span>#{idx + 1}</span>
                <span className="text-sm font-extrabold tabular-nums text-text-primary">
                  {o.rendered_percent}%
                </span>
              </div>
              <SubjectAvatar
                art={o.art}
                label={o.name}
                sizeClass={isPoster ? "h-16 w-11" : "h-12 w-12"}
                widthClass={podiumAnyPoster ? "h-16 w-11" : "h-12 w-12"}
                poster={isPoster}
                reserveSlotWhenMissing={podiumHasAnyArt}
              />
              <div className="mt-2 line-clamp-2 text-xs font-semibold leading-tight text-text-primary">
                {o.name}
              </div>
              {o.art?.detail && (
                <div className="mt-0.5 text-[10px] leading-tight text-text-muted">{o.art.detail}</div>
              )}
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-elevated">
                <div
                  className="h-full rounded-full bg-accent-brand"
                  style={{
                    width: `${Math.max(6, Math.min(100, o.rendered_percent))}%`,
                    backgroundColor: o.art?.accent_color || undefined,
                  }}
                />
              </div>
            </Link>
          );
        })}
      </div>

      {chasers.length > 0 && expanded && (
        <div className="divide-y divide-surface-border rounded-card border border-surface-border bg-surface-card">
          {chasers.map((o) => (
            <Link
              key={o.outcome_id}
              href={href}
              className="relative flex items-center justify-between gap-3 overflow-hidden px-3 py-2 transition-colors hover:bg-surface-elevated"
            >
              <div
                className="pointer-events-none absolute inset-y-0 left-0 bg-surface-elevated/80"
                style={{ width: `${Math.max(4, Math.min(100, o.rendered_percent))}%` }}
              />
              <div className="relative flex min-w-0 items-center gap-2.5">
                {chasersHaveAnyArt && (
                  <SubjectAvatar
                    art={o.art}
                    label={o.name}
                    sizeClass="h-8 w-8"
                    widthClass="w-8 h-1"
                    reserveSlotWhenMissing
                  />
                )}
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-text-primary">{o.name}</div>
                  {o.art?.detail && (
                    <div className="truncate text-[11px] text-text-muted">{o.art.detail}</div>
                  )}
                </div>
              </div>
              <span className="relative text-sm font-bold tabular-nums text-text-primary">
                {o.rendered_percent}%
              </span>
            </Link>
          ))}
        </div>
      )}

      <ShowAllButton
        expanded={expanded}
        totalCount={outcomes.length}
        visibleLimit={3}
        noun="contenders"
        onToggle={() => setExpanded((v) => !v)}
      />
    </div>
  );
}

function SiblingFieldsGridBlock({
  items,
  limit = 3,
}: {
  items: Record<string, unknown>[];
  limit?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? items : items.slice(0, limit);
  return (
    <div className="space-y-2.5" data-machinery-form="sibling_fields_grid">
      <div className="grid grid-cols-1 gap-3">
        {shown.map((m) => {
          const mid = Number(m.market_id ?? 0);
          const title = String(m.title ?? "");
          const href = String(m.href ?? `/futures/${mid}`);
          const scaleOrdered = Boolean(m.scale_ordered);
          const leaderOid = Number(m.leader_outcome_id ?? 0);
          const outcomes = ((m.outcomes as MachineryOutcomeVisual[] | undefined) ?? []).slice(0, 4);
          const marketHasAnyArt = !scaleOrdered && outcomes.some((o) => Boolean(o.art?.url));
          return (
            <Link
              key={mid}
              href={href}
              data-scale-ordered={scaleOrdered ? "true" : undefined}
              className="block rounded-card border border-surface-border bg-surface-card p-3.5 transition-colors hover:bg-surface-elevated"
            >
              <div className="mb-2.5 flex items-center justify-between gap-2">
                <h3 className="text-sm font-bold text-text-primary">{title}</h3>
                <span className="text-xs text-text-muted" aria-hidden="true">
                  ›
                </span>
              </div>
              <div className="space-y-2">
                {outcomes.map((o) => {
                  const isPoster = o.art?.kind === "tmdb_poster";
                  const isFav = !scaleOrdered || (leaderOid > 0 && o.outcome_id === leaderOid);
                  return (
                    <div key={o.outcome_id} className="flex items-center gap-2.5">
                      {marketHasAnyArt && (
                        <SubjectAvatar
                          art={o.art}
                          label={o.name}
                          sizeClass={isPoster ? "h-9 w-7" : "h-7 w-7"}
                          widthClass="w-7 h-1"
                          poster={isPoster}
                          reserveSlotWhenMissing
                        />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline justify-between gap-2">
                          <span
                            className={`truncate text-xs ${
                              isFav ? "font-semibold text-text-primary" : "font-medium text-text-secondary"
                            }`}
                          >
                            {o.name}
                          </span>
                          <span
                            className={`text-xs tabular-nums ${
                              isFav ? "font-bold text-text-primary" : "font-semibold text-text-secondary"
                            }`}
                          >
                            {o.rendered_percent}%
                          </span>
                        </div>
                        <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-elevated">
                          <div
                            className={`h-full rounded-full ${isFav ? "bg-accent-brand" : "bg-slate-400"}`}
                            style={{
                              width: `${Math.max(4, Math.min(100, o.rendered_percent))}%`,
                              backgroundColor: !scaleOrdered ? o.art?.accent_color || undefined : undefined,
                            }}
                          />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Link>
          );
        })}
      </div>
      <ShowAllButton
        expanded={expanded}
        totalCount={items.length}
        visibleLimit={limit}
        noun="markets"
        onToggle={() => setExpanded((v) => !v)}
      />
    </div>
  );
}

function BenchmarkStripBlock({
  items,
  limit = 3,
}: {
  items: Record<string, unknown>[];
  limit?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? items : items.slice(0, limit);
  const stripHasAnyArt = shown.some((m) =>
    Boolean(((m.outcomes as MachineryOutcomeVisual[] | undefined)?.[0])?.art?.url),
  );
  return (
    <div className="space-y-2" data-machinery-form="benchmark_strip">
      <div className="divide-y divide-surface-border rounded-card border border-surface-border bg-surface-card">
        {shown.map((m) => {
          const mid = Number(m.market_id ?? 0);
          const title = String(m.title ?? "");
          const href = String(m.href ?? `/futures/${mid}`);
          const outcomes = (m.outcomes as MachineryOutcomeVisual[] | undefined) ?? [];
          const yes = outcomes[0];
          if (!yes) return null;
          return (
            <Link
              key={mid}
              href={href}
              className="flex items-center justify-between gap-3 px-3.5 py-2.5 transition-colors hover:bg-surface-elevated"
            >
              <div className="flex min-w-0 items-center gap-2.5">
                {stripHasAnyArt && (
                  <SubjectAvatar
                    art={yes.art}
                    label={title}
                    sizeClass="h-7 w-7"
                    widthClass="w-7 h-1"
                    reserveSlotWhenMissing
                  />
                )}
                <span className="line-clamp-2 text-xs font-medium text-text-primary">{title}</span>
              </div>
              <span className="shrink-0 rounded-md bg-surface-elevated px-2 py-1 text-xs font-bold tabular-nums text-text-primary">
                {yes.rendered_percent}%
              </span>
            </Link>
          );
        })}
      </div>
      <ShowAllButton
        expanded={expanded}
        totalCount={items.length}
        visibleLimit={limit}
        noun="benchmarks"
        onToggle={() => setExpanded((v) => !v)}
      />
    </div>
  );
}

function SingleHistoryChartCard({
  chart,
  compact = false,
}: {
  chart: MachineryHistoryChartItem;
  compact?: boolean;
}) {
  const W = 520;
  const H = compact ? 88 : 124;
  const L = 34;
  const R = W - 10;
  const T = 10;
  const B = H - 14;
  const yMin = Number.isFinite(chart.y_min) ? chart.y_min : 0;
  const yMax = Number.isFinite(chart.y_max) && chart.y_max > yMin ? chart.y_max : 100;
  const ySpan = Math.max(1, yMax - yMin);
  const yMid = Math.round((yMin + yMax) / 2);
  const yOf = (pct: number) => B - ((Math.max(yMin, Math.min(yMax, pct)) - yMin) / ySpan) * (B - T);

  const series = resolveDistinctChartSeries((chart.series ?? []).slice(0, 3));
  const inner = (
    <>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="truncate text-xs font-bold text-text-primary">{chart.title}</span>
        <span className="shrink-0 text-[11px] text-text-muted">
          {formatShortSpanDate(chart.start_iso)}–{formatShortSpanDate(chart.end_iso)}
        </span>
      </div>
      <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1">
        {series.slice(0, 3).map((s) => (
          <span key={s.outcome_id} className="inline-flex items-center gap-1.5 text-[11px]">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            <span className="truncate font-medium text-text-secondary">{s.name}</span>
            <span className="font-bold tabular-nums text-text-primary">{s.current_pct}%</span>
          </span>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className={compact ? "h-20 w-full" : "h-28 w-full"}
        role="img"
        aria-label={`Probability trend chart for ${chart.title}`}
      >
        {[yMin, yMid, yMax].map((tick) => (
          <g key={tick}>
            <line
              x1={L}
              x2={R}
              y1={yOf(tick)}
              y2={yOf(tick)}
              stroke="var(--surface-border)"
              strokeWidth={1}
            />
            <text
              x={0}
              y={yOf(tick) + 3}
              fontSize={10}
              fill="var(--text-muted)"
            >
              {tick}%
            </text>
          </g>
        ))}
        {series.slice(0, 3).map((s) => {
          const pts = s.points ?? [];
          if (!pts.length) return null;
          const d = pts
            .map((pt, idx) => {
              const x = L + (pts.length === 1 ? 0.5 : idx / (pts.length - 1)) * (R - L);
              const y = yOf(pt.pct);
              return `${idx === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
            })
            .join(" ");
          const lastY = yOf(pts[pts.length - 1].pct);
          return (
            <g key={s.outcome_id}>
              <path
                d={d}
                fill="none"
                stroke={s.color}
                strokeWidth={2.25}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle cx={R} cy={lastY} r={3} fill={s.color} />
            </g>
          );
        })}
      </svg>
    </>
  );

  if (compact) {
    return (
      <div
        data-testid="machinery-card-mini-chart"
        className="mt-3 rounded-lg border border-surface-border bg-surface-elevated/40 p-2.5"
      >
        {inner}
      </div>
    );
  }

  return (
    <Link
      href={chart.href || `/futures/${chart.market_id}`}
      className="block rounded-card border border-surface-border bg-surface-card p-3.5 transition-colors hover:bg-surface-elevated"
    >
      {inner}
    </Link>
  );
}

function ProbabilityHistoryChartBlock({
  items,
  limit = 3,
}: {
  items: Record<string, unknown>[];
  limit?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const charts = items as unknown as MachineryHistoryChartItem[];
  const shown = expanded ? charts : charts.slice(0, limit);
  return (
    <div className="space-y-2.5" data-machinery-form="probability_history_chart">
      <div className="grid grid-cols-1 gap-3">
        {shown.map((chart) => (
          <SingleHistoryChartCard key={chart.market_id} chart={chart} />
        ))}
      </div>
      <ShowAllButton
        expanded={expanded}
        totalCount={charts.length}
        visibleLimit={limit}
        noun="charts"
        onToggle={() => setExpanded((v) => !v)}
      />
    </div>
  );
}

export default function MachinerySectionRenderer({
  visualBlock,
  members,
}: {
  visualBlock: MachineryVisualBlock;
  members: CollectionMember[];
}) {
  const { form_id, initial_visible_limit, paired_metric_set, items = [] } = visualBlock;
  const limit = Math.min(3, Math.max(1, Number(initial_visible_limit ?? 3)));
  if (form_id === "paired_stage_bars" && paired_metric_set) {
    return (
      <div data-machinery-form="paired_stage_bars">
        <AwardCategoryPairedCard
          set={paired_metric_set}
          surface="collection"
          initialLimit={limit}
          showHeader={false}
        />
      </div>
    );
  }
  if (form_id === "probability_history_chart") {
    return <ProbabilityHistoryChartBlock items={items} limit={limit} />;
  }
  if (form_id === "coin_flip_matchups") {
    return <CoinFlipMatchupsBlock items={items} limit={limit} />;
  }
  if (form_id === "matchup_slate") {
    return <MatchupSlateBlock members={members} limit={limit} />;
  }
  if (form_id === "duel_bar") {
    return <DuelBarBlock items={items} />;
  }
  if (form_id === "contender_spotlight") {
    return <ContenderSpotlightBlock items={items} limit={limit} />;
  }
  if (form_id === "benchmark_strip") {
    return <BenchmarkStripBlock items={items} limit={limit} />;
  }
  return <SiblingFieldsGridBlock items={items} limit={limit} />;
}

export function MachineryDiscoverCard({ card }: { card: MachineryCardContract }) {
  const isEventCard =
    card.form_id === "coin_flip_matchups" || card.form_id === "matchup_slate";
  const maxPct = card.rows.reduce(
    (acc, r) => Math.max(acc, Number(r.rendered_percent ?? 0)),
    0,
  );
  const anyCardAwayArt =
    isEventCard &&
    card.rows.some((r) => Boolean((r.away_art as MachinerySubjectArt | undefined)?.url));
  const anyCardHomeArt =
    isEventCard &&
    card.rows.some((r) => Boolean((r.home_art as MachinerySubjectArt | undefined)?.url));
  const anyCardOutcomeArt =
    !isEventCard &&
    !card.scale_ordered &&
    card.rows.some((r) => Boolean((r.art as MachinerySubjectArt | undefined)?.url));

  return (
    <Link
      href={card.destination_href}
      data-testid="machinery-discover-card"
      data-machinery-card-form={card.form_id}
      data-scale-ordered={card.scale_ordered ? "true" : undefined}
      className="block rounded-card border border-surface-border bg-surface-card p-4 transition-colors hover:bg-surface-elevated"
    >
      <div className="mb-1 text-[11px] font-bold uppercase tracking-wider text-accent-brand">
        {card.kicker}
      </div>
      <h3 className="text-base font-bold leading-snug text-text-primary">{card.title}</h3>
      {card.subtitle && (
        <p className="mt-0.5 text-xs text-text-secondary">{card.subtitle}</p>
      )}

      {card.mini_chart && <SingleHistoryChartCard chart={card.mini_chart} compact />}

      <div className="mt-3 divide-y divide-surface-border">
        {isEventCard
          ? card.rows.map((r) => {
              const eid = Number(r.event_id ?? 0);
              const awayShort = String(r.away_short ?? "");
              const homeShort = String(r.home_short ?? "");
              const awayPct = Number(r.away_pct ?? 50);
              const homePct = Number(r.home_pct ?? 50);
              const awayArt = r.away_art as MachinerySubjectArt | undefined;
              const homeArt = r.home_art as MachinerySubjectArt | undefined;
              return (
                <div key={eid} className="flex items-center justify-between gap-2 py-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <SubjectAvatar
                      art={awayArt}
                      label={awayShort}
                      sizeClass="h-7 w-7"
                      widthClass="w-7 h-1"
                      reserveSlotWhenMissing={anyCardAwayArt}
                    />
                    <span className="text-xs font-semibold text-text-primary">{awayShort}</span>
                    <span className="text-[11px] text-text-muted">at</span>
                    <SubjectAvatar
                      art={homeArt}
                      label={homeShort}
                      sizeClass="h-7 w-7"
                      widthClass="w-7 h-1"
                      reserveSlotWhenMissing={anyCardHomeArt}
                    />
                    <span className="text-xs font-semibold text-text-primary">{homeShort}</span>
                  </div>
                  <span className="shrink-0 text-xs font-bold tabular-nums text-text-primary">
                    {awayPct}%–{homePct}%
                  </span>
                </div>
              );
            })
          : card.rows.map((r) => {
              const oid = Number(r.outcome_id ?? 0);
              const name = String(r.name ?? "");
              const pct = Number(r.rendered_percent ?? 0);
              const art = r.art as MachinerySubjectArt | undefined;
              const isFav = !card.scale_ordered || pct === maxPct;
              return (
                <div key={oid} className="flex items-center gap-2.5 py-2">
                  {anyCardOutcomeArt && (
                    <SubjectAvatar
                      art={art}
                      label={name}
                      sizeClass="h-8 w-8"
                      widthClass="w-8 h-1"
                      reserveSlotWhenMissing
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span
                        className={`truncate text-sm ${
                          isFav ? "font-semibold text-text-primary" : "font-medium text-text-secondary"
                        }`}
                      >
                        {name}
                      </span>
                      <span
                        className={`text-sm tabular-nums ${
                          isFav ? "font-bold text-text-primary" : "font-semibold text-text-secondary"
                        }`}
                      >
                        {pct}%
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-elevated">
                      <div
                        className={`h-full rounded-full ${isFav ? "bg-accent-brand" : "bg-slate-400"}`}
                        style={{
                          width: `${Math.max(4, Math.min(100, pct))}%`,
                          backgroundColor: !card.scale_ordered ? art?.accent_color || undefined : undefined,
                        }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
      </div>

      <div className="mt-3 flex flex-col gap-1 border-t border-surface-border pt-2.5 text-xs text-text-secondary">
        {card.footer ? <span>{card.footer}</span> : null}
        <span className="font-semibold text-accent-brand">
          Open all {card.section_count} sections ›
        </span>
      </div>
    </Link>
  );
}
