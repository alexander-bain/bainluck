"use client";
/* eslint-disable @next/next/no-img-element */

/**
 * Issue 13551 (Ruling 366: B, 367: A, and Fable's 7 rules) — Layout-generic Kit v1 web renderer.
 * Draws purely from `layout` (`stack | grid | calendar | axis`) and the 8 shared marks.
 * `variant` is ignored at render time so unknown future variants still render cleanly.
 * Light-mode semantic tokens only (`bg-surface-*`, `text-kit-*`, `bg-kit-*`,
 * `border-surface-border`), zero dark classes, zero literal color hexes in TSX.
 */

import React from "react";
import {
  resolveKitMarkHex,
  resolveKitRangeFillStyle,
  resolveKitSplitBarHexes,
  tileClasses,
  toneClass,
} from "./kitTones";
import {
  ALLOWED_KIT_V1_LAYOUTS,
  ALLOWED_KIT_V1_MARKS,
  type KitV1AdaptiveColor,
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
const BAR_STYLE_SET = new Set<string>(["single", "split", "range"]);
const ROW_LAYOUT_SET = new Set<string>(["matrix", "stacked_cells"]);
const SCALE_KIND_SET = new Set<string>(["percent", "numeric", "time"]);
const NUMBER_UNIT_SET = new Set<string>(["%", "days", "one_in_n"]);

export const COSMETIC_KIT_V1_FIELDS: readonly string[] = [
  "variant",
  "word.style",
  "word.tone",
  "word.align",
  "word.width",
  "picture.size",
  "picture.contain",
  "picture.subject_kind",
  "number.tone",
  "number.prominence",
  "number.align",
  "number.width",
  "bar.width",
  "tile.highlight_role",
  "ring.tone",
  "body.header_layout",
];

export const MEANING_CARRYING_KIT_V1_FIELDS: readonly string[] = [
  "kit_version",
  "layout",
  "mark",
  "bar.bar_style",
  "scale.scale_kind",
  "body.row_layout",
  "number.unit",
  "adaptive_color",
  "picture.url",
  "body",
  "refusal_reason",
  "fallback_today",
];
const MARKS_ARRAY_KEYS = new Set([
  "marks",
  "header_marks",
  "footer_marks",
  "leading",
  "summary_marks",
  "sub_marks",
]);

function isHexSix(val: unknown): val is string {
  if (typeof val !== "string" || val.length !== 7 || val.charCodeAt(0) !== 35) {
    return false;
  }
  for (let i = 1; i < 7; i++) {
    const code = val.charCodeAt(i);
    const isDigit = code >= 48 && code <= 57;
    const isUpper = code >= 65 && code <= 70;
    const isLower = code >= 97 && code <= 102;
    if (!isDigit && !isUpper && !isLower) return false;
  }
  return true;
}

function isAdaptiveColor(val: unknown): val is KitV1AdaptiveColor {
  if (!val || typeof val !== "object" || Array.isArray(val)) return false;
  const obj = val as Record<string, unknown>;
  return isHexSix(obj.light) && isHexSix(obj.dark);
}

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
      const hasUrl = typeof obj.url === "string" && obj.url.startsWith("https://");
      const hasInitials =
        obj.url === null &&
        typeof obj.initials === "string" &&
        obj.initials.trim().length > 0 &&
        obj.initials.trim().length <= 3;
      if (!hasUrl && !hasInitials) {
        return false;
      }
    }
    if (obj.mark === "number") {
      if (obj.unit !== undefined && obj.unit !== null && (typeof obj.unit !== "string" || !NUMBER_UNIT_SET.has(obj.unit))) {
        return false;
      }
    }
    if (obj.mark === "bar") {
      if (typeof obj.bar_style !== "string" || !BAR_STYLE_SET.has(obj.bar_style)) {
        return false;
      }
      if (obj.fill_color !== undefined && obj.fill_color !== null && !isAdaptiveColor(obj.fill_color)) {
        return false;
      }
      if (Array.isArray(obj.segments)) {
        for (const seg of obj.segments) {
          if (seg && typeof seg === "object") {
            const segCol = (seg as Record<string, unknown>).color;
            if (segCol !== undefined && segCol !== null && !isAdaptiveColor(segCol)) {
              return false;
            }
          }
        }
      }
    }
    if (obj.mark === "dot" || obj.mark === "line") {
      if (obj.color !== undefined && obj.color !== null && !isAdaptiveColor(obj.color)) {
        return false;
      }
    }
  }
  for (const [key, val] of Object.entries(obj)) {
    if (key === "route" || key === "provenance") continue;
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
      typeof body.row_layout === "string" &&
      ROW_LAYOUT_SET.has(body.row_layout) &&
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
      typeof scale?.scale_kind === "string" &&
      SCALE_KIND_SET.has(scale.scale_kind) &&
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
  if (!mark.url) {
    return (
      <span
        aria-hidden="true"
        title={mark.alt}
        className={`${dim} inline-flex shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[10px] font-bold leading-none text-kit-secondary`}
      >
        {mark.initials ?? "?"}
      </span>
    );
  }
  if (mark.subject_kind === "film") {
    const posterDim =
      mark.size === "xs"
        ? "h-7 w-[19px]"
        : mark.size === "md"
        ? "h-10 w-[27px]"
        : "h-8 w-[22px]";
    return (
      <img
        src={mark.url}
        alt={mark.alt}
        className={`${posterDim} shrink-0 rounded-[4px] border border-surface-border bg-surface-base object-cover`}
      />
    );
  }
  if (mark.subject_kind === "person") {
    return (
      <img
        src={mark.url}
        alt={mark.alt}
        className={`${dim} aspect-square shrink-0 rounded-full border border-surface-border bg-surface-base object-cover object-top`}
      />
    );
  }
  const contain = mark.contain ?? true;
  return (
    <img
      src={mark.url}
      alt={mark.alt}
      className={`${dim} shrink-0 rounded-md border border-surface-border bg-surface-base ${
        contain ? "object-contain p-0.5" : "object-cover"
      }`}
    />
  );
}

function alignClass(align?: string): string {
  if (align === "right") return "text-right";
  if (align === "center") return "text-center";
  return "text-left";
}

function wordWidthClass(width?: string): string {
  if (width === "flex") return "min-w-0 flex-1 break-words";
  if (width === "xs") return "w-8 shrink-0";
  if (width === "sm") return "w-16 shrink-0";
  return "shrink-0";
}

export function computeCountdownDaysLeft(
  deadlineIso: string,
  now: Date = new Date(),
): number | null {
  const target = new Date(deadlineIso);
  if (Number.isNaN(target.getTime())) return null;
  const toPtMidnightUtcMs = (d: Date): number | null => {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Los_Angeles",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(d);
    const y = Number(parts.find((p) => p.type === "year")?.value);
    const m = Number(parts.find((p) => p.type === "month")?.value);
    const day = Number(parts.find((p) => p.type === "day")?.value);
    if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(day)) return null;
    return Date.UTC(y, m - 1, day);
  };
  const targetDayMs = toPtMidnightUtcMs(target);
  const nowDayMs = toPtMidnightUtcMs(now);
  if (targetDayMs === null || nowDayMs === null) return null;
  return Math.round((targetDayMs - nowDayMs) / 86_400_000);
}

function WordMarkView({ mark }: { mark: KitV1WordMark }) {
  if (mark.style === "pill") {
    return (
      <p className="rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1.5 text-[11px] leading-relaxed text-kit-secondary">
        {mark.text}
      </p>
    );
  }
  if (mark.style === "hero_label") {
    const liveDays = mark.deadline_iso ? computeCountdownDaysLeft(mark.deadline_iso) : null;
    const heroText =
      liveDays === null
        ? mark.text
        : liveDays <= 0
        ? "ends today"
        : liveDays === 1
        ? "day left"
        : "days left";
    return (
      <div className="min-w-0 flex-1">
        <div className="text-xs font-bold text-kit-primary">{heroText}</div>
        {mark.secondary_text && (
          <div className="text-[11px] text-kit-secondary">{mark.secondary_text}</div>
        )}
      </div>
    );
  }
  if (mark.style === "kicker") {
    return (
      <span
        className={`text-[10px] font-bold uppercase tracking-wide ${
          mark.tone ? toneClass(mark.tone) : "text-kit-accent"
        } ${alignClass(mark.align)}`}
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
        <div className={mark.secondary_text ? "font-semibold text-kit-secondary" : "font-medium"}>
          {mark.text}
        </div>
        {mark.secondary_text && <div className="text-kit-muted">{mark.secondary_text}</div>}
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
      <span
        className={`text-[11px] font-bold tabular-nums ${toneClass(
          mark.tone ?? "muted",
        )} ${mark.width === "xs" ? "inline-block w-6 shrink-0" : ""}`}
      >
        {mark.text}
      </span>
    );
  }
  if (mark.secondary_text) {
    return (
      <div className={`min-w-0 leading-snug ${alignClass(mark.align)} ${wordWidthClass(mark.width)}`}>
        <div
          className={`text-xs leading-snug ${mark.bold ? "font-semibold" : ""} ${toneClass(
            mark.tone,
          )}`}
        >
          {mark.text}
        </div>
        <div className="text-[10px] font-medium text-kit-muted">{mark.secondary_text}</div>
      </div>
    );
  }
  return (
    <span
      className={`text-xs leading-tight ${mark.bold ? "font-semibold" : ""} ${toneClass(
        mark.tone,
      )} ${alignClass(mark.align)} ${wordWidthClass(mark.width)}`}
    >
      {mark.text}
    </span>
  );
}

function NumberMarkView({ mark }: { mark: KitV1NumberMark }) {
  const liveDays =
    mark.unit === "days" && mark.deadline_iso
      ? computeCountdownDaysLeft(mark.deadline_iso)
      : null;
  const shownDisplay =
    liveDays === null ? mark.display : liveDays <= 0 ? "Today" : String(liveDays);
  if (mark.prominence === "hero") {
    return (
      <span className={`text-2xl font-extrabold tabular-nums ${toneClass(mark.tone)}`}>
        {shownDisplay}
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
      {shownDisplay}
    </span>
  );
}

function BarMarkView({ mark }: { mark: KitV1BarMark }) {
  if (mark.bar_style === "split" && Array.isArray(mark.segments)) {
    const twoPair =
      mark.segments.length === 2
        ? resolveKitSplitBarHexes(mark.segments[0]?.color, mark.segments[1]?.color)
        : null;
    return (
      <div className="flex h-2.5 flex-1 overflow-hidden rounded-full bg-kit-track">
        {mark.segments.map((seg, idx) => (
          <div
            key={`${seg.label ?? idx}-${idx}`}
            className={`h-full ${idx > 0 ? "border-l-2 border-surface-card" : ""}`}
            style={{
              width: `${Math.max(0, Math.min(100, seg.fill * 100))}%`,
              backgroundColor: twoPair
                ? twoPair[idx]
                : resolveKitMarkHex(seg.color, idx),
            }}
          />
        ))}
      </div>
    );
  }
  if (mark.bar_style === "range" && typeof mark.lo === "number" && typeof mark.hi === "number") {
    const leftPct = Math.max(0, Math.min(96, mark.lo * 100));
    const widthPct = Math.max(4, Math.min(100 - leftPct, (mark.hi - mark.lo) * 100));
    const rangeStyle = resolveKitRangeFillStyle(mark.fill_color);
    return (
      <div className="relative h-5 flex-1 rounded border border-surface-border/80 bg-kit-track">
        <div
          className="absolute top-0.5 bottom-0.5 flex items-center justify-center rounded border px-1 text-[10px] font-bold tabular-nums text-kit-primary"
          style={{
            left: `${leftPct}%`,
            width: `${widthPct}%`,
            ...rangeStyle,
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
    <div className={`${trackWidth} shrink-0 overflow-hidden rounded-full bg-kit-track`}>
      <div
        className="h-full rounded-full"
        style={{
          width: `${pct}%`,
          backgroundColor: resolveKitMarkHex(mark.fill_color, 0),
        }}
      />
    </div>
  );
}

function TileMarkView({ mark }: { mark: KitV1TileMark }) {
  const palette = tileClasses(mark);
  const isCompactMatrix = !mark.top_label && !mark.bottom_label;
  if (isCompactMatrix) {
    return (
      <div
        className={`flex h-7 items-center justify-center rounded-md border text-xs font-bold tabular-nums ${palette.container} ${palette.foreground}`}
      >
        {mark.center_label}
      </div>
    );
  }
  const hasBottom = mark.bottom_label !== undefined && mark.bottom_label !== null;
  return (
    <div className={`rounded-lg border px-0.5 py-1.5 text-center ${palette.container}`}>
      {mark.top_label && (
        <div className={`text-[10px] font-medium ${palette.secondaryForeground}`}>
          {mark.top_label}
        </div>
      )}
      <div
        className={`${mark.top_label ? "mt-0.5 text-sm" : "text-xs"} font-extrabold tabular-nums ${
          palette.foreground
        }`}
      >
        {mark.center_label}
      </div>
      {hasBottom && (
        <div
          className={`mt-0.5 text-[9px] font-bold leading-tight tabular-nums ${palette.secondaryForeground}`}
        >
          {mark.bottom_label}
        </div>
      )}
    </div>
  );
}

function RingMarkView({ mark }: { mark: KitV1RingMark }) {
  const pct = Math.round(Math.max(0, Math.min(1, mark.progress)) * 100);
  const borderTone = mark.tone === "muted" ? "border-kit-muted" : "border-kit-accent";
  return (
    <span
      className={`inline-flex h-7 min-w-7 items-center justify-center rounded-full border-2 ${borderTone} px-1 text-[10px] font-bold tabular-nums text-kit-primary`}
    >
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
      {headerMarks.length > 0 && body.header_layout === "split" && (
        <div className="flex items-center justify-between gap-2">
          {headerMarks.map((m, idx) => (
            <KitMarkView key={`shs-${idx}`} mark={m} />
          ))}
        </div>
      )}
      {headerMarks.length > 0 && body.header_layout !== "none" && body.header_layout !== "split" && (
        <div className="flex items-center gap-2.5 rounded-lg border border-surface-border bg-surface-elevated px-3 py-2">
          {headerMarks.map((m, idx) => (
            <KitMarkView key={`sh-${idx}`} mark={m} />
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
              <div className="mt-2 border-t border-dashed border-surface-border pt-1 text-center text-[10px] font-semibold text-kit-muted">
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
    const isDenseMatrix = body.columns.length >= 3;
    const colWidthPx = isDenseMatrix ? "minmax(54px, 76px)" : "minmax(66px, 92px)";
    const gridCols = hasRank
      ? `18px minmax(0,1fr) repeat(${body.columns.length}, ${colWidthPx})`
      : `minmax(0,1fr) repeat(${body.columns.length}, ${colWidthPx})`;

    return (
      <div className="space-y-1.5">
        {body.show_column_headers && (
          <div
            className="grid items-end gap-1.5 pb-1 text-[10px] font-semibold leading-tight text-kit-muted"
            style={{ gridTemplateColumns: gridCols }}
          >
            {hasRank && <span>#</span>}
            <span>{body.leading_label ?? "Item"}</span>
            {body.columns.map((c) => (
              <span key={c.key} className="break-words text-center">
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
              <div
                className={`flex min-w-0 items-center gap-1.5 overflow-hidden ${
                  isDenseMatrix ? "[&>span]:text-[11px]" : ""
                }`}
              >
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

function useIsLargeRootText(): boolean {
  const [isLarge, setIsLarge] = React.useState(false);
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const check = () => {
      const px = Number.parseFloat(window.getComputedStyle(document.documentElement).fontSize);
      setIsLarge(Number.isFinite(px) && px >= 20);
    };
    check();
    window.addEventListener("resize", check);
    const observer =
      typeof MutationObserver !== "undefined" ? new MutationObserver(check) : null;
    observer?.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["style", "class"],
    });
    return () => {
      window.removeEventListener("resize", check);
      observer?.disconnect();
    };
  }, []);
  return isLarge;
}

function AxisLayout({
  body,
  forceLargeText = false,
}: {
  body: KitV1AxisBody;
  forceLargeText?: boolean;
}) {
  const { scale, highlight_band: band } = body;
  const isLargeText = useIsLargeRootText() || forceLargeText;
  const dots = (body.marks ?? []).filter((m): m is KitV1DotMark => m.mark === "dot");
  const lines = (body.marks ?? []).filter((m): m is KitV1LineMark => m.mark === "line");
  const elevatedDots = dots.filter((d) => d.picture && typeof d.y_lane === "number");
  const baseDots = dots.filter((d) => !(d.picture && typeof d.y_lane === "number"));
  const maxLane = elevatedDots.reduce((m, d) => Math.max(m, d.y_lane ?? 0), 0);
  const trackHeight = (maxLane + 1) * 48 + 56;
  const stackedSummaries = (body.summary_marks ?? []).some(
    (m) => m.mark === "word" && m.text.length > 24,
  );
  const sortedBubbleDots = [...elevatedDots].sort((a, b) => b.x - a.x);

  return (
    <div className="space-y-2.5">
      {dots.length > 0 && isLargeText && sortedBubbleDots.length > 0 && (
        <div
          data-testid="axis-large-text-list"
          className="space-y-1.5 rounded-xl border border-surface-border bg-surface-elevated/60 px-3 py-2"
        >
          {band && (
            <div className="text-[11px] font-semibold uppercase tracking-wide text-kit-muted">
              {band.label} ({Math.round(band.lo)}%–{Math.round(band.hi)}%)
            </div>
          )}
          <div className="divide-y divide-surface-border/60">
            {sortedBubbleDots.map((pt, idx) => {
              const teamName = pt.label.split(":", 1)[0].trim() || pt.picture?.alt || pt.label;
              const pctText = pt.badge_text ?? `${Math.round(pt.x)}%`;
              return (
                <div
                  key={`lt-${pt.label}-${idx}`}
                  className="flex items-center justify-between gap-2 py-1.5 first:pt-0 last:pb-0"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    {pt.picture && <PictureMarkView mark={pt.picture} />}
                    <span className="text-sm font-medium text-kit-primary">{teamName}</span>
                  </div>
                  <span className="shrink-0 text-sm font-bold tabular-nums text-kit-primary">
                    {pctText}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {dots.length > 0 && !(isLargeText && sortedBubbleDots.length > 0) && (
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
              <div className="pt-0.5 text-center text-[10px] font-semibold uppercase tracking-wide text-kit-muted">
                {band.label}
              </div>
            </div>
          )}

          <div className="absolute bottom-5 left-0 right-0 h-0.5 bg-surface-border" />

          {baseDots.map((pt, idx) => (
            <div
              key={`bd-${pt.label}-${idx}`}
              title={pt.label}
              className="absolute h-2.5 w-2.5 -translate-x-1/2 rounded-full border border-surface-card"
              style={{
                left: `${Math.min(98, Math.max(2, toAxisPercent(pt.x, scale.min, scale.max)))}%`,
                bottom: `${22 + (idx % 3) * 6}px`,
                backgroundColor: resolveKitMarkHex(pt.color, idx),
              }}
            />
          ))}

          {elevatedDots.map((pt, idx) => {
            const pctText = pt.badge_text ?? `${Math.round(pt.x)}%`;
            return (
              <div
                key={`ed-${pt.label}-${idx}`}
                title={pt.label}
                className="absolute flex -translate-x-1/2 flex-col items-center"
                style={{
                  left: `${toAxisPercent(pt.x, scale.min, scale.max)}%`,
                  bottom: `${28 + (pt.y_lane ?? 0) * 48}px`,
                }}
              >
                {pt.picture &&
                  (pt.picture.url ? (
                    <img
                      src={pt.picture.url}
                      alt={pt.picture.alt}
                      className="h-5 w-5 rounded-full border border-surface-border bg-surface-card object-contain p-0.5 shadow-sm"
                    />
                  ) : (
                    <PictureMarkView mark={pt.picture} />
                  ))}
                {pt.picture?.alt && pt.picture.alt.length <= 5 && (
                  <span className="mt-0.5 rounded bg-surface-card/90 px-0.5 text-[9px] font-bold leading-none text-kit-secondary">
                    {pt.picture.alt}
                  </span>
                )}
                {(pt.badge_text || pt.in_band) && (
                  <span className="rounded bg-surface-card/90 px-0.5 text-[9px] font-extrabold leading-none tabular-nums text-kit-primary">
                    {pctText}
                  </span>
                )}
              </div>
            );
          })}

          <div className="absolute bottom-0 left-0 right-0 flex justify-between text-[10px] tabular-nums text-kit-muted">
            {scale.ticks.map((t) => (
              <span key={`${t.x}-${t.label}`}>{t.label}</span>
            ))}
          </div>
        </div>
      )}

      {sortedBubbleDots.length > 0 && !(isLargeText && sortedBubbleDots.length > 0) && (
        <ul className="sr-only">
          {sortedBubbleDots.map((pt, idx) => (
            <li key={`sr-bubble-${idx}`}>{pt.label}</li>
          ))}
        </ul>
      )}

      {lines.length > 0 && dots.length === 0 && (
        <div className="space-y-1 rounded-lg border border-surface-border bg-surface-elevated p-2">
          <div className="flex justify-between text-[10px] tabular-nums text-kit-muted">
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
          {dots.length === 0 && lines.length === 0 && scale.ticks.length > 0 && (
            <div className="flex justify-between border-t border-surface-border pt-1 text-[10px] tabular-nums text-kit-muted">
              {scale.ticks.map((t) => (
                <span key={`st-${t.x}-${t.label}`}>{t.label}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {body.summary_marks && body.summary_marks.length > 0 && (
        stackedSummaries ? (
          <div className="space-y-1 text-[11px] font-medium text-kit-secondary">
            {body.summary_marks.map((m, idx) => (
              <div key={`as-${idx}`} className="truncate">
                <KitMarkView mark={m} />
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2 text-[11px] font-semibold text-kit-secondary">
            {body.summary_marks.map((m, idx) => (
              <KitMarkView key={`as-${idx}`} mark={m} />
            ))}
          </div>
        )
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

export function KitCardRenderer({
  spec,
  forceLargeText = false,
}: {
  spec: KitV1CardSpec;
  forceLargeText?: boolean;
}) {
  const parsed = parseKitCardV1(spec);
  if (!parsed || !parsed.layout || !parsed.body) {
    return (
      <article className="w-full rounded-2xl border border-accent-danger/40 bg-surface-card p-3.5 shadow-sm">
        <div className="text-[10px] font-bold uppercase tracking-wide text-accent-danger">
          Standard card fallback
        </div>
        <p className="mt-1 text-xs leading-relaxed text-kit-secondary">
          {spec.refusal_reason || "No Kit v1 shape fits safely; render standard card instead."}
        </p>
      </article>
    );
  }

  return (
    <article className="w-full rounded-2xl border border-surface-border bg-surface-card p-3.5 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        {parsed.kicker ? (
          <div className="text-[10px] font-bold uppercase tracking-wider text-kit-accent">
            {parsed.kicker}
          </div>
        ) : (
          <span />
        )}
        {parsed.source_mark?.label && (
          <span className="text-[10px] font-medium text-kit-muted">
            {parsed.source_mark.label}
          </span>
        )}
      </div>
      {parsed.common_headline && (
        <h3 className="mt-1 text-base font-bold leading-snug text-kit-primary">
          {parsed.common_headline}
        </h3>
      )}
      {parsed.stat_caption && (
        <p className="mt-0.5 text-xs leading-snug text-kit-secondary">
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
          <AxisLayout body={parsed.body as KitV1AxisBody} forceLargeText={forceLargeText} />
        )}
      </div>

      {parsed.footnote && (
        <p className="mt-2.5 border-t border-surface-border/60 pt-2 text-[10px] leading-snug text-kit-muted">
          {parsed.footnote}
        </p>
      )}
      {parsed.disclosure && (
        <p
          className={`mt-1.5 text-[11px] ${
            parsed.route ? "font-semibold text-kit-accent" : "text-kit-muted"
          }`}
        >
          {parsed.disclosure}
        </p>
      )}
    </article>
  );
}
