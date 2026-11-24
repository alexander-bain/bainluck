"use client";
/* eslint-disable @next/next/no-img-element */

/**
 * Issue 13551 (Ruling 366: B, 367: A, and Fable's 7 rules) — Kit v1 web renderer.
 * Light-mode semantic tokens only (`bg-surface-*`, `text-text-*`, `border-surface-border`,
 * `text-accent-*`), zero dark-mode utilities, zero raw hex colors in TSX.
 */

import React from "react";
import type {
  BubbleLineData,
  CalendarStripData,
  CountdownData,
  DatedTilesData,
  KitV1CardSpec,
  OneInNData,
  RoadAheadData,
  ScoreboardGridData,
  SingleSportSlateData,
} from "./types";

function MemberAvatar({
  src,
  alt,
  size = "sm",
  contain = false,
}: {
  src: string;
  alt: string;
  size?: "xs" | "sm" | "md";
  contain?: boolean;
}) {
  const dim =
    size === "xs"
      ? "h-5 w-5"
      : size === "md"
      ? "h-8 w-8"
      : "h-6 w-6";
  return (
    <img
      src={src}
      alt={alt}
      className={`${dim} shrink-0 rounded-full border border-surface-border bg-surface-base ${
        contain ? "object-contain p-0.5" : "object-cover"
      }`}
    />
  );
}

function heatToneClass(pct: number): string {
  if (pct >= 60) return "bg-accent-brand text-text-inverse";
  if (pct >= 30) return "bg-accent-brand/20 text-text-primary";
  if (pct >= 12) return "bg-accent-brand/10 text-text-primary";
  return "bg-surface-elevated text-text-secondary";
}

function ScoreboardGridBody({ data }: { data: ScoreboardGridData }) {
  return (
    <div className="space-y-1.5">
      <div
        className="grid items-end gap-1.5 pb-1 text-[10px] font-semibold leading-tight text-text-muted"
        style={{
          gridTemplateColumns: `16px minmax(0,1fr) repeat(${data.columns.length}, 66px)`,
        }}
      >
        <span>#</span>
        <span>Contender</span>
        {data.columns.map((c) => (
          <span key={c.key} className="text-center">
            {c.label}
          </span>
        ))}
      </div>
      {data.rows.map((row) => (
        <div
          key={`${row.rank}-${row.name}`}
          className="grid items-center gap-1.5 border-t border-surface-border/60 pt-1.5"
          style={{
            gridTemplateColumns: `16px minmax(0,1fr) repeat(${data.columns.length}, 66px)`,
          }}
        >
          <span className="text-[11px] font-bold tabular-nums text-text-muted">
            {row.rank}
          </span>
          <div className="flex min-w-0 items-center gap-1.5">
            <MemberAvatar
              src={row.image_url}
              alt={row.name}
              size="sm"
              contain={row.image_kind === "team"}
            />
            <span className="truncate text-xs font-semibold text-text-primary">
              {row.name}
            </span>
          </div>
          {data.columns.map((c) => {
            const val = row.cells[c.key];
            if (val === null || val === undefined) {
              return (
                <div
                  key={c.key}
                  className="flex h-7 items-center justify-center rounded-md bg-surface-elevated text-[11px] text-text-muted"
                >
                  —
                </div>
              );
            }
            return (
              <div
                key={c.key}
                className={`flex h-7 items-center justify-center rounded-md text-xs font-bold tabular-nums ${heatToneClass(
                  val,
                )}`}
              >
                {val}%
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function DatedTilesBody({ data }: { data: DatedTilesData }) {
  return (
    <div className="space-y-3">
      {data.rows.map((row) => {
        const visibleCols = data.aligned
          ? data.columns
          : data.columns.filter((c) => row.cells[c.key] !== null && row.cells[c.key] !== undefined);
        return (
          <div key={row.name} className="space-y-1.5 border-t border-surface-border/60 pt-2 first:border-t-0 first:pt-0">
            <div className="flex items-center gap-2">
              <MemberAvatar
                src={row.image_url}
                alt={row.name}
                size="xs"
                contain={row.image_kind !== "person"}
              />
              <span className="text-xs font-semibold leading-snug text-text-primary">
                {row.name}
              </span>
            </div>
            <div
              className="grid gap-1.5"
              style={{
                gridTemplateColumns: `repeat(${Math.max(1, visibleCols.length)}, minmax(0,1fr))`,
              }}
            >
              {visibleCols.map((col) => {
                const v = row.cells[col.key];
                const hasVal = v !== null && v !== undefined;
                return (
                  <div
                    key={col.key}
                    className={`rounded-lg border border-surface-border/60 px-2 py-1.5 text-center ${
                      hasVal ? heatToneClass(v) : "bg-surface-elevated/60 text-text-muted"
                    }`}
                  >
                    <div className="text-[10px] font-medium opacity-85">
                      by {col.label}
                    </div>
                    <div className="mt-0.5 text-sm font-bold tabular-nums">
                      {hasVal ? `${v}%` : "—"}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CountdownBody({ data }: { data: CountdownData }) {
  return (
    <div className="space-y-2.5">
      <div className="flex items-baseline gap-2.5 rounded-lg border border-surface-border bg-surface-elevated px-3 py-2">
        <span className="text-2xl font-extrabold tabular-nums text-accent-brand">
          {data.days_left}
        </span>
        <div className="min-w-0">
          <div className="text-xs font-bold text-text-primary">
            {data.days_left === 1 ? "day left" : "days left"}
          </div>
          <div className="text-[11px] text-text-muted">{data.deadline_label}</div>
        </div>
      </div>
      <div className="divide-y divide-surface-border/60">
        {data.rows.map((row) => (
          <div key={row.name} className="flex items-center gap-2 py-2">
            <MemberAvatar
              src={row.image_url}
              alt={row.name}
              size="sm"
              contain={row.image_kind !== "person"}
            />
            <span className="min-w-0 flex-1 text-xs leading-snug text-text-primary">
              {row.name}
            </span>
            <div className="h-2 w-14 shrink-0 overflow-hidden rounded-full bg-surface-elevated">
              <div
                className="h-full rounded-full bg-accent-brand"
                style={{ width: `${Math.max(3, row.p)}%` }}
              />
            </div>
            <span className="w-9 shrink-0 text-right text-xs font-bold tabular-nums text-text-primary">
              {row.p}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RoadAheadBody({ data }: { data: RoadAheadData }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1.5">
        <MemberAvatar src={data.team_image_url} alt={data.team_name} size="sm" contain />
        <span className="text-xs font-bold text-text-primary">{data.team_name}</span>
      </div>
      <div className="divide-y divide-surface-border/60">
        {data.rows.map((row) => (
          <div key={`${row.day}-${row.opponent_abbr}`} className="flex items-center gap-2 py-2">
            <div className="w-16 shrink-0 text-[10px] leading-tight text-text-muted">
              <div className="font-semibold text-text-secondary">{row.day}</div>
              <div>{row.clock}</div>
            </div>
            <div className="flex min-w-0 flex-1 items-center gap-1.5">
              <MemberAvatar src={row.opponent_image_url} alt={row.opponent_name} size="sm" contain />
              <span className="text-xs font-semibold text-text-primary">
                {row.home_or_away} {row.opponent_abbr}
              </span>
            </div>
            <div className="h-2.5 w-20 shrink-0 overflow-hidden rounded-full bg-surface-elevated">
              <div
                className="h-full rounded-full bg-accent-brand"
                style={{
                  width: `${Math.max(4, row.team_p)}%`,
                  backgroundColor: data.team_color ?? undefined,
                }}
              />
            </div>
            <span className="w-9 shrink-0 text-right text-xs font-bold tabular-nums text-text-primary">
              {row.team_p}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function BubbleLineBody({ data }: { data: BubbleLineData }) {
  const maxLane = data.points.reduce(
    (m, pt) => (pt.in_doubt && typeof pt.lane === "number" ? Math.max(m, pt.lane) : m),
    0,
  );
  const trackHeight = (maxLane + 1) * 26 + 52;
  const doubtTeams = data.points.filter((pt) => pt.in_doubt);
  const outsideTeams = data.points.filter((pt) => !pt.in_doubt);

  return (
    <div className="space-y-2.5">
      <div className="relative w-full" style={{ height: `${trackHeight}px` }}>
        {/* Shaded in-doubt band */}
        <div
          className="absolute bottom-5 top-0 rounded-lg bg-surface-elevated/80 border border-surface-border/50"
          style={{
            left: `${data.band_low}%`,
            width: `${data.band_high - data.band_low}%`,
          }}
        >
          <div className="pt-0.5 text-center text-[10px] font-semibold uppercase tracking-wide text-text-muted">
            {data.band_label}
          </div>
        </div>

        {/* Base 0-100 axis */}
        <div className="absolute bottom-5 left-0 right-0 h-0.5 bg-surface-border" />

        {/* Outside points plotted above baseline */}
        {outsideTeams.map((pt, idx) => (
          <div
            key={`${pt.abbr}-${idx}`}
            title={`${pt.name}: ${pt.p}%`}
            className="absolute h-2.5 w-2.5 -translate-x-1/2 rounded-full border border-surface-card bg-text-muted"
            style={{
              left: `${Math.min(98, Math.max(2, pt.p))}%`,
              bottom: `${22 + (idx % 3) * 6}px`,
              backgroundColor: pt.color ?? undefined,
            }}
          />
        ))}

        {/* Elevated team crest pins for teams in doubt */}
        {doubtTeams.map((pt) => {
          const bottomPx = 28 + (pt.lane ?? 0) * 24;
          return (
            <div
              key={pt.abbr}
              title={`${pt.name}: ${pt.p}%`}
              className="absolute flex -translate-x-1/2 flex-col items-center"
              style={{
                left: `${pt.p}%`,
                bottom: `${bottomPx}px`,
              }}
            >
              <img
                src={pt.image_url}
                alt={pt.abbr}
                className="h-5 w-5 rounded-full border border-surface-border bg-surface-card object-contain p-0.5 shadow-sm"
              />
            </div>
          );
        })}

        {/* Axis tick labels */}
        <div className="absolute bottom-0 left-0 right-0 flex justify-between text-[10px] tabular-nums text-text-muted">
          <span>0%</span>
          <span>{data.band_low}%</span>
          <span>50%</span>
          <span>{data.band_high}%</span>
          <span>100%</span>
        </div>
      </div>

      <div className="flex items-center justify-between text-[11px] font-semibold text-text-secondary">
        <span>
          {data.low_count} at {data.band_low}% or less
        </span>
        <span>
          {data.high_count} at {data.band_high}% or more
        </span>
      </div>

      <p className="rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1.5 text-[11px] leading-relaxed text-text-secondary">
        {data.doubt_summary}
      </p>
    </div>
  );
}

function OneInNBody({ data }: { data: OneInNData }) {
  return (
    <div className="divide-y divide-surface-border/60">
      {data.rows.map((row) => (
        <div key={row.name} className="flex items-center gap-2 py-2 first:pt-0 last:pb-0">
          <MemberAvatar
            src={row.image_url}
            alt={row.name}
            size="sm"
            contain={row.image_kind !== "person"}
          />
          <span className="min-w-0 flex-1 text-xs leading-snug text-text-primary">
            {row.name}
          </span>
          <div className="flex shrink-0 items-baseline gap-1.5">
            <span className="text-sm font-extrabold tabular-nums text-accent-brand">
              1 in {row.one_in_n}
            </span>
            <span className="text-[11px] font-semibold tabular-nums text-text-muted">
              {row.p}%
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function SingleSportSlateBody({ data }: { data: SingleSportSlateData }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wide text-text-muted">
        <span>{data.league_label}</span>
        <span>{data.rows.length} games</span>
      </div>
      <div className="divide-y divide-surface-border/60">
        {data.rows.map((game) => {
          const isLive = game.status === "live";
          return (
            <div key={`${game.away.abbr}-${game.home.abbr}`} className="py-2 first:pt-0 last:pb-0">
              <div className="flex items-center gap-2">
                <MemberAvatar src={game.away.image_url} alt={game.away.abbr} size="sm" contain />
                <span className="w-8 shrink-0 text-[11px] font-bold text-text-primary">
                  {game.away.abbr}
                </span>
                <span className="w-8 shrink-0 text-xs font-bold tabular-nums text-text-primary">
                  {game.away.p}%
                </span>
                <div className="flex h-2.5 flex-1 overflow-hidden rounded-full bg-surface-elevated">
                  <div
                    className="h-full bg-accent-brand"
                    style={{
                      width: `${game.away.p}%`,
                      backgroundColor: game.away.color ?? undefined,
                    }}
                  />
                  <div
                    className="h-full border-l border-surface-card bg-accent-live"
                    style={{
                      width: `${game.home.p}%`,
                      backgroundColor: game.home.color ?? undefined,
                    }}
                  />
                </div>
                <span className="w-8 shrink-0 text-right text-xs font-bold tabular-nums text-text-primary">
                  {game.home.p}%
                </span>
                <span className="w-8 shrink-0 text-right text-[11px] font-bold text-text-primary">
                  {game.home.abbr}
                </span>
                <MemberAvatar src={game.home.image_url} alt={game.home.abbr} size="sm" contain />
              </div>
              <div className="mt-1 text-center text-[10px] font-medium text-text-muted">
                {isLive && game.score[0] !== null && game.score[1] !== null
                  ? `Live · ${game.score[0]}–${game.score[1]}`
                  : `${game.day} · ${game.clock}`}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CalendarStripBody({ data }: { data: CalendarStripData }) {
  const maxPct = Math.max(1, ...data.days.map((d) => d.daily_pct));
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[11px] font-medium text-text-muted">
        <span>{data.month_span_label}</span>
        <span className="text-accent-brand font-semibold">Daily chance</span>
      </div>
      <div
        className="grid gap-1"
        style={{ gridTemplateColumns: `repeat(${data.days.length}, minmax(0,1fr))` }}
      >
        {data.days.map((day) => {
          const isZero = day.daily_pct <= 0;
          const ratio = day.daily_pct / maxPct;
          const shadeClass = day.is_peak
            ? "border-accent-brand bg-accent-brand text-text-inverse"
            : isZero
            ? "border-surface-border bg-surface-elevated text-text-muted"
            : ratio >= 0.4
            ? "border-accent-brand/40 bg-accent-brand/30 text-text-primary"
            : ratio >= 0.15
            ? "border-accent-brand/30 bg-accent-brand/20 text-text-primary"
            : "border-surface-border bg-accent-brand/10 text-text-primary";
          return (
            <div key={`${day.month_abbr}-${day.day_num}`} className="text-center">
              <div className="mb-0.5 text-[10px] font-medium text-text-muted">{day.dow}</div>
              <div className={`rounded-lg border px-0.5 py-1.5 ${shadeClass}`}>
                <div className="text-xs font-extrabold tabular-nums">{day.day_num}</div>
                <div
                  className={`mt-0.5 text-[10px] font-bold tabular-nums ${
                    day.is_peak ? "text-text-inverse" : "text-text-secondary"
                  }`}
                >
                  {isZero ? "·" : `${day.daily_pct}%`}
                </div>
              </div>
              <div className="mt-0.5 text-[9px] text-text-muted">{day.month_abbr}</div>
            </div>
          );
        })}
      </div>
      <p className="text-[11px] leading-snug text-text-secondary">{data.ladder_rule_note}</p>
      <p className="text-[10px] text-text-muted">{data.ladder_footer}</p>
    </div>
  );
}

export function KitCardRenderer({ spec }: { spec: KitV1CardSpec }) {
  if (spec.refusal_reason || !spec.look || !spec.data) {
    return (
      <article className="w-full rounded-2xl border border-accent-danger/40 bg-surface-card p-3.5 shadow-sm">
        <div className="text-[10px] font-bold uppercase tracking-wide text-accent-danger">
          Rule 1 fallback · Keep today&apos;s card
        </div>
        <p className="mt-1 text-xs leading-relaxed text-text-secondary">
          {spec.refusal_reason || "No Kit v1 shape fits safely; render standard card instead."}
        </p>
      </article>
    );
  }

  return (
    <article className="w-full rounded-2xl border border-surface-border bg-surface-card p-3.5 shadow-sm">
      {spec.kicker && (
        <div className="text-[10px] font-bold uppercase tracking-wider text-accent-brand">
          {spec.kicker}
        </div>
      )}
      {spec.common_headline && (
        <h3 className="mt-1 text-base font-bold leading-snug text-text-primary">
          {spec.common_headline}
        </h3>
      )}
      {spec.stat_caption && (
        <p className="mt-0.5 text-xs leading-snug text-text-secondary">
          {spec.stat_caption}
        </p>
      )}

      <div className="mt-3">
        {spec.look === "scoreboard_grid" && (
          <ScoreboardGridBody data={spec.data as ScoreboardGridData} />
        )}
        {spec.look === "dated_tiles" && (
          <DatedTilesBody data={spec.data as DatedTilesData} />
        )}
        {spec.look === "countdown" && (
          <CountdownBody data={spec.data as CountdownData} />
        )}
        {spec.look === "road_ahead" && (
          <RoadAheadBody data={spec.data as RoadAheadData} />
        )}
        {spec.look === "bubble_line" && (
          <BubbleLineBody data={spec.data as BubbleLineData} />
        )}
        {spec.look === "one_in_n" && (
          <OneInNBody data={spec.data as OneInNData} />
        )}
        {spec.look === "single_sport_slate" && (
          <SingleSportSlateBody data={spec.data as SingleSportSlateData} />
        )}
        {spec.look === "calendar_strip" && (
          <CalendarStripBody data={spec.data as CalendarStripData} />
        )}
      </div>

      {spec.disclosure && (
        <p className="mt-2.5 border-t border-surface-border/60 pt-2 text-[11px] text-text-muted">
          {spec.disclosure}
        </p>
      )}
    </article>
  );
}
