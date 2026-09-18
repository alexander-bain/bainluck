/**
 * The Daily Challenge's guess target: a subject, the question, and the number
 * the reader guesses against.
 *
 * ═══ #7004 — THE ABSENT LABEL IS THE POINT OF THIS COMPONENT ═══
 *
 * This box used to be headed **"Market line"**. The number in it is NOT the
 * market's line and provably never is. It comes from `deterministicThreshold`
 * in `app/daily/page.tsx`, which offsets the real probability by a seeded
 * 0.12–0.25 and re-offsets the other way if clamping brings it back within 10
 * points. latency/567 swept the function's whole admitted domain — actual 5..95
 * pct × 4,000 question ids × 3 date keys, **1,092,000 inputs**:
 *
 *     gap |displayed − actual|        min 11 pts · max 25 pts
 *     displayed within 10 pts         0 / 1,092,000
 *
 * The offset is the POINT of the game, and the codebase says so: the shared
 * helper `lib/play/threshold.ts` documents "a 10–25% gap … guaranteed ≥10%
 * away". So the repo promised this number is never the market's line while the
 * page called it exactly that.
 *
 * Live on 2026-09-18, `/daily` at 390px signed out: "Espanyol to win — **34%**"
 * under the heading "Market line", with the card's own *Open market details*
 * link directly below landing on `/events/15306048` and its **54%** in 48pt
 * over a two-day chart that never dips under 50%. We printed a false fact about
 * a market and handed the reader the link that disproves it.
 *
 * 🔴 **Nothing replaces the label.** `/play` renders the same class of number
 * and is the in-repo correct form — it attributes nothing ("Is the chance of X
 * higher or lower than N%?"). The question is already inside this box, so the
 * heading was never load-bearing: subject → question → number is complete and
 * claims nothing. "The line" and "Guess against" were both rejected — "line" is
 * betting vocabulary on a product whose own footer reads "Probability, not
 * betting", and trading a false attribution for a betting word is not the trade.
 *
 * 🔴 It lives in its own file so that absence can be GUARDED. As a local
 * function inside `app/daily/page.tsx` it was unreachable from a test: the
 * page loads its questions in a `useEffect`, which server rendering never runs,
 * and the suite's environment is `node` — so a rendered assertion about this
 * box was impossible where it used to live. Two primitive props, no page-local
 * types, so it renders standalone.
 */
export function DailyThresholdBox({
  subject,
  threshold,
}: {
  subject: string;
  threshold: number;
}) {
  return (
    <div
      data-testid="daily-threshold-box"
      className="mt-6 rounded-lg border border-surface-border bg-surface-deep p-4"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-lg font-semibold">{subject}</p>
          <p className="text-sm text-text-muted">
            Is the probability higher or lower than this?
          </p>
        </div>
        <div className="font-mono text-5xl font-black tabular-nums">{threshold}%</div>
      </div>
    </div>
  );
}

export default DailyThresholdBox;
