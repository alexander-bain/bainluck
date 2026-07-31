"use strict";

/**
 * L2-221 Item 1 — the single redaction boundary for browser-audit evidence.
 *
 * Nothing reaches a manifest, an attachment, or a log line without passing
 * through here. The rule the queue sets is absolute: no raw cookies, no auth
 * headers, no storage state, and no arbitrary query/user text in artifacts.
 *
 * Plain CommonJS (with a sibling `.d.ts`) so the same implementation is
 * importable from the TypeScript specs AND runnable by bare `node` in a
 * workflow step, with no transpiler and no dependency.
 */

/** Headers that are dropped entirely — the key is recorded, never the value. */
const SENSITIVE_HEADERS = new Set([
  "authorization",
  "proxy-authorization",
  "cookie",
  "set-cookie",
  "x-api-key",
  "x-auth-token",
  "x-admin-token",
  "x-csrf-token",
  "x-session-token",
  "www-authenticate",
]);

const REDACTED = "[redacted]";
const REDACTED_VALUE = "[redacted-value]";

const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
/** Bearer/Basic/token-ish credential material. */
const BEARER_RE = /\b(bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{8,}/gi;
/** JWTs and other long opaque tokens. */
const JWT_RE = /\beyJ[A-Za-z0-9._-]{16,}/g;
const LONG_TOKEN_RE = /\b[A-Fa-f0-9]{32,}\b/g;

/**
 * Phone redaction requires >= 7 REAL digits, not merely a phone-ish shape.
 *
 * This is the L2-219/L2-220 trap, imported deliberately: a shape-matching
 * scrubber rewrote the build tag `1.4.2 (231)` to `[redacted-phone])`. An
 * evidence rail that mangles build tags cannot attest build identity, so the
 * two rails must agree on the >= 7-digit rule.
 */
const PHONE_CANDIDATE_RE = /\+?[\d][\d\s().-]{6,}\d/g;

/**
 * ISO-8601 dates and timestamps clear the >= 7-digit bar comfortably
 * (`2026-07-31` alone is 8 digits), so they are masked out before phone
 * redaction runs and restored afterwards. Found by this module's own fixture:
 * without it every timestamp in the evidence became `[redacted-phone]` — the
 * same class of over-redaction as the build-tag bug, one layer down.
 */
const ISO_DATETIME_RE =
  /\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?/g;

/** The mask starts with a letter, so it cannot itself match a phone candidate. */
const DATE_MASK_PREFIX = "ISODATE";
const DATE_MASK_RE = /\sISODATE(\d+)\s/g;

function digitCount(value) {
  let n = 0;
  for (const ch of value) if (ch >= "0" && ch <= "9") n += 1;
  return n;
}

/**
 * Scrub free text (console messages, error strings, page titles) of identity
 * and credential material. Returns a string for any input.
 *
 * @param {unknown} value
 * @param {{ maxLength?: number }} [options]
 * @returns {string}
 */
function redactText(value, options) {
  const maxLength = (options && options.maxLength) || 500;
  if (value == null) return "";
  let text = typeof value === "string" ? value : String(value);

  text = text.replace(EMAIL_RE, "[redacted-email]");
  text = text.replace(JWT_RE, "[redacted-token]");
  text = text.replace(BEARER_RE, "[redacted-credential]");
  text = text.replace(LONG_TOKEN_RE, "[redacted-token]");

  // Mask timestamps, redact phones, restore. A date is not a phone number.
  const dates = [];
  text = text.replace(ISO_DATETIME_RE, (match) => {
    dates.push(match);
    return " " + DATE_MASK_PREFIX + (dates.length - 1) + " ";
  });
  text = text.replace(PHONE_CANDIDATE_RE, (match) =>
    digitCount(match) >= 7 ? "[redacted-phone]" : match
  );
  text = text.replace(DATE_MASK_RE, (_, index) => dates[Number(index)]);

  // Any URL embedded in prose still has to lose its query values.
  text = text.replace(/https?:\/\/\S+/g, (match) => redactUrl(match));

  if (text.length > maxLength) text = text.slice(0, maxLength) + "…[truncated]";
  return text;
}

/**
 * Keep origin + path + the SHAPE of the query (keys only). Query VALUES are
 * where user text lives — search terms, ids, tokens — so they never survive.
 * The fragment is dropped entirely.
 *
 * @param {unknown} rawUrl
 * @returns {string}
 */
function redactUrl(rawUrl) {
  if (rawUrl == null) return "";
  const text = typeof rawUrl === "string" ? rawUrl : String(rawUrl);
  let parsed;
  try {
    parsed = new URL(text);
  } catch {
    // Not absolute: treat as a path, still strip any query values.
    const [pathPart, query] = text.split("?");
    if (!query) return pathPart.split("#")[0];
    const keys = query
      .split("#")[0]
      .split("&")
      .filter(Boolean)
      .map((pair) => pair.split("=")[0] + "=" + REDACTED_VALUE);
    return pathPart + "?" + keys.join("&");
  }
  const keys = [...parsed.searchParams.keys()];
  const query = keys.length
    ? "?" + keys.map((k) => k + "=" + REDACTED_VALUE).join("&")
    : "";
  return parsed.origin + parsed.pathname + query;
}

/**
 * Drop credential-bearing headers outright and redact the rest.
 *
 * @param {Record<string, string> | null | undefined} headers
 * @returns {Record<string, string>}
 */
function redactHeaders(headers) {
  /** @type {Record<string, string>} */
  const out = {};
  if (!headers) return out;
  for (const [key, value] of Object.entries(headers)) {
    const lower = key.toLowerCase();
    out[lower] = SENSITIVE_HEADERS.has(lower) ? REDACTED : redactText(value, { maxLength: 200 });
  }
  return out;
}

/**
 * Patterns whose presence anywhere in a serialized manifest means redaction
 * failed. `assertRedacted` is the last gate before an artifact is published;
 * it fails the run rather than shipping the leak.
 */
const LEAK_PATTERNS = [
  { id: "cookie_header", re: /"(cookie|set-cookie)"\s*:\s*"(?!\[redacted\])/i },
  { id: "authorization_header", re: /"authorization"\s*:\s*"(?!\[redacted\])/i },
  { id: "bearer_token", re: /\bbearer\s+[A-Za-z0-9._~+/=-]{8,}/i },
  { id: "jwt", re: /\beyJ[A-Za-z0-9._-]{16,}/ },
  { id: "email", re: EMAIL_RE },
  { id: "storage_state", re: /"(cookies|origins)"\s*:\s*\[\s*\{\s*"name"/i },
];

/**
 * @param {unknown} payload any JSON-serializable evidence object
 * @returns {{ ok: boolean, leaks: string[] }}
 */
function assertRedacted(payload) {
  const serialized = JSON.stringify(payload) || "";
  const leaks = [];
  for (const { id, re } of LEAK_PATTERNS) {
    // Fresh lastIndex — several patterns are global.
    const probe = new RegExp(re.source, re.flags.replace("g", ""));
    if (probe.test(serialized)) leaks.push(id);
  }
  return { ok: leaks.length === 0, leaks };
}

module.exports = {
  SENSITIVE_HEADERS,
  REDACTED,
  REDACTED_VALUE,
  redactText,
  redactUrl,
  redactHeaders,
  assertRedacted,
};
