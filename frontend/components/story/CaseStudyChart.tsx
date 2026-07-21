/**
 * CaseStudyChart — the "what the number knew" visual for a case study, cropped to
 * ONE annotated moment (L2-143 punch template, Beat 2). Pure presentational SVG,
 * no client hooks — safe to render from server or client pages. Colors come from
 * design-system tokens via `currentColor` (light-mode only).
 */
import type { CaseStudyChart as ChartData } from "@/lib/story-content";

const VW = 320;
const VH = 132;
const PAD_X = 10;
const PAD_TOP = 14;
const PAD_BOTTOM = 18;

function LineChart({
  chart,
}: {
  chart: Extract<ChartData, { type: "line" }>;
}) {
  const { points, annotationIndex, annotationLabel, caption } = chart;
  const n = points.length;
  const usableW = VW - PAD_X * 2;
  const usableH = VH - PAD_TOP - PAD_BOTTOM;

  const x = (i: number) => PAD_X + (usableW * i) / (n - 1);
  const y = (p: number) => PAD_TOP + usableH * (1 - p / 100);

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(p).toFixed(1)}`)
    .join(" ");
  const areaPath = `${linePath} L ${x(n - 1).toFixed(1)} ${(VH - PAD_BOTTOM).toFixed(
    1
  )} L ${x(0).toFixed(1)} ${(VH - PAD_BOTTOM).toFixed(1)} Z`;

  const ai = Math.max(0, Math.min(n - 1, annotationIndex));
  const ax = x(ai);
  const ay = y(points[ai]);
  const labelRight = ax > VW / 2;

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${VW} ${VH}`}
        className="w-full h-auto"
        role="img"
        aria-label={`${caption}. ${annotationLabel}.`}
      >
        {/* 50% reference line */}
        <line
          x1={PAD_X}
          x2={VW - PAD_X}
          y1={y(50)}
          y2={y(50)}
          className="text-surface-border"
          stroke="currentColor"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
        {/* area fill */}
        <path d={areaPath} className="text-accent-brand" fill="currentColor" fillOpacity={0.08} />
        {/* probability line */}
        <path
          d={linePath}
          className="text-accent-brand"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {/* annotated moment */}
        <line
          x1={ax}
          x2={ax}
          y1={ay}
          y2={VH - PAD_BOTTOM}
          className="text-text-muted"
          stroke="currentColor"
          strokeWidth={1}
          strokeDasharray="2 2"
        />
        <circle cx={ax} cy={ay} r={5.5} className="text-accent-brand" fill="currentColor" />
        <circle cx={ax} cy={ay} r={2.5} fill="#fff" />
        <text
          x={labelRight ? ax - 8 : ax + 8}
          y={Math.max(PAD_TOP + 4, ay - 8)}
          className="text-text-primary"
          fill="currentColor"
          fontSize={11}
          fontWeight={600}
          textAnchor={labelRight ? "end" : "start"}
        >
          {annotationLabel}
        </text>
      </svg>
      <figcaption className="text-micro text-text-muted mt-1.5">{caption}</figcaption>
    </figure>
  );
}

function BarChart({
  chart,
}: {
  chart: Extract<ChartData, { type: "bars" }>;
}) {
  const { bars, annotationLabel, caption } = chart;
  const max = Math.max(...bars.map((b) => b.value), 1);

  return (
    <figure className="m-0">
      <div
        className="space-y-2.5"
        role="img"
        aria-label={`${caption}. ${bars
          .map((b) => `${b.label} ${b.value}%`)
          .join(", ")}. ${annotationLabel}.`}
      >
        {bars.map((b) => (
          <div key={b.label} className="flex items-center gap-3">
            <div className="w-28 shrink-0 text-micro text-text-secondary text-right">
              {b.label}
            </div>
            <div className="flex-1 h-6 rounded-md bg-surface-deep overflow-hidden">
              <div
                className={`h-full rounded-md ${
                  b.highlight ? "bg-accent-brand" : "bg-text-muted/40"
                }`}
                style={{ width: `${Math.max(4, (b.value / max) * 100)}%` }}
              />
            </div>
            <div
              className={`w-12 shrink-0 font-mono text-caption ${
                b.highlight ? "text-accent-brand font-bold" : "text-text-secondary"
              }`}
            >
              {b.value}%
            </div>
          </div>
        ))}
      </div>
      <figcaption className="text-micro text-text-muted mt-2">
        {caption} — <span className="text-text-secondary">{annotationLabel}</span>
      </figcaption>
    </figure>
  );
}

export default function CaseStudyChart({ chart }: { chart: ChartData }) {
  return chart.type === "line" ? <LineChart chart={chart} /> : <BarChart chart={chart} />;
}
