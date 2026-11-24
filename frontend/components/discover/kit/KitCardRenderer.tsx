"use client";
/* eslint-disable @next/next/no-img-element */

/**
 * Issue 13551 (Ruling 366: B, 367: A, and Fable's 7 rules) — Layout-generic Kit v1 web renderer.
 * Draws purely from `layout` (`stack | grid | calendar | axis`) and the 8 shared marks.
 * `variant` is ignored at render time so unknown future variants still render cleanly.
 * Light-mode semantic tokens only (`bg-surface-*`, `text-text-*`, `border-surface-border`,
 * `text-accent-*`), zero dark classes, zero literal color hexes in TSX.
 */

import React from "react";
import {
  ALLOWED_KIT_V1_LAYOUTS,
  ALLOWED_KIT_V1_MARKS,
  type KitV1AxisBody,
  type KitV1BarMark,
  type KitV1CalendarBody,
  type KitV1CardSpec,
  type KitV1DotMark,
  type KitV1GridBody,
  type KitV1Layout,
  type KitV1LineMark,
  type KitV1Mark,
  type KitV1NumberMark,
  type KitV1PictureMark,
  type KitV1RingMark,
  type KitV1StackBody,
  type KitV1TileMark,
  type KitV1WordMark,
} from "./types";

const MARK_SET = new Set<string>(ALLOWED_KIT_V1_MARKS);
const LAYOUT_SET = new Set<string>(ALLOWED_KIT_V1_LAYOUTS);
const MARKS_ARRAY_KEYS = new Set([
  "marks",
  "header_marks",
  "footer_marks",
  "leading",
  "summary_marks",
  "sub_marks",
]);

function validateMarksRecursive(node: unknown, insideMarksArray: boolean): boolean {
  if (Array.isArray(node)) {
    return node.every((el) => validateMarksRecursive(el, insideMarksArray));
  }
  if (!node || typeof node !== "object") {
    return true;
  }
  const obj = node as Record<string, unknown>;
  if ("mark" in obj || insideMarksArray) {
    if (typeof obj.mark !== "string" || !MARK_SET.has(obj.mark)) {
      return false;
    }
    if (obj.mark === "picture") {
      if (typeof obj.url !== "string" || !obj.url.startsWith("https://")) {
        return false;
      }
    }
  }
  for (const [key, val] of Object.entries(obj)) {
    if (key === "route") continue;
    if (!validateMarksRecursive(val, MARKS_ARRAY_KEYS.has(key))) {
      return false;
    }
  }
  return true;
}

function hasRenderableContent(layout: KitV1Layout, body: Record<string, unknown>): boolean {
  if (layout === "stack") {
    return Array.isArray(body.items) && body.items.length > 0;
  }
  if (layout === "grid") {
    return (
      Array.isArray(body.columns) &&
      body.columns.length > 0 &&
      Array.isArray(body.rows) &&
      body.rows.length > 0
    );
  }
  if (layout === "calendar") {
    return Array.isArray(body.days) && body.days.length >= 2;
  }
  if (layout === "axis") {
    const scale = body.scale as Record<string, unknown> | undefined;
    const hasScale =
      Boolean(scale) &&
      typeof scale?.min === "number" &&
      typeof scale?.max === "number" &&
      scale.min < scale.max &&
      Array.isArray(scale?.ticks) &&
      scale.ticks.length > 0;
    const hasPoints =
      (Array.isArray(body.marks) && body.marks.length > 0) ||
      (Array.isArray(body.series) && body.series.length > 0);
    return hasScale && hasPoints;
  }
  return false;
}

export function parseKitCardV1(raw: unknown): KitV1CardSpec | null {
  if (!raw || typeof raw !== "object") return null;
  const candidate = raw as Record<string, unknown>;
  if (candidate.kit_version !== 1) return null;
  if (typeof candidate.id !== "string" || !candidate.id.trim()) return null;
  if (candidate.refusal_reason || candidate.fallback_today === true) return null;

  const layout = candidate.layout;
  if (typeof layout !== "string" || !LAYOUT_SET.has(layout)) return null;

  const variant = candidate["variant"];
  if (variant !== undefined && variant !== null && typeof variant !== "string") return null;

  const body = candidate.body;
  if (!body || typeof body !== "object" || Array.isArray(body)) return null;
  const bodyRecord = body as Record<string, unknown>;
  if (!hasRenderableContent(layout as KitV1Layout, bodyRecord)) return null;
  if (!validateMarksRecursive(bodyRecord, false)) return null;

  return raw as KitV1CardSpec;
}

// ---------------------------------------------------------------------------
// Generic mark renderers (8 shared primitives)
// ---------------------------------------------------------------------------

function PictureMarkView({ mark }: { mark: KitV1PictureMark }) {
  const dim =
    mark.size === "xs"
      ? "h-5 w-5"
      : mark.size === "md"
      ? "h-8 w-8"
      : "h-6 w-6";
  const contain = mark.contain ?? mark.subject_kind !== "person";
  return (
    <img
      src={mark.url}
      alt={mark.alt}
      className={`${dim} shrink-0 rounded-full border border-surface-border bg-surface-base ${
        contain ? "object-contain p-0.5" : "object-cover"
      }`}
    />
  );
}

function toneClass(tone?: string): string {
  if (tone === "accent") return "text-accent-brand";
  if (tone === "muted") return "text-text-muted";
  if (tone === "secondary") return "text-text-secondary";
  return "text-text-primary";
}

function alignClass(align?: string): string {
  if (align === "right") return "text-right";
  if (align === "center") return "text-center";
  return "text-left";
}

function wordWidthClass(width?: string): string {
  if (width === "flex") return "min-w-0 flex-1";
  if (width === "xs") return "w-8 shrink-0";
  if (width === "sm") return "w-16 shrink-0";
  return "shrink-0";
}

function WordMarkView({ mark }: { mark: KitV1WordMark }) {
  if (mark.style === "pill") {
    return (
      <p className="rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1.5 text-[11px] leading-relaxed text-text-secondary">
        {mark.text}
      </p>
    );
  }
  if (mark.style === "hero_label") {
    return (
      <div className="min-w-0 flex-1">
        <div className="text-xs font-bold text-text-primary">{mark.text}</div>
        {mark.secondary_text && (
          <div className="text-[11px] text-text-muted">{mark.secondary_text}</div>
        )}
      </div>
    );
  }
  if (mark.style === "kicker") {
    return (
      <span
        className={`text-[10px] font-bold uppercase tracking-wide ${toneClass(
          mark.tone,
        )} ${alignClass(mark.align)}`}
      >
        {mark.text}
      </span>
    );
  }
  if (mark.style === "meta") {
    return (
      <div
        className={`text-[10px] leading-tight ${toneClass(
          mark.tone,
        )} ${alignClass(mark.align)} ${wordWidthClass(mark.width)}`}
      >
        <div className={mark.secondary_text ? "font-semibold text-text-secondary" : "font-medium"}>
          {mark.text}
        </div>
        {mark.secondary_text && <div className="text-text-muted">{mark.secondary_text}</div>}
      </div>
    );
  }
  if (mark.style === "sub") {
    return (
      <span
        className={`text-[11px] font-medium leading-snug ${toneClass(
          mark.tone,
        )} ${alignClass(mark.align)}`}
      >
        {mark.text}
      </span>
    );
  }
  if (mark.style === "rank") {
    return (
      <span className="text-[11px] font-bold tabular-nums text-text-muted">
        {mark.text}
      </span>
    );
  }
  return (
    <span
      className={`text-xs leading-snug ${mark.bold ? "font-semibold" : ""} ${toneClass(
        mark.tone,
      )} ${alignClass(mark.align)} ${wordWidthClass(mark.width)}`}
    >
      {mark.text}
    </span>
  );
}

function NumberMarkView({ mark }: { mark: KitV1NumberMark }) {
  if (mark.prominence === "hero") {
    return (
      <span className={`text-2xl font-extrabold tabular-nums ${toneClass(mark.tone)}`}>
        {mark.display}
      </span>
    );
  }
  const sizeWeight =
    mark.unit === "one_in_n"
      ? "text-sm font-extrabold"
      : mark.prominence === "secondary"
      ? "text-[11px] font-semibold"
      : "text-xs font-bold";
  const widthCls =
    mark.width === "xs"
      ? "w-8 shrink-0"
      : mark.width === "sm"
      ? "w-9 shrink-0"
      : "shrink-0";
  return (
    <span
      className={`tabular-nums ${sizeWeight} ${toneClass(mark.tone)} ${alignClass(
        mark.align,
      )} ${widthCls}`}
    >
      {mark.display}
    </span>
  );
}

function BarMarkView({ mark }: { mark: KitV1BarMark }) {
  if (mark.bar_style === "split" && Array.isArray(mark.segments)) {
    return (
      <div className="flex h-2.5 flex-1 overflow-hidden rounded-full bg-surface-elevated">
        {mark.segments.map((seg, idx) => (
          <div
            key={`${seg.label ?? idx}-${idx}`}
            className={`h-full ${
              idx === 0 ? "bg-accent-brand" : "border-l border-surface-card bg-accent-live"
            }`}
            style={{
              width: `${Math.max(0, Math.min(100, seg.fill * 100))}%`,
              backgroundColor: seg.color ?? undefined,
            }}
          />
        ))}
      </div>
    );
  }
  if (mark.bar_style === "range" && typeof mark.lo === "number" && typeof mark.hi === "number") {
    const leftPct = Math.max(0, Math.min(96, mark.lo * 100));
    const widthPct = Math.max(4, Math.min(100 - leftPct, (mark.hi - mark.lo) * 100));
    return (
      <div className="relative h-5 flex-1 rounded bg-surface-elevated">
        <div
          className="absolute top-1 bottom-1 flex items-center justify-center rounded bg-accent-brand/25 px-1 text-[10px] font-bold tabular-nums text-text-primary"
          style={{
            left: `${leftPct}%`,
            width: `${widthPct}%`,
            backgroundColor: mark.fill_color ?? undefined,
          }}
        >
          {mark.pct_label ?? ""}
        </div>
      </div>
    );
  }
  const trackWidth =
    mark.width === "md" ? "h-2.5 w-20" : mark.width === "flex" ? "h-2 flex-1" : "h-2 w-14";
  const pct = Math.max(3, Math.min(100, (mark.fill ?? 0) * 100));
  return (
    <div className={`${trackWidth} shrink-0 overflow-hidden rounded-full bg-surface-elevated`}>
      <div
        className="h-full rounded-full bg-accent-brand"
        style={{
          width: `${pct}%`,
          backgroundColor: mark.fill_color ?? undefined,
        }}
      />
    </div>
  );
}

function tileToneClass(mark: KitV1TileMark): string {
  if (mark.muted) {
    return "border-surface-border/60 bg-surface-elevated/60 text-text-muted";
  }
  if (mark.highlight_role === "day_peak" || mark.shade >= 0.6) {
    return "border-accent-brand bg-accent-brand text-text-inverse";
  }
  if (mark.shade >= 0.3) {
    return "border-accent-brand/40 bg-accent-brand/25 text-text-primary";
  }
  if (mark.shade >= 0.12) {
    return "border-accent-brand/30 bg-accent-brand/15 text-text-primary";
  }
  return "border-surface-border/60 bg-surface-elevated text-text-secondary";
}

function TileMarkView({ mark }: { mark: KitV1TileMark }) {
  const isCompactMatrix = !mark.top_label && !mark.bottom_label;
  if (isCompactMatrix) {
    return (
      <div
        className={`flex h-7 items-center justify-center rounded-md border text-xs font-bold tabular-nums ${tileToneClass(
          mark,
        )}`}
      >
        {mark.center_label}
      </div>
    );
  }
  const hasBottom = mark.bottom_label !== undefined && mark.bottom_label !== null;
  return (
    <div className={`rounded-lg border px-1.5 py-1.5 text-center ${tileToneClass(mark)}`}>
      {mark.top_label && (
        <div className="text-[10px] font-medium opacity-85">{mark.top_label}</div>
      )}
      <div
        className={`${mark.top_label ? "mt-0.5 text-sm" : "text-xs"} font-extrabold tabular-nums`}
      >
        {mark.center_label}
      </div>
      {hasBottom && (
        <div
          className={`mt-0.5 text-[10px] font-bold tabular-nums ${
            mark.highlight_role === "day_peak"
              ? "text-text-inverse"
              : mark.muted
              ? "text-text-muted"
              : "text-text-secondary"
          }`}
        >
          {mark.bottom_label}
        </div>
      )}
    </div>
  );
}

function RingMarkView({ mark }: { mark: KitV1RingMark }) {
  const pct = Math.round(Math.max(0, Math.min(1, mark.progress)) * 100);
  return (
    <span className="inline-flex h-7 min-w-7 items-center justify-center rounded-full border-2 border-accent-brand px-1 text-[10px] font-bold tabular-nums text-text-primary">
      {mark.label ?? `${pct}%`}
    </span>
  );
}

function KitMarkView({ mark }: { mark: KitV1Mark }) {
  switch (mark.mark) {
    case "picture":
      return <PictureMarkView mark={mark} />;
    case "word":
      return <WordMarkView mark={mark} />;
    case "number":
      return <NumberMarkView mark={mark} />;
    case "bar":
      return <BarMarkView mark={mark} />;
    case "tile":
      return <TileMarkView mark={mark} />;
    case "ring":
      return <RingMarkView mark={mark} />;
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// 4 Generic Layout Renderers (zero branching on variant hint)
// ---------------------------------------------------------------------------

function StackLayout({ body }: { body: KitV1StackBody }) {
  const headerMarks = body.header_marks ?? [];
  const footerMarks = body.footer_marks ?? [];
  return (
    <div className="space-y-2.5">
      {headerMarks.length > 0 && body.header_layout === "banner" && (
        <div className="flex items-center gap-2.5 rounded-lg border border-surface-border bg-surface-elevated px-3 py-2">
          {headerMarks.map((m, idx) => (
            <KitMarkView key={`sh-${idx}`} mark={m} />
          ))}
        </div>
      )}
      {headerMarks.length > 0 && body.header_layout === "split" && (
        <div className="flex items-center justify-between gap-2">
          {headerMarks.map((m, idx) => (
            <KitMarkView key={`shs-${idx}`} mark={m} />
          ))}
        </div>
      )}

      <div className="divide-y divide-surface-border/60">
        {body.items.map((item) => (
          <div key={item.id} className="py-2 first:pt-0 last:pb-0">
            <div className="flex items-center gap-2">
              {item.marks.map((m, mIdx) => (
                <KitMarkView key={`${item.id}-m-${mIdx}`} mark={m} />
              ))}
            </div>
            {item.sub_marks && item.sub_marks.length > 0 && (
              <div className="mt-1 flex justify-center gap-2">
                {item.sub_marks.map((sm, smIdx) => (
                  <KitMarkView key={`${item.id}-sm-${smIdx}`} mark={sm} />
                ))}
              </div>
            )}
            {item.divider_after && (
              <div className="mt-2 border-t border-dashed border-surface-border pt-1 text-center text-[10px] font-semibold text-text-muted">
                {item.divider_after.label}
              </div>
            )}
          </div>
        ))}
      </div>

      {footerMarks.length > 0 && (
        <div className="space-y-1">
          {footerMarks.map((m, idx) => (
            <KitMarkView key={`sf-${idx}`} mark={m} />
          ))}
        </div>
      )}
    </div>
  );
}

function GridLayout({ body }: { body: KitV1GridBody }) {
  if (body.row_layout === "matrix") {
    const firstLeading = body.rows[0]?.leading ?? [];
    const hasRank =
      firstLeading.length > 0 &&
      firstLeading[0]?.mark === "word" &&
      firstLeading[0]?.style === "rank";
    const gridCols = hasRank
      ? `16px minmax(0,1fr) repeat(${body.columns.length}, 66px)`
      : `minmax(0,1fr) repeat(${body.columns.length}, 66px)`;

    return (
      <div className="space-y-1.5">
        {body.show_column_headers && (
          <div
            className="grid items-end gap-1.5 pb-1 text-[10px] font-semibold leading-tight text-text-muted"
            style={{ gridTemplateColumns: gridCols }}
          >
            {hasRank && <span>#</span>}
            <span>{body.leading_label ?? "Item"}</span>
            {body.columns.map((c) => (
              <span key={c.key} className="text-center">
                {c.label}
              </span>
            ))}
          </div>
        )}
        {body.rows.map((row) => {
          const rankMark = hasRank ? row.leading[0] : null;
          const entityMarks = hasRank ? row.leading.slice(1) : row.leading;
          const cellByKey = new Map(row.cells.map((cell) => [cell.column_key, cell]));
          return (
            <div
              key={row.id}
              className="grid items-center gap-1.5 border-t border-surface-border/60 pt-1.5"
              style={{ gridTemplateColumns: gridCols }}
            >
              {rankMark && <KitMarkView mark={rankMark} />}
              <div className="flex min-w-0 items-center gap-1.5">
                {entityMarks.map((lm, lIdx) => (
                  <KitMarkView key={`${row.id}-l-${lIdx}`} mark={lm} />
                ))}
              </div>
              {body.columns.map((c) => {
                const cell = cellByKey.get(c.key);
                return (
                  <div key={`${row.id}-${c.key}`}>
                    {cell?.marks.map((cm, cIdx) => (
                      <KitMarkView key={`${row.id}-${c.key}-${cIdx}`} mark={cm} />
                    ))}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {body.rows.map((row) => (
        <div
          key={row.id}
          className="space-y-1.5 border-t border-surface-border/60 pt-2 first:border-t-0 first:pt-0"
        >
          <div className="flex items-center gap-2">
            {row.leading.map((lm, lIdx) => (
              <KitMarkView key={`${row.id}-sl-${lIdx}`} mark={lm} />
            ))}
          </div>
          <div
            className="grid gap-1.5"
            style={{
              gridTemplateColumns: `repeat(${Math.max(1, row.cells.length)}, minmax(0,1fr))`,
            }}
          >
            {row.cells.map((cell) => (
              <div key={`${row.id}-${cell.column_key}`}>
                {cell.marks.map((cm, cIdx) => (
                  <KitMarkView key={`${row.id}-${cell.column_key}-${cIdx}`} mark={cm} />
                ))}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function CalendarLayout({ body }: { body: KitV1CalendarBody }) {
  const headerMarks = body.header_marks ?? [];
  const footerMarks = body.footer_marks ?? [];
  return (
    <div className="space-y-2">
      {headerMarks.length > 0 && (
        <div className="flex items-center justify-between gap-2">
          {headerMarks.map((m, idx) => (
            <KitMarkView key={`ch-${idx}`} mark={m} />
          ))}
        </div>
      )}
      <div
        className="grid gap-1"
        style={{ gridTemplateColumns: `repeat(${body.days.length}, minmax(0,1fr))` }}
      >
        {body.days.map((day) => (
          <div key={day.date_key} className="space-y-0.5 text-center">
            {day.marks.map((dm, idx) => (
              <div key={`${day.date_key}-${idx}`} className={dm.mark === "tile" ? "" : "flex justify-center"}>
                <KitMarkView mark={dm} />
              </div>
            ))}
          </div>
        ))}
      </div>
      {footerMarks.length > 0 && (
        <div className="space-y-1">
          {footerMarks.map((m, idx) => (
            <div key={`cf-${idx}`}>
              <KitMarkView mark={m} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function toAxisPercent(val: number, min: number, max: number): number {
  const span = Math.max(1e-6, max - min);
  return Math.max(0, Math.min(100, ((val - min) / span) * 100));
}

function AxisLayout({ body }: { body: KitV1AxisBody }) {
  const { scale, highlight_band: band } = body;
  const dots = (body.marks ?? []).filter((m): m is KitV1DotMark => m.mark === "dot");
  const lines = (body.marks ?? []).filter((m): m is KitV1LineMark => m.mark === "line");
  const elevatedDots = dots.filter((d) => d.picture && typeof d.y_lane === "number");
  const baseDots = dots.filter((d) => !(d.picture && typeof d.y_lane === "number"));
  const maxLane = elevatedDots.reduce((m, d) => Math.max(m, d.y_lane ?? 0), 0);
  const trackHeight = (maxLane + 1) * 26 + 52;

  return (
    <div className="space-y-2.5">
      {dots.length > 0 && (
        <div className="relative w-full" style={{ height: `${trackHeight}px` }}>
          {band && (
            <div
              className="absolute bottom-5 top-0 rounded-lg border border-surface-border/50 bg-surface-elevated/80"
              style={{
                left: `${toAxisPercent(band.lo, scale.min, scale.max)}%`,
                width: `${
                  toAxisPercent(band.hi, scale.min, scale.max) -
                  toAxisPercent(band.lo, scale.min, scale.max)
                }%`,
              }}
            >
              <div className="pt-0.5 text-center text-[10px] font-semibold uppercase tracking-wide text-text-muted">
                {band.label}
              </div>
            </div>
          )}

          <div className="absolute bottom-5 left-0 right-0 h-0.5 bg-surface-border" />

          {baseDots.map((pt, idx) => (
            <div
              key={`bd-${pt.label}-${idx}`}
              title={pt.label}
              className="absolute h-2.5 w-2.5 -translate-x-1/2 rounded-full border border-surface-card bg-text-muted"
              style={{
                left: `${Math.min(98, Math.max(2, toAxisPercent(pt.x, scale.min, scale.max)))}%`,
                bottom: `${22 + (idx % 3) * 6}px`,
                backgroundColor: pt.color ?? undefined,
              }}
            />
          ))}

          {elevatedDots.map((pt, idx) => (
            <div
              key={`ed-${pt.label}-${idx}`}
              title={pt.label}
              className="absolute flex -translate-x-1/2 flex-col items-center"
              style={{
                left: `${toAxisPercent(pt.x, scale.min, scale.max)}%`,
                bottom: `${28 + (pt.y_lane ?? 0) * 24}px`,
              }}
            >
              {pt.picture && (
                <img
                  src={pt.picture.url}
                  alt={pt.picture.alt}
                  className="h-5 w-5 rounded-full border border-surface-border bg-surface-card object-contain p-0.5 shadow-sm"
                />
              )}
            </div>
          ))}

          <div className="absolute bottom-0 left-0 right-0 flex justify-between text-[10px] tabular-nums text-text-muted">
            {scale.ticks.map((t) => (
              <span key={`${t.x}-${t.label}`}>{t.label}</span>
            ))}
          </div>
        </div>
      )}

      {lines.length > 0 && dots.length === 0 && (
        <div className="space-y-1 rounded-lg border border-surface-border bg-surface-elevated p-2">
          <div className="flex justify-between text-[10px] tabular-nums text-text-muted">
            {scale.ticks.map((t) => (
              <span key={`${t.x}-${t.label}`}>{t.label}</span>
            ))}
          </div>
        </div>
      )}

      {body.series && body.series.length > 0 && (
        <div className="space-y-2">
          {body.series.map((s) => (
            <div key={s.id} className="space-y-1">
              {s.leading && s.leading.length > 0 && (
                <div className="flex items-center gap-2">
                  {s.leading.map((lm, lIdx) => (
                    <KitMarkView key={`${s.id}-l-${lIdx}`} mark={lm} />
                  ))}
                </div>
              )}
              <div className="flex items-center gap-2">
                {s.marks.map((sm, mIdx) => (
                  <KitMarkView key={`${s.id}-m-${mIdx}`} mark={sm} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {body.summary_marks && body.summary_marks.length > 0 && (
        <div className="flex items-center justify-between gap-2 text-[11px] font-semibold text-text-secondary">
          {body.summary_marks.map((m, idx) => (
            <KitMarkView key={`as-${idx}`} mark={m} />
          ))}
        </div>
      )}

      {body.footer_marks && body.footer_marks.length > 0 && (
        <div className="space-y-1">
          {body.footer_marks.map((m, idx) => (
            <KitMarkView key={`af-${idx}`} mark={m} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public KitCardRenderer entry point
// ---------------------------------------------------------------------------

export function KitCardRenderer({ spec }: { spec: KitV1CardSpec }) {
  const parsed = parseKitCardV1(spec);
  if (!parsed || !parsed.layout || !parsed.body) {
    return (
      <article className="w-full rounded-2xl border border-accent-danger/40 bg-surface-card p-3.5 shadow-sm">
        <div className="text-[10px] font-bold uppercase tracking-wide text-accent-danger">
          Standard card fallback
        </div>
        <p className="mt-1 text-xs leading-relaxed text-text-secondary">
          {spec.refusal_reason || "No Kit v1 shape fits safely; render standard card instead."}
        </p>
      </article>
    );
  }

  return (
    <article className="w-full rounded-2xl border border-surface-border bg-surface-card p-3.5 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        {parsed.kicker ? (
          <div className="text-[10px] font-bold uppercase tracking-wider text-accent-brand">
            {parsed.kicker}
          </div>
        ) : (
          <span />
        )}
        {parsed.source_mark?.label && (
          <span className="text-[10px] font-medium text-text-muted">
            {parsed.source_mark.label}
          </span>
        )}
      </div>
      {parsed.common_headline && (
        <h3 className="mt-1 text-base font-bold leading-snug text-text-primary">
          {parsed.common_headline}
        </h3>
      )}
      {parsed.stat_caption && (
        <p className="mt-0.5 text-xs leading-snug text-text-secondary">
          {parsed.stat_caption}
        </p>
      )}

      <div className="mt-3">
        {parsed.layout === "stack" && (
          <StackLayout body={parsed.body as KitV1StackBody} />
        )}
        {parsed.layout === "grid" && (
          <GridLayout body={parsed.body as KitV1GridBody} />
        )}
        {parsed.layout === "calendar" && (
          <CalendarLayout body={parsed.body as KitV1CalendarBody} />
        )}
        {parsed.layout === "axis" && (
          <AxisLayout body={parsed.body as KitV1AxisBody} />
        )}
      </div>

      {parsed.footnote && (
        <p className="mt-2.5 border-t border-surface-border/60 pt-2 text-[10px] leading-snug text-text-muted">
          {parsed.footnote}
        </p>
      )}
      {parsed.disclosure && (
        <p className="mt-1.5 text-[11px] text-text-muted">
          {parsed.disclosure}
        </p>
      )}
    </article>
  );
}
