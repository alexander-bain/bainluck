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
}

export interface JourneyArtifact {
  name: string;
  sha256: string;
  bytes?: number;
}

export interface JourneyObservation {
  /** Set when the browser/runner itself broke — never a product verdict. */
  infra?: { crashed: boolean; reason?: string } | null;
  /** true = observed SHA equals requested SHA; null/undefined = unresolved. */
  shaMatch?: boolean | null;
  shaDetail?: string | null;
  expectedPath?: string | null;
  urlPath?: string | null;
  realCardFound?: boolean;
  /** `null` unless a real card was observed — see timing.duration_only_when_observed. */
  firstCardMs?: number | null;
  emptyState?: { name: string; visible: boolean } | null;
  mainRegionNonBlank?: boolean;
  consoleErrors?: string[];
  pageErrors?: string[];
  failedRequests?: FailedRequestSummary[];
  allowedFailures?: string[];
  artifacts?: JourneyArtifact[];
}

export type JourneyResult = "pass" | "fail" | "infra_error" | "superseded";

export declare const RESULTS: {
  PASS: "pass";
  FAIL: "fail";
  INFRA_ERROR: "infra_error";
  SUPERSEDED: "superseded";
};

export declare const TERMINAL_RESULTS: readonly JourneyResult[];

export declare function evaluateJourney(observation: JourneyObservation): {
  result: JourneyResult;
  assertions: JourneyAssertion[];
  checked_clean: string[];
};
