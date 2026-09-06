/**
 * Telling "this sport is not there" from "we could not ask" — #3254.
 *
 * `/sport/tennis/atp` rendered `Sport "tennis" not found` on production
 * (2026-09-05), then served the full ATP page ~2 minutes later without a
 * deploy. Tennis existed the whole time. The page had been rate limited —
 * `{"detail":"Rate limit exceeded: 60/minute","retry_after":41}` — and the
 * slug-resolution loop turned every outcome into a claim of permanent absence
 * through a bare `catch {}`.
 *
 * That is gotcha #36 ("never catch-all in an API client returning Optional —
 * 429 must re-raise") and gotcha #53 ("an empty read and a broken read must not
 * render identically"), landing on a rendered surface. A reader told a thing
 * does not exist stops looking for it; a reader told we could not reach it
 * reloads — and here reloading was all it took.
 *
 * The wording itself is `lib/loadFailure.ts`'s job (#2783) and is not
 * re-invented here (ruling 025 clause 2). What this module adds is the bit
 * loadFailure cannot know: these pages try SEVERAL slugs before giving up, so
 * "did anything 404" is not the question — "did every candidate 404" is.
 */
import type { LoadFailure } from "@/lib/loadFailure";
import { describeLoadFailure } from "@/lib/loadFailure";

/** The status-carrying error shape `apiFetch` throws (`lib/api.ts`). */
type MaybeApiError = { status?: number; message?: string } | null | undefined;

export interface SportResolutionFailure extends LoadFailure {
  /**
   * True ONLY when the sport's absence was ESTABLISHED — every candidate slug
   * answered 404. False whenever we merely failed to ask, which is when the
   * page must not claim absence and must keep offering the sport as an escape.
   */
  sportAbsent: boolean;
  /** HTTP status, for publishing as an attribute rather than as copy. */
  status?: number;
}

/**
 * Whether a thrown candidate-slug error means we could not ASK.
 *
 * A 404 is the alias mechanism working as designed: `/sport/icehockey/...`
 * tries `icehockey` (404) before `hockey` (200), so a 404 is expected traffic
 * and must stay silent. Every other outcome — 429, 5xx, a timeout, an offline
 * device (no status at all) — means the question never got an answer.
 *
 * This one predicate is the whole defect: the loop used to discard it.
 */
export function isUnreachable(error: unknown): boolean {
  return (error as MaybeApiError)?.status !== 404;
}

/**
 * The honest failure for a hierarchy that would not resolve.
 *
 * `unreachable` is the last non-404 error the candidate loop saw, or null when
 * every candidate cleanly 404'd. Note the asymmetry: ONE unreachable candidate
 * is enough to disqualify the not-found claim even if a later candidate 404s,
 * because a 404 on the alias slug tells us nothing about the sport when we
 * never got a verdict on the real one.
 */
export function classifySportResolutionFailure(
  unreachable: MaybeApiError,
  sportSlug: string,
): SportResolutionFailure {
  if (unreachable) {
    return {
      ...describeLoadFailure(unreachable, "league"),
      sportAbsent: false,
      status: unreachable.status,
    };
  }

  return {
    title: `Sport "${sportSlug}" not found`,
    message: "Check the address, or browse the sports we cover.",
    // A 404 reloads as a 404. Offering the button invites the reader to keep
    // pressing it — `loadFailure.ts`'s own rule, applied here.
    retryable: false,
    sportAbsent: true,
    status: 404,
  };
}
