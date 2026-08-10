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
const { classifyMainRegion } = require("./contentState");
const { classifyErrorVolume, isNavigationCancellation } = require("./errorVolume");

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

function assertion(id, ok, detail, reasonCode) {
  const record = {
    assertion_id: id,
    ok: Boolean(ok),
    detail: detail == null ? null : String(detail),
  };
  // Only present when a stable code exists. The filer fingerprints on this, so
  // it deliberately carries NO counts — a fingerprint containing "2036" would
  // file a fresh issue every run as the number drifted.
  if (reasonCode) record.reason_code = String(reasonCode);
  return record;
}

/**
 * Record one error-volume channel (UX-P029 Item 3).
 *
 * Under the threshold this is not a pass to be celebrated, it is evidence
 * retained — so it lands in `checked_clean` with its numbers rather than adding
 * another green assertion to every journey.
 */
function volumeAssertion(assertions, checkedClean, id, channel, detail) {
  if (channel.exceeded) {
    assertions.push(
      assertion(
        id,
        false,
        `${detail}; over the ${channel.threshold} threshold (${channel.reason_code})`,
        channel.reason_code
      )
    );
    return;
  }
  checkedClean.push(`${id} (${detail}, threshold ${channel.threshold})`);
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

  // --- Is the main region showing anything, independently of the card hook?
  //
  //     L2-239. A journey may hand this over as measurements (`mainRegion`) or,
  //     for the surfaces that have not been converted, as a pre-computed
  //     boolean. Measurements are strictly better and are preferred when both
  //     are present: the spec then cannot decide its own verdict, and the
  //     ranking of rendered substance over a leftover loading marker lives in
  //     one place the contract fixtures drive. See `helpers/contentState.js`
  //     for the /discover double-skeleton false red this closes.
  //
  //     Note what is NOT consulted here: `realCardFound` and `emptyState`. This
  //     check and `content.real_card_or_named_empty` above must be able to
  //     catch each other's false positive, which they cannot do if they read
  //     the same signal.
  if (o.mainRegion) {
    const region = classifyMainRegion(o.mainRegion);
    assertions.push(
      assertion(
        "content.main_region_nonblank",
        region.nonBlank,
        `${region.state}: ${region.detail}`
      )
    );
  } else if (typeof o.mainRegionNonBlank === "boolean") {
    assertions.push(
      assertion(
        "content.main_region_nonblank",
        o.mainRegionNonBlank === true,
        o.mainRegionNonBlank === true ? null : "main region rendered blank"
      )
    );
  } else {
    // Neither form supplied. That is a caller defect, and it must not read as
    // an absent check — an unobserved region is not a proven one.
    assertions.push(
      assertion(
        "content.main_region_nonblank",
        false,
        "no main-region observation was recorded"
      )
    );
  }

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
  //
  // UX-P043 (#1649). Two graders read this same list and disagreed 7 vs 0 in
  // one manifest: `classifyErrorVolume` excludes navigation teardown and said
  // 0, this assertion counted everything and said 7. The event-page pack was
  // red 4/4 on a page whose own screenshot is healthy, entirely on `?_rsc=`
  // prefetches cancelled by the click the spec itself performs.
  //
  // The correct fix is NOT to widen the filter — #1525 rules that out by name
  // ("never a widened filter") and prescribes the L2-235 shape instead: a
  // DECLARED, named allowance that fails when it stops firing. So a teardown
  // abort is excused only when the journey said in advance that it expected
  // one, and a declaration that matches nothing is itself a failure.
  //
  // Two clauses keep this from becoming the mute button #1525 feared:
  //
  //   - `isNavigationCancellation` is IMPORTED from errorVolume, not re-stated.
  //     One predicate, so the two graders cannot drift apart again — which is
  //     the actual bug being fixed here, not the red.
  //   - A feed request is NEVER excusable. #1525 Shape A is an aborted
  //     `/api/feed` on the landing route, it is a real open defect, and it is
  //     invisible to the backend's own metrics — this rail is the only place it
  //     shows up. A blanket abort filter would have swallowed it silently,
  //     which is the trap this clause exists to avoid.
  //
  // Anything that is not an abort — a 4xx, a 5xx, a DNS failure — is untouched
  // by the declaration and still fails on a declared URL.
  const failedRequests = Array.isArray(o.failedRequests) ? o.failedRequests : [];
  const allowed = new Set(Array.isArray(o.allowedFailures) ? o.allowedFailures : []);
  const allowedAborts = Array.isArray(o.allowedNavigationAborts) ? o.allowedNavigationAborts : [];

  /**
   * An allowance is either a bare substring (STRICT — it must fire, see the
   * staleness check below) or `{ match, intermittent: true, issue }` for a
   * phenomenon MEASURED to be racy.
   *
   * Why the second form exists (INT-034, 2026-08-10). Next cancels an in-flight
   * RSC prefetch when a spec tears down, and whether one is in flight at that
   * instant is a race. Measured on `discover.route [desktop]` at one fixed SHA
   * against production: **2 of 3 runs carried exactly one abort, 1 of 3 carried
   * none** (31428469455 and 31431570162 fired; 31431775245 passed clean).
   *
   * For a racy abort the strict form has no correct setting. Undeclared, the
   * rail reds on the 2-in-3 where it fires; declared-and-strict, the staleness
   * check reds on the 1-in-3 where it does not. That is the same cry-wolf
   * moved to a different third of the runs, not a fix.
   *
   * So `intermittent` relaxes EXACTLY ONE thing — whether the allowance is
   * required to fire — and nothing else. It is still an abort-only, non-feed,
   * substring-scoped allowance, so a 4xx, a 5xx, or a feed request on the same
   * URL fails exactly as before. The declaration must carry an `issue`, so it
   * stays attributable, and L2-235's rule is untouched for every strict
   * allowance in the suite (event-page's `_rsc=` is deterministic at 7-12 per
   * journey and stays strict).
   */
  const allowanceMatch = (a) => (typeof a === "string" ? a : String((a && a.match) || ""));
  const allowanceIsIntermittent = (a) => typeof a === "object" && a !== null && a.intermittent === true;

  /** A declared teardown allowance covers f only if f really is one. */
  const abortAllowanceMatches = (f, allowance) => {
    if (!isNavigationCancellation(f)) return false;
    if (f && f.abort && f.abort.is_feed_request === true) return false;
    if (f && f.isFeedRequest === true) return false;
    const needle = allowanceMatch(allowance);
    if (!needle) return false;
    return String((f && f.url) || "").includes(needle);
  };

  const unexpected = failedRequests.filter(
    (f) =>
      !allowed.has(f && f.url ? f.url : "") &&
      !allowedAborts.some((allowance) => abortAllowanceMatches(f, allowance))
  );
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

  // An allowance nobody can see expire is one that outlives its reason and
  // quietly covers the next failure that happens to match. Same rule the
  // console channel already carries, and the same rule L2-233 put on the
  // lockfile check.
  const strictAborts = allowedAborts.filter((a) => !allowanceIsIntermittent(a));
  if (strictAborts.length > 0) {
    const staleAborts = strictAborts.filter(
      (allowance) => !failedRequests.some((f) => abortAllowanceMatches(f, allowance))
    );
    assertions.push(
      assertion(
        "network.declared_allowances_fired",
        staleAborts.length === 0,
        staleAborts.length === 0
          ? null
          : `${staleAborts.length} declared navigation-abort allowance(s) matched nothing: ` +
              staleAborts.map(allowanceMatch).join("; ")
      )
    );
  } else if (allowedAborts.length > 0) {
    // Every declared allowance is intermittent, so "it did not fire" is not a
    // finding. Recorded rather than silent: an operator must still be able to
    // see that this journey is carrying a relaxed allowance and which one.
    checkedClean.push(
      "network.declared_allowances_fired (all declared allowances are intermittent: " +
        allowedAborts.map((a) => `${allowanceMatch(a)}${a.issue ? ` #${a.issue}` : ""}`).join("; ") +
        ")"
    );
  } else {
    checkedClean.push(
      "network.declared_allowances_fired (journey declares no navigation-abort allowances)"
    );
  }

  // --- Error VOLUME (UX-P029 Item 3 / #1600). ---
  //
  // Computed from the RAW observations, before `allowedFailures` /
  // `allowedConsoleErrors`, and therefore UNWAIVABLE. That is the whole point:
  // the per-error assertions above can be declared away one string at a time,
  // and #1600 — ~2,036 failed requests in a single load — could otherwise be
  // silenced by declaring `en.wikipedia.org` once. An allowance is for a known
  // benign error; it is not a licence to issue two thousand requests.
  //
  // Below the threshold nothing fails here and the counts still ride in the
  // manifest: a small number of errors is evidence, not a verdict.
  const errorVolume = classifyErrorVolume(o);
  volumeAssertion(
    assertions,
    checkedClean,
    "console.error_volume_within_policy",
    errorVolume.console,
    `${errorVolume.console.total} console error(s) (${errorVolume.console.distinct} distinct)`
  );
  volumeAssertion(
    assertions,
    checkedClean,
    "network.failure_volume_within_policy",
    errorVolume.requests,
    `${errorVolume.requests.total} failed request(s) (${errorVolume.requests.distinct} distinct)` +
      (errorVolume.requests.by_origin.length
        ? ` — top origin ${errorVolume.requests.by_origin[0].origin} x${errorVolume.requests.by_origin[0].count}`
        : "")
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
  classifyMainRegion,
  evaluateJourney,
  evaluateTelemetryLedger,
  telemetryRuleMatches,
};
