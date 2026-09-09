/**
 * THE DEFAULT SHARE CARD — the picture a pasted bainluck.com link unfurls with.
 *
 * ═══ WHY THIS FILE EXISTS ═══
 *
 * Alex's distribution audit (2026-09-08): "home share card -> no og:image
 * anywhere; 'summary', not large-image -- blocker".
 *
 * Measured on production before writing this, because the audit's "anywhere"
 * was an overstatement worth correcting: `/about`, `/events/[id]` and
 * `/futures/[id]` DO ship a 1200x630 `opengraph-image` and DO declare
 * `summary_large_image`. What had no image at all was the ROOT — and with it
 * `/`, `/discover`, `/sports`, `/calibration`, `/politics`, `/economics`,
 * `/entertainment`, `/weather`, `/play` and the team pages, i.e. every URL a
 * stranger is actually handed first.
 *
 * A root `opengraph-image` is inherited by every descendant segment that does
 * not define its own, so this one file is the whole fix for all of them, and
 * the three routes above keep their own (better, content-specific) cards.
 *
 * ⚠️ **THE INHERITANCE IS NOT A GUESS AND MUST NOT BECOME ONE.** A page whose
 * layout exports `metadata.openGraph` is the case that could plausibly drop the
 * inherited image, and most of the routes listed above do exactly that. It is
 * verified against BUILT HTML — not reasoned about — by
 * `__tests__/shareUnfurl.test.ts`, which reads the rendered `<meta>` tags for
 * each route out of `.next` and fails if any of them lacks an absolute
 * `og:image`. This is the LAT-P086 failure mode (a thing that builds valid and
 * is silently never used) and the guard is the only reason to trust the claim.
 *
 * Design deliberately matches `app/about/opengraph-image.tsx`: same light
 * surface, same lockup, same 60/40 chip. A share card is the first thing a
 * stranger sees of the brand and two different brands would be worse than one
 * plain one.
 */
import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt =
  "Bain Luck — see what the world thinks will happen, as probabilities.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          background: "#f8fafc",
          color: "#111827",
          fontFamily: "Inter, Arial, sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ fontSize: 44 }}>🍀</div>
          <div style={{ fontSize: 34, fontWeight: 800 }}>Bain Luck</div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <div
            style={{
              fontSize: 66,
              fontWeight: 900,
              lineHeight: 1.05,
              maxWidth: 940,
            }}
          >
            See what the world thinks will happen.
          </div>
          <div
            style={{
              fontSize: 30,
              color: "#475569",
              lineHeight: 1.3,
              maxWidth: 900,
            }}
          >
            Sports, politics, economics and culture — every question as one
            clean probability.
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              border: "2px solid #d1d5db",
              borderRadius: 999,
              padding: "12px 22px",
              fontSize: 24,
              fontWeight: 700,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            <span style={{ color: "#111827" }}>60%</span>
            <span style={{ color: "#94a3b8", fontWeight: 500 }}>vs</span>
            <span style={{ color: "#64748b" }}>40%</span>
          </div>
          <div style={{ fontSize: 24, color: "#64748b" }}>bainluck.com</div>
        </div>
      </div>
    ),
    size
  );
}
