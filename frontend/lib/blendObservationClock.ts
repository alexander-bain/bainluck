import { isQuoteStreamStatus } from "./eventQuoteStream";
import { PINNABLE_HERO_SOURCE } from "./chartEdgePin";
import { compareFoldRevision, parseFoldRevision, type FoldRevision } from "./foldRevision";

/**
 * #8749 / #837 — the headline and the chart agree on the NEWEST observed blend,
 * whichever payload happened to carry it.
 *
 * The page holds three copies of one number: the detail payload's hero, the
 * frames the stream applies to it, and the history payload's pinned edge.
 * Until PR #8758 only two of them carried a clock. The pinned edge's
 * `timestamp` is the minute the history route SERVED it — it may be carrying a
 * detail hero cached up to a TTL earlier — so ordering a real observation
 * against it answered "which request came later", not "which price is newer".
 * PIT@DET line 421 (live/617) is the case that ordering could not see: a
 * history refetch carried 53.2 while the headline held an older 52.03, and
 * `pinChartEdgeToHero` then wrote the older number over the newer one.
 *
 * `hero_probability_observed_at` and `blend_edge_observed_at` date the two
 * VALUES. They are provenance, not a version: equal or unknown clocks decide
 * nothing, and every function here returns its input untouched unless one
 * side is strictly newer and both sides are known.
 *
 * #9051: a price clock cannot see a source REMOVAL, so when both sides carry
 * the fold revision they were computed from (`lib/foldRevision.ts`), commit
 * order decides first and the price clock only breaks a tie within one
 * snapshot.
 */

/**
 * The history payload's pinned edge as an observation of the blend.
 * `foldRevision` (#9051): the revision of the fold the edge was computed from,
 * present only when the payload serves a well-formed one.
 */
export type BlendEdgeObservation = {
  p: number;
  observedAt: string;
  foldRevision?: FoldRevision;
};

type ServedEdge = {
  aggregate_line?: Array<{ timestamp: string; home_probability: number }> | null;
  blend_edge_pinned?: boolean | null;
  blend_edge_observed_at?: string | null;
  blend_edge_fold_revision?: unknown;
};

type AdoptingHero = {
  status?: string | null;
  hero_probability?: number | null;
  hero_probability_away?: number | null;
  hero_probability_source?: string | null;
  hero_probability_observed_at?: string | null;
  blend_fold_revision?: unknown;
};

/**
 * The served edge with its observation clock, or `null` when there is no pin,
 * no clock (a legacy cache entry stays unknown), or no usable price. Reads the
 * SERVED response: `_pin_blend_edge` writes the last point of the array it
 * returns, and a merged array's last point may be a frame.
 */
export function servedBlendEdgeObservation(
  history: ServedEdge | null | undefined,
): BlendEdgeObservation | null {
  if (!history?.blend_edge_pinned) return null;
  const at = history.blend_edge_observed_at;
  if (typeof at !== "string" || !Number.isFinite(Date.parse(at))) return null;
  const line = history.aggregate_line;
  const p = line?.[line.length - 1]?.home_probability;
  if (typeof p !== "number" || !Number.isFinite(p) || p < 0 || p > 1) return null;
  const foldRevision = parseFoldRevision(history.blend_edge_fold_revision);
  return foldRevision ? { p, observedAt: at, foldRevision } : { p, observedAt: at };
}

/**
 * The history-newer direction: when the chart's pinned edge was observed
 * strictly after the headline's blend, the headline takes the edge's price and
 * clock. Both are the same quantity — `_pin_blend_edge` pins the detail
 * route's own `hero_probability` or the same folded computation — so this is
 * the headline catching up, not a second number replacing the first.
 *
 * Live blend headlines only: a settled winner, an opening fallback and
 * `final_unresolved` are different claims (terminal handling is untouched).
 * An unknown headline clock adopts nothing on the price rule. A withheld away
 * side (#6238, draw-priced sports) stays withheld. Returns the SAME object when
 * nothing changes, so an SWR mutate through it is a no-op.
 *
 * #9051, when both carry a fold revision: an OLDER or incomparable edge is
 * refused however much newer its price (it can still fold a removed source); a
 * NEWER one is adopted with its own price clock even when that clock is older
 * (a removal can leave only an older surviving quote) or its value unchanged;
 * the same snapshot falls to the price rule. An adopted edge's revision is kept
 * on the headline, so a delayed older edge cannot undo it. An edge with no
 * revision is refused by a headline that holds one (Codex on 64a14a3d8d: a
 * value is never tagged with a revision borrowed from another value), and a
 * headline with none takes the price rule and then the edge's revision.
 */
export function adoptNewerBlendEdge<T extends AdoptingHero>(
  event: T | undefined, edge: BlendEdgeObservation | null | undefined,
): T | undefined {
  if (!event || !edge || !isQuoteStreamStatus(event.status) ||
      event.hero_probability_source !== PINNABLE_HERO_SOURCE ||
      typeof event.hero_probability !== "number" ||
      !Number.isFinite(event.hero_probability)) return event;
  const heldRevision = parseFoldRevision(event.blend_fold_revision);
  const edgeRevision = parseFoldRevision(edge.foldRevision);
  // Value and revision stay paired: an unversioned edge on a versioned headline
  // can neither take its revision nor be ordered against it.
  if (heldRevision && !edgeRevision) return event;
  const order = heldRevision && edgeRevision ? compareFoldRevision(edgeRevision, heldRevision) : null;
  if (order === "older" || order === "incomparable") return event;
  if (order !== "newer") {
    const heroAt = Date.parse(event.hero_probability_observed_at ?? "");
    if (!Number.isFinite(heroAt) || Date.parse(edge.observedAt) <= heroAt) return event;
  }
  return {
    ...event,
    hero_probability: edge.p,
    hero_probability_away:
      event.hero_probability_away == null ? event.hero_probability_away : 1 - edge.p,
    hero_probability_observed_at: edge.observedAt,
    ...(edgeRevision ? { blend_fold_revision: edgeRevision } : {}),
  };
}

/**
 * #9051: true when the held live blend refuses `edge` because the two cannot be
 * ordered — a twin joined or left the fold, or the components disagree. Only a
 * fresh detail read can say which fold is current, so the page asks for one
 * (and does NOT write the cache in the same tick; see the page's history effect).
 */
export function edgeInvalidatesHeldBlend(
  event: AdoptingHero | undefined, edge: BlendEdgeObservation | null | undefined,
): boolean {
  if (!event || !edge || !isQuoteStreamStatus(event.status) ||
      event.hero_probability_source !== PINNABLE_HERO_SOURCE) return false;
  const heldRevision = parseFoldRevision(event.blend_fold_revision);
  const edgeRevision = parseFoldRevision(edge.foldRevision);
  return !!heldRevision && !!edgeRevision && compareFoldRevision(edgeRevision, heldRevision) === "incomparable";
}
