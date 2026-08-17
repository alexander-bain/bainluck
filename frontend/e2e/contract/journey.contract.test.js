"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const { evaluateJourney } = require("../helpers/journey");

/**
 * L2-221 Item 1 — the false-green fixtures.
 *
 * These drive the SAME evaluator the live specs use, with no browser and no
 * network, so a fixture proven to fail here cannot pass in production.
 *
 * They run on `node --test` — no Playwright, no browser download, no registry
 * — deliberately. A gate that only runs when a package install succeeds is a
 * gate that will be skipped on the day it matters.
 */

const SHA_A = "a".repeat(40);

/** A journey that should be, and stays, green. Every fixture mutates this. */
function healthy(overrides = {}) {
  return {
    infra: null,
    shaMatch: true,
    shaDetail: "frontend deployment matches the requested sha",
    expectedPath: "/discover",
    urlPath: "/discover",
    realCardFound: true,
    firstCardMs: 1234,
    emptyState: null,
    mainRegionNonBlank: true,
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    artifacts: [{ name: "terminal.png", sha256: "b".repeat(64) }],
    ...overrides,
  };
}

function failedIds(observation) {
  return evaluateJourney(observation)
    .assertions.filter((a) => !a.ok)
    .map((a) => a.assertion_id);
}

describe("journey evaluator — the control", () => {
  it("a healthy journey passes", () => {
    const verdict = evaluateJourney(healthy());
    assert.equal(verdict.result, "pass");
    assert.ok(verdict.assertions.every((a) => a.ok));
  });

  it("is not vacuous — the control carries real assertions", () => {
    // Guards against the evaluator degrading to "no checks, all green".
    const ids = evaluateJourney(healthy()).assertions.map((a) => a.assertion_id);
    assert.ok(ids.includes("content.real_card_or_named_empty"));
    assert.ok(ids.includes("build.frontend_sha_matches"));
    assert.ok(ids.includes("network.no_unexpected_failures"));
    assert.ok(ids.length >= 8, `expected >= 8 assertions, got ${ids.length}`);
  });
});

describe("false-green fixtures — every one of these must FAIL", () => {
  it("blank DOM: no card, no empty state", () => {
    const observation = healthy({ realCardFound: false, firstCardMs: null, mainRegionNonBlank: false });
    assert.equal(evaluateJourney(observation).result, "fail");
    const ids = failedIds(observation);
    assert.ok(ids.includes("content.real_card_or_named_empty"));
    assert.ok(ids.includes("content.main_region_nonblank"));
  });

  it("UX-P087 (#1909): the BOOLEAN path must not claim the region was blank", () => {
    // The verdict stays FAIL — that part was always right. What was wrong is the
    // sentence attached to it. All this path receives is a boolean derived from
    // a threshold the spec chose and did not disclose, and it reported
    // "main region rendered blank" as a fact. On run 32009921496 that sentence
    // was untrue: Discover had rendered "Failed to load feed / Try again", 29
    // characters against the consent pack's `> 40`. A P2 was filed against a
    // blank screen the app never showed.
    //
    // Gotcha #53's shape inside the grader: the emptier of two readings stated
    // as a finding. The detail must describe what was OBSERVED (a false boolean)
    // and name the signal that would settle it.
    const observation = healthy({ mainRegionNonBlank: false });
    const check = evaluateJourney(observation).assertions.find(
      (a) => a.assertion_id === "content.main_region_nonblank"
    );
    assert.equal(check.ok, false, "the verdict must still be a failure");
    assert.ok(
      !/rendered blank/i.test(check.detail),
      `the boolean path must not assert blankness it cannot observe — got: ${check.detail}`
    );
    assert.ok(
      /mainRegion/.test(check.detail),
      "the detail must name the measurement form that would make this gradeable"
    );
  });

  it("the MEASUREMENT path may say 'blank' — because it discloses the numbers", () => {
    // The other direction, so the fixture above cannot be satisfied by banning
    // the word everywhere. `classifyMainRegion` states the observation
    // ("N chars of content (min M)"), so its wording is a measurement, not a
    // guess — and a reader can check it.
    const observation = healthy({
      mainRegion: { textLength: 3, skeletonTextLength: 0, visibleSkeletonCount: 0 },
    });
    const check = evaluateJourney(observation).assertions.find(
      (a) => a.assertion_id === "content.main_region_nonblank"
    );
    assert.equal(check.ok, false);
    assert.ok(/chars of content/.test(check.detail), `expected disclosed counts, got: ${check.detail}`);
  });

  it("THE C96 P1 REGRESSION: a duration recorded for a card that never appeared", () => {
    // The exact old-spec behaviour — `.catch(() => {})` then record
    // `Date.now() - t0` anyway. It must fail on BOTH counts.
    const observation = healthy({ realCardFound: false, firstCardMs: 4210 });
    assert.equal(evaluateJourney(observation).result, "fail");
    const ids = failedIds(observation);
    assert.ok(ids.includes("timing.duration_only_when_observed"));
    assert.ok(ids.includes("content.real_card_or_named_empty"));
  });

  it("console error", () => {
    const observation = healthy({ consoleErrors: ["TypeError: x is not a function"] });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("console.no_errors"));
  });

  it("uncaught page error", () => {
    const observation = healthy({ pageErrors: ["ReferenceError: boom"] });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("page.no_uncaught_errors"));
  });

  it("failed request", () => {
    const observation = healthy({
      failedRequests: [{ url: "https://www.bainluck.com/api/feed", status: 500 }],
    });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("network.no_unexpected_failures"));
  });

  it("wrong SHA", () => {
    const observation = healthy({ shaMatch: false, shaDetail: `frontend deployment is ${SHA_A}` });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("build.frontend_sha_matches"));
  });

  it("missing SHA — an unresolved authority is a failure, not a skip", () => {
    for (const value of [null, undefined]) {
      const observation = healthy({ shaMatch: value });
      assert.equal(evaluateJourney(observation).result, "fail");
      assert.ok(failedIds(observation).includes("build.frontend_sha_matches"));
    }
  });

  it("missing artifact", () => {
    assert.ok(failedIds(healthy({ artifacts: [] })).includes("evidence.artifacts_present"));
    assert.ok(
      failedIds(healthy({ artifacts: [{ name: "terminal.png", sha256: "" }] })).includes(
        "evidence.artifacts_present"
      )
    );
  });

  it("an empty state that was DECLARED but not seen is not proof", () => {
    const observation = healthy({
      realCardFound: false,
      firstCardMs: null,
      emptyState: { name: "You're all caught up", visible: false },
    });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("content.real_card_or_named_empty"));
  });

  it("an UNNAMED empty state is not proof either", () => {
    const observation = healthy({
      realCardFound: false,
      firstCardMs: null,
      emptyState: { name: "", visible: true },
    });
    assert.equal(evaluateJourney(observation).result, "fail");
  });

  it("wrong route", () => {
    const observation = healthy({ expectedPath: "/discover", urlPath: "/login" });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("route.expected_path"));
  });
});

describe("legitimate outcomes", () => {
  it("a NAMED empty state that was actually visible passes", () => {
    const verdict = evaluateJourney(
      healthy({
        realCardFound: false,
        firstCardMs: null,
        emptyState: { name: "You're all caught up", visible: true },
      })
    );
    assert.equal(verdict.result, "pass");
  });

  it("a crashed browser is infra_error, never a product fail", () => {
    const verdict = evaluateJourney(
      healthy({ infra: { crashed: true, reason: "page crashed" }, realCardFound: false })
    );
    assert.equal(verdict.result, "infra_error");
  });

  it("an explicitly allowed failure does not fail the journey", () => {
    const url = "https://www.bainluck.com/api/known-404";
    const verdict = evaluateJourney(
      healthy({ failedRequests: [{ url, status: 404 }], allowedFailures: [url] })
    );
    assert.equal(verdict.result, "pass");
  });
});

/**
 * L2-235 — declared console allowances.
 *
 * A journey whose subject IS an error state (a stale challenge link must render
 * a named not-found page) provokes a 4xx on purpose. Chromium then logs its own
 * "Failed to load resource" message, so declaring the request on the network
 * channel is not enough and the journey is permanently red on the console one.
 *
 * The allowance is narrow in both directions, and these fixtures are what keep
 * it that way.
 */
describe("declared console allowances", () => {
  const CHROMIUM_404 = "Failed to load resource: the server responded with a status of 404 ()";
  const DECLARED = "Failed to load resource: the server responded with a status of 404";

  it("a declared console error does not fail the journey", () => {
    const verdict = evaluateJourney(
      healthy({ consoleErrors: [CHROMIUM_404], allowedConsoleErrors: [DECLARED] })
    );
    assert.equal(verdict.result, "pass");
  });

  it("an UNDECLARED error still fails, even alongside a declared one", () => {
    // The hazard being closed: one legitimate allowance turning into a blanket
    // mute for whatever else the page happened to log.
    const ids = failedIds(
      healthy({
        consoleErrors: [CHROMIUM_404, "TypeError: x is not a function"],
        allowedConsoleErrors: [DECLARED],
      })
    );
    assert.ok(ids.includes("console.no_errors"));
  });

  it("a declared allowance that matches NOTHING fails", () => {
    // Same rule L2-233 put on the lockfile version check. An allowance nobody
    // can see expire outlives its reason and silently covers the next error
    // that happens to match it.
    const ids = failedIds(healthy({ consoleErrors: [], allowedConsoleErrors: [DECLARED] }));
    assert.ok(ids.includes("console.declared_allowances_fired"));
  });

  it("declaring nothing leaves the original behaviour exactly as it was", () => {
    const ids = failedIds(healthy({ consoleErrors: ["TypeError: x is not a function"] }));
    assert.ok(ids.includes("console.no_errors"));
    assert.ok(!ids.includes("console.declared_allowances_fired"));

    // And a clean journey does not acquire a new assertion it must satisfy.
    const clean = evaluateJourney(healthy());
    assert.equal(clean.result, "pass");
    assert.ok(
      clean.checked_clean.some((c) => c.startsWith("console.declared_allowances_fired")),
      "an undeclared journey must record the allowance check as checked-clean"
    );
  });

  it("the allowance is a substring of the observed error, not the reverse", () => {
    // A short declaration must not be satisfiable by an unrelated long error,
    // and a long declaration must not match a short error that merely prefixes
    // it — the direction matters, so it is pinned.
    const ids = failedIds(
      healthy({ consoleErrors: ["404"], allowedConsoleErrors: [DECLARED] })
    );
    assert.ok(ids.includes("console.no_errors"));
    assert.ok(ids.includes("console.declared_allowances_fired"));
  });
});

/**
 * UX-P043 (#1649) — declared navigation-abort allowances.
 *
 * The event-page pack failed 4/4 on its first dispatch (runs 31355571532 and
 * 31356326468) against a page whose own screenshot is healthy, entirely on
 * `?_rsc=` prefetches that the spec's own click cancelled. The same manifest
 * graded the same list twice and disagreed: `classifyErrorVolume` excluded
 * teardown and reported 0, this assertion counted everything and reported 7.
 *
 * The fixture below IS that payload, copied from run 31356326468's manifest
 * (`event.page.probability` / desktop), so the before/after is measured rather
 * than imagined.
 *
 * #1525 forbids the shortcut — "never a widened filter" — so the allowance is
 * declared, scoped, and expiring. Each half is pinned below, in both
 * directions.
 */
const RSC_TEARDOWN = [
  {
    url: "https://www.bainluck.com/sport/soccer/mls?_rsc=[redacted-value]",
    method: "GET",
    status: null,
    failure: "net::ERR_ABORTED",
    abort: {
      aborted: true,
      resource_type: "fetch",
      elapsed_before_abort_ms: 78,
      is_feed_request: false,
      frame_url: "https://www.bainluck.com/sports",
    },
  },
  {
    url: "https://www.bainluck.com/events/15191121?_rsc=[redacted-value]",
    method: "GET",
    status: null,
    failure: "net::ERR_ABORTED",
    abort: {
      aborted: true,
      resource_type: "fetch",
      elapsed_before_abort_ms: 159,
      is_feed_request: false,
      frame_url: "https://www.bainluck.com/sports",
    },
  },
];

describe("declared navigation-abort allowances (UX-P043 / #1649)", () => {
  it("BEFORE: teardown aborts fail when nothing is declared", () => {
    const observation = healthy({ failedRequests: RSC_TEARDOWN });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("network.no_unexpected_failures"));
  });

  it("AFTER: the same payload passes once the journey declares it", () => {
    const observation = healthy({
      failedRequests: RSC_TEARDOWN,
      allowedNavigationAborts: ["_rsc="],
    });
    const verdict = evaluateJourney(observation);
    assert.equal(verdict.result, "pass", JSON.stringify(failedIds(observation)));
  });

  it("an aborted /api/feed is NEVER excused — #1525 Shape A stays graded", () => {
    // The trap this clause exists to avoid: a blanket abort filter would have
    // silently swallowed the one abort that is a real open defect, and one the
    // backend's own metrics cannot see.
    const observation = healthy({
      failedRequests: [
        {
          url: "https://api.bainluck.com/api/feed?limit=[redacted-value]&_rsc=[redacted-value]",
          method: "GET",
          status: null,
          failure: "net::ERR_ABORTED",
          abort: {
            aborted: true,
            resource_type: "fetch",
            elapsed_before_abort_ms: 12,
            is_feed_request: true,
            frame_url: "https://www.bainluck.com/",
          },
        },
      ],
      allowedNavigationAborts: ["_rsc="],
    });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("network.no_unexpected_failures"));
  });

  it("a 5xx on a declared URL still fails — the allowance covers aborts only", () => {
    const observation = healthy({
      failedRequests: [
        {
          url: "https://www.bainluck.com/events/15191121?_rsc=[redacted-value]",
          method: "GET",
          status: 500,
          failure: null,
        },
      ],
      allowedNavigationAborts: ["_rsc="],
    });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("network.no_unexpected_failures"));
  });

  it("an UNDECLARED teardown abort still fails", () => {
    const observation = healthy({
      failedRequests: RSC_TEARDOWN,
      allowedNavigationAborts: ["/some/other/path"],
    });
    assert.equal(evaluateJourney(observation).result, "fail");
    assert.ok(failedIds(observation).includes("network.no_unexpected_failures"));
  });

  /**
   * UX-P047 (#1648 P1, Fable ruling) — expiry MOVED from the journey to the run.
   *
   * It did not go away. An allowance that fires nowhere in the run is still red;
   * see manifest.contract.test.js, which grades the union. What changed is the
   * scope, because a Next viewport prefetch is racy: `discover-smoke` never
   * clicks, and desktop saw the abort while mobile saw none IN THE SAME RUN.
   * Failing the journey that happened not to see one converts a flaky red into a
   * different flaky red.
   */
  it("a declared allowance matching nothing no longer fails the JOURNEY — the run grades expiry", () => {
    const observation = healthy({
      failedRequests: [],
      allowedNavigationAborts: ["_rsc="],
    });
    const verdict = evaluateJourney(observation);
    assert.equal(verdict.result, "pass", JSON.stringify(failedIds(observation)));
    assert.deepEqual(verdict.declared_navigation_allowances, ["_rsc="]);
    assert.deepEqual(verdict.fired_navigation_allowances, [], "nothing fired here, and it says so");
  });

  it("a journey that DID see the abort reports it as fired, so the run can tell", () => {
    const verdict = evaluateJourney(
      healthy({ failedRequests: RSC_TEARDOWN, allowedNavigationAborts: ["_rsc="] })
    );
    assert.deepEqual(verdict.declared_navigation_allowances, ["_rsc="]);
    assert.deepEqual(verdict.fired_navigation_allowances, ["_rsc="]);
  });

  it("an aborted /api/feed does NOT count as firing an allowance", () => {
    // Otherwise Shape A could keep an expiring allowance alive — the one abort
    // that must never be excused would be the thing preserving the excuse.
    const verdict = evaluateJourney(
      healthy({
        failedRequests: [
          {
            url: "https://api.bainluck.com/api/feed?_rsc=[redacted-value]",
            failure: "net::ERR_ABORTED",
            abort: { aborted: true, is_feed_request: true },
          },
        ],
        allowedNavigationAborts: ["_rsc="],
      })
    );
    assert.deepEqual(verdict.fired_navigation_allowances, []);
    assert.equal(verdict.result, "fail");
  });

  it("declaring nothing records the check as clean rather than silently skipping it", () => {
    const verdict = evaluateJourney(healthy());
    assert.ok(
      verdict.checked_clean.some((c) => c.startsWith("network.declared_allowances_fired")),
      JSON.stringify(verdict.checked_clean)
    );
  });

  describe("a MEASURED-intermittent allowance (INT-034) — relaxes one thing, only one", () => {
    // Measured on discover.route [desktop] at one fixed SHA: 2 of 3 runs
    // carried the abort, 1 of 3 did not. A strict declaration reds the clean
    // run; no declaration reds the other two. Both are the same false alarm.
    const INTERMITTENT = { match: "_rsc=", issue: 1525, intermittent: true };

    it("excuses the abort when it FIRES, exactly like the strict form", () => {
      const observation = healthy({
        failedRequests: RSC_TEARDOWN,
        allowedNavigationAborts: [INTERMITTENT],
      });
      assert.equal(
        evaluateJourney(observation).result,
        "pass",
        JSON.stringify(failedIds(observation))
      );
    });

    it("does NOT fail when it matches nothing — the whole point", () => {
      const observation = healthy({
        failedRequests: [],
        allowedNavigationAborts: [INTERMITTENT],
      });
      const verdict = evaluateJourney(observation);
      assert.equal(verdict.result, "pass", JSON.stringify(failedIds(observation)));
      assert.ok(
        !failedIds(observation).includes("network.declared_allowances_fired"),
        "an intermittent allowance that did not fire is not a finding"
      );
    });

    it("a STRICT allowance that matches nothing is graded at RUN level — L2-235 intact, relocated", () => {
      // The rule this relaxes for one declaration must be unchanged for the
      // rest. event-page's `_rsc=` is deterministic and stays strict.
      //
      // UX-P047 (#1648 P1, Fable ruling): a strict allowance may legitimately
      // fire in ONE journey of a run and not another, so the journey no longer
      // fails on its own — it REPORTS, and `deriveRunResult` reds the run when
      // the allowance fired nowhere. See manifest.contract.test.js, which owns
      // the red. Nothing is excused: firing nowhere is still a failure, one
      // scope up.
      const observation = healthy({
        failedRequests: [],
        allowedNavigationAborts: ["_rsc="],
      });
      const verdict = evaluateJourney(observation);
      assert.equal(verdict.result, "pass", JSON.stringify(failedIds(observation)));
      assert.deepEqual(verdict.declared_navigation_allowances, ["_rsc="]);
      assert.deepEqual(verdict.fired_navigation_allowances, []);
    });

    it("an INTERMITTENT allowance is exempt from expiry entirely — the run must not grade it", () => {
      // INT-034 measured 1 run in 3 with NO abort anywhere, so a mandatory
      // run-level fire would red that clean run. Recording it as declared would
      // ask the run to grade exactly the thing the declaration says is racy.
      const verdict = evaluateJourney(
        healthy({
          failedRequests: [],
          allowedNavigationAborts: [{ match: "_rsc=", issue: 1525, intermittent: true }],
        })
      );
      assert.equal(verdict.result, "pass");
      assert.deepEqual(verdict.declared_navigation_allowances, []);
    });

    it("stays VISIBLE — a relaxed allowance is recorded, never silent", () => {
      const verdict = evaluateJourney(
        healthy({ failedRequests: [], allowedNavigationAborts: [INTERMITTENT] })
      );
      assert.ok(
        verdict.checked_clean.some(
          (c) => c.includes("intermittent") && c.includes("#1525")
        ),
        JSON.stringify(verdict.checked_clean)
      );
    });

    it("an aborted /api/feed is STILL never excused by the relaxed form", () => {
      // Shape A stays graded. `intermittent` relaxes staleness and nothing else.
      const observation = healthy({
        failedRequests: [
          {
            url: "https://api.bainluck.com/api/feed?limit=20&_rsc=x",
            method: "GET",
            status: null,
            failure: "net::ERR_ABORTED",
            abort: { aborted: true, is_feed_request: true },
          },
        ],
        allowedNavigationAborts: [INTERMITTENT],
      });
      assert.equal(evaluateJourney(observation).result, "fail");
      assert.ok(failedIds(observation).includes("network.no_unexpected_failures"));
    });

    it("a 5xx on the same URL is STILL not an abort and still fails", () => {
      const observation = healthy({
        failedRequests: [
          {
            url: "https://www.bainluck.com/futures/108445?_rsc=x",
            method: "GET",
            status: 503,
            failure: null,
          },
        ],
        allowedNavigationAborts: [INTERMITTENT],
      });
      assert.equal(evaluateJourney(observation).result, "fail");
      assert.ok(failedIds(observation).includes("network.no_unexpected_failures"));
    });
  });

  it("the two graders now agree on the same input", () => {
    // The actual bug: one predicate, read by one grader. If these ever disagree
    // again the rail is back to being red on a healthy page.
    const observation = healthy({
      failedRequests: RSC_TEARDOWN,
      allowedNavigationAborts: ["_rsc="],
    });
    const verdict = evaluateJourney(observation);
    const network = verdict.assertions.find((a) => a.assertion_id === "network.no_unexpected_failures");
    assert.equal(network.ok, true);
    assert.ok(
      verdict.checked_clean.some((c) => c.includes("network.failure_volume_within_policy")),
      JSON.stringify(verdict.checked_clean)
    );
  });
});
