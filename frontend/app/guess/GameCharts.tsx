"use client";

// The two charts at the end: points card by card, and each player's chance of
// winning card by card. Asked for in playtesting ("like fantasy football").
//
// Drawn as plain SVG. Every line is named at its right-hand end, so the chart
// reads without relying on color, and a line for a house player is dashed.

export interface ChartSeries {
  name: string;
  values: number[];
  /** A Tailwind text color class; the line and its label take `currentColor`. */
  color: string;
  dashed: boolean;
}

interface LineChartProps {
  title: string;
  note?: string;
  series: ChartSeries[];
  yMax: number;
  /** Turns a y value into its axis label. */
  yLabel: (value: number) => string;
  /** Where one round ends and the next begins, as a card number. */
  roundAt: number;
}

const W = 340;
const H = 200;
const LABEL_GAP = 12;
const LEFT = 34;
const RIGHT = 248;
const TOP = 14;
const BOTTOM = 166;

export function LineChart({ title, note, series, yMax, yLabel, roundAt }: LineChartProps) {
  const steps = Math.max(1, ...series.map((s) => s.values.length - 1));
  const x = (i: number) => LEFT + ((RIGHT - LEFT) * i) / steps;
  const y = (v: number) => BOTTOM - ((BOTTOM - TOP) * Math.max(0, Math.min(yMax, v))) / yMax;

  // Labels at the right-hand end, nudged apart so no two overlap: first pushed
  // down from the top, then pulled back up from the bottom so none leaves the plot.
  const ends = series
    .map((s, index) => ({ index, at: y(s.values[s.values.length - 1] ?? 0) }))
    .sort((a, b) => a.at - b.at);
  for (let i = 1; i < ends.length; i += 1) {
    if (ends[i].at - ends[i - 1].at < LABEL_GAP) ends[i].at = ends[i - 1].at + LABEL_GAP;
  }
  for (let i = ends.length - 1; i >= 0; i -= 1) {
    const limit = i === ends.length - 1 ? BOTTOM + 4 : ends[i + 1].at - LABEL_GAP;
    if (ends[i].at > limit) ends[i].at = limit;
  }
  const labelAt = new Map(ends.map((e) => [e.index, e.at]));

  const grid = [0, 0.25, 0.5, 0.75, 1].map((f) => f * yMax);

  return (
    <figure className="rounded-3xl border-2 border-surface-border bg-surface-card p-3">
      <figcaption className="px-1 text-sm font-black text-text-primary">{title}</figcaption>
      {note && <p className="px-1 text-xs text-text-secondary">{note}</p>}
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 h-auto w-full" role="img" aria-label={title}>
        {grid.map((v) => (
          <g key={v} className="text-text-muted">
            <line x1={LEFT} x2={RIGHT} y1={y(v)} y2={y(v)} stroke="currentColor" strokeWidth={0.5} strokeDasharray="2 3" />
            <text x={LEFT - 5} y={y(v) + 3} textAnchor="end" fontSize={9} fill="currentColor">
              {yLabel(v)}
            </text>
          </g>
        ))}
        <g className="text-text-secondary">
          {[0, roundAt, steps]
            .filter((v, i, all) => v <= steps && all.indexOf(v) === i)
            .map((card) => (
              <text key={card} x={x(card)} y={H - 8} textAnchor="middle" fontSize={9} fill="currentColor">
                {card === 0 ? "start" : `card ${card}`}
              </text>
            ))}
          {roundAt < steps && <line x1={x(roundAt)} x2={x(roundAt)} y1={TOP} y2={BOTTOM} stroke="currentColor" strokeWidth={0.5} />}
        </g>
        {series.map((s, index) => (
          <g key={s.name} className={s.color}>
            <polyline
              fill="none"
              stroke="currentColor"
              strokeWidth={2.5}
              strokeLinejoin="round"
              strokeLinecap="round"
              strokeDasharray={s.dashed ? "5 4" : undefined}
              points={s.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}
            />
            <circle cx={x(s.values.length - 1)} cy={y(s.values[s.values.length - 1] ?? 0)} r={3} fill="currentColor" />
            <text x={RIGHT + 8} y={(labelAt.get(index) ?? 0) + 3} fontSize={10} fontWeight={700} fill="currentColor">
              {s.name.length > 11 ? `${s.name.slice(0, 10)}…` : s.name} {yLabel(s.values[s.values.length - 1] ?? 0)}
            </text>
          </g>
        ))}
      </svg>
    </figure>
  );
}
