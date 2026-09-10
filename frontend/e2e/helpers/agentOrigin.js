"use strict";

/**
 * Notice 39 / #4763 — the e2e rail names itself on our own wire.
 *
 * ## The rail this exists for, and what it was doing
 *
 * `backend/app/utils/agent_origin.py` is this contract for the ~90 Python probes.
 * It cannot reach here: it is Python, and `browser-audit.yml` drives Node. So the
 * one fleet rail that runs against production ON A SCHEDULE was the one rail with
 * no carrier at all.
 *
 * MEASURED on production, 30-day window, read 2026-09-10 (#4763). The
 * `tournament-inventory` pack resolves two slugs by asking the real search API
 * (`/api/events/search?q=tennis`, `?q=grand%20prix`), on the `desktop` and
 * `mobile` projects, once per scheduled run. Only CI asks for BOTH terms, so
 * co-occurrence inside an hour separates robot from person:
 *
 *     grand prix   51 rows in a CI hour,  0 solo   — rank 17 of 571 terms
 *     tennis       51 rows in a CI hour, 12 solo   — rank 11 of 571 terms
 *
 * `grand prix` has ZERO organic searches in thirty days. It sits in the top 20 of
 * the table notice 39 names — "every 'what are people doing' read must tell a
 * person from a lane" — purely because we ask for it once a day.
 *
 * ## What this does NOT claim, because it was checked
 *
 * No warming or latency harm today. `search_head_warmer._head_from_user_rows`
 * filters to `session_id IS NOT NULL OR user_id IS NOT NULL`, and both terms
 * measure 100% session-less (0 attested of 51 and of 63), so the head warmer
 * cannot elect either one; `DEFAULT_HEAD_SIZE = 8` puts them below the cut in any
 * case. `/api/events/search` casts no trending vote either — both
 * `_record_trending` call sites are inside `typeahead_search`.
 *
 * So the defect is that the TABLE misreports demand to anything reading it without
 * knowing to filter on `session_id`. The designed defense is this header; what is
 * actually covering us is an unrelated filter that happens to exclude session-less
 * rows. That is worth closing before a "top search terms" panel inherits the lie.
 *
 * ## Why a helper and not `extraHTTPHeaders` in playwright.config.ts
 *
 * `tools/shop-shot.mjs` sets the header that way and is right to: it shoots our own
 * pages and nothing else. This rail is different in two ways that both bite.
 *
 *   1. A context-wide header goes to EVERY host a page contacts, including the
 *      third parties our pages load. An internal header naming our lanes has no
 *      business on a third party's wire — the same rule `is_our_host` exists to
 *      enforce in Python, and the same rule `agentOriginCarriers.contract.test.js`
 *      already pins for the shell carrier ("never sends the header to a host that
 *      is not ours").
 *   2. The alternative — a `page.route()` interceptor that filters by host — puts
 *      a JS hop in front of every request in a rail that contains
 *      `discover-latency.spec.ts` and `sports-latency.spec.ts`. Distorting the
 *      thing you are measuring to label it is not a trade worth making.
 *
 * So the tag goes on the EXPLICIT API calls the specs make, all of which are built
 * from `AUDIT_API_BASE_URL` and are therefore ours by construction — and
 * `isOurHost` still guards them, so the guarantee does not rest on that being
 * remembered.
 *
 * ## The naming rule differs from Python's ON PURPOSE
 *
 * `resolve_agent()` in Python returns None when `BL_AGENT` is unset, and MUST: an
 * unset variable is an ABSENCE, a human running a script by hand looks exactly
 * like a lane that forgot, and tagging on absence would silently delete real
 * people from the table (notice 39 guard 1).
 *
 * `GITHUB_ACTIONS === "true"` is not an absence. It is a positive assertion, made
 * by the runner and not by us, that no person is present. A run inside GitHub
 * Actions is definitionally a robot, so naming it is a deduction rather than a
 * guess — and it means a workflow added next month is tagged without anyone
 * remembering to edit an `env:` block. `BL_AGENT` still wins when set, so a human
 * driving a pack locally is untagged, and `BL_AGENT=user` still says "count me".
 */

/** The wire name. Must agree with `agent_origin.ORIGIN_HEADER` character for character. */
const ORIGIN_HEADER = "x-bainluck-origin";

/** The one value honoured POSITIVELY — it KEEPS the search-log row. */
const ORIGIN_USER = "user";

const OUR_HOSTS = ["bainluck.com", "localhost", "127.0.0.1"];

/**
 * The agent name for THIS call, or null when nothing may be added.
 *
 * Read at call time, never captured at module load: `agent_origin.resolve_agent`
 * carries a long comment about why, and it applies identically here. A name baked
 * in at import produces the wrong answer for any caller that sets `BL_AGENT`
 * afterwards, and the failure is silent in both directions.
 */
function resolveAgent() {
  const named = (process.env.BL_AGENT || "").trim();
  if (named) return named;

  // Not a default-on-absence. See the header comment: this is the runner
  // asserting that it is a runner.
  if (process.env.GITHUB_ACTIONS === "true") {
    const workflow = (process.env.GITHUB_WORKFLOW || "").trim();
    // Kept to the shape a log reader can scan: `ci:Browser audit` → `ci:browser-audit`.
    const slug = workflow
      ? workflow.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "")
      : "";
    return slug ? `ci:${slug}` : "ci";
  }

  return null;
}

/** Lowercased hostname of `url`, or "" when it has none. */
function hostOf(url) {
  try {
    // A bare host has no protocol until it is given one, rather than being
    // string-munged — the same reason `agent_origin._host_of` does this.
    return new URL(String(url).includes("//") ? url : `//${url}`, "http://placeholder").hostname.toLowerCase();
  } catch {
    // An unparseable URL is not ours; refusing to tag is the safe direction.
    return "";
  }
}

/**
 * True when `url` points at a host we own.
 *
 * Matches the parsed HOST as a suffix, never a substring: a substring test tags
 * `https://example.com/?ref=bainluck.com`, which is a third party.
 */
function isOurHost(url) {
  const host = hostOf(url);
  if (!host) return false;
  return OUR_HOSTS.some((h) => host === h || host.endsWith(`.${h}`));
}

/**
 * Headers to ADD so `url` says who sent it. Possibly empty — the caller merges.
 *
 * Empty is the correct answer for a third-party host, an already-tagged request,
 * or a caller that never named itself. An explicit header from the caller always
 * wins: two disagreeing `x-bainluck-origin` values are worse than none, because
 * the backend reads the first and the caller's stated intent loses silently.
 */
function originHeaders(url, existing) {
  if (!isOurHost(url)) return {};

  const lowered = new Set(Object.keys(existing || {}).map((k) => String(k).toLowerCase()));
  if (lowered.has(ORIGIN_HEADER)) return {};

  const who = resolveAgent();
  if (who === null) return {};

  const headers = { [ORIGIN_HEADER]: who };
  // The router log records the UA, which makes fleet traffic legible without a
  // database read. Never clobber a caller's own — and note this rail CAN set one
  // safely, unlike `shop-shot.mjs`, because these are API calls and not the page
  // render whose fidelity a bot UA would change.
  if (!lowered.has("user-agent")) {
    headers["User-Agent"] = `BainLuckBot/1.0 (${who})`;
  }
  return headers;
}

/** `headers` plus the origin tag — the one-call form for request builders. */
function tagged(url, headers) {
  const merged = { ...(headers || {}) };
  return { ...merged, ...originHeaders(url, merged) };
}

module.exports = {
  ORIGIN_HEADER,
  ORIGIN_USER,
  resolveAgent,
  isOurHost,
  originHeaders,
  tagged,
};
