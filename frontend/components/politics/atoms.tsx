/** Politics-page atoms shared by the page and its extracted sections.
 *
 * Lifted verbatim out of `app/politics/page.tsx` by UX-P187 so that
 * `CrossSourceSpotlight` could be extracted and render-tested: a Next.js route
 * file may only export the reserved names, so nothing declared inside one can
 * be driven by a test. Mirrors the `components/economics/atoms.tsx` precedent.
 *
 * The CSS module still lives with the page — these are the same class names on
 * the same stylesheet, not a copy.
 */
import s from "@/app/politics/politics.module.css";

export const BORDER_COLOR: Record<string, string> = {
  presidential: "#3B82F6",
  congressional: "#8B5CF6",
  gubernatorial: "#10B981",
  policy: "#F59E0B",
  scotus: "#EF4444",
  international: "#0EA5E9",
  other: "#9CA3AF",
};

export function SourceBadge({ source, compact = false }: { source: string; compact?: boolean }) {
  if (source === "both" || source === "Both") {
    return (
      <span className={s.srcBoth} title="Both Kalshi and Polymarket">
        <span className={s.srcDot} style={{ background: "#22C55E" }} />
        <span className={s.srcDot} style={{ background: "#3B82F6" }} />
        {!compact && "Both"}
      </span>
    );
  }
  if (source === "kalshi") {
    return (
      <span className={s.srcKalshi}>
        <span className={s.srcDot} style={{ background: "#22C55E" }} />
        Kalshi
      </span>
    );
  }
  return (
    <span className={s.srcPolymarket}>
      <span className={s.srcDot} style={{ background: "#3B82F6" }} />
      Polymarket
    </span>
  );
}
