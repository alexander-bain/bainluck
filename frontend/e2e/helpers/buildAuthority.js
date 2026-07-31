"use strict";

/**
 * L2-221 Item 2 — exact frontend deployment authority.
 *
 * C96 [P1]: CI knows the triggering Git SHA and the backend `/health` exposes
 * the Heroku SHA, but **Vercel deploys independently**. A browser run that
 * reads neither can test the previous or the next deployment and still be
 * attached as proof for the requested commit.
 *
 * So: the frontend publishes its own non-secret marker (`/api/frontend-build`, plus a
 * `<meta>` tag on every rendered page), and this module is the only thing
 * allowed to decide whether a run may claim a SHA. The backend SHA is
 * *recorded* alongside — never substituted for the frontend's.
 */

const FULL_SHA_RE = /^[0-9a-f]{40}$/;

/**
 * @param {unknown} value
 * @returns {string|null} a lowercase 40-hex sha, or null if it isn't one
 */
function normalizeSha(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim().toLowerCase();
  return FULL_SHA_RE.test(trimmed) ? trimmed : null;
}

/**
 * Deliberately strict: abbreviated SHAs do not satisfy authority. A 7-char
 * prefix is ambiguous across a long-lived repo, and "close enough" is exactly
 * how a run gets attached to the wrong deployment.
 *
 * @param {unknown} requested
 * @param {unknown} observed
 * @returns {{ match: boolean, requested: string|null, observed: string|null, reason: string }}
 */
function compareSha(requested, observed) {
  const req = normalizeSha(requested);
  const obs = normalizeSha(observed);
  if (!req) {
    return { match: false, requested: null, observed: obs, reason: "requested sha is missing or not a full 40-hex sha" };
  }
  if (!obs) {
    return { match: false, requested: req, observed: null, reason: "frontend build marker is missing or not a full 40-hex sha" };
  }
  if (req !== obs) {
    return { match: false, requested: req, observed: obs, reason: `frontend deployment is ${obs}, requested ${req}` };
  }
  return { match: true, requested: req, observed: obs, reason: "frontend deployment matches the requested sha" };
}

/**
 * Read the public build marker. Non-secret by construction: it exposes a
 * commit sha and nothing else.
 *
 * @param {string} baseUrl
 * @param {{ fetchImpl?: typeof fetch, timeoutMs?: number }} [options]
 * @returns {Promise<{ ok: boolean, commit: string|null, status: number|null, error: string|null }>}
 */
async function fetchFrontendBuild(baseUrl, options) {
  const doFetch = (options && options.fetchImpl) || globalThis.fetch;
  const timeoutMs = (options && options.timeoutMs) || 15_000;
  const url = `${String(baseUrl).replace(/\/+$/, "")}/api/frontend-build`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await doFetch(url, {
      signal: controller.signal,
      headers: { accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) {
      return { ok: false, commit: null, status: res.status, error: `build marker returned HTTP ${res.status}` };
    }
    const body = await res.json();
    return { ok: true, commit: normalizeSha(body && body.commit), status: res.status, error: null };
  } catch (err) {
    return { ok: false, commit: null, status: null, error: String((err && err.message) || err) };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Poll the marker until it equals `requestedSha`, bounded.
 *
 * Clock and fetch are injectable so the contract tests cover the timeout,
 * mismatch and never-appears paths deterministically, with no network and no
 * real waiting.
 *
 * @param {{
 *   baseUrl: string,
 *   requestedSha: string,
 *   timeoutMs?: number,
 *   intervalMs?: number,
 *   fetchImpl?: typeof fetch,
 *   now?: () => number,
 *   sleep?: (ms: number) => Promise<void>,
 *   onAttempt?: (info: { attempt: number, observed: string|null, error: string|null }) => void,
 * }} options
 * @returns {Promise<{ ok: boolean, observed: string|null, attempts: number, reason: string, lastError: string|null }>}
 */
async function waitForFrontendSha(options) {
  const {
    baseUrl,
    requestedSha,
    timeoutMs = 600_000,
    intervalMs = 10_000,
    fetchImpl,
    now = () => Date.now(),
    sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
    onAttempt,
  } = options;

  const req = normalizeSha(requestedSha);
  if (!req) {
    return {
      ok: false,
      observed: null,
      attempts: 0,
      reason: "requested sha is missing or not a full 40-hex sha",
      lastError: null,
    };
  }

  const deadline = now() + timeoutMs;
  let attempts = 0;
  let observed = null;
  let lastError = null;

  for (;;) {
    attempts += 1;
    const probe = await fetchFrontendBuild(baseUrl, { fetchImpl });
    observed = probe.commit;
    lastError = probe.error;
    if (onAttempt) onAttempt({ attempt: attempts, observed, error: lastError });

    if (observed && observed === req) {
      return { ok: true, observed, attempts, reason: "frontend deployment matches the requested sha", lastError: null };
    }
    if (now() >= deadline) {
      const verdict = compareSha(req, observed);
      return {
        ok: false,
        observed,
        attempts,
        reason: `timed out after ${attempts} attempt(s): ${verdict.reason}`,
        lastError,
      };
    }
    await sleep(intervalMs);
  }
}

/**
 * The backend SHA is a *second ledger entry*, never a stand-in. This helper
 * exists so callers cannot casually pass a backend value into the frontend
 * authority slot: it returns a distinctly-named field.
 *
 * @param {string} apiBaseUrl
 * @param {{ fetchImpl?: typeof fetch, timeoutMs?: number }} [options]
 * @returns {Promise<{ observed_backend_sha: string|null, error: string|null }>}
 */
async function fetchBackendHealthSha(apiBaseUrl, options) {
  const doFetch = (options && options.fetchImpl) || globalThis.fetch;
  const timeoutMs = (options && options.timeoutMs) || 15_000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await doFetch(`${String(apiBaseUrl).replace(/\/+$/, "")}/health`, {
      signal: controller.signal,
      headers: { accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) return { observed_backend_sha: null, error: `health returned HTTP ${res.status}` };
    const body = await res.json();
    const raw = body && (body.commit || body.sha || body.release);
    return { observed_backend_sha: typeof raw === "string" ? raw.trim().toLowerCase() : null, error: null };
  } catch (err) {
    return { observed_backend_sha: null, error: String((err && err.message) || err) };
  } finally {
    clearTimeout(timer);
  }
}

module.exports = {
  FULL_SHA_RE,
  normalizeSha,
  compareSha,
  fetchFrontendBuild,
  waitForFrontendSha,
  fetchBackendHealthSha,
};
