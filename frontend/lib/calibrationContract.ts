// L2-232 — the population-version contract, decided in ONE pure place.
//
// ## Why this exists
//
// `/api/calibration` stamps every payload with a `population_version` (Q297 §3 /
// C111 P2). That string names WHICH POPULATION the numbers were built from —
// which rows are in, which are excluded, which repairs had landed. The page's
// labels ("well-traded", "resolved outcomes", the exclusion reconciliation in
// the methodology section) describe ONE such population. Put this build's labels
// on a payload built under a different one and every number is quietly
// mislabelled: still finite, still plausible, still wrong.
//
// Before this module the web page decoded the version and published it as a data
// attribute for the browser rail — and then rendered the curve regardless. It
// could observe a mismatch; it could not refuse one.
//
// ## Why the compatible set is a LIST, and why it is not the backend's constant
//
// The obvious implementation — one hard-coded expected version, compared for
// equality — is the one that must not be built, and we have the outage to prove
// it. Twice:
//
//   1. BACKEND, 2026-08-02 ~04:35–06:00 UTC. Q299 bumped
//      `CALIBRATION_POPULATION_VERSION` q267 -> q299 and every serve tier
//      re-validates version, so the instant the dyno booted BOTH the live Redis
//      key and the 7-day durable last-good became `wrong_version`. The
//      replacement could not exist until the next hourly precompute. The public
//      page served `no_trustworthy_snapshot` until `dc79c9b4` rolled the
//      constant back. A version bump invalidated the only good copy before its
//      successor existed.
//
//   2. NATIVE, the same day. L2-231 shipped `expectedPopulationVersion = "q299"`
//      into the iOS build. `dc79c9b4` then rolled the SERVER back to q267 — so
//      the app began refusing a perfectly valid payload. The client's own
//      constant, not the data, took the surface down.
//
// Both failures are the same shape: a single expected version, held by one side,
// turns the other side's ordinary change into an outage. So:
//
//   * The set below is a statement about THIS FRONTEND BUILD — "these are the
//     populations my labels honestly describe" — not a mirror of the server's
//     current constant. It can hold several at once, which is what makes a
//     server-side roll-forward or roll-BACK between listed versions a non-event
//     on the client.
//
//   * `frontend/e2e/contract/populationVersion.contract.test.js` fails CI when
//     the backend's constant is not in this list. That is the part that matters:
//     a bump can no longer reach production ahead of the client that has to
//     label it. It turns a dark page into a red build.
//
// ## The rollout order this implies (do not skip a step)
//
//   1. Add the NEW version to `COMPATIBLE_POPULATION_VERSIONS` and ship it,
//      after confirming this page's labels actually describe that population.
//   2. THEN bump `CALIBRATION_POPULATION_VERSION` in the backend.
//
// In that order both versions are acceptable to the client for the whole
// window, so it does not matter whether Vercel or Heroku lands first. Reversed,
// there is a window where the deployed frontend refuses the deployed backend —
// which is failure (2) above, rebuilt.

/**
 * The population contracts THIS BUILD's labels honestly describe.
 *
 * `q267` is the population currently published by
 * `backend/app/tasks/precompute_calibration.py` and the one this page's
 * methodology/exclusion copy was written against.
 *
 * Adding an entry is a claim, not a formality: it asserts that the hero copy,
 * the cohort toggle, the category bar and the "what's included" reconciliation
 * in the methodology section all remain TRUE of the new population. If a bump
 * introduces exclusion classes this page has no field or copy for, the raw ->
 * published drop it explains becomes incomplete, and the honest move is to
 * teach the page first and extend this list second.
 */
export const COMPATIBLE_POPULATION_VERSIONS: readonly string[] = ["q267"];

/**
 * A version token we are willing to read at all: a short, printable
 * slug. Deliberately permissive about WHICH slug (that is the list's job) and
 * strict about SHAPE, so an object, a number or a sentence is caught as a
 * contract break rather than silently compared as a string and rejected as
 * merely "unknown".
 */
const VERSION_TOKEN = /^[a-z0-9][a-z0-9._-]{0,31}$/i;

export type CalibrationContractState =
  /** The payload names a population this build's labels describe. */
  | "match"
  /**
   * The payload does not name a population at all.
   *
   * Rendered, never claimed as verified. Refusing every payload that predates
   * the contract field would be its own dishonesty — and it would hand any
   * older cached copy the power to blank the page. (Same ruling as native's
   * `.unverified`, L2-231.)
   */
  | "unverified"
  /** Something is there, but it is not a version. We cannot check it, so we refuse. */
  | "malformed"
  /** A real version, and not one this build can label. */
  | "incompatible";

export interface CalibrationContractDecision {
  state: CalibrationContractState;
  /**
   * May the page put its current labels on these numbers?
   *
   * The single question this module exists to answer. `false` means render an
   * explicit refusal — never a blank page, and never the curve.
   */
  render: boolean;
  /** The version the server declared, verbatim, or `""` when it declared none. */
  servedVersion: string;
  /**
   * Backend-authorized degradation: the server told us this is a dated
   * last-good copy (`cache.status === "stale"`), so the page owes the reader a
   * dated banner.
   *
   * Only ever `true` when `render` is `true`. A refused artifact does not get a
   * "here is a slightly old snapshot" frame around numbers we will not stand
   * behind — that would read as a minor caveat on a major refusal. This
   * ordering is the "poison ordering" case: refusal outranks degradation.
   */
  degraded: boolean;
  /**
   * Whether that degraded copy carries a build date. An undated stale payload
   * still banners (dropping the banner would lose the honesty signal entirely),
   * but it cannot say WHEN, and the rail should be able to see the difference.
   */
  degradedDated: boolean;
}

/** The shape this module needs. Deliberately narrower than `CalibrationData`. */
export interface CalibrationContractInput {
  population_version?: unknown;
  cache?: { status?: unknown; generated_at?: unknown } | null;
}

/**
 * Decide, from a served payload, whether the page may label it.
 *
 * Pure and total: every input — including `null`, a payload with a numeric
 * version, or one with a `cache` block of the wrong shape — produces a
 * decision. Nothing here throws, because the caller is a render path and an
 * exception there is the blank page this queue exists to prevent.
 */
export function decideCalibrationContract(
  data: CalibrationContractInput | null | undefined,
): CalibrationContractDecision {
  const raw = data?.population_version;

  // Order matters, and this is the order:
  //
  //   malformed -> unverified -> incompatible -> match
  //
  // Type first, because a non-string can never be compared against the list
  // meaningfully; absence second, because absence is a legitimate older payload
  // and not a break; membership last.
  let state: CalibrationContractState;
  let servedVersion = "";

  if (raw === undefined || raw === null) {
    state = "unverified";
  } else if (typeof raw !== "string") {
    // A number, object or array here means the server said something about its
    // population that we could not read. That is a contract break, not an old
    // payload, and it is the one case where "say nothing" and "say gibberish"
    // must be graded differently.
    state = "malformed";
  } else if (raw.trim() === "") {
    // An empty string carries no claim. Treated as absence, not as gibberish —
    // it is what a `?? ""` upstream produces, and refusing on it would let a
    // serialization quirk blank the page.
    state = "unverified";
  } else {
    servedVersion = raw.trim();
    if (!VERSION_TOKEN.test(servedVersion)) {
      state = "malformed";
    } else if (COMPATIBLE_POPULATION_VERSIONS.includes(servedVersion)) {
      state = "match";
    } else {
      // Older-and-dropped or newer-and-unknown are the same fact from here: a
      // real population whose labels this build cannot vouch for. They are NOT
      // distinguished, deliberately — treating "future" as safe would re-create
      // the failure this module documents, and treating it as a distinct user-
      // facing state would be jargon without a decision attached.
      state = "incompatible";
    }
  }

  const render = state === "match" || state === "unverified";

  // Degradation is the SERVER's call, never inferred. `cache.status === "stale"`
  // is the only authorization; anything else renders as current because that is
  // what it is.
  const cacheStatus = data?.cache?.status;
  const degraded = render && cacheStatus === "stale";
  const generatedAt = data?.cache?.generated_at;
  const degradedDated =
    degraded && typeof generatedAt === "string" && generatedAt.trim() !== "";

  return { state, render, servedVersion, degraded, degradedDated };
}

/**
 * The one refusal message, shared by `malformed` and `incompatible`.
 *
 * Both are the same fact to a reader — we cannot confirm this page's
 * descriptions match the data — and the distinction between them is diagnostic,
 * not editorial, so it is published as a data attribute rather than spent on
 * copy. Deliberately:
 *
 *   * no version string, which is unexplained jargon to everyone outside this
 *     repo (native's L2-231 wording printed both versions and is corrected to
 *     match this);
 *   * no "try again" invitation, because retrying the same build cannot fix it;
 *     recovery is a republish or a redeploy, and SWR's own 5-minute poll picks
 *     either up without the reader doing anything.
 */
export const CONTRACT_REFUSAL_MESSAGE =
  "We're not showing calibration numbers right now — we can't confirm this " +
  "page's descriptions match the data the server sent, and labelling them " +
  "wrong would be worse than not showing them. The page updates " +
  "automatically; please check back shortly.";
