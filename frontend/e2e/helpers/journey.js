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
const { classifyErrorVolume } = require("./errorVolume");
const {
  abortAllowanceMatches,
  firedAllowances,
  allowanceMatch,
  allowanceIsIntermittent,
  allowanceIsInstrumentInduced,
  instrumentAllowancesMissingAftermath,
  isThirdParty,
} = require("./navigationAborts");
const {
  consoleErrorsAreRateLimitEcho,
  describeRateLimit,
  networkFailuresAreSelfInflicted,
} = require("./rateLimit");

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
 * Mark one assertion as describing the RUNNER rather than the product (#1908).
 *
 * The flag rides on the assertion, NOT on the journey, and that is the whole
 * point. `sweepFiling` already had two ways to reach "infra": a whole journey
 * whose result is `infra_error`, and a fixed set of assertion ids. Neither fits
 * a condition that hits SOME assertions of an otherwise product-graded journey —
 * and using the journey-level lever here would have muted
 * `content.main_region_nonblank` on `consent.two_tabs`, which is #1909, the one
 * real defect the whole consent census existed to surface.
 *
 * Still `ok: false`. This does not turn a non-pass into a pass; it says which
 * kind of non-pass it is, so the filer can decline to mint a product issue while
 * the manifest keeps the whole reading.
 */
function markInfra(record, detail) {
  record.infra = true;
  if (detail) record.detail = String(detail);
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

/** Just the origin of a URL, for a bounded, non-revealing exclusion note. */
function originOf(url) {
  try {
    return new URL(String(url)).origin;
  } catch {
    return "(unparseable)";
  }
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * Does an observed telemetry destination match a ledger rule?
 * `hostSuffix` matches the host or any subdomain of it; `pathPrefix` is a
 * literal prefix. A rule with neither matches nothing (a typo must not become
 * a wildcard).
 *
 * #1658 adds `eventName`, and it is the axis the ledger was missing rather than
 * a convenience. `page_view_exactly_once` matched on HOST and counted every GA4
 * `/g/collect` beacon — `page_view` plus `session_start`, `first_visit`,
 * `scroll_depth` and `time_on_page` — then reported the total as page views.
 * Four requests, one page view, and an assertion whose id made a claim its
 * matcher could not make.
 *
 * Note what is NOT the fix: dropping the assertion, or relaxing it to
 * `at_least 1`. The property it protects is real and specific — "the withheld
 * page view is released ONCE, not a replay of the session, and not the
 * double-count the old `gtag('config', …)` re-send caused". Every one-liner
 * shaped like "stop failing on GA noise" deletes that guard, which is the same
 * trap #1908's M1 walked around. Counting the RIGHT population keeps it.
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
  if (rule.eventName) {
    // Strict equality against the recorder's allowlisted value. An observation
    // with no event (a gtag.js script load, a Vercel beacon) never satisfies an
    // event-scoped rule — otherwise narrowing a rule would silently widen it.
    if (observed?.event !== rule.eventName) return false;
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
  //     UX-P095 (ruling 021's instrument-induced carve-out): this branch — and
  //     ONLY this branch — is the "aftermath" the carve-out trades an excused
  //     abort against. The boolean branch below cannot serve: it is a threshold
  //     the spec chose and did not disclose, so it cannot tell a loading region
  //     from a blank one, which is the exact distinction the aftermath turns on.
  let aftermathGraded = false;
  if (o.mainRegion) {
    const region = classifyMainRegion(o.mainRegion);
    aftermathGraded = true;
    assertions.push(
      assertion(
        "content.main_region_nonblank",
        region.nonBlank,
        `${region.state}: ${region.detail}`
      )
    );
  } else if (typeof o.mainRegionNonBlank === "boolean") {
    //     UX-P087 (#1909): the boolean path must NOT state blankness as a fact.
    //
    //     All this branch receives is `true`/`false` from a threshold the spec
    //     chose and did not disclose (the consent pack's is `length > 40`). It
    //     used to report `"main region rendered blank"`, and on run 32009921496
    //     that sentence was simply untrue: the page rendered "Failed to load feed
    //     / Try again" — 29 characters, correct, visible in the run's own
    //     screenshot. The wording sent a P2 to be filed against a blank screen
    //     the app never showed.
    //
    //     This is gotcha #53's shape inside the grader — an emptier reading
    //     asserted as a fact about the world — and the fix is the same one: say
    //     what was actually observed, and name the signal that would settle it.
    //     The VERDICT is unchanged; only the claim it makes about itself is.
    assertions.push(
      assertion(
        "content.main_region_nonblank",
        o.mainRegionNonBlank === true,
        o.mainRegionNonBlank === true
          ? null
          : "the journey's own main-region check returned false — a pre-computed " +
              "boolean, so the threshold and the observed text are NOT visible here. " +
              "This does not establish that the region was blank: a short honest " +
              "state grades the same as an empty one. Read the terminal screenshot, " +
              "and convert the journey to `mainRegion` measurements to make the " +
              "distinction gradeable."
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

  // --- Which SURFACE rendered, not merely how much of it. ---
  //
  //     UX-P057. `route.expected_path` proves the URL and
  //     `content.main_region_nonblank` proves a character count. Neither says
  //     the page is the page: a route that 200s with the wrong surface, a
  //     generic error body, or a shell that never hydrated its subject all
  //     satisfy both — enough characters at the right address.
  //
  //     #1650 is the standing example. `settled_props_verdict` grades a char
  //     count, so the question "does the settled page speak the settled
  //     vocabulary" has been unanswerable in the rail for six cycles.
  //
  //     ONE marker is enough, deliberately. Requiring all of them makes the
  //     assertion a copy of the page's current wording, and it would then fail
  //     on every honest copy edit — a guard nobody believes is worse than no
  //     guard (UX-P053's find). Matching is case-insensitive for the same
  //     reason.
  //
  //     Declared markers with NO observed text is a FAILURE, not a skip. An
  //     unobserved surface is not a proven one — the same rule the main-region
  //     branch above already applies to itself.
  const markers = Array.isArray(o.surfaceMarkers)
    ? o.surfaceMarkers.filter((m) => isNonEmptyString(m))
    : [];
  if (markers.length === 0) {
    checkedClean.push("content.surface_vocabulary (journey declares no surface markers)");
  } else if (!isNonEmptyString(o.surfaceText)) {
    assertions.push(
      assertion(
        "content.surface_vocabulary",
        false,
        `${markers.length} marker(s) declared but no surface text was observed`
      )
    );
  } else {
    const haystack = String(o.surfaceText).toLowerCase();
    const found = markers.filter((m) => haystack.includes(String(m).toLowerCase()));
    assertions.push(
      assertion(
        "content.surface_vocabulary",
        found.length > 0,
        found.length > 0
          ? `matched ${redactText(found[0], { maxLength: 60 })}`
          : `none of ${markers.length} declared marker(s) appeared: ` +
            markers.map((m) => redactText(m, { maxLength: 40 })).join("; ")
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
  const consoleAssertion = assertion(
    "console.no_errors",
    unexpectedConsole.length === 0,
    unexpectedConsole.length === 0
      ? null
      : `${unexpectedConsole.length} console error(s): ${unexpectedConsole
          .slice(0, 3)
          .map((text) => redactText(text, { maxLength: 200 }))
          .join("; ")}`
  );
  // #1908 M1's ECHO. One rate-limit burst surfaces on both channels, and the
  // census mistook the console copies for a fourth mechanism until it read the
  // text. Gated on a 429 having actually been observed on the network channel in
  // THIS journey — "Failed to fetch" is also what a genuinely broken endpoint
  // logs, and without that gate this would reclassify a real outage as
  // infrastructure, which is cry-wolf inverted into a mute button.
  // Reads `o.failedRequests` rather than the `failedRequests` const, which is
  // declared further down for the network channel — the console channel is
  // graded first, and closing over it here is a temporal-dead-zone crash the
  // contract test caught on its first run.
  if (consoleErrorsAreRateLimitEcho(unexpectedConsole, o.failedRequests)) {
    markInfra(
      consoleAssertion,
      `${unexpectedConsole.length} console error(s), all the fetch-failure echo of ` +
        `a self-inflicted 429 in this same journey (#1908 M1): ${unexpectedConsole
          .slice(0, 3)
          .map((text) => redactText(text, { maxLength: 200 }))
          .join("; ")}`
    );
  }
  assertions.push(consoleAssertion);
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

  // UX-P058 (#1610/#1612/#1614). Resource-load console messages are graded on the
  // NETWORK channel, which is the only ledger that can name a URL and scope it to
  // first-party. Say so in the manifest with the count: a check that quietly grades
  // less than its name suggests is how a mute button hides, and this lane has
  // already shipped one coverage number (`surface_vocabulary_coverage`) for exactly
  // that reason. `checked_clean` is the rail's existing word for "considered, not
  // graded here".
  const consoleResourceErrors = Array.isArray(o.consoleResourceErrors)
    ? o.consoleResourceErrors
    : [];
  checkedClean.push(
    `console.resource_errors_graded_on_network (${consoleResourceErrors.length} resource-load ` +
      `message(s); first-party failures are graded by network.no_unexpected_failures)`
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
   *
   * UX-P047 (#1648 P1, Fable ruling): the three helpers this block used to
   * define locally — `allowanceMatch`, `allowanceIsIntermittent` and
   * `abortAllowanceMatches` — are now IMPORTED from `helpers/navigationAborts`,
   * which the volume grader imports too. #1649 had already shared the predicate
   * and the two graders drifted apart anyway, because each still owned its own
   * DECISION built from it. Sharing an ingredient is not sharing a policy.
   */

  // UX-P095 — the carve-out's condition 3, carried explicitly rather than
  // implied. An instrument-induced excuse applies only where this says the
  // aftermath was graded from measurements, and `abortAllowanceMatches` refuses
  // when it is absent, so a future grader that forgets to pass it excuses
  // nothing instead of excusing everything.
  const abortContext = { aftermathGraded };

  // UX-P095 — third-party failures are not graded HERE, and the asymmetry this
  // closes was live: the collector's `response` channel has always recorded a
  // 4xx/5xx only when it is first-party, while its `requestfailed` channel
  // recorded everything. So one ledger held two policies, and run 32177161167
  // failed `consent.grant` on two `google-analytics.com` beacons cancelled at
  // teardown. They stay in the manifest, flagged; they are simply not OUR defect.
  //
  // The VOLUME grader is deliberately left counting them (#1600 was a
  // ~2,000-request Wikipedia fan-out). These two graders answer different
  // questions — "is this one failure a defect" and "is this page fanning out" —
  // and only the first one is about attribution.
  const thirdParty = failedRequests.filter(isThirdParty);
  const unexpected = failedRequests.filter(
    (f) =>
      !isThirdParty(f) &&
      !allowed.has(f && f.url ? f.url : "") &&
      !allowedAborts.some((allowance) =>
        abortAllowanceMatches(f, allowance, abortContext)
      )
  );
  const networkAssertion = assertion(
    "network.no_unexpected_failures",
    unexpected.length === 0,
    unexpected.length === 0
      ? null
      : `${unexpected.length} failed request(s): ${unexpected
          .slice(0, 5)
          .map((f) => `${redactUrl(f.url)} ${f.status ?? f.failure ?? ""}`.trim())
          .join("; ")}`
  );
  // #1908 M1 — the rail throttling itself is not a product finding. Classified,
  // never suppressed: the assertion stays `ok: false` and keeps its URLs, so the
  // manifest still shows exactly what happened; only the FILER declines to mint
  // an issue from it. Requires EVERY unexpected failure to be a first-party 429,
  // so one genuine failure alongside the burst keeps the whole thing graded.
  if (networkFailuresAreSelfInflicted(unexpected)) {
    markInfra(
      networkAssertion,
      `${describeRateLimit(unexpected)} Observed: ${unexpected
        .slice(0, 5)
        .map((f) => `${redactUrl(f.url)} ${f.status}`)
        .join("; ")}`
    );
  }
  assertions.push(networkAssertion);

  // NO SILENT EXCLUSIONS. An exclusion nobody can see is indistinguishable from
  // an absence (gotcha #53), so the count and the origins are recorded even
  // though they are not graded.
  if (thirdParty.length > 0) {
    checkedClean.push(
      `network.third_party_failures_not_graded (${thirdParty.length} excluded: ` +
        `${[...new Set(thirdParty.map((f) => originOf(f && f.url)))].slice(0, 5).join(", ")})`
    );
  }

  // UX-P095 — THE CARVE-OUT MAY NOT BECOME A DELETION (ruling 021, amended).
  //
  // Clause 3 of the amendment says the aftermath is graded, always. A journey
  // that declares an instrument-induced allowance and then hands over no
  // measured main-region observation would get the excuse and grade nothing in
  // its place — the abort excused, the blank region the excuse was traded for
  // never looked at. That is strictly worse than the pre-amendment red.
  //
  // So it is an ASSERTION, not a convention. `abortAllowanceMatches` already
  // refuses the excuse in that state (fail-closed), which keeps the grading
  // correct; this makes the mistake VISIBLE instead of leaving a spec author
  // wondering why their declaration does nothing.
  const orphanInstrumentAllowances = instrumentAllowancesMissingAftermath(
    allowedAborts,
    abortContext
  );
  if (allowedAborts.some(allowanceIsInstrumentInduced)) {
    assertions.push(
      assertion(
        "network.instrument_allowance_has_aftermath",
        orphanInstrumentAllowances.length === 0,
        orphanInstrumentAllowances.length === 0
          ? null
          : "this journey declares an instrument-induced abort allowance but hands " +
              "over no measured main-region observation, so there is no aftermath to " +
              "grade. Ruling 021's carve-out trades the abort FOR the aftermath; " +
              "without one the excuse is a deletion. Pass `mainRegion` measurements " +
              "to journey.finish (the pre-computed boolean does not qualify — it " +
              "cannot tell loading from blank)."
      )
    );
  }

  // UX-P047 (#1648 P1, Fable ruling) — STRICT EXPIRY MOVED TO THE RUN.
  //
  // An allowance nobody can see expire outlives its reason and quietly covers
  // the next failure that happens to match (#1525, L2-235). That property is
  // kept; only its SCOPE moves. A strict allowance may legitimately fire in one
  // journey of a run and not another, so the journey now REPORTS what it
  // declared and what fired, and `unfiredAllowances` grades the union at run
  // level — an allowance that fires NOWHERE in the run is still red.
  //
  // INTERMITTENT allowances are exempt from expiry entirely, as INT-034
  // established with a measurement this lane could not argue with: at one fixed
  // SHA, 2 of 3 runs carried the abort and 1 of 3 carried NONE ANYWHERE. Under a
  // mandatory run-level fire that clean run would go red, so run-level alone is
  // not sufficient for a racy phenomenon — it is only sufficient for a
  // deterministic one that happens to land in a different journey.
  const strictAborts = allowedAborts.filter((a) => !allowanceIsIntermittent(a));
  const fired = firedAllowances(failedRequests, strictAborts, abortContext).map(
    allowanceMatch
  );
  if (strictAborts.length > 0) {
    checkedClean.push(
      `network.declared_allowances_fired (run-level: ${fired.length}/${strictAborts.length} ` +
        `strict allowance(s) fired in this journey; expiry is graded across the run)`
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
  const errorVolume = classifyErrorVolume(o, abortContext);
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

  // #1908 M1 — three-way, not two-way. A journey whose ONLY failing assertions
  // describe the runner did not fail; it could not be checked, and this rail's
  // own `checked: 0 → unknown` rule says those are different facts (gotcha #53).
  // The moment ONE product assertion fails, the journey is a product FAIL again
  // and every finding on it files normally — which is how `consent.two_tabs`
  // keeps reporting #1909's blank main region through a 12 × 429 burst.
  const failing = assertions.filter((a) => !a.ok);
  const result =
    failing.length === 0
      ? RESULTS.PASS
      : failing.every((a) => a.infra === true)
        ? RESULTS.INFRA_ERROR
        : RESULTS.FAIL;
  return {
    result,
    assertions,
    checked_clean: checkedClean,
    // UX-P047 (#1648 P1): reported, not graded, HERE. The run grades the union —
    // an allowance that fires in no journey at all is still red.
    // STRICT allowances only. An intermittent one is exempt from expiry by
    // definition, so recording it here would ask the run to grade a thing the
    // declaration explicitly says is not gradeable.
    declared_navigation_allowances: strictAborts.map(allowanceMatch),
    fired_navigation_allowances: fired,
  };
}

module.exports = {
  RESULTS,
  TERMINAL_RESULTS,
  classifyMainRegion,
  evaluateJourney,
  evaluateTelemetryLedger,
  telemetryRuleMatches,
};
