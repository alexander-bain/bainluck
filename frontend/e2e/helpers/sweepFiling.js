"use strict";

/**
 * UX-P029 Item 2 — turn a VALIDATED manifest into filing decisions.
 *
 * This is the pure half of the sweep filer. It never touches the network, never
 * calls GitHub, and never reads a token; the privileged workflow feeds it a
 * manifest and acts on what it returns. Keeping the decision pure is what makes
 * "two concurrent consumers do not duplicate" a testable claim rather than a hope.
 *
 * It mirrors the C182 state machine (`backend/scripts/evals/
 * browser_sweep_filing_contract.py`) exactly — same actions, same refusal codes —
 * because two implementations of one lifecycle that drift are worse than one.
 *
 * The three rules that matter, and why:
 *
 *   1. **UNKNOWN and infrastructure failures never file a product defect.**
 *      A runner that died, an expired artifact, or an untrusted manifest tells
 *      you nothing about the product. Filing "the site is broken" off a broken
 *      runner is how a rail loses its audience — which is the very thing #1598
 *      is about.
 *   2. **A fingerprint must be stable across runs.** It is built from the reason
 *      code + canonical URL + stable identity, and deliberately contains no
 *      counts, timestamps, run ids or SHAs. A fingerprint carrying "2036" files
 *      a fresh issue every night as the number drifts.
 *   3. **Recovery needs CONTINUOUS green.** One clean run after a failure is a
 *      flake as often as a fix, so closing waits for the standing continuous-GREEN
 *      duration.
 */

const CONTINUOUS_GREEN_RUNS_TO_CLOSE = 2;

/** Mirrors C182's `SAFE`: what may appear in a fingerprint at all. */
const SAFE_FINGERPRINT = /^[a-z0-9._:/-]{1,240}$/;

const ACTIONS = Object.freeze({
  FILE: "file",
  COMMENT: "comment",
  COMMENT_CLOSE: "comment_close",
  COMMENT_RECOVERY_PENDING: "comment_recovery_pending",
  NO_OP: "no_op",
  REFUSE: "refuse",
});

/**
 * Assertions that describe the RUNNER, not the product. A failure here is
 * infrastructure: it must never become a product defect issue.
 */
const INFRA_ASSERTIONS = new Set([
  "run.manifest_written",
  "run.runner_completed",
  "build.sha_bound",
]);

/**
 * Canonicalize a URL for fingerprinting: origin + path, with query and fragment
 * dropped. A tournament slug rotates weekly, so a fingerprint keyed on the full
 * query would file a new issue every week for one persistent defect.
 */
function canonicalUrl(url) {
  const text = String(url || "").trim();
  if (!text) return "";
  const match = /^([a-z][a-z0-9+.-]*:\/\/[^/?#]+)([^?#]*)/i.exec(text);
  if (!match) return text.toLowerCase().split(/[?#]/)[0];
  const path = (match[2] || "/").replace(/\/+$/, "") || "/";
  return `${match[1].toLowerCase()}${path}`;
}

/** Lowercase, collapse anything unsafe, so the result always matches SAFE. */
function slug(value, fallback) {
  const text = String(value == null ? "" : value)
    .toLowerCase()
    .replace(/[^a-z0-9._:/-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return text || fallback;
}

/**
 * Build the stable identity of one finding.
 *
 * `reason_code:journey:canonical-url` — the reason code says WHAT broke, the
 * journey says which surface asked, and the canonical URL says where. Nothing
 * volatile is included.
 */
function buildFingerprint(finding) {
  const reason = slug(finding.reason_code || finding.assertion_id, "unknown");
  const journey = slug(finding.journey_id, "unknown");
  const url = slug(canonicalUrl(finding.url), "no-url");
  const fingerprint = `${reason}:${journey}:${url}`.slice(0, 240);
  return SAFE_FINGERPRINT.test(fingerprint) ? fingerprint : null;
}

/**
 * Extract findings from a manifest. One finding per FAILED assertion.
 *
 * Only journeys with a terminal `fail` result contribute product findings;
 * an `infra_error` journey yields an infra finding that cannot be filed.
 */
function findingsFromManifest(manifest) {
  const journeys = Array.isArray(manifest && manifest.journeys) ? manifest.journeys : [];
  const runUrlBase = (manifest && manifest.run && manifest.run.base_url) || "";
  const findings = [];

  for (const journey of journeys) {
    const result = String(journey && journey.result);
    if (result !== "fail" && result !== "infra_error") continue;

    const assertions = Array.isArray(journey.assertions) ? journey.assertions : [];
    for (const a of assertions) {
      if (!a || a.ok !== false) continue;
      // `a.infra` is the third route, added for #1908 M1: a condition that hits
      // SOME assertions of a journey the rest of which is product-graded. The
      // journey-level lever was the wrong instrument for it — using that would
      // have muted `content.main_region_nonblank` on `consent.two_tabs`, i.e.
      // #1909, the one real defect inside thirteen issues of rail noise.
      const isInfra =
        result === "infra_error" || INFRA_ASSERTIONS.has(a.assertion_id) || a.infra === true;
      const finding = {
        journey_id: journey.journey_id,
        project: journey.project,
        assertion_id: a.assertion_id,
        // A stable code when the assertion carries one (the volume checks do);
        // otherwise the assertion id, which is itself stable.
        reason_code: a.reason_code || a.assertion_id,
        detail: a.detail == null ? null : String(a.detail),
        url: journey.url || runUrlBase,
        infra: isInfra,
      };
      finding.fingerprint = buildFingerprint(finding);
      findings.push(finding);
    }
  }
  return findings;
}

/**
 * Decide what to do about ONE fingerprint, given the manifest's trust state and
 * what is already open on the board. Mirrors C182 `evaluate_case`.
 *
 * `state`:
 *   verdict            "FAIL" | "PASS" | "UNKNOWN" | "INFRA"
 *   manifestValid      the validator accepted the manifest
 *   shaBound           the run proved which deployment it graded
 *   fingerprint        stable id (null when it could not be built safely)
 *   artifactExpired    evidence is no longer retrievable
 *   openIssue          an open issue already declares this fingerprint
 *   concurrentClaimLost another consumer won the create race
 *   consecutiveClean   how many CONTINUOUS green runs have been observed
 *   closedPrior        this fingerprint was previously filed and closed
 */
function decide(state) {
  const s = state || {};
  const reasons = [];

  if (!s.manifestValid) reasons.push("MANIFEST_UNTRUSTED");
  if (!s.shaBound) reasons.push("SHA_UNBOUND");
  if (s.fingerprint && !SAFE_FINGERPRINT.test(String(s.fingerprint))) {
    reasons.push("FINGERPRINT_UNSAFE");
  }
  if (s.artifactExpired) reasons.push("ARTIFACT_UNAVAILABLE");

  // Untrusted evidence refuses outright — it neither files nor closes. Acting on
  // a manifest we cannot vouch for is worse than doing nothing, in both
  // directions: a false file spams, a false close hides a live defect.
  if (reasons.length) {
    return { action: ACTIONS.REFUSE, reason_codes: reasons.sort(), new_episode: false };
  }

  const verdict = String(s.verdict || "").toUpperCase();

  if (verdict === "UNKNOWN" || verdict === "INFRA") {
    return { action: ACTIONS.NO_OP, reason_codes: [], new_episode: false };
  }

  if (verdict === "FAIL") {
    // Either an existing issue or a lost create race means COMMENT, never a
    // second issue. That is the whole anti-duplicate rule, and it has to hold
    // for two consumers running at once.
    const action = s.openIssue || s.concurrentClaimLost ? ACTIONS.COMMENT : ACTIONS.FILE;
    return {
      action,
      reason_codes: [],
      new_episode: Boolean(s.closedPrior),
    };
  }

  if (verdict === "PASS") {
    if (s.openIssue) {
      const clean = Number(s.consecutiveClean || 0);
      return {
        action:
          clean >= CONTINUOUS_GREEN_RUNS_TO_CLOSE
            ? ACTIONS.COMMENT_CLOSE
            : ACTIONS.COMMENT_RECOVERY_PENDING,
        reason_codes: [],
        new_episode: false,
      };
    }
    return { action: ACTIONS.NO_OP, reason_codes: [], new_episode: false };
  }

  return { action: ACTIONS.NO_OP, reason_codes: [], new_episode: false };
}

module.exports = {
  ACTIONS,
  CONTINUOUS_GREEN_RUNS_TO_CLOSE,
  SAFE_FINGERPRINT,
  INFRA_ASSERTIONS,
  canonicalUrl,
  buildFingerprint,
  findingsFromManifest,
  decide,
};
