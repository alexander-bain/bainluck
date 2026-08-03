export type ContentState = "content" | "loading" | "blank" | "malformed";

/**
 * What a spec measured about the page's main region.
 *
 * Deliberately measurements, not a verdict: the spec observes, the shared
 * evaluator decides. `skeletonTextLength` is the text carried by the VISIBLE
 * skeleton markers, so `textLength - skeletonTextLength` is the rendered
 * substance that is not a loading placeholder.
 */
export interface MainRegionObservation {
  /** Trimmed `innerText` length of `main` (or `body` where no `main` exists). */
  textLength: number;
  /** Combined trimmed `innerText` length of every VISIBLE skeleton marker. */
  skeletonTextLength: number;
  /** How many skeleton markers are visible. Distinguishes loading from blank. */
  visibleSkeletonCount: number;
  /** Override the non-skeleton character floor. Default `MIN_CONTENT_CHARS`. */
  minChars?: number;
}

export declare const MIN_CONTENT_CHARS: number;

export declare const CONTENT_STATES: {
  CONTENT: "content";
  LOADING: "loading";
  BLANK: "blank";
  MALFORMED: "malformed";
};

export declare function classifyMainRegion(input: MainRegionObservation): {
  state: ContentState;
  nonBlank: boolean;
  detail: string;
};
