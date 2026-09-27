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

/**
 * #9051 (Codex review of PR #9061) — a history EDGE is not dated like a frame.
 *
 * A frame's `updated_at` is the database write that published it, so it orders
 * against a database removal. A history edge's `observedAt` is the newest PRICE
 * its blend folded, and a price observed before a removal is legitimately
 * written into the post-removal blend after it (the matcher stamps the
 * observation, not its commit). Timeline, all 05:00:ssZ: Polymarket .4 at 00;
 * Polymarket .5 observed 10; Kalshi removed 15; the matcher commits .5 at 20
 * into the post-removal row. The edge `{p: .5, observedAt: 10}` folds no
 * removed source, yet `10 <= 15`. Two edges with identical observation clocks
 * can come from either membership, so the price clock cannot decide.
 *
 * So the edge carries the MEMBERSHIP it was computed from:
 * `blend_edge_source_removed_at` is the `blend_source_removed_at` of the blend
 * the edge folds — the same database clock the hero carries, so the two
 * compare like for like. An edge whose membership removal is older than the
 * hero's (or `null`: that membership had no removal) was computed before the
 * served removal and still folds the removed source. Equal is the same
 * membership, and the ordinary price ordering decides.
 *
 * `undefined` means the history payload does not carry the key (the producer
 * half is not shipped, or a legacy cache entry): no membership claim, so this
 * decides nothing. An unparseable string decides nothing too.
 */
export function edgePredatesServedSourceRemoval(
  served: RemovalDated | null | undefined,
  edgeMembershipRemovedAt: string | null | undefined,
): boolean {
  const removedAt = Date.parse(served?.blend_source_removed_at ?? "");
  if (!Number.isFinite(removedAt) || edgeMembershipRemovedAt === undefined) return false;
  if (edgeMembershipRemovedAt === null) return true;
  const edgeRemovedAt = Date.parse(edgeMembershipRemovedAt);
  return Number.isFinite(edgeRemovedAt) && edgeRemovedAt < removedAt;
}
