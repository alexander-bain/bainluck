/** UX-P029 Item 3 — console/request error VOLUME policy (#1600). */

export interface FailedRequestLike {
  url?: string;
  status?: number | null;
  failure?: string | null;
  /** Set by a spec that knows the request died because the page navigated. */
  navigationCancelled?: boolean;
}

export interface ErrorVolumeChannel {
  total: number;
  distinct: number;
  threshold: number;
  exceeded: boolean;
  /** Stable, count-free code — safe to fingerprint. `null` when within policy. */
  reason_code: string | null;
}

export interface RequestVolumeChannel extends ErrorVolumeChannel {
  /** Excluded from `total`, reported so the exclusion is never silent. */
  navigation_cancelled_excluded: number;
  by_origin: { origin: string; count: number }[];
}

export interface ErrorVolumeVerdict {
  policy_version: string;
  console: ErrorVolumeChannel;
  requests: RequestVolumeChannel;
}

export declare const ERROR_VOLUME_POLICY_VERSION: string;
export declare const CONSOLE_ERROR_VOLUME_THRESHOLD: number;
export declare const REQUEST_FAILURE_VOLUME_THRESHOLD: number;
export declare const REASON_CONSOLE_VOLUME: string;
export declare const REASON_REQUEST_VOLUME: string;

export declare function classifyErrorVolume(observation: {
  consoleErrors?: string[];
  failedRequests?: FailedRequestLike[];
}): ErrorVolumeVerdict;

export declare function isNavigationCancellation(failure: FailedRequestLike | null): boolean;
