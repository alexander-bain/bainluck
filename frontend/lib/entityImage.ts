// Identity-guarded async image resolution for the grouped-feed avatar
// components (PlayerStatCard.PlayerAvatar + ProgressionLadder.TeamLogo). L2-199.
//
// The invariant, plainly: an image resolved for entity A must NEVER be shown
// next to entity B. Two independent failure modes make this real in the grouped
// feed:
//
//   1. Recycled instances — GroupedFeedRenderer keys rows by entity identity
//      (L2-178), which prevents the common recycle. But if a row IS ever reused
//      for a different entity, the avatar's local state (resolved url / failed)
//      must reset, or it paints the previous entity's face.
//   2. Late lookups — a Wikipedia lookup fired for entity A can resolve AFTER
//      the identity changed to B. Its `.then` would call setState with A's image
//      while B is mounted.
//
// `EntityImageGate` mirrors `TypeaheadRequestGate` (L2-198): a tiny framework-
// free class so the "only the current identity's result is applied" rule is
// unit-testable in the repo's node test environment (no jsdom/RTL). `begin()`
// opens a resolution generation bound to an entity identity; `owns()` is true
// only while that identity is still current, so a late lookup for a superseded
// identity is dropped before it can call setState.

import { useEffect, useRef, useState } from "react";

export class EntityImageGate {
  private current: string | null = null;

  /**
   * Open a resolution generation for `identity`, superseding any prior one.
   * Hold the identity and check `owns()` after the async lookup resolves.
   */
  begin(identity: string): string {
    this.current = identity;
    return identity;
  }

  /**
   * True only while `identity` is the identity currently mounted. A caller MUST
   * check this after awaiting the lookup and before applying the result, so a
   * late lookup for a previous entity cannot land on the current one.
   */
  owns(identity: string): boolean {
    return this.current === identity;
  }

  /** Abandon the in-flight generation (unmount) so no late result applies. */
  cancel(): void {
    this.current = null;
  }
}

export interface EntityImageState {
  /** The URL to render, or null to fall back (initials/colored square). */
  url: string | null;
  /** True once every resolution path has failed. */
  failed: boolean;
  /** Call from an <img> onError to drop a broken URL and fall back. */
  markFailed: () => void;
}

/**
 * Resolve an entity's image with identity-safe reset + late-lookup cancellation.
 *
 * - Seeds from `directUrl` (ESPN headshot / team logo / passed-in URL).
 * - Re-seeds whenever `identity` or `directUrl` changes, so a recycled instance
 *   can never keep the previous entity's resolved image or failure state.
 * - Falls back to `lookup(identity)` (e.g. Wikipedia) only while no image is
 *   resolved and it hasn't failed; the gate + an `active` flag drop a result
 *   whose identity is no longer current.
 *
 * `lookup` MUST be a stable reference (pass a module-level function, not an
 * inline arrow) — it participates in the effect dependency list.
 */
export function useEntityImage(
  identity: string,
  directUrl: string | null | undefined,
  lookup: (identity: string) => Promise<string | null>,
): EntityImageState {
  const [url, setUrl] = useState<string | null>(directUrl || null);
  const [failed, setFailed] = useState(false);
  const gate = useRef(new EntityImageGate()).current;

  // Re-seed on identity/direct-URL change — the belt-and-suspenders reset for
  // any instance reuse the key fix doesn't cover.
  useEffect(() => {
    setUrl(directUrl || null);
    setFailed(false);
  }, [identity, directUrl]);

  useEffect(() => {
    if (url || failed) return;
    gate.begin(identity);
    let active = true;
    lookup(identity).then((resolved) => {
      // Dropped if this component unmounted (`active`) or the identity changed
      // out from under the lookup (`owns`) — a late A cannot land on B.
      if (!active || !gate.owns(identity)) return;
      if (resolved) setUrl(resolved);
      else setFailed(true);
    });
    return () => {
      active = false;
      gate.cancel();
    };
  }, [identity, url, failed, gate, lookup]);

  return {
    url,
    failed,
    markFailed: () => {
      setUrl(null);
      setFailed(true);
    },
  };
}
