/** UX-P029 Item 2 — pure decision layer for the browser-sweep filer (#1598). */

export type SweepAction =
  | "file"
  | "comment"
  | "comment_close"
  | "comment_recovery_pending"
  | "no_op"
  | "refuse";

export interface SweepFinding {
  journey_id: string;
  project: string;
  assertion_id: string;
  /** The assertion's stable `reason_code` when it has one, else its id. */
  reason_code: string;
  detail: string | null;
  url: string;
  /** True when the failure describes the RUNNER, never the product. */
  infra: boolean;
  /** `null` when a safe key could not be built. */
  fingerprint: string | null;
}

export interface SweepDecisionState {
  verdict: "FAIL" | "PASS" | "UNKNOWN" | "INFRA" | string;
  manifestValid?: boolean;
  shaBound?: boolean;
  fingerprint?: string | null;
  artifactExpired?: boolean;
  openIssue?: boolean;
  concurrentClaimLost?: boolean;
  consecutiveClean?: number;
  closedPrior?: boolean;
}

export interface SweepDecision {
  action: SweepAction;
  /** Sorted refusal codes; empty unless `action === "refuse"`. */
  reason_codes: string[];
  /** A defect that returns after its issue was closed. */
  new_episode: boolean;
}

export declare const ACTIONS: Record<string, SweepAction>;
export declare const CONTINUOUS_GREEN_RUNS_TO_CLOSE: number;
export declare const SAFE_FINGERPRINT: RegExp;
export declare const INFRA_ASSERTIONS: Set<string>;

export declare function canonicalUrl(url: string): string;
export declare function buildFingerprint(finding: Partial<SweepFinding>): string | null;
export declare function findingsFromManifest(manifest: unknown): SweepFinding[];
export declare function decide(state: SweepDecisionState): SweepDecision;
