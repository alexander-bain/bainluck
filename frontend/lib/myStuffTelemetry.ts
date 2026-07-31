/**
 * My Stuff first-card telemetry (L2-217 Item 3 / C88).
 *
 * Makes time-to-first-team-card measurable on the web My Stuff surface, under
 * the `my-stuff-first-card/v1` authority contract
 * (`backend/scripts/evals/my_stuff_first_card.py`).
 *
 * Two rules the contract exists to enforce, and this module encodes:
 *   1. **Model assignment is not first render.** A `data_ready` packet reports
 *      when the required feed arrived; a `first_render` packet reports when a
 *      real card actually rendered. The two are separate stages of the same
 *      packet shape so a fast data-ready can never be read as a fast first
 *      paint. A packet that has not rendered reports `first_render_ms: -1`.
 *   2. **First render means a real card.** `first_render_ms` is only ever set
 *      alongside `item_count > 0` — never for an empty success, a cancellation,
 *      a superseded identity, or a required failure.
 *
 * Privacy contract: a packet carries ONLY opaque durations, counts, a coarse
 * cache label, a build tag, and a bounded outcome class. It NEVER carries a
 * uid, email, token, session id, item id, or market text. `-1` marks a stage
 * that did not run or is not measurable from the browser (the same convention
 * the native latency rail uses).
 *
 * Every emit is best-effort: a failure here can never change rendering.
 */

import { trackEvent } from "@/lib/analytics";

/**
 * The bounded outcome classes, mirroring `decide()` in the C88 contract. Web
 * observes a subset of the native ones (there is no native-style in-memory
 * response cache on this surface), but the vocabulary is shared so one query
 * can read both platforms.
 */
export type MyStuffOutcomeClass =
  | "sign_in_required"
  | "network_success"
  | "swr_cache_hit"
  | "empty_success"
  | "partial_success"
  | "required_failure"
  | "identity_superseded"
  | "cancelled";

export type MyStuffCacheOutcome = "hit" | "miss" | "none";

export type MyStuffStage = "data_ready" | "first_render";

/** The C88 packet, plus the stage discriminator. */
export interface MyStuffTelemetry {
  stage: MyStuffStage;
  auth_ready_ms: number;
  network_ms: number;
  backend_elapsed_ms: number;
  decode_ms: number;
  required_data_ready_ms: number;
  first_render_ms: number;
  cache_outcome: MyStuffCacheOutcome;
  cache_age_seconds: number;
  item_count: number;
  app_build: string;
  surface: "my_stuff";
  outcome_class: MyStuffOutcomeClass;
}

/** The 12 attribution fields the C88 contract requires on every packet. */
export const MY_STUFF_REQUIRED_TELEMETRY_FIELDS = [
  "auth_ready_ms",
  "network_ms",
  "backend_elapsed_ms",
  "decode_ms",
  "required_data_ready_ms",
  "first_render_ms",
  "cache_outcome",
  "cache_age_seconds",
  "item_count",
  "app_build",
  "surface",
  "outcome_class",
] as const;

/**
 * A bounded, non-PII build tag so a field trace maps to the deploy it came
 * from. Vercel exposes the commit sha when configured; otherwise a constant.
 * Truncated to 7 chars — enough to identify a deploy, and never user data.
 */
export function webAppBuild(): string {
  const sha = process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA;
  return sha ? sha.slice(0, 7) : "web";
}

/** Clamp a duration to a non-negative integer; `null`/`undefined` → -1. */
function ms(value: number | null | undefined): number {
  if (value == null || !Number.isFinite(value)) return -1;
  return Math.max(0, Math.round(value));
}

export interface MyStuffOutcomeInputs {
  /** A stable principal has resolved for the viewer. */
  identityReady: boolean;
  /** The principal that dispatched the required request, if any. */
  dispatchPrincipal?: string | null;
  /** The principal in effect now. */
  currentPrincipal?: string | null;
  /** State of the REQUIRED (team feed) request. */
  requiredRequest: "not_started" | "success" | "failure" | "cancelled";
  /** State of the OPTIONAL (team futures) request. */
  optionalRequest?: "not_started" | "success" | "failure" | "hung";
  /** Renderable item count from the required response. */
  requiredItemCount: number;
  /** Whether the required payload was served from the SWR cache. */
  fromCache?: boolean;
}

/**
 * Classify a My Stuff load, mirroring the C88 decision core's `outcome_class`.
 *
 * Order matters and is deliberately fail-closed: identity questions are settled
 * BEFORE success is considered, so a response that arrived under a superseded
 * principal is never reported as a success (and, upstream, never rendered).
 */
export function classifyMyStuffOutcome(input: MyStuffOutcomeInputs): MyStuffOutcomeClass {
  if (!input.identityReady) return "sign_in_required";
  if (
    input.dispatchPrincipal != null &&
    input.currentPrincipal != null &&
    input.dispatchPrincipal !== input.currentPrincipal
  ) {
    return "identity_superseded";
  }
  if (input.requiredRequest === "cancelled") return "cancelled";
  if (input.requiredRequest === "not_started") return "sign_in_required";
  if (input.requiredRequest === "failure") return "required_failure";
  if (input.requiredItemCount <= 0) return "empty_success";
  if (input.optionalRequest === "failure" || input.optionalRequest === "hung") {
    return "partial_success";
  }
  return input.fromCache ? "swr_cache_hit" : "network_success";
}

export interface MyStuffTelemetryInputs {
  stage: MyStuffStage;
  outcomeClass: MyStuffOutcomeClass;
  itemCount: number;
  authReadyMs?: number | null;
  networkMs?: number | null;
  backendElapsedMs?: number | null;
  decodeMs?: number | null;
  requiredDataReadyMs?: number | null;
  /** Only ever supplied by the `first_render` stage. */
  firstRenderMs?: number | null;
  cacheOutcome?: MyStuffCacheOutcome;
  cacheAgeSeconds?: number | null;
  appBuild?: string;
}

/**
 * Build the packet. Pure, so the "first render implies a real card" invariant is
 * directly testable.
 *
 * `first_render_ms` is force-cleared to -1 whenever the stage is not
 * `first_render` OR the item count is not positive — so an empty success, a
 * cancellation, a required failure, or a plain model assignment can never
 * report a first-card time, no matter what the caller passes.
 */
export function buildMyStuffTelemetry(input: MyStuffTelemetryInputs): MyStuffTelemetry {
  const itemCount = Math.max(0, Math.round(input.itemCount));
  const rendered = input.stage === "first_render" && itemCount > 0;
  return {
    stage: input.stage,
    auth_ready_ms: ms(input.authReadyMs),
    network_ms: ms(input.networkMs),
    backend_elapsed_ms: ms(input.backendElapsedMs),
    decode_ms: ms(input.decodeMs),
    required_data_ready_ms: ms(input.requiredDataReadyMs),
    first_render_ms: rendered ? ms(input.firstRenderMs) : -1,
    cache_outcome: input.cacheOutcome ?? "none",
    cache_age_seconds: ms(input.cacheAgeSeconds),
    item_count: itemCount,
    app_build: input.appBuild ?? webAppBuild(),
    surface: "my_stuff",
    outcome_class: input.outcomeClass,
  };
}

/**
 * Emit through the existing consent-aware analytics rail. Never throws; returns
 * the packet it emitted so callers/tests can assert on it.
 */
export function reportMyStuffTelemetry(input: MyStuffTelemetryInputs): MyStuffTelemetry | null {
  try {
    const packet = buildMyStuffTelemetry(input);
    trackEvent("my_stuff_load", packet);
    return packet;
  } catch {
    return null;
  }
}
