"use strict";

/**
 * UX-P029 Item 2 — the sweep filer's decision layer.
 *
 * Pins the queue's acceptance: a seeded failure files/comments once, UNKNOWN
 * no-ops, two concurrent consumers do not duplicate, and recovery obeys the
 * continuous-GREEN rule. Kept semantically identical to C182
 * (`backend/scripts/evals/browser_sweep_filing_contract.py`).
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  ACTIONS,
  CONTINUOUS_GREEN_RUNS_TO_CLOSE,
  SAFE_FINGERPRINT,
  canonicalUrl,
  buildFingerprint,
  findingsFromManifest,
  decide,
} = require("../helpers/sweepFiling");

const trusted = (over) => ({ manifestValid: true, shaBound: true, ...over });

// ------------------------------------------------------------ fingerprints ---

test("a fingerprint drops query and fragment so a rotating slug is still ONE defect", () => {
  assert.equal(
    canonicalUrl("https://www.bainluck.com/event/tennis/us-open-2026?ref=feed#top"),
    "https://www.bainluck.com/event/tennis/us-open-2026"
  );
  assert.equal(canonicalUrl("https://WWW.BainLuck.com/sports/"), "https://www.bainluck.com/sports");
  assert.equal(canonicalUrl(""), "");
});

test("a fingerprint is built from reason code + journey + canonical url, and nothing else", () => {
  const fp = buildFingerprint({
    reason_code: "REQUEST_FAILURE_VOLUME_EXCEEDED",
    journey_id: "tournament.tennis",
    url: "https://www.bainluck.com/event/tennis/us-open-2026",
    // Everything below is volatile and must NOT reach the key.
    detail: "2036 failed request(s) — top origin https://en.wikipedia.org x2036",
    run_id: "30864618239",
    sha: "1c4fe7e5b366f3e96324cce9c3a9585fed97e146",
  });

  assert.equal(
    fp,
    "request_failure_volume_exceeded:tournament.tennis:https://www.bainluck.com/event/tennis/us-open-2026"
  );
  assert.ok(SAFE_FINGERPRINT.test(fp));
  // The year in the slug is part of the identity; the COUNT and the run id are not.
  assert.ok(!fp.includes("2036"), "a count must never reach the key");
  assert.ok(!fp.includes("30864618239"), "a run id must never reach the key");
  assert.ok(!fp.includes("1c4fe7e5"), "a sha must never reach the key");
});

test("the same defect on two nights fingerprints identically", () => {
  const night = (n) =>
    buildFingerprint({
      reason_code: "CONSOLE_ERROR_VOLUME_EXCEEDED",
      journey_id: "tournament.tennis",
      url: `https://www.bainluck.com/event/tennis/us-open-2026?run=${n}`,
    });
  assert.equal(night(1), night(2));
});

test("a hostile journey id cannot smuggle unsafe characters into the key", () => {
  const fp = buildFingerprint({
    reason_code: "X",
    journey_id: "a`b$(whoami) <script>",
    url: "https://www.bainluck.com/x",
  });
  assert.ok(SAFE_FINGERPRINT.test(fp), fp);
});

// ------------------------------------------------- manifest -> findings ---

const FAILING_MANIFEST = {
  run: { base_url: "https://www.bainluck.com", result: "fail" },
  journeys: [
    {
      journey_id: "tournament.f1",
      project: "desktop",
      result: "fail",
      url: "https://www.bainluck.com/event/f1/belgian-grand-prix",
      assertions: [
        { assertion_id: "content.main_region_nonblank", ok: false, detail: "main region rendered blank" },
        { assertion_id: "network.failure_volume_within_policy", ok: false, detail: "2036 failed", reason_code: "REQUEST_FAILURE_VOLUME_EXCEEDED" },
        { assertion_id: "content.card_present", ok: true, detail: null },
      ],
    },
    { journey_id: "tournament.awards", project: "desktop", result: "pass", assertions: [{ assertion_id: "x", ok: true }] },
  ],
};

test("only failed assertions on failed journeys become findings", () => {
  const findings = findingsFromManifest(FAILING_MANIFEST);
  assert.equal(findings.length, 2);
  assert.deepEqual(
    findings.map((f) => f.assertion_id).sort(),
    ["content.main_region_nonblank", "network.failure_volume_within_policy"]
  );
});

test("a finding prefers the assertion's stable reason_code over its id", () => {
  const volume = findingsFromManifest(FAILING_MANIFEST).find(
    (f) => f.assertion_id === "network.failure_volume_within_policy"
  );
  assert.equal(volume.reason_code, "REQUEST_FAILURE_VOLUME_EXCEEDED");
  assert.ok(volume.fingerprint.startsWith("request_failure_volume_exceeded:"));
});

test("an infra_error journey yields findings marked infra, never product defects", () => {
  const findings = findingsFromManifest({
    run: { base_url: "https://www.bainluck.com" },
    journeys: [
      {
        journey_id: "deploy.smoke",
        result: "infra_error",
        assertions: [{ assertion_id: "run.runner_completed", ok: false, detail: "runner died" }],
      },
    ],
  });
  assert.equal(findings.length, 1);
  assert.equal(findings[0].infra, true);
});

test("an empty or malformed manifest yields no findings rather than throwing", () => {
  assert.deepEqual(findingsFromManifest(null), []);
  assert.deepEqual(findingsFromManifest({}), []);
  assert.deepEqual(findingsFromManifest({ journeys: "nope" }), []);
});

// ------------------------------------------------------------- decisions ---

test("a first real failure FILES once", () => {
  assert.deepEqual(decide(trusted({ verdict: "FAIL", fingerprint: "a:b:c" })), {
    action: ACTIONS.FILE,
    reason_codes: [],
    new_episode: false,
  });
});

test("the same failure again COMMENTS — never a second issue", () => {
  const d = decide(trusted({ verdict: "FAIL", fingerprint: "a:b:c", openIssue: true }));
  assert.equal(d.action, ACTIONS.COMMENT);
});

test("two concurrent consumers do not duplicate — the loser comments", () => {
  // Both see no open issue; one wins the create claim, the other must not file.
  const winner = decide(trusted({ verdict: "FAIL", fingerprint: "a:b:c" }));
  const loser = decide(trusted({ verdict: "FAIL", fingerprint: "a:b:c", concurrentClaimLost: true }));
  assert.equal(winner.action, ACTIONS.FILE);
  assert.equal(loser.action, ACTIONS.COMMENT);
});

test("UNKNOWN and INFRA no-op — a broken runner is not a product defect", () => {
  for (const verdict of ["UNKNOWN", "INFRA"]) {
    const d = decide(trusted({ verdict, fingerprint: "a:b:c" }));
    assert.equal(d.action, ACTIONS.NO_OP, `${verdict} must not file`);
  }
});

test("an untrusted manifest REFUSES — it neither files nor closes", () => {
  const d = decide({ verdict: "FAIL", manifestValid: false, shaBound: true, fingerprint: "a:b:c" });
  assert.equal(d.action, ACTIONS.REFUSE);
  assert.deepEqual(d.reason_codes, ["MANIFEST_UNTRUSTED"]);
});

test("an unbound SHA REFUSES — a result that names no deployment proves nothing", () => {
  const d = decide({ verdict: "FAIL", manifestValid: true, shaBound: false, fingerprint: "a:b:c" });
  assert.equal(d.action, ACTIONS.REFUSE);
  assert.deepEqual(d.reason_codes, ["SHA_UNBOUND"]);
});

test("refusal reasons accumulate and are sorted, so the log is deterministic", () => {
  const d = decide({
    verdict: "FAIL",
    manifestValid: false,
    shaBound: false,
    artifactExpired: true,
    fingerprint: "NOT SAFE!!",
  });
  assert.deepEqual(d.reason_codes, [
    "ARTIFACT_UNAVAILABLE",
    "FINGERPRINT_UNSAFE",
    "MANIFEST_UNTRUSTED",
    "SHA_UNBOUND",
  ]);
});

test("an expired artifact REFUSES — an issue with unreachable evidence is noise", () => {
  const d = decide(trusted({ verdict: "FAIL", fingerprint: "a:b:c", artifactExpired: true }));
  assert.equal(d.action, ACTIONS.REFUSE);
});

// -------------------------------------------------------------- recovery ---

test("ONE clean run does not close — recovery needs CONTINUOUS green", () => {
  const d = decide(trusted({ verdict: "PASS", fingerprint: "a:b:c", openIssue: true, consecutiveClean: 1 }));
  assert.equal(d.action, ACTIONS.COMMENT_RECOVERY_PENDING);
});

test("the standing continuous-GREEN duration closes it", () => {
  const d = decide(
    trusted({
      verdict: "PASS",
      fingerprint: "a:b:c",
      openIssue: true,
      consecutiveClean: CONTINUOUS_GREEN_RUNS_TO_CLOSE,
    })
  );
  assert.equal(d.action, ACTIONS.COMMENT_CLOSE);
});

test("green with nothing open is a no-op, not a stray comment", () => {
  assert.equal(decide(trusted({ verdict: "PASS", fingerprint: "a:b:c" })).action, ACTIONS.NO_OP);
});

test("a defect returning after closure is flagged as a NEW episode", () => {
  const d = decide(trusted({ verdict: "FAIL", fingerprint: "a:b:c", closedPrior: true }));
  assert.equal(d.action, ACTIONS.FILE);
  assert.equal(d.new_episode, true, "a recurrence must be distinguishable from a first sighting");
});

test("a refusal is never also a new episode", () => {
  const d = decide({ verdict: "FAIL", manifestValid: false, shaBound: true, closedPrior: true });
  assert.equal(d.new_episode, false);
});

// ------------------------------------------- cross-implementation agreement ---

test("the JS decision layer agrees with C182's Python state machine, case for case", () => {
  // Two implementations of one lifecycle that drift are worse than one. C182
  // (`backend/scripts/evals/browser_sweep_filing_contract.py` + its fixture) is
  // the authority; this asserts we match it on every case it defines.
  //
  // SKIPPED WHEN ABSENT, deliberately: C182 landed on master AFTER this branch
  // was cut, so the corpus is not in this tree yet. A hard failure here would be
  // a false red about a merge ordering rather than about behaviour. Once C182 is
  // on master this becomes a live gate with no further edit.
  const fs = require("node:fs");
  const path = require("node:path");
  const fixture = path.join(
    __dirname, "..", "..", "..",
    "backend", "tests", "evals", "fixtures", "browser_sweep_filing_contract.json"
  );
  if (!fs.existsSync(fixture)) {
    console.log("      ↳ C182 corpus not present in this tree yet — agreement check deferred");
    return;
  }

  const corpus = JSON.parse(fs.readFileSync(fixture, "utf8"));
  assert.equal(corpus.schema_version, "browser-sweep-filing/v1");

  for (const c of corpus.cases) {
    const x = c.input;
    const got = decide({
      verdict: x.verdict,
      manifestValid: x.manifest_valid,
      shaBound: x.sha_bound,
      fingerprint: x.fingerprint,
      artifactExpired: x.artifact_expired,
      openIssue: x.open_issue,
      concurrentClaimLost: x.concurrent_claim_lost,
      consecutiveClean: x.consecutive_clean,
      closedPrior: x.closed_prior,
    });
    assert.equal(got.action, c.expected.action, `${c.id}: action`);
    assert.deepEqual(got.reason_codes, c.expected.reason_codes, `${c.id}: reason_codes`);
    assert.equal(got.new_episode, c.expected.new_episode, `${c.id}: new_episode`);
  }
});
