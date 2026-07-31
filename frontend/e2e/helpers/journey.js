"use strict";

/**
 * L2-221 Item 1 — journey verdicts, as a pure function.
 *
 * The whole point of extracting this is that the false-green cases can be
 * proven mechanically without a browser. The spec feeds this function a real
 * observation; the contract tests feed it a fixture. Same code path, so a
 * fixture that fails here cannot pass in production.
 *
 * The defect this exists to kill (C96 [P1], `discover-latency.spec.ts:77`):
 * a `.catch(() => {})` around the first-card wait, followed by recording an
 * elapsed number unconditionally — a blank render produced a plausible
 * latency and a green run. Here, a missing card with no proven named empty
 * state is a FAIL, and recording a duration for a card that never appeared is
 * itself a failed assertion.
 */

const { redactText, redactUrl } = require("./redaction");

/** Terminal results. Anything else is a bug in the caller. */
const RESULTS = Object.freeze({
  PASS: "pass",
  FAIL: "fail",
  INFRA_ERROR: "infra_error",
  SUPERSEDED: "superseded",
});

const TERMINAL_RESULTS = Object.freeze([
  RESULTS.PASS,
  RESULTS.FAIL,
  RESULTS.INFRA_ERROR,
  RESULTS.SUPERSEDED,
]);

function assertion(id, ok, detail) {
  return { assertion_id: id, ok: Boolean(ok), detail: detail == null ? null : String(detail) };
}

/**
 * @param {any} observation
 * @returns {{ result: string, assertions: Array<{assertion_id: string, ok: boolean, detail: string|null}>, checked_clean: string[] }}
 */
function evaluateJourney(observation) {
  const o = observation || {};
  const assertions = [];
  const checkedClean = [];

  // --- Infrastructure first: a crashed browser is never a product verdict. ---
  if (o.infra && o.infra.crashed) {
    assertions.push(
      assertion("infra.browser_alive", false, redactText(o.infra.reason || "browser crashed"))
    );
    return { result: RESULTS.INFRA_ERROR, assertions, checked_clean: checkedClean };
  }
  assertions.push(assertion("infra.browser_alive", true, null));

  // --- Build authority. Recorded per journey so a mismatch cannot be lost in
  //     a run-level summary nobody reads. ---
  if (o.shaMatch === null || o.shaMatch === undefined) {
    assertions.push(
      assertion("build.frontend_sha_matches", false, "no frontend build authority was resolved")
    );
  } else {
    assertions.push(
      assertion(
        "build.frontend_sha_matches",
        o.shaMatch === true,
        o.shaDetail == null ? null : redactText(o.shaDetail)
      )
    );
  }

  // --- Route identity. ---
  if (o.expectedPath) {
    const actual = o.urlPath || "";
    assertions.push(
      assertion(
        "route.expected_path",
        actual === o.expectedPath,
        `expected ${o.expectedPath}, observed ${redactUrl(actual)}`
      )
    );
  } else {
    checkedClean.push("route.expected_path (journey declares no expected path)");
  }

  // --- Content. A real card, OR a NAMED empty state that was actually seen.
  //     "The page was blank" never satisfies either branch. ---
  const realCard = o.realCardFound === true;
  const empty = o.emptyState || null;
  const namedEmptyProven = Boolean(empty && empty.name && empty.visible === true);
  assertions.push(
    assertion(
      "content.real_card_or_named_empty",
      realCard || namedEmptyProven,
      realCard
        ? "a real (non-skeleton) card was visible"
        : namedEmptyProven
          ? `named empty state rendered: ${redactText(empty.name, { maxLength: 80 })}`
          : empty
            ? `empty state "${redactText(empty.name || "(unnamed)", { maxLength: 80 })}" was declared but not proven visible`
            : "no real card and no named empty state"
    )
  );

  assertions.push(
    assertion(
      "content.main_region_nonblank",
      o.mainRegionNonBlank === true,
      o.mainRegionNonBlank === true ? null : "main region rendered blank"
    )
  );

  // --- The exact false-green guard: a duration may only exist for a card that
  //     was actually found. Recording elapsed time for an absent card is the
  //     C96 [P1] defect, so it is an assertion, not a comment. ---
  const hasDuration = typeof o.firstCardMs === "number";
  assertions.push(
    assertion(
      "timing.duration_only_when_observed",
      realCard ? hasDuration : !hasDuration,
      realCard
        ? hasDuration
          ? null
          : "card was found but no duration recorded"
        : hasDuration
          ? `no card was found, yet firstCardMs=${o.firstCardMs} was recorded`
          : null
    )
  );

  // --- Console / page errors. ---
  const consoleErrors = Array.isArray(o.consoleErrors) ? o.consoleErrors : [];
  assertions.push(
    assertion(
      "console.no_errors",
      consoleErrors.length === 0,
      consoleErrors.length === 0 ? null : `${consoleErrors.length} console error(s)`
    )
  );

  const pageErrors = Array.isArray(o.pageErrors) ? o.pageErrors : [];
  assertions.push(
    assertion(
      "page.no_uncaught_errors",
      pageErrors.length === 0,
      pageErrors.length === 0 ? null : `${pageErrors.length} uncaught page error(s)`
    )
  );

  // --- Network. Same-origin 4xx/5xx and outright request failures. ---
  const failedRequests = Array.isArray(o.failedRequests) ? o.failedRequests : [];
  const allowed = new Set(Array.isArray(o.allowedFailures) ? o.allowedFailures : []);
  const unexpected = failedRequests.filter((f) => !allowed.has(f && f.url ? f.url : ""));
  assertions.push(
    assertion(
      "network.no_unexpected_failures",
      unexpected.length === 0,
      unexpected.length === 0
        ? null
        : `${unexpected.length} failed request(s): ${unexpected
            .slice(0, 5)
            .map((f) => `${redactUrl(f.url)} ${f.status ?? f.failure ?? ""}`.trim())
            .join("; ")}`
    )
  );

  // --- Artifacts. A journey with no evidence is not a proven journey. ---
  const artifacts = Array.isArray(o.artifacts) ? o.artifacts : [];
  assertions.push(
    assertion(
      "evidence.artifacts_present",
      artifacts.length > 0 && artifacts.every((a) => a && a.name && a.sha256),
      artifacts.length === 0 ? "no artifacts recorded" : null
    )
  );

  const result = assertions.every((a) => a.ok) ? RESULTS.PASS : RESULTS.FAIL;
  return { result, assertions, checked_clean: checkedClean };
}

module.exports = { RESULTS, TERMINAL_RESULTS, evaluateJourney };
