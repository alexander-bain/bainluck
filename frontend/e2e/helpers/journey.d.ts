import type { MainRegionObservation } from "./contentState";
import type { AbortPacket } from "./abortRecord";

export type { MainRegionObservation };

export interface JourneyAssertion {
  assertion_id: string;
  ok: boolean;
  detail: string | null;
}

export interface FailedRequestSummary {
  url: string;
  status?: number | null;
  failure?: string | null;
  method?: string;
  /** L2-241 (#1525 Shape A): present only on an aborted request. */
  abort?: AbortPacket;
}

export interface JourneyArtifact {
  name: string;
  /** Relative to the manifest's directory, under the `artifacts/` root. */
  path: string;
  sha256: string;
  bytes?: number;
}

export interface TelemetryObservation {
  host: string;
  path: string;
  count: number;
}

export interface TelemetryLedgerRule {
  /** Stable id — becomes the `telemetry.<id>` assertion. */
  id: string;
  /** Matches this host or any subdomain of it. */
  hostSuffix?: string;
  /** Literal path prefix. */
  pathPrefix?: string;
  expect: "absent" | "exact" | "at_least";
  /** Required for `exact` / `at_least`. */
  count?: number;
}

export interface TelemetryExpectation {
  rules: TelemetryLedgerRule[];
  /** Minimum observation window before an absence is believed. Default 1000ms. */
  minWindowMs?: number;
  /** Opt out of the exhaustiveness check. Off by default, deliberately. */
  allowUnlisted?: boolean;
}

export interface JourneyObservation {
  /** Set when the browser/runner itself broke — never a product verdict. */
  infra?: { crashed: boolean; reason?: string } | null;
  /** true = observed SHA equals requested SHA; null/undefined = unresolved. */
  shaMatch?: boolean | null;
  shaDetail?: string | null;
  expectedPath?: string | null;
  urlPath?: string | null;
  /** The origin the browser actually landed on. */
  finalOrigin?: string | null;
  /** Allowlist for `finalOrigin`. Omit to skip the check explicitly. */
  canonicalOrigins?: string[];
  redirectChain?: string[];
  /** Max redirect hops before the chain is treated as a defect. Default 3. */
  maxRedirects?: number;
  realCardFound?: boolean;
  /** `null` unless a real card was observed — see timing.duration_only_when_observed. */
  firstCardMs?: number | null;
  emptyState?: { name: string; visible: boolean } | null;
  /**
   * Preferred (L2-239): raw measurements, graded by `classifyMainRegion`.
   * Takes precedence over `mainRegionNonBlank` when both are present.
   */
  mainRegion?: MainRegionObservation | null;
  /** Legacy pre-computed verdict, for surfaces not yet converted. */
  mainRegionNonBlank?: boolean;
  consoleErrors?: string[];
  pageErrors?: string[];
  failedRequests?: FailedRequestSummary[];
  allowedFailures?: string[];
  /** Declared console-error substrings. Undeclared errors still fail, and a
   *  declared allowance that matches nothing fails too. */
  allowedConsoleErrors?: string[];
  artifacts?: JourneyArtifact[];
  /** `"none"` opts a non-feed journey out of the card/empty-state assertion. */
  contentMode?: "card" | "none";
  /** Telemetry destinations actually observed during the journey. */
  telemetry?: TelemetryObservation[];
  /** What the journey claims about telemetry. Absent = not evaluated. */
  telemetryExpectation?: TelemetryExpectation | null;
  /** How long telemetry was watched. Absence is not believed without this. */
  telemetryWindowMs?: number | null;
}

export type JourneyResult = "pass" | "fail" | "infra_error" | "superseded";

export declare const RESULTS: {
  PASS: "pass";
  FAIL: "fail";
  INFRA_ERROR: "infra_error";
  SUPERSEDED: "superseded";
};

export declare const TERMINAL_RESULTS: readonly JourneyResult[];

export declare function classifyMainRegion(input: MainRegionObservation): {
  state: "content" | "loading" | "blank" | "malformed";
  nonBlank: boolean;
  detail: string;
};

export declare function evaluateJourney(observation: JourneyObservation): {
  result: JourneyResult;
  assertions: JourneyAssertion[];
  checked_clean: string[];
};
