/**
 * #9051 — a served source REMOVAL orders against held observations.
 *
 * The page holds blends that other payloads delivered: pushed frames and the
 * history payload's pinned edge. Each is a whole blend dated by the newest
 * price it folded, and `lib/blendObservationClock.ts` orders them against the
 * detail hero by those price clocks. That ordering cannot see a removal. After
 * a source is retired, the fresh detail response serves the survivors' blend,
 * dated by the survivors' last quote, which can be OLDER than a frame the page
 * received before the retirement. Price ordering then reapplied that frame: its
 * blend still folded the removed source, and `applyLiveFrame` recreated the
 * removed source's entry. Measured on the exact PR #9028 helpers: Kalshi .8 +
 * Polymarket .4 held at .6 over a post-removal response serving .4.
 *
 * Refusing every frame whose source the response lacks is NOT the fix: a stale
 * response computed before a source first appeared is byte-identical to a fresh
 * one computed after it was removed (#8779 delivers exactly that new source).
 * Only the server knows which happened, so it says so:
 * `blend_source_removed_at` dates the latest committed removal of any source
 * from the blend this response's hero folds. Additions and price writes never
 * move it, so a stale pre-addition response carries an older removal clock
 * than the new source's first frame and the frame still lands.
 *
 * A held blend observed at or before that removal predates the membership the
 * response reports, whichever source it was about — a frame for a survivor
 * still folded the removed source into its `p`. Equal clocks keep the response
 * (the removal is the later write on that row). Absent, null or unparseable
 * removal clocks, and unparseable observation clocks, decide nothing: every
 * existing ordering rule applies unchanged.
 */

type RemovalDated = { blend_source_removed_at?: string | null };

export function predatesServedSourceRemoval(
  served: RemovalDated | null | undefined,
  observedAt: string | null | undefined,
): boolean {
  const removedAt = Date.parse(served?.blend_source_removed_at ?? "");
  const at = Date.parse(observedAt ?? "");
  return Number.isFinite(removedAt) && Number.isFinite(at) && at <= removedAt;
}
