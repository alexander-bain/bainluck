/**
 * CaseStudyChart — the "what the number knew" visual for a case study, cropped to
 * ONE annotated moment (L2-143 punch template, Beat 2). Pure presentational SVG,
 * no client hooks — safe to render from server or client pages. Colors come from
 * design-system tokens via `currentColor` (light-mode only).
 */
import type { CaseStudyChart as ChartData } from "@/lib/story-content";
import Sparkline from "@/components/Sparkline";

// L2-150: the annotated case-study line now rides the shared single-market renderer.
// Geometry (320×132, big pads for label + caption), the 50% reference line, the flat
// area fill, and the annotated moment are all preserved via Sparkline props.
function LineChart({
  chart,
}: {
  chart: Extract<ChartData, { type: "line" }>;
}) {
  const { points, annotationIndex, annotationLabel, caption } = chart;
  return (
    <Sparkline
      data={points}
      domain={[0, 100]}
      width={320}
      height={132}
      padX={10}
      padTop={14}
      padBottom={18}
      stroke={2.5}
      color="var(--accent-brand)"
      area="flat"
      referenceValue={50}
      annotation={{ index: annotationIndex, label: annotationLabel }}
      caption={caption}
      ariaLabel={`${caption}. ${annotationLabel}.`}
      className="w-full h-auto"
    />
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
