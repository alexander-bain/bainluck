"use client";

import React from "react";
import styles from "./formsLabPreview.module.css";
import { FormsLabCardFrame, MemberAvatar } from "./FormsLabShell";
import type {
  DeadlineRaceSeries,
  FormsLabCardEnvelope,
  OneAxisBody,
  SharedScaleBin,
  SharedScaleSeries,
} from "./types_forms_lab_13551";

function renderSharedScale(body: OneAxisBody) {
  const minVal = body.axis_min ?? 0;
  const maxVal = body.axis_max ?? 460;
  const span = Math.max(1, maxVal - minVal);
  const ticks = body.ticks || [0, 100, 200, 300, 400];
  const unit = body.axis_unit || "$M";
  const series = (body.series || []) as SharedScaleSeries[];

  return (
    <div className={styles.axisTrackWrap}>
      {series.map((s) => {
        const peakPct = Math.max(...s.bins.map((b) => b.pct), 0);
        return (
          <div key={s.id}>
            <div className={styles.axisSeriesHead}>
              <span className={styles.axisSeriesName}>
                <MemberAvatar art={s.art} label={s.name} />
                <span>{s.name}</span>
              </span>
              <span className={styles.axisSeriesPeak}>{s.peak_label}</span>
            </div>
            <div className={styles.axisLane}>
              {s.bins.map((bin: SharedScaleBin) => {
                const leftPct = Math.max(0, ((bin.lo - minVal) / span) * 100);
                const widthPct = Math.max(2.5, ((bin.hi - bin.lo) / span) * 100);
                const isPeak = bin.pct === peakPct && peakPct > 0;
                const segTone =
                  s.tone === "c2" && isPeak
                    ? styles.axisSegC2
                    : isPeak
                    ? styles.axisSegAccent
                    : "";
                const showInlinePct = widthPct >= 10.0;
                const arrowLabel = bin.open_high ? `${bin.pct_label} →` : bin.open_low ? `← ${bin.pct_label}` : bin.pct_label;
                return (
                  <React.Fragment key={`${s.id}-${bin.label}`}>
                    <div
                      title={`${bin.label}: ${bin.pct_label}`}
                      className={`${styles.axisSeg} ${segTone}`}
                      style={{
                        left: `${leftPct}%`,
                        width: `${widthPct}%`,
                        opacity: isPeak ? 1 : Math.max(0.35, 0.35 + (bin.pct / Math.max(peakPct, 1)) * 0.55),
                      }}
                    >
                      {showInlinePct ? arrowLabel : ""}
                    </div>
                    {isPeak && !showInlinePct && (
                      <span
                        className={styles.axisPeakFlag}
                        style={{ left: `${leftPct + widthPct / 2}%` }}
                      >
                        {bin.pct_label}
                      </span>
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        );
      })}
      <div className={styles.axisTickRow}>
        {ticks.map((t) => (
          <span key={t}>
            {t}
            {unit === "$M" ? "M" : ` ${unit}`}
          </span>
        ))}
      </div>
    </div>
  );
}

function renderDeadlineRace(body: OneAxisBody) {
  const dates = body.dates || ["Nov 30", "Dec 15", "Dec 31"];
  const series = (body.series || []) as DeadlineRaceSeries[];
  const refPct = body.ref_line_pct ?? 50;
  const W = 350;
  const H = 148;
  const xL = 32;
  const xR = 322;
  const yT = 20;
  const yB = 120;
  const xFor = (i: number) => xL + (i / Math.max(1, dates.length - 1)) * (xR - xL);
  const yFor = (pct: number) => yB - (Math.min(100, Math.max(0, pct)) / 100) * (yB - yT);
  const strokes = ["var(--fl-accent)", "var(--fl-c3)"];

  return (
    <div>
      <div className={styles.seriesChips}>
        {series.map((s, idx) => (
          <span key={s.id} className={styles.seriesChip}>
            <MemberAvatar art={s.art} label={s.name} small />
            <span>{s.short_label || s.name}</span>
            <strong style={{ color: strokes[idx % strokes.length] }}>
              {s.points[s.points.length - 1]?.pct_label}
            </strong>
          </span>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className={styles.chartSvg} role="img" aria-label="Deadline race chart">
        {[0, 50, 100].map((tick) => {
          const y = yFor(tick);
          return (
            <g key={tick}>
              <line
                x1={xL}
                x2={xR}
                y1={y}
                y2={y}
                stroke="var(--fl-line)"
                strokeDasharray={tick === refPct ? "4 3" : undefined}
                strokeWidth={tick === refPct ? 1.5 : 1}
              />
              <text x={xL - 5} y={y + 3} fontSize="9.5" textAnchor="end" fill="var(--fl-muted)">
                {tick}%
              </text>
            </g>
          );
        })}
        {dates.map((d, i) => (
          <text key={d} x={xFor(i)} y={H - 8} fontSize="10" fontWeight="600" textAnchor="middle" fill="var(--fl-muted)">
            {d}
          </text>
        ))}
        {series.map((s, sIdx) => {
          const color = strokes[sIdx % strokes.length];
          const pathD = s.points
            .map((pt, i) => `${i === 0 ? "M" : "L"}${xFor(i).toFixed(1)},${yFor(pt.pct).toFixed(1)}`)
            .join(" ");
          return (
            <g key={s.id}>
              <path d={pathD} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              {s.points.map((pt, i) => {
                const cx = xFor(i);
                const cy = yFor(pt.pct);
                const isFirstLower = i === 0 && sIdx > 0;
                const tx = isFirstLower ? cx + 17 : cx;
                const ty = isFirstLower ? cy + 3 : sIdx === 0 ? cy - 8 : cy + 13;
                return (
                  <g key={`${s.id}-${pt.date}`}>
                    <circle cx={cx} cy={cy} r="4" fill={color} stroke="var(--fl-surface)" strokeWidth="1.5" />
                    <text
                      x={tx}
                      y={ty}
                      fontSize="10"
                      fontWeight="700"
                      textAnchor="middle"
                      fill={color}
                    >
                      {pt.pct_label}
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function renderTheClimb(body: OneAxisBody) {
  const points = body.points || [];
  const refPct = body.ref_line_pct ?? 50;
  const W = 350;
  const H = 148;
  const xL = 32;
  const xR = 326;
  const yT = 22;
  const yB = 118;
  const xFor = (i: number) => xL + (i / Math.max(1, points.length - 1)) * (xR - xL);
  const yFor = (pct: number) => yB - (Math.min(100, Math.max(0, pct)) / 100) * (yB - yT);
  const pathD = points.map((pt, i) => `${i === 0 ? "M" : "L"}${xFor(i).toFixed(1)},${yFor(pt.pct).toFixed(1)}`).join(" ");

  return (
    <div>
      {body.art && (
        <div className={styles.seriesChips}>
          <span className={styles.seriesChip}>
            <MemberAvatar art={body.art} label={body.subject || "Climb"} small />
            <span>{body.subject}</span>
            <strong>{points[points.length - 1]?.pct_label}</strong>
          </span>
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} className={styles.chartSvg} role="img" aria-label="Cumulative climb chart">
        {[0, 50, 100].map((tick) => {
          const y = yFor(tick);
          return (
            <g key={tick}>
              <line
                x1={xL}
                x2={xR}
                y1={y}
                y2={y}
                stroke="var(--fl-line)"
                strokeDasharray={tick === refPct ? "4 3" : undefined}
                strokeWidth={tick === refPct ? 1.5 : 1}
              />
              <text x={xL - 5} y={y + 3} fontSize="9.5" textAnchor="end" fill="var(--fl-muted)">
                {tick}%
              </text>
            </g>
          );
        })}
        <path d={pathD} fill="none" stroke="var(--fl-accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {points.map((pt, i) => {
          const cx = xFor(i);
          const cy = yFor(pt.pct);
          const showLabel = i === 0 || i === points.length - 1 || i % 2 === 0;
          return (
            <g key={pt.date}>
              <circle cx={cx} cy={cy} r="3.6" fill="var(--fl-accent)" stroke="var(--fl-surface)" strokeWidth="1.5" />
              {showLabel && (
                <>
                  <text x={cx} y={cy - 8} fontSize="9.5" fontWeight="700" textAnchor="middle" fill="var(--fl-accent)">
                    {pt.pct_label}
                  </text>
                  <text x={cx} y={H - 8} fontSize="8.5" textAnchor="middle" fill="var(--fl-muted)">
                    {pt.date.replace("Jan ", "")}
                  </text>
                </>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function OneAxisCard({ card }: { card: FormsLabCardEnvelope }) {
  const body = card.body as unknown as OneAxisBody;
  let inner: React.ReactNode = null;
  if (card.form_variant === "shared_scale") {
    inner = renderSharedScale(body);
  } else if (card.form_variant === "deadline_race") {
    inner = renderDeadlineRace(body);
  } else {
    inner = renderTheClimb(body);
  }
  return <FormsLabCardFrame card={card}>{inner}</FormsLabCardFrame>;
}
