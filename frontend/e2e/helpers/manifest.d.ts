import type { JourneyAssertion, JourneyArtifact, JourneyResult, FailedRequestSummary } from "./journey";

export declare const SCHEMA_VERSION: "browser-audit/v1";
export declare const REQUIRED_RUN_FIELDS: readonly string[];
export declare const REQUIRED_JOURNEY_FIELDS: readonly string[];
export declare const REQUIRED_RUNTIME_FIELDS: readonly string[];

export interface JourneyRecord {
  journey_id: string;
  project: string;
  viewport: { width: number; height: number } | null;
  url_path: string;
  redirect_chain?: string[];
  selected_fixture_ids?: string[];
  started_at_utc: string;
  finished_at_utc: string;
  duration_ms: number;
  assertions: JourneyAssertion[];
  checked_clean?: string[];
  console_errors: string[];
  page_errors: string[];
  failed_requests: FailedRequestSummary[];
  telemetry_requests?: Array<{ host: string; path: string; count: number }>;
  first_card_ms?: number | null;
  artifacts: JourneyArtifact[];
  attempt: number;
  result: JourneyResult;
}

export interface RunManifest {
  schema_version: string;
  run: {
    run_id: string;
    run_url: string;
    pack: string;
    trigger: string;
    started_at_utc: string;
    started_at_pt: string;
    finished_at_utc: string;
    finished_at_pt: string;
    requested_frontend_sha: string | null;
    observed_frontend_sha: string | null;
    observed_backend_sha: string | null;
    base_url: string;
    final_origin: string | null;
    runtime: { node: string; playwright: string; browser: string; os: string };
    selected_count: number;
    completed_count: number;
    failed_count: number;
    result: JourneyResult;
    superseded_by: string | null;
    notes: string[];
  };
  journeys: JourneyRecord[];
}

export declare function sha256(data: Buffer | string): string;

export declare function stamps(date: Date | string | number): { utc: string; pt: string };

export declare function deriveRunResult(
  journeys: Array<{ result: string }>,
  options?: { superseded?: boolean }
): JourneyResult;

export declare function buildRunManifest(input: {
  runId?: string;
  runUrl?: string;
  pack?: string;
  trigger?: string;
  startedAt?: Date | string | number;
  finishedAt?: Date | string | number;
  requestedFrontendSha?: string | null;
  observedFrontendSha?: string | null;
  observedBackendSha?: string | null;
  baseUrl?: string;
  finalOrigin?: string | null;
  runtime?: { node?: string; playwright?: string; browser?: string; os?: string };
  selectedCount?: number;
  journeys?: JourneyRecord[];
  result?: JourneyResult;
  superseded?: boolean;
  supersededBy?: string | null;
  notes?: string[];
}): RunManifest;

export declare function validateManifest(manifest: unknown): { ok: boolean; errors: string[] };
