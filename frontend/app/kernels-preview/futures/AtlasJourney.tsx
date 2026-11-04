"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Info } from "lucide-react";
import { chartSeriesPath } from "@/lib/chartSeriesPath";
import { seriesGapThresholdMs } from "@/lib/seriesFreshness";
import { datePT, observations, percentText, type Observation, type PrototypeData } from "./_model";
import styles from "./prototype.module.css";

export function SourceMark() {
  return <Info size={11} strokeWidth={1.5} className={styles.sourceMark} aria-label="Source information reserved" role="img" />;
}
export function Chance({ value }: { value: number | null }) {
  return <span className={styles.chance}>{percentText(value)}<SourceMark /></span>;
}

export default function AtlasJourney({ data, selectedId, name, color, result, onDetails }: {
  data: PrototypeData; selectedId: number; name: string; color: string;
  result: "won" | "lost" | null; onDetails: (point: Observation | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(350);
  const [index, setIndex] = useState<number | null>(null);
  const [gap, setGap] = useState(false);
  const blended = data.sources.length > 1;
  const points = useMemo(() => data.sources.length > 1 ? [] : observations(data.history, selectedId), [data, selectedId]);
  useEffect(() => { setIndex(null); setGap(false); }, [selectedId]);
  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setWidth(Math.max(240, el.clientWidth)));
    setWidth(Math.max(240, el.clientWidth));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const activeIndex = Math.min(index ?? points.length - 1, points.length - 1);
  const point = points[activeIndex];
  const left = 31, right = width - 10, top = 16, bottom = 196;
  const first = points[0]?.t ?? Date.parse(data.capturedAt);
  const last = points[points.length - 1]?.t ?? first;
  const span = Math.max(last - first, 1);
  const x = (t: number) => last === first ? (left + right) / 2 : left + (t - first) / span * (right - left);
  const y = (p: number) => bottom - p * (bottom - top);
  const plotted = points.map((p) => ({ t: p.t, x: x(p.t), y: y(p.probability) }));
  const paths = chartSeriesPath(plotted);
  const threshold = seriesGapThresholdMs(points.map((p) => p.t)) ?? Infinity;
  function selectAt(clientX: number, el: SVGSVGElement) {
    const rect = el.getBoundingClientRect();
    const px = (clientX - rect.left) / rect.width * width;
    if (!points.length) return;
    const t = first + (px - left) / (right - left) * span;
    const after = points.findIndex((p) => p.t >= t);
    const before = after > 0 ? after - 1 : after < 0 ? points.length - 1 : 0;
    const nearest = after < 0 ? before : Math.abs(points[before].t - t) < Math.abs(points[after].t - t) ? before : after;
    const interiorGap = after > 0 && points[after].t - points[before].t > threshold;
    // A blank interval cannot snap to a distant endpoint and pretend it was observed.
    if ((interiorGap || points.length === 1) && Math.abs(x(points[nearest].t) - px) > 12) {
      setGap(true); return;
    }
    setIndex(nearest); setGap(false);
  }
  return <section className={styles.journey} aria-label="Probability journey" style={{ "--identity": color } as React.CSSProperties}>
    <div className={styles.sectionHeading}><h2>Probability journey</h2><button className={styles.textButton} onClick={() => onDetails(point ?? null)}>Details</button></div>
    <div className={styles.journeyReading} aria-live="polite">
      <div><strong>{name}</strong><span>{gap ? "No recorded observation in this interval" : point ? `Recorded · ${datePT(point.timestamp, true)}` : blended ? "Blended journey not supplied" : "No recorded journey supplied"}</span></div>
      {point && !gap && <strong><Chance value={point.probability} /></strong>}
    </div>
    <div ref={container} className={styles.plot}>
      <svg viewBox={`0 0 ${width} 225`} height="225" width="100%" onPointerDown={(e) => selectAt(e.clientX, e.currentTarget)} role="img" aria-label={`${name}. Zero to 100 percent, straight recorded segments; blank intervals contain no observations.`} data-testid="atlas-journey">
        {[1, .5, 0].map((p) => <g key={p}><line x1={left} x2={right} y1={y(p)} y2={y(p)} className={styles.gridLine} /><text x={left - 6} y={y(p) + 4} textAnchor="end" className={styles.axis}>{p * 100}%</text></g>)}
        {paths.runs.map((d, i) => <path key={i} d={d} className={styles.journeyLine} data-kind="observed-run" />)}
        {paths.dots.map((p) => <circle key={p.t} cx={p.x} cy={p.y} r="3.5" className={styles.recordedDot} />)}
        {points.length > 0 && <circle cx={x(points[0].t)} cy={y(points[0].probability)} r="4" className={styles.firstObservation} />}
        {point && !gap && <><line x1={x(point.t)} x2={x(point.t)} y1={top} y2={bottom} className={styles.crosshair} /><circle cx={x(point.t)} cy={y(point.probability)} r="5" className={styles.recordedDot} /></>}
        {points.length > 0 && <><text x={left} y="220" className={styles.axis}>{datePT(points[0].timestamp)}</text>{points.length > 1 && <text x={right} y="220" textAnchor="end" className={styles.axis}>{datePT(points[points.length - 1].timestamp)}</text>}</>}
      </svg>
      {!points.length && <p className={styles.emptyPlot}>{blended ? "No blended history in this capture." : "No observations for this outcome in the served history."}<br />The recorded headline stays separate.</p>}
    </div>
    {points.length > 1 && <div className={styles.observationControls}>
      <button aria-label="Earlier recorded observation" disabled={activeIndex <= 0} onClick={() => { setIndex(activeIndex - 1); setGap(false); }}><ChevronLeft size={17} /></button>
      <input type="range" min="0" max={points.length - 1} value={activeIndex} aria-label="Inspect recorded probability" aria-valuetext={point ? `${percentText(point.probability)}, ${datePT(point.timestamp, true)}` : "No observation"} onChange={(e) => { setIndex(Number(e.target.value)); setGap(false); }} />
      <button aria-label="Later recorded observation" disabled={activeIndex >= points.length - 1} onClick={() => { setIndex(activeIndex + 1); setGap(false); }}><ChevronRight size={17} /></button>
    </div>}
    <p className={styles.note}>{result ? `${name} · ${result === "won" ? "Won" : "Lost"}. The result adds no probability point.` : points.length === 1 ? "One observation; no path is inferred." : points.length ? "Full recorded journey · tap the plot to inspect. Gaps stay blank." : data.historyNote}</p>
  </section>;
}
