"use strict";

/**
 * L2-221 Item 1 — the versioned evidence manifest and its validator.
 *
 * The invariant this file exists to enforce (C96 "Evidence schema"):
 *
 *   A manifest is valid only when schema validation passes, the requested SHA
 *   equals the observed FRONTEND SHA, the selected count is positive, and
 *   every selected journey has a terminal result and required artifacts.
 *
 * Everything else in the rail can be re-implemented; this is the gate that
 * makes "the run was green" mean something. It is deliberately hand-rolled
 * (no ajv, no dependency) so it runs from bare `node` in a workflow step and
 * is trivially unit-testable. `schema/audit-manifest.schema.json` publishes
 * the same contract for interop, and a contract test proves the two agree.
 */

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { TERMINAL_RESULTS } = require("./journey");
const { normalizeSha } = require("./buildAuthority");
const { assertRedacted } = require("./redaction");

const SCHEMA_VERSION = "browser-audit/v1";

const REQUIRED_RUN_FIELDS = Object.freeze([
  "run_id",
  "run_url",
  "pack",
  "trigger",
  "started_at_utc",
  "started_at_pt",
  "finished_at_utc",
  "requested_frontend_sha",
  "observed_frontend_sha",
  // L2-223: the commit whose specs/validator actually graded the run. Without
  // it a dispatch from any ref can audit a deployment using foreign grading
  // code and be filed as proof for the deployed commit.
  "checkout_sha",
  "runner_status",
  "base_url",
  "runtime",
  "selected_count",
  "completed_count",
  "failed_count",
  "result",
]);

/**
 * L2-223 — the only origins a run may audit.
 *
 * `base_url` is a free-text dispatch input. Left ungraded, someone can point
 * the rail at a staging clone, a preview deployment, or an attacker-controlled
 * lookalike and attach the resulting green to a production commit. The
 * allowlist is exact-origin: a subdomain match is NOT enough, because
 * `www.bainluck.com.evil.test` ends with nothing useful and
 * `preview.bainluck.com` is a different build.
 */
const CANONICAL_ORIGINS = Object.freeze(["https://www.bainluck.com", "https://bainluck.com"]);
const CANONICAL_API_ORIGINS = Object.freeze(["https://api.bainluck.com"]);

/** Terminal Playwright runner statuses that may accompany a green run. */
const RUNNER_STATUSES = Object.freeze(["passed", "failed", "timedout", "interrupted"]);

/**
 * The single relative subtree artifact paths may live under, resolved against
 * the manifest's own directory. Keeping evidence beside the manifest is what
 * makes "contained in the uploaded Actions artifact" checkable at all: the
 * workflow uploads that directory, so a path outside it is a claim about bytes
 * nobody will ever be able to fetch.
 */
const ARTIFACT_ROOT = "artifacts";

const REQUIRED_JOURNEY_FIELDS = Object.freeze([
  "journey_id",
  "project",
  "viewport",
  "url_path",
  "started_at_utc",
  "finished_at_utc",
  "duration_ms",
  "assertions",
  "console_errors",
  "page_errors",
  "failed_requests",
  "artifacts",
  "attempt",
  "result",
]);

const REQUIRED_RUNTIME_FIELDS = Object.freeze(["node", "playwright", "browser", "os"]);

const SHA256_RE = /^[0-9a-f]{64}$/;

/** @param {Buffer|string} data */
function sha256(data) {
  return crypto.createHash("sha256").update(data).digest("hex");
}

/** ISO-8601 UTC, and the Pacific rendering Alex reads. */
function stamps(date) {
  const d = date instanceof Date ? date : new Date(date);
  return {
    utc: d.toISOString(),
    pt: new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Los_Angeles",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(d),
  };
}

/**
 * Derive the run-level terminal result from the journeys. Never optimistic:
 * one infra_error makes the whole run an infra_error, one fail makes it a
 * fail, and an empty journey list is an infra_error (a rail that collected
 * nothing must never conclude success — the exact defect r323 found in the
 * dead provider's sweep).
 *
 * @param {Array<{result: string}>} journeys
 * @param {{ superseded?: boolean }} [options]
 * @returns {"pass"|"fail"|"infra_error"|"superseded"}
 */
function deriveRunResult(journeys, options) {
  if (options && options.superseded) return "superseded";
  const list = Array.isArray(journeys) ? journeys : [];
  if (list.length === 0) return "infra_error";
  if (list.some((j) => j && j.result === "infra_error")) return "infra_error";
  if (list.some((j) => j && j.result === "superseded")) return "superseded";
  if (list.some((j) => !j || j.result !== "pass")) return "fail";
  return "pass";
}

/**
 * @param {any} input
 * @returns {any} the manifest object (not yet validated — always validate it)
 */
function buildRunManifest(input) {
  const journeys = Array.isArray(input.journeys) ? input.journeys : [];
  const started = stamps(input.startedAt || new Date());
  const finished = stamps(input.finishedAt || new Date());
  const failed = journeys.filter((j) => j && j.result !== "pass").length;

  return {
    schema_version: SCHEMA_VERSION,
    run: {
      run_id: String(input.runId || "local"),
      run_url: String(input.runUrl || "local"),
      pack: String(input.pack || "deploy-smoke"),
      trigger: String(input.trigger || "manual"),
      started_at_utc: started.utc,
      started_at_pt: started.pt,
      finished_at_utc: finished.utc,
      finished_at_pt: finished.pt,
      requested_frontend_sha: normalizeSha(input.requestedFrontendSha),
      observed_frontend_sha: normalizeSha(input.observedFrontendSha),
      // The commit that supplied the specs, evaluator and validator. Recorded
      // separately from the deployed commit because they are different facts.
      checkout_sha: normalizeSha(input.checkoutSha),
      // How the requested commit relates to the checkout, PROVEN by the
      // workflow (`git merge-base --is-ancestor`) — never assumed.
      checkout_ancestry: input.checkoutAncestry || null,
      // Playwright's own terminal verdict for the process. A run whose runner
      // failed is not green no matter what the journey records say.
      runner_status: input.runnerStatus || null,
      // Recorded, never substituted for the frontend authority.
      observed_backend_sha: input.observedBackendSha || null,
      base_url: String(input.baseUrl || ""),
      final_origin: input.finalOrigin || null,
      api_base_url: input.apiBaseUrl || null,
      runtime: {
        node: String((input.runtime && input.runtime.node) || process.version),
        playwright: String((input.runtime && input.runtime.playwright) || "unknown"),
        browser: String((input.runtime && input.runtime.browser) || "unknown"),
        os: String((input.runtime && input.runtime.os) || `${process.platform}-${process.arch}`),
      },
      selected_count: Number.isFinite(input.selectedCount) ? input.selectedCount : 0,
      completed_count: journeys.length,
      failed_count: failed,
      result: input.result || deriveRunResult(journeys, { superseded: input.superseded }),
      superseded_by: input.supersededBy || null,
      notes: Array.isArray(input.notes) ? input.notes : [],
    },
    journeys,
  };
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * Exact-origin allowlist check.
 *
 * Deliberately not a suffix test. `bainluck.com.attacker.test` and
 * `preview-x.bainluck.com` both pass a naive `endsWith`, and the second is the
 * realistic one: a preview deployment is a real Vercel host serving a
 * different build, so a green from it would be attached to the wrong commit.
 *
 * @param {unknown} value
 * @param {readonly string[]} allowlist
 * @param {string} field
 */
function checkOrigin(value, allowlist, field) {
  const errors = [];
  if (!isNonEmptyString(value)) {
    errors.push(`${field} is required and must be an absolute https URL`);
    return { ok: false, errors };
  }
  let parsed;
  try {
    parsed = new URL(String(value));
  } catch {
    errors.push(`${field} is not a parseable URL`);
    return { ok: false, errors };
  }
  if (parsed.protocol !== "https:") {
    errors.push(`${field} must be https (got ${parsed.protocol.replace(":", "") || "no scheme"})`);
  }
  if (!allowlist.includes(parsed.origin)) {
    errors.push(`${field} origin ${parsed.origin} is not one of the canonical origins ${allowlist.join(", ")}`);
  }
  return { ok: errors.length === 0, errors };
}

/**
 * L2-223 Item 2 — is this a path we could actually go and read inside the
 * uploaded Actions artifact?
 *
 * Everything here is a STRING check; the bytes are verified separately by
 * `verifyArtifactBytes`, which needs a filesystem. Splitting them keeps
 * `validateManifest` usable on a downloaded manifest with no files beside it,
 * while the workflow (which does have the files) runs both.
 *
 * @param {unknown} rawPath
 * @param {string} where
 * @returns {{ ok: boolean, normalized: string|null, errors: string[] }}
 */
function checkArtifactPath(rawPath, where) {
  const errors = [];
  if (!isNonEmptyString(rawPath)) {
    return { ok: false, normalized: null, errors: [`${where}.path is required`] };
  }
  const value = String(rawPath);
  if (value.includes("\0")) {
    return { ok: false, normalized: null, errors: [`${where}.path contains a NUL byte`] };
  }
  // Reject Windows separators and drive letters before normalising, so a
  // `..\\` cannot survive on a posix runner as an ordinary filename.
  if (value.includes("\\") || /^[a-zA-Z]:/.test(value)) {
    errors.push(`${where}.path must use posix separators and no drive letter (got ${JSON.stringify(value)})`);
  }
  if (path.posix.isAbsolute(value) || value.startsWith("/")) {
    errors.push(`${where}.path must be relative to the manifest directory (got ${JSON.stringify(value)})`);
  }
  const normalized = path.posix.normalize(value);
  if (normalized !== value) {
    errors.push(`${where}.path must already be normalized (${JSON.stringify(value)} normalizes to ${JSON.stringify(normalized)})`);
  }
  if (normalized === ".." || normalized.startsWith("../") || normalized.includes("/../")) {
    errors.push(`${where}.path escapes the artifact root`);
  }
  if (!normalized.startsWith(`${ARTIFACT_ROOT}/`)) {
    errors.push(`${where}.path must live under "${ARTIFACT_ROOT}/" — evidence outside the uploaded tree cannot be fetched`);
  }
  return { ok: errors.length === 0, normalized: errors.length === 0 ? normalized : null, errors };
}

/**
 * L2-223 Item 2 — the bytes exist, are a regular file, and hash to what the
 * manifest claims.
 *
 * Before this, `artifacts: [{name, sha256}]` with a plausible-looking digest
 * validated with no file anywhere. A fictional artifact is worse than no
 * artifact: it reads as evidence in every downstream summary.
 *
 * @param {any} manifest
 * @param {{ root: string, fsImpl?: typeof fs }} options root = the manifest's directory
 * @returns {{ ok: boolean, errors: string[], verified: number }}
 */
function verifyArtifactBytes(manifest, options) {
  const errors = [];
  let verified = 0;
  const io = (options && options.fsImpl) || fs;
  const root = path.resolve(String((options && options.root) || "."));
  const journeys = Array.isArray(manifest && manifest.journeys) ? manifest.journeys : [];

  // Uniqueness is global, not per journey: two journeys pointing at one file
  // means one of them is claiming evidence it did not produce.
  const seenPaths = new Map();

  journeys.forEach((journey, ji) => {
    const artifacts = Array.isArray(journey && journey.artifacts) ? journey.artifacts : [];
    artifacts.forEach((artifact, ai) => {
      const where = `journeys[${ji}].artifacts[${ai}]`;
      const pathCheck = checkArtifactPath(artifact && artifact.path, where);
      if (!pathCheck.ok) {
        errors.push(...pathCheck.errors);
        return;
      }
      const rel = pathCheck.normalized;
      const owner = `${journey.journey_id}::${journey.project}`;
      if (seenPaths.has(rel)) {
        errors.push(`${where}.path ${rel} is already claimed by ${seenPaths.get(rel)}`);
        return;
      }
      seenPaths.set(rel, owner);

      const absolute = path.resolve(root, rel);
      // Belt and braces: even a normalized relative path can leave the root
      // through a symlinked parent directory.
      if (absolute !== root && !absolute.startsWith(`${root}${path.sep}`)) {
        errors.push(`${where}.path resolves outside the artifact root`);
        return;
      }

      let stat;
      try {
        stat = io.lstatSync(absolute);
      } catch {
        errors.push(`${where}.path ${rel} does not exist — the manifest claims evidence that was never written`);
        return;
      }
      if (stat.isSymbolicLink()) {
        errors.push(`${where}.path ${rel} is a symlink; artifacts must be regular files whose bytes travel in the upload`);
        return;
      }
      if (!stat.isFile()) {
        errors.push(`${where}.path ${rel} is not a regular file`);
        return;
      }

      let buffer;
      try {
        buffer = io.readFileSync(absolute);
      } catch (err) {
        errors.push(`${where}.path ${rel} could not be read: ${String((err && err.message) || err)}`);
        return;
      }
      const digest = sha256(buffer);
      if (digest !== String(artifact.sha256 || "").toLowerCase()) {
        errors.push(`${where} sha256 mismatch — manifest says ${artifact.sha256}, bytes hash to ${digest}`);
        return;
      }
      if (Number.isFinite(artifact.bytes) && artifact.bytes !== buffer.byteLength) {
        errors.push(`${where} byte count mismatch — manifest says ${artifact.bytes}, file is ${buffer.byteLength}`);
        return;
      }
      verified += 1;
    });
  });

  return { ok: errors.length === 0, errors, verified };
}

/**
 * @param {any} manifest
 * @returns {{ ok: boolean, errors: string[] }}
 */
function validateManifest(manifest) {
  /** @type {string[]} */
  const errors = [];

  if (!manifest || typeof manifest !== "object") {
    return { ok: false, errors: ["manifest is not an object"] };
  }
  if (manifest.schema_version !== SCHEMA_VERSION) {
    errors.push(`schema_version must be "${SCHEMA_VERSION}" (got ${JSON.stringify(manifest.schema_version)})`);
  }

  const run = manifest.run;
  if (!run || typeof run !== "object") {
    errors.push("run block is missing");
    return { ok: false, errors };
  }

  for (const field of REQUIRED_RUN_FIELDS) {
    const value = run[field];
    if (value === undefined || value === null || value === "") {
      errors.push(`run.${field} is required`);
    }
  }

  if (run.runtime && typeof run.runtime === "object") {
    for (const field of REQUIRED_RUNTIME_FIELDS) {
      if (!isNonEmptyString(run.runtime[field])) errors.push(`run.runtime.${field} is required`);
    }
  }

  if (!TERMINAL_RESULTS.includes(run.result)) {
    errors.push(`run.result must be one of ${TERMINAL_RESULTS.join("|")} (got ${JSON.stringify(run.result)})`);
  }

  // --- Invariant 1: a run that selected nothing is never valid evidence. ---
  if (!(Number.isInteger(run.selected_count) && run.selected_count > 0)) {
    errors.push("run.selected_count must be a positive integer — a run that selected zero journeys proves nothing");
  }

  const journeys = Array.isArray(manifest.journeys) ? manifest.journeys : null;
  if (!journeys) {
    errors.push("journeys must be an array");
    return { ok: false, errors };
  }
  if (journeys.length === 0) {
    errors.push("journeys must not be empty — a run that collected nothing must never validate");
  }
  if (run.completed_count !== journeys.length) {
    errors.push(`run.completed_count (${run.completed_count}) must equal the number of journeys (${journeys.length})`);
  }
  // L2-223: `journeys <= selected` was the wrong direction. Selecting two
  // journeys and completing one is the classic partial run — the runner died
  // after the first, and the manifest still validated because one record is
  // not "more than" two. Every selected journey must have produced a record.
  if (Number.isInteger(run.selected_count) && run.selected_count !== journeys.length) {
    errors.push(
      `run.selected_count (${run.selected_count}) must equal the number of journeys (${journeys.length}) — ` +
        "a selected journey that produced no record is an unproven journey"
    );
  }

  // --- Invariant 2: exact frontend build authority. Backend never substitutes. ---
  const requested = normalizeSha(run.requested_frontend_sha);
  const observed = normalizeSha(run.observed_frontend_sha);
  if (!requested) errors.push("run.requested_frontend_sha must be a full 40-hex sha");
  if (!observed) {
    errors.push("run.observed_frontend_sha must be a full 40-hex sha read from the frontend build marker");
  }
  if (requested && observed && requested !== observed && run.result !== "superseded") {
    errors.push(`frontend sha mismatch: requested ${requested}, deployed ${observed}`);
  }
  if (run.result === "superseded" && !isNonEmptyString(run.superseded_by)) {
    errors.push("run.superseded_by is required when run.result is superseded");
  }

  // --- Invariant 2b (L2-223): the GRADING code's commit is bound too. ---
  //
  // Requested-equals-observed proves which deployment was exercised. It says
  // nothing about which commit's specs, evaluator and validator did the
  // grading. A dispatch from an arbitrary ref checks out that ref's rail and
  // runs it against production, so a weakened evaluator on a side branch can
  // manufacture a green for a commit it never graded honestly.
  const checkout = normalizeSha(run.checkout_sha);
  if (!checkout) {
    errors.push("run.checkout_sha must be a full 40-hex sha — the grading commit is part of the claim");
  }
  if (checkout && requested && checkout !== requested) {
    // Not equal is legitimate and normal: master moves ahead of what Vercel
    // has deployed. But it is only legitimate when the workflow PROVED the
    // deployed commit is in the checked-out history. Anything else — a fork, a
    // side branch, a rewritten commit — is a foreign ref.
    if (run.checkout_ancestry !== "requested-is-ancestor-of-checkout") {
      errors.push(
        `run.checkout_sha (${checkout}) differs from the audited commit (${requested}) without proven ancestry — ` +
          'run.checkout_ancestry must be "requested-is-ancestor-of-checkout"'
      );
    }
  }

  // --- Invariant 2c (L2-223): the runner's own verdict binds the run. ---
  //
  // Journey records are written by the journeys themselves. If the runner
  // fails, times out, or is interrupted, records for the journeys that DID
  // finish can all read `pass` — and before this check the manifest validated,
  // because nothing carried the process-level outcome. Silence about a dead
  // runner is exactly the retired provider's `success` with 0 of 3 collected.
  if (!RUNNER_STATUSES.includes(run.runner_status)) {
    errors.push(
      `run.runner_status must be one of ${RUNNER_STATUSES.join("|")} (got ${JSON.stringify(run.runner_status)})`
    );
  } else if (run.runner_status !== "passed" && run.result === "pass") {
    errors.push(
      `run.result is pass while the runner terminated "${run.runner_status}" — ` +
        "a run whose runner did not pass is never green"
    );
  }

  // --- Invariant 2d (L2-223): the audited origin is allowlisted. ---
  const originVerdict = checkOrigin(run.base_url, CANONICAL_ORIGINS, "run.base_url");
  errors.push(...originVerdict.errors);
  if (run.api_base_url) {
    errors.push(...checkOrigin(run.api_base_url, CANONICAL_API_ORIGINS, "run.api_base_url").errors);
  }
  // The FINAL origin is the one the browser actually ended on. A canonical
  // start that redirects somewhere else proves nothing about the canonical
  // site, so the landing origin is held to the same allowlist.
  if (run.final_origin) {
    errors.push(...checkOrigin(run.final_origin, CANONICAL_ORIGINS, "run.final_origin").errors);
  }

  // --- Invariant 3: every journey terminal, evidenced, and consistent. ---
  const seen = new Set();
  journeys.forEach((journey, index) => {
    const where = `journeys[${index}]`;
    if (!journey || typeof journey !== "object") {
      errors.push(`${where} is not an object`);
      return;
    }
    for (const field of REQUIRED_JOURNEY_FIELDS) {
      if (journey[field] === undefined || journey[field] === null) {
        errors.push(`${where}.${field} is required`);
      }
    }
    const key = `${journey.journey_id}::${journey.project}`;
    if (seen.has(key)) errors.push(`${where} duplicates journey id ${key}`);
    seen.add(key);

    if (!TERMINAL_RESULTS.includes(journey.result)) {
      errors.push(`${where}.result must be one of ${TERMINAL_RESULTS.join("|")} (got ${JSON.stringify(journey.result)})`);
    }
    if (!Array.isArray(journey.assertions) || journey.assertions.length === 0) {
      errors.push(`${where}.assertions must be a non-empty array`);
    } else {
      journey.assertions.forEach((a, ai) => {
        if (!a || !isNonEmptyString(a.assertion_id) || typeof a.ok !== "boolean") {
          errors.push(`${where}.assertions[${ai}] needs assertion_id and a boolean ok`);
        }
      });
      const anyFailed = journey.assertions.some((a) => a && a.ok === false);
      if (anyFailed && journey.result === "pass") {
        errors.push(`${where} reports pass while carrying a failed assertion`);
      }
      if (!anyFailed && journey.result === "fail") {
        errors.push(`${where} reports fail with no failed assertion`);
      }
    }
    if (!Array.isArray(journey.artifacts) || journey.artifacts.length === 0) {
      errors.push(`${where}.artifacts must be a non-empty array — a journey with no evidence is not proof`);
    } else {
      journey.artifacts.forEach((artifact, ai) => {
        const aWhere = `${where}.artifacts[${ai}]`;
        if (!artifact || !isNonEmptyString(artifact.name)) {
          errors.push(`${aWhere}.name is required`);
        }
        if (!artifact || !SHA256_RE.test(String(artifact.sha256 || ""))) {
          errors.push(`${aWhere}.sha256 must be a 64-hex digest`);
        }
        // L2-223: a digest with no path is unfalsifiable. The path is what
        // lets a reviewer open the file and re-hash it.
        errors.push(...checkArtifactPath(artifact && artifact.path, aWhere).errors);
        if (artifact && !(Number.isInteger(artifact.bytes) && artifact.bytes > 0)) {
          errors.push(`${aWhere}.bytes must be a positive integer — a zero-byte artifact is not evidence`);
        }
        // --- Trace honesty (L2-223 Item 2). ---
        //
        // A Playwright trace is a zip of the whole session: request bodies,
        // response bodies, storage, and every cookie header the page sent.
        // Scrubbing the manifest's JSON fields does nothing to it. Phase 1
        // publishes artifacts unconditionally with 90-day retention and has no
        // reviewed containment policy, so the rail must not carry traces at
        // all — declaring one is a policy violation, not a formatting error.
        if (artifact && /(^|[^a-z])trace([^a-z]|$)|\.trace\.zip$/i.test(String(artifact.name))) {
          errors.push(
            `${aWhere} declares a Playwright trace — phase 1 has no reviewed containment policy for raw traces, ` +
              "so trace capture must stay off (screenshots and scrubbed JSON are the closure evidence)"
          );
        }
      });
      // Duplicate paths inside one journey are caught here even when no
      // filesystem is available to `verifyArtifactBytes`.
      const paths = journey.artifacts.map((a) => (a && typeof a.path === "string" ? a.path : null)).filter(Boolean);
      const dupes = paths.filter((p, i) => paths.indexOf(p) !== i);
      for (const dupe of new Set(dupes)) {
        errors.push(`${where} claims the same artifact path twice: ${dupe}`);
      }
    }
  });

  const observedFail = journeys.filter((j) => j && j.result !== "pass").length;
  if (run.failed_count !== observedFail) {
    errors.push(`run.failed_count (${run.failed_count}) must equal the number of non-pass journeys (${observedFail})`);
  }

  // --- Invariant 4: the run result must agree with the journeys it carries. ---
  const derived = deriveRunResult(journeys, { superseded: run.result === "superseded" });
  if (run.result !== derived) {
    errors.push(`run.result (${run.result}) disagrees with the journeys, which derive ${derived}`);
  }

  // --- Invariant 5: nothing sensitive survived redaction. ---
  const redaction = assertRedacted(manifest);
  if (!redaction.ok) {
    errors.push(`redaction failed — manifest contains ${redaction.leaks.join(", ")}`);
  }

  return { ok: errors.length === 0, errors };
}

module.exports = {
  SCHEMA_VERSION,
  REQUIRED_RUN_FIELDS,
  REQUIRED_JOURNEY_FIELDS,
  REQUIRED_RUNTIME_FIELDS,
  CANONICAL_ORIGINS,
  CANONICAL_API_ORIGINS,
  RUNNER_STATUSES,
  ARTIFACT_ROOT,
  sha256,
  stamps,
  deriveRunResult,
  buildRunManifest,
  validateManifest,
  checkOrigin,
  checkArtifactPath,
  verifyArtifactBytes,
};
