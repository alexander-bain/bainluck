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

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * Does an observed telemetry destination match a ledger rule?
 * `hostSuffix` matches the host or any subdomain of it; `pathPrefix` is a
 * literal prefix. A rule with neither matches nothing (a typo must not become
 * a wildcard).
 */
function telemetryRuleMatches(rule, observed) {
  const host = String((observed && observed.host) || "");
  const path = String((observed && observed.path) || "");
  let matched = false;
  if (rule.hostSuffix) {
    if (host !== rule.hostSuffix && !host.endsWith(`.${rule.hostSuffix}`)) return false;
    matched = true;
  }
  if (rule.pathPrefix) {
    if (!path.startsWith(rule.pathPrefix)) return false;
    matched = true;
  }
  return matched;
}

/**
 * The consent pack's network ledger (L2-222 Item 3 / #1453).
 *
 * A consent claim is half about what DID happen and half about what did NOT.
 * "Zero analytics requests" is the assertion that matters most after a Decline,
 * and it is also the easiest one to fake: a run that never gave the page a
 * chance to send anything observes zero and reports success. So absence is only
 * accepted alongside a declared, non-trivial observation window — a journey
 * that cannot say how long it watched cannot prove a negative.
 *
 * Rules are exhaustive by default: any observed telemetry destination that no
 * rule mentions fails the journey. Otherwise a new provider could start
 * beaconing after a Decline and every existing rule would still be satisfied.
 */
function evaluateTelemetryLedger(o, assertions, checkedClean) {
  const expectation = o.telemetryExpectation;
  if (!expectation) {
    checkedClean.push("telemetry.ledger (journey declares no telemetry expectation)");
    return;
  }

  const observed = Array.isArray(o.telemetry) ? o.telemetry : [];
  const rules = Array.isArray(expectation.rules) ? expectation.rules : [];

  // Absence needs a window. This is the anti-false-green guard for the whole
  // ledger, so it is asserted before any individual rule.
  const windowMs = typeof o.telemetryWindowMs === "number" ? o.telemetryWindowMs : null;
  const minWindow =
    typeof expectation.minWindowMs === "number" ? expectation.minWindowMs : 1000;
  assertions.push(
    assertion(
      "telemetry.observation_window",
      windowMs !== null && windowMs >= minWindow,
      windowMs === null
        ? "no telemetry observation window was recorded — absence cannot be proven"
        : windowMs >= minWindow
          ? `${windowMs}ms observed (min ${minWindow}ms)`
          : `only ${windowMs}ms observed, below the ${minWindow}ms floor`
    )
  );

  for (const rule of rules) {
    const id = String(rule.id || "unnamed");
    const hits = observed.filter((x) => telemetryRuleMatches(rule, x));
    const count = hits.reduce((n, x) => n + (Number(x.count) || 0), 0);
    let ok;
    let detail;
    if (rule.expect === "absent") {
      ok = count === 0;
      detail = ok
        ? "0 requests, as required"
        : `${count} request(s) to ${hits.map((x) => `${x.host}${x.path}`).join(", ")}`;
    } else if (rule.expect === "exact") {
      const want = Number(rule.count);
      ok = count === want;
      detail = `${count} request(s), expected exactly ${want}`;
    } else if (rule.expect === "at_least") {
      const want = Number(rule.count);
      ok = count >= want;
      detail = `${count} request(s), expected at least ${want}`;
    } else {
      ok = false;
      detail = `unknown expectation "${redactText(String(rule.expect))}"`;
    }
    assertions.push(assertion(`telemetry.${id}`, ok, detail));
  }

  if (expectation.allowUnlisted === true) {
    checkedClean.push("telemetry.no_unlisted_destinations (explicitly allowed)");
    return;
  }
  const unlisted = observed.filter((x) => !rules.some((r) => telemetryRuleMatches(r, x)));
  assertions.push(
    assertion(
      "telemetry.no_unlisted_destinations",
      unlisted.length === 0,
      unlisted.length === 0
        ? null
        : `${unlisted.length} unlisted destination(s): ${unlisted
            .slice(0, 5)
            .map((x) => `${x.host}${x.path}`)
            .join("; ")}`
    )
  );
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

  // --- Origin identity and bounded redirects (L2-223). ---
  //
  // The path alone does not say WHICH site rendered it. A canonical start that
  // redirects to a preview host still lands on `/discover`, and every content
  // assertion below would then be graded against the wrong build. An
  // unbounded redirect chain is the same problem in slow motion, so the hop
  // count is capped rather than merely recorded.
  if (Array.isArray(o.canonicalOrigins) && o.canonicalOrigins.length > 0) {
    const finalOrigin = isNonEmptyString(o.finalOrigin) ? o.finalOrigin : null;
    assertions.push(
      assertion(
        "route.final_origin_canonical",
        finalOrigin !== null && o.canonicalOrigins.includes(finalOrigin),
        finalOrigin === null
          ? "no final origin was resolved"
          : `landed on ${redactUrl(finalOrigin)}`
      )
    );
    const hops = Array.isArray(o.redirectChain) ? o.redirectChain.length : 0;
    const maxHops = Number.isFinite(o.maxRedirects) ? o.maxRedirects : 3;
    assertions.push(
      assertion("route.redirects_bounded", hops <= maxHops, `${hops} redirect(s), max ${maxHops}`)
    );
  } else {
    checkedClean.push("route.final_origin_canonical (journey declares no canonical origins)");
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
  //     "The page was blank" never satisfies either branch.
  //
  //     `contentMode: "none"` exists for journeys whose subject is not the feed
  //     (the consent pack's network-only legs). It is an explicit opt-out, not
  //     a default, so a feed journey cannot quietly acquire it — and the
  //     main-region check below still applies either way, so an opted-out
  //     journey on a blank page still fails. ---
  const contentMode = o.contentMode === "none" ? "none" : "card";
  const realCard = o.realCardFound === true;
  const empty = o.emptyState || null;
  const namedEmptyProven = Boolean(empty && empty.name && empty.visible === true);
  if (contentMode === "none") {
    checkedClean.push("content.real_card_or_named_empty (journey declares no feed content)");
  } else {
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
  }

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
  //
  // L2-235. `allowedConsoleErrors` is the console-channel twin of
  // `allowedFailures`, and it exists because without it the rail cannot grade
  // an error state AT ALL. Chromium emits its own "Failed to load resource: the
  // server responded with a status of 404" for any 4xx subresource, so a
  // journey whose entire subject is "a stale challenge link must render a named
  // not-found state" fails on the console channel even after declaring the 404
  // on the network channel. The choice was a permanently-red journey or no
  // coverage of error states; this is the third option.
  //
  // Two things keep it from becoming a mute button:
  //
  //   - Substring match against a DECLARED string, per journey. There is no
  //     wildcard and no journey-wide suppression; anything undeclared still
  //     fails, which the contract fixtures pin.
  //   - A declared allowance that does NOT fire is itself a failure. Same rule
  //     L2-233 put on the lockfile version check: an allowance nobody can see
  //     expire is one that outlives its reason and quietly covers the next
  //     error that happens to match.
  const consoleErrors = Array.isArray(o.consoleErrors) ? o.consoleErrors : [];
  const allowedConsole = Array.isArray(o.allowedConsoleErrors) ? o.allowedConsoleErrors : [];
  const matchesAllowance = (text, allowance) => String(text).includes(allowance);
  const unexpectedConsole = consoleErrors.filter(
    (text) => !allowedConsole.some((allowance) => matchesAllowance(text, allowance))
  );
  assertions.push(
    assertion(
      "console.no_errors",
      unexpectedConsole.length === 0,
      unexpectedConsole.length === 0
        ? null
        : `${unexpectedConsole.length} console error(s): ${unexpectedConsole
            .slice(0, 3)
            .map((text) => redactText(text, { maxLength: 200 }))
            .join("; ")}`
    )
  );
  if (allowedConsole.length > 0) {
    const stale = allowedConsole.filter(
      (allowance) => !consoleErrors.some((text) => matchesAllowance(text, allowance))
    );
    assertions.push(
      assertion(
        "console.declared_allowances_fired",
        stale.length === 0,
        stale.length === 0
          ? null
          : `${stale.length} declared console allowance(s) matched nothing: ${stale.join("; ")}`
      )
    );
  } else {
    checkedClean.push("console.declared_allowances_fired (journey declares no console allowances)");
  }

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

  // --- Telemetry ledger (L2-222 Item 3 / #1453). ---
  evaluateTelemetryLedger(o, assertions, checkedClean);

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

module.exports = {
  RESULTS,
  TERMINAL_RESULTS,
  evaluateJourney,
  evaluateTelemetryLedger,
  telemetryRuleMatches,
};
