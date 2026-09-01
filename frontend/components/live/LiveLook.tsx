"use client";

/**
 * THE LIVE LOOK — the three shared pieces, used by every live card and hero.
 *
 * Alex, 2026-09-01, LIVE UPDATES ruling (2): animated number (<=1 change/~5s),
 * "live · Ns ago" pulse, last-10-min sparkline. The illiquidity ring stays.
 *
 * All three are presentational. Every decision — throttling, the age label, the
 * window — is `lib/live/liveNumber.ts`, so the same rules can be pointed at the
 * native surface without a second implementation drifting from this one (the
 * `event_concept_population` lesson, one directory over).
 *
 * ⚠️ ALL THREE RENDER NOTHING WHEN THEY HAVE NOTHING. Not an empty box, not a
 * skeleton, not a zero — the absence of a live number is a card that looks
 * exactly like it did before this feature existed. A live chrome that appears
 * before its data is a card that looks broken for the first two seconds of
 * every load, and it is how "live" stops meaning anything.
 */

import Sparkline from "@/components/Sparkline";
import {
  hasLiveSparkline,
  livePulse,
  liveWindow,
  type LivePoint,
} from "@/lib/live/liveNumber";

/* ────────────────────────────── the number ────────────────────────────── */

/**
 * The live probability, in points.
 *
 * 🔴 IT STEPS. It does not tween, ease, roll or count. `61` becomes `67`, and
 * the digits `62`–`66` are never painted because the market never quoted them
 * (`lib/live/liveNumber.ts` opens with the argument). What animates is a
 * ~500ms tint in the direction of travel, which is a statement ABOUT the
 * change rather than a fake rendering OF it.
 *
 * The tint is a CSS transition on colour only — no transform, no layout — so it
 * cannot shift the hero, and `motion-reduce:` drops it entirely for a reader
 * who has asked for that. The NUMBER is never withheld from anybody; only the
 * decoration is.
 */
export function LiveNumber({
  value,
  direction,
  className,
  testId = "live-number",
}: {
  value: number | null;
  direction: -1 | 0 | 1;
  className?: string;
  testId?: string;
}) {
  if (value == null || !Number.isFinite(value)) return null;
  const tint =
    direction > 0
      ? "text-accent-live"
      : direction < 0
        ? "text-accent-danger"
        : "";
  return (
    <span
      className={`tabular-nums transition-colors duration-500 motion-reduce:transition-none ${tint} ${className ?? ""}`.trim()}
      data-testid={testId}
      data-live-direction={direction}
      // The rendered integer, so a browser rail can compare the painted number
      // against the hero on the page this card links to (the UX-P003 contract).
      data-live-value={Math.round(value)}
      aria-live="polite"
      // A screen reader that announced every throttled change would be
      // unusable. `polite` + the 5s floor is roughly one announcement per five
      // seconds, which is the same budget the sighted reader gets.
    >
      {Math.round(value)}%
    </span>
  );
}

/* ─────────────────────────────── the pulse ─────────────────────────────── */

const PULSE_SKIN: Record<string, { dot: string; text: string }> = {
  live: { dot: "bg-accent-live animate-pulse motion-reduce:animate-none", text: "text-accent-live" },
  waiting: { dot: "bg-text-muted", text: "text-text-muted" },
  paused: { dot: "bg-accent-warning", text: "text-accent-warning" },
};

/**
 * "live · 12s ago", and the honest thing past two minutes.
 *
 * 🔴 `observedAt` MUST BE THE TIMESTAMP OF THE NUMBER ON SCREEN, not the last
 * frame received. The throttle can hold a value back by up to five seconds, so
 * passing the newest observation would print an age fresher than the pixel
 * beside it. `useLiveBlend` returns `shown`, which is the painted point, and
 * that is the one to pass.
 *
 * Past `LIVE_AGE_LIMIT_MS` the dot stops pulsing and stops being green, and the
 * label says "updates paused". That is the state the Flow Sentinel exists to
 * catch and it is the one this component makes unreachable-by-accident: there
 * is no prop that forces a live tone.
 */
export function LivePulse({
  observedAt,
  now,
  className,
}: {
  observedAt: number | null;
  now: number;
  className?: string;
}) {
  const pulse = livePulse(observedAt, now);
  if (!pulse) return null;
  const skin = PULSE_SKIN[pulse.tone] ?? PULSE_SKIN.waiting;
  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] font-medium ${skin.text} ${className ?? ""}`.trim()}
      data-testid="live-pulse"
      data-live-tone={pulse.tone}
      data-live-age-ms={pulse.ageMs}
      title={
        pulse.tone === "paused"
          ? "Nothing new has reached us for over two minutes"
          : "How long ago this number was observed"
      }
    >
      <span className={`w-1.5 h-1.5 rounded-full ${skin.dot}`} aria-hidden="true" />
      {pulse.label}
    </span>
  );
}

/* ───────────────────────────── the sparkline ───────────────────────────── */

/**
 * The last ten minutes, drawn as raw segments on the honest axis.
 *
 * Rides the shared `Sparkline`, which already carries the standing chart
 * rulings — no smoothing, fixed [0,100] probability domain, minimal chrome. A
 * hand-rolled one here would be the sixth copy of a renderer L2-150 spent a
 * queue consolidating, and the first one free to grow a bezier.
 *
 * ⚠️ `domain` IS LEFT AT ITS [0,100] DEFAULT ON PURPOSE. Auto-fitting a
 * ten-minute window is the single most tempting change to this component and it
 * is the one that makes it lie: a market that moved 61.2 → 61.6 would draw a
 * dramatic climb across the full height of the box. The flat line is the truth,
 * and a flat line is exactly what a reader should see when nothing happened.
 */
export function LiveSparkline({
  series,
  now,
  width = 64,
  height = 18,
}: {
  series: readonly LivePoint[];
  now: number;
  width?: number;
  height?: number;
}) {
  const windowed = liveWindow(series, now);
  if (!hasLiveSparkline(windowed)) return null;
  return (
    <span
      className="inline-flex items-center"
      data-testid="live-sparkline"
      data-live-points={windowed.length}
      title="The last ten minutes"
    >
      <Sparkline
        data={windowed.map((p) => p.value)}
        width={width}
        height={height}
        color="trend"
        stroke={1.5}
      />
    </span>
  );
}
