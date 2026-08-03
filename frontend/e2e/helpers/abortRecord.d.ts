/** L2-241 — bounded abort fields for a failed request (#1525 Shape A). */
export interface AbortPacket {
  aborted: true;
  resource_type: string | null;
  /** How far the request got (ms) before aborting; null when unknowable. */
  elapsed_before_abort_ms: number | null;
  is_feed_request: boolean;
  /** Redacted (query values stripped). */
  frame_url: string | null;
}

export interface DescribeAbortInput {
  failureText?: unknown;
  resourceType?: unknown;
  /** Playwright's request.timing() — phase offsets in ms, -1 for unreached. */
  timing?: Record<string, number> | null;
  frameUrl?: unknown;
  isFeed?: unknown;
}

export declare function isAbort(failureText: unknown): boolean;
export declare function boundedMs(value: unknown): number | null;
export declare function describeAbort(input: DescribeAbortInput | null | undefined): AbortPacket | null;
export declare const ABORT_RE: RegExp;
