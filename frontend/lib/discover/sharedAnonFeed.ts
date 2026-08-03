/**
 * C133 — anonymous cold-work sharing, client side (Queue L2-242).
 *
 * A genuinely first-time, signed-out visitor should reuse Bain Luck's WARM
 * shared anonymous feed instead of minting a session id that forces the backend
 * to build a guaranteed-cold, single-owner `s:<uuid>` cache key. The backend
 * cache key is (`backend/app/routes/feed.py`):
 *     u:<user>              — authenticated (bearer wins; never the shared feed)
 *     s:<session_id>        — signed out WITH an x-session-id → cold, TTL 5s
 *     anon                  — signed out WITHOUT any session id → warm, TTL 60s
 * So the ONLY lever we pull here is whether the FIRST request carries
 * `x-session-id`. Omitting it on the proven-first request routes a fresh visitor
 * to the shared `anon` warm build; everyone else keeps their own session-scoped
 * seen/dismiss/affinity experience.
 *
 * This maps directly onto the backend C133 contract
 * (`backend/scripts/evals/anonymous_cold_sharing_contract.py`):
 *   - a `no_session_anon` response is byte-shareable across first-time visitors;
 *   - `fresh_session_zero_interactions` is NEVER cross-session; and
 *   - unknown interaction authority FAILS CLOSED (`INTERACTION_AUTHORITY_UNKNOWN`).
 *
 * The decision only ever changes WHICH principal a request is attributed to. It
 * never relabels a response, reorders cards, touches ranking / eligibility /
 * freshness, and it never mints or erases the durable session — a suppressed
 * request simply does not read-through-mint one.
 */

/**
 * Whether the device can PROVE it has zero prior interactions. `unknown` means
 * we could not read local storage (private mode / quota / corruption) and must
 * fail closed to the private, session-scoped path.
 */
export type InteractionAuthority = "known_zero" | "known_present" | "unknown";

export type FeedPrincipalMode = "authenticated" | "session" | "shared_anon";

export interface FeedPrincipalInput {
  /** A verified authenticated identity is present (bearer token / signed in). */
  authenticated: boolean;
  /** A durable `bainluck_session_id` already exists in local storage. */
  hasDurableSession: boolean;
  /** Positive proof of prior interaction/seen/dismiss, or `unknown` (fail closed). */
  interactionAuthority: InteractionAuthority;
  /**
   * The reader interacted (swipe / dismiss / thumb / seen) THIS mount, before a
   * durable session id has necessarily been persisted. In-memory evidence still
   * moves the request onto the per-session path.
   */
  hasInMemoryInteraction: boolean;
}

export interface FeedPrincipalDecision {
  mode: FeedPrincipalMode;
  /**
   * When true, the feed fetch MUST omit `x-session-id` and MUST NOT mint a
   * session. True only for a proven first-time, signed-out, zero-interaction
   * request.
   */
  suppressSessionId: boolean;
}

/**
 * The one pure decision. Authenticated identity always wins; any durable or
 * in-memory interaction evidence keeps the request session-scoped; the shared
 * warm feed is allowed ONLY when zero interactions are positively proven for a
 * signed-out visitor with no durable session. Everything else fails closed.
 */
export function decideFeedPrincipal(input: FeedPrincipalInput): FeedPrincipalDecision {
  if (input.authenticated) {
    return { mode: "authenticated", suppressSessionId: false };
  }
  if (input.hasDurableSession || input.hasInMemoryInteraction) {
    return { mode: "session", suppressSessionId: false };
  }
  if (input.interactionAuthority === "known_zero") {
    return { mode: "shared_anon", suppressSessionId: true };
  }
  // "known_present" or "unknown" → private, session-scoped feed (fail closed).
  return { mode: "session", suppressSessionId: false };
}

// ---------------------------------------------------------------------------
// Impure client-state reads. These MIRROR the storage keys owned by the
// writers below; they are stable identifiers (renaming any of them is a data
// migration, not a refactor), so duplicating the literal here is intentional:
//   bainluck_session_id                 — getDiscoverSessionId (discoverInteractions.ts)
//   discover_interaction_profile_v1     — recordDiscoverInteraction (discoverInteractions.ts)
//   discover_dismissed                  — saveDismissed (app/discover/page.tsx)
//   discover_has_swiped                 — swipe-hint dismissal (app/discover/page.tsx)
// ---------------------------------------------------------------------------
const SESSION_STORAGE_KEY = "bainluck_session_id";
const PROFILE_STORAGE_KEY = "discover_interaction_profile_v1";
const DISMISSED_STORAGE_KEY = "discover_dismissed";
const SWIPED_STORAGE_KEY = "discover_has_swiped";

function hasProfileEvidence(raw: string | null): boolean {
  if (!raw) return false;
  try {
    const parsed = JSON.parse(raw) as { categories?: Record<string, unknown> } | null;
    const categories = parsed?.categories;
    return (
      !!categories &&
      typeof categories === "object" &&
      Object.keys(categories).length > 0
    );
  } catch {
    // A malformed profile blob is itself evidence of prior device state we can
    // no longer read cleanly — treat as present (fail closed).
    return true;
  }
}

function hasDismissEvidence(raw: string | null): boolean {
  if (!raw) return false;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) return parsed.length > 0; // legacy array format
    const items = (parsed as { items?: unknown } | null)?.items;
    return Array.isArray(items) && items.length > 0;
  } catch {
    return true; // malformed → present (fail closed)
  }
}

export interface ClientPrincipalState {
  hasDurableSession: boolean;
  interactionAuthority: InteractionAuthority;
}

/**
 * Read the durable session + interaction evidence in ONE bounded try/catch. Any
 * storage failure (private mode, quota, SSR) collapses to
 * `{ hasDurableSession: false, interactionAuthority: "unknown" }`, which the
 * pure decision fails closed on.
 */
export function readClientPrincipalState(): ClientPrincipalState {
  if (typeof window === "undefined") {
    return { hasDurableSession: false, interactionAuthority: "unknown" };
  }
  try {
    const store = window.localStorage;
    const hasDurableSession = !!store.getItem(SESSION_STORAGE_KEY);
    const hasEvidence =
      !!store.getItem(SWIPED_STORAGE_KEY) ||
      hasProfileEvidence(store.getItem(PROFILE_STORAGE_KEY)) ||
      hasDismissEvidence(store.getItem(DISMISSED_STORAGE_KEY));
    return {
      hasDurableSession,
      interactionAuthority: hasEvidence ? "known_present" : "known_zero",
    };
  } catch {
    return { hasDurableSession: false, interactionAuthority: "unknown" };
  }
}

/**
 * Should the feed fetch suppress `x-session-id` (and skip minting) for this
 * request? Returns false whenever the caller is not eligible (e.g. pagination,
 * a non-first request), so all existing call sites keep their exact behavior.
 */
export function resolveSharedAnonSuppression(opts: {
  eligible: boolean;
  authenticated: boolean;
  hasInMemoryInteraction?: boolean;
}): boolean {
  if (!opts.eligible) return false;
  const state = readClientPrincipalState();
  return decideFeedPrincipal({
    authenticated: opts.authenticated,
    hasDurableSession: state.hasDurableSession,
    interactionAuthority: state.interactionAuthority,
    hasInMemoryInteraction: !!opts.hasInMemoryInteraction,
  }).suppressSessionId;
}
