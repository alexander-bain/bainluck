/** Notice 39 / #4763 — see `agentOrigin.js` for why this rail needed its own carrier. */

/** The wire name, agreeing with `agent_origin.ORIGIN_HEADER`. */
export declare const ORIGIN_HEADER: "x-bainluck-origin";

/** The one value honoured POSITIVELY — it KEEPS the search-log row. */
export declare const ORIGIN_USER: "user";

/** The agent name for this call, or null when nothing may be added. */
export declare function resolveAgent(): string | null;

/** True when `url` points at a host we own (suffix match on the parsed host). */
export declare function isOurHost(url: string): boolean;

/** Headers to ADD so `url` says who sent it. Possibly empty; the caller merges. */
export declare function originHeaders(
  url: string,
  existing?: Record<string, string> | null,
): Record<string, string>;

/** `headers` plus the origin tag — the one-call form for request builders. */
export declare function tagged(
  url: string,
  headers?: Record<string, string> | null,
): Record<string, string>;
