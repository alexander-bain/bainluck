/**
 * UX-P053 (#1650) — the settled-props specimen finder, extracted so the contract
 * suite can prove it against fixtures instead of against a live slate that
 * changes hourly (and that, at 18:10 PT, contains no specimen at all).
 */

/** Leagues that publish player props, tried before any unfiltered listing. */
export declare const PROP_BEARING_SPORTS: readonly string[];

/** How far back the lookback listing reaches. */
export declare const HIGHLIGHT_LOOKBACK_DAYS: number;

/** Per-listing page size. Bounds a listing, not the expensive per-event probes. */
export declare const LISTING_LIMIT: number;

/** Total `/game-markets` fetches allowed across ALL listings. */
export declare const MAX_PROP_PROBES: number;

/** Statuses whose page can exhibit #1650. A live game cannot. */
export declare const SETTLED_STATUSES: ReadonlySet<string>;

/** A listing to try, and how to read the events out of its response body. */
export interface SpecimenListing {
  url: string;
  pick: (body: any) => unknown;
}

/** The listings to try, in order: lookback first, day-bounded as fallback. */
export declare function specimenListings(apiBase: string): SpecimenListing[];

/** Newest first — the ASC listing puts prop-bearing evening games last. */
export declare function newestFirst<T>(events: T[] | null | undefined): T[];

/** Could this listing entry's page exhibit #1650 at all? */
export declare function isSettledCandidate(
  ev: { status?: string | null } | null | undefined,
): boolean;

/** A settled game that publishes player props, and how many were graded. */
export interface Specimen {
  id: number;
  propCount: number;
  /** Props the backend typed a verdict for — an explicit `hit`, never a default. */
  gradedCount: number;
}

/** Minimal Playwright `APIResponse` shape, injected so this never imports a browser. */
export interface SpecimenResponse {
  ok: () => boolean;
  json: () => Promise<any>;
}

/**
 * Search for a settled event that publishes player props.
 *
 * `null` is a legitimate answer on a thin slate, and the caller MUST fail on it:
 * a run that collected no evidence is not a pass on this rail.
 */
export declare function findSettledEventWithProps(
  get: (url: string) => Promise<SpecimenResponse>,
  apiBase: string,
): Promise<Specimen | null>;
