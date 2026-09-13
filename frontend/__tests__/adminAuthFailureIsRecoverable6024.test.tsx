// #6024 — A REJECTED ADMIN SECRET IS NOT A VERDICT ON THE SITE, AND IT IS
// RECOVERABLE WITHOUT KNOWING A TRICK.
//
// ── WHAT ALEX SAW ────────────────────────────────────────────────────────────
//
// /admin, 2026-09-13. Under the heading "Is the system healthy?", a red
// **Critical** badge, and next to it, as the answer:
//
//     Admin API error 403: Invalid admin secret
//
// The system was healthy. The coordinator's ADMIN_TOKEN got HTTP 200 out of the
// same API in the same window and confirmed a single heavy scheduler. What had
// failed was the credential typed into that tab — and the page had turned
// "you are not authorized to ask" into "the answer is: broken", in red, as a
// confirmed finding, beneath a question about the site's health.
//
// Below it the cockpit printed "Cockpit failed to load: Admin API error 403"
// and the sentinels printed "can't confirm the sentinel ran". One rejected
// string, a screenful of red, none of it about the site.
//
// ── THE TWO MECHANISMS ───────────────────────────────────────────────────────
//
// 1. `adminFetchJSON` threw a bare `Error` whose message was the only record of
//    the status, and three pages mapped `error → "critical"` without looking at
//    it. A 401/403 and a 500 were the same event.
//
// 2. `AdminAuthProvider` takes any non-empty string into in-memory state — the
//    server is the only judge, correctly — but nothing could put it back. No
//    sign-out, no "change secret", and the failing page never said that a
//    reload clears it. A wrong secret was a dead tab.
//
// ── WHAT IS ASSERTED, AND THE ONE LINK THAT IS NOT ───────────────────────────
//
// The chain: a 403 response → a typed error → classified as auth, not fault →
// the header draws `unauthorized` and not Critical → the recovery control is
// on screen → the state transition it performs → the prompt drawn from THAT
// state says the secret was rejected.
//
// The one link no test here covers is the browser dispatching the click, and
// that is a property of this suite, not a gap chosen for convenience: there is
// no jsdom and no testing-library in this project, and render tests are
// `renderToStaticMarkup`, which discards handlers. That is why
// `lib/adminAuthState.ts` exists as pure functions — the transition is asserted
// directly rather than inferred from a button being present. /admin is
// auth-gated and no lane can sign in, so under notice 49 this closes on tests
// plus rendered output, with no LOOK owed.
//
// ── WHAT MUST NOT REGRESS INTO A BYPASS ──────────────────────────────────────
//
// The last two tests are the security half: nothing validates a secret on the
// client, and nothing persists one. A "helpful" future change that pre-checks
// the secret locally, or remembers it so the reader is not re-prompted, would
// pass every test above it.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { AdminApiError, isAdminAuthError } from "@/lib/adminFetch";
import { adminErrorStatus, adminErrorSummary } from "@/lib/adminHealthStatus";
import {
  ADMIN_AUTH_INITIAL,
  adminAuthClear,
  adminAuthSubmit,
} from "@/lib/adminAuthState";
import AdminSecretPrompt from "@/components/admin/AdminSecretPrompt";
import PageHeader from "@/components/admin/PageHeader";

describe("#6024 a 403 is classified as a credential failure, not a fault", () => {
  it("carries the status instead of burying it in the message", () => {
    const err = new AdminApiError(403, "Invalid admin secret");
    expect(err.status).toBe(403);
    expect(err.body).toBe("Invalid admin secret");
    // Still an Error: every existing `error.message` call site is unaffected.
    expect(err).toBeInstanceOf(Error);
    expect(err.message).toContain("403");
  });

  it.each([401, 403])("treats %i as an auth failure", (status) => {
    expect(isAdminAuthError(new AdminApiError(status, ""))).toBe(true);
  });

  it.each([400, 404, 429, 500, 502, 503])(
    "does NOT treat %i as an auth failure",
    (status) => {
      // The narrowing is the whole point. If 500 ever classified as auth, a
      // real outage would render as "check your secret" and hide itself.
      expect(isAdminAuthError(new AdminApiError(status, ""))).toBe(false);
    }
  );

  it("does not guess from an untyped error", () => {
    // A plain Error whose text happens to mention 403 is not evidence.
    expect(isAdminAuthError(new Error("Admin API error 403: nope"))).toBe(false);
    expect(isAdminAuthError(new TypeError("Failed to fetch"))).toBe(false);
    expect(isAdminAuthError(undefined)).toBe(false);
    expect(isAdminAuthError(null)).toBe(false);
    expect(isAdminAuthError("403")).toBe(false);
  });
});

describe("#6024 the header stops answering a health question it could not ask", () => {
  it("gives a 403 the unauthorized state, not critical", () => {
    expect(adminErrorStatus(new AdminApiError(403, "Invalid admin secret"))).toBe(
      "unauthorized"
    );
  });

  it("leaves every other failure critical", () => {
    expect(adminErrorStatus(new AdminApiError(500, "boom"))).toBe("critical");
    expect(adminErrorStatus(new Error("Failed to fetch"))).toBe("critical");
  });

  it("replaces the diagnostic string with a sentence that says whose problem it is", () => {
    const summary = adminErrorSummary(new AdminApiError(403, "Invalid admin secret"));
    // This is the literal text of Alex's screenshot. It must not survive.
    expect(summary).not.toContain("Admin API error");
    expect(summary).not.toContain("403");
    expect(summary.toLowerCase()).toContain("rejected");
    // And it must not leave the impression the site is in trouble.
    expect(summary.toLowerCase()).toContain("not bad");
  });

  it("passes a real fault's message through untouched", () => {
    expect(adminErrorSummary(new AdminApiError(500, "worker pool exhausted"))).toContain(
      "worker pool exhausted"
    );
  });

  it("renders `unauthorized` as a neutral non-verdict, never the word Critical", () => {
    const html = renderToStaticMarkup(
      <PageHeader
        question="Is the system healthy?"
        status="unauthorized"
        summary={adminErrorSummary(new AdminApiError(403, "Invalid admin secret"))}
        ideal="All workers healthy, quota on budget, all sources reporting."
      />
    );
    expect(html).toContain("Not authorized");
    expect(html).not.toContain("Critical");
    // Neutral, not red: the danger token is what made it read as a finding.
    expect(html).not.toContain("accent-danger");
  });

  it("still draws Critical when the system really is critical", () => {
    // The narrowing must not have softened the state it was narrowed out of.
    const html = renderToStaticMarkup(
      <PageHeader
        question="Is the system healthy?"
        status="critical"
        summary="Critical task failures: poll_kalshi_markets"
        ideal="All workers healthy."
      />
    );
    expect(html).toContain("Critical");
    expect(html).toContain("accent-danger");
  });
});

describe("#6024 a rejected secret is clearable and re-enterable", () => {
  it("starts with no secret and no accusation", () => {
    expect(ADMIN_AUTH_INITIAL).toEqual({ secret: null, rejected: false });
  });

  it("clearing on a 403 drops the secret AND marks why the prompt is back", () => {
    // This is the recovery itself. Before #6024 there was no transition here at
    // all: a wrong secret stayed in state until the tab was reloaded.
    expect(adminAuthClear({ rejected: true })).toEqual({
      secret: null,
      rejected: true,
    });
  });

  it("a deliberate swap accuses nothing", () => {
    expect(adminAuthClear()).toEqual({ secret: null, rejected: false });
    expect(adminAuthClear({})).toEqual({ secret: null, rejected: false });
  });

  it("re-entering clears the rejection and holds the new secret", () => {
    expect(adminAuthSubmit("  s3cret  ")).toEqual({
      secret: "s3cret",
      rejected: false,
    });
  });

  it("the prompt drawn from the rejected state says the secret was refused, and clears the site of blame", () => {
    const { rejected } = adminAuthClear({ rejected: true });
    const html = renderToStaticMarkup(
      <AdminSecretPrompt rejected={rejected} onSubmit={() => {}} />
    );
    expect(html).toContain("rejected by the server");
    expect(html).toContain("nothing is wrong with the site");
    // And it is a usable prompt, not just a message.
    expect(html).toContain('type="password"');
    expect(html).toContain("Enter");
  });

  it("the ordinary prompt does not accuse a secret that was never entered", () => {
    const html = renderToStaticMarkup(
      <AdminSecretPrompt rejected={false} onSubmit={() => {}} />
    );
    expect(html).not.toContain("rejected");
    expect(html).toContain('type="password"');
  });
});

describe("#6024 the recovery does not weaken authorization", () => {
  it("accepts a secret without judging it — the server is the only judge", () => {
    // A client-side verdict on a secret is either useless or a bypass. The
    // submit transition must take whatever was typed and let the API refuse it.
    expect(adminAuthSubmit("obviously-wrong").secret).toBe("obviously-wrong");
    expect(adminAuthSubmit("x").secret).toBe("x");
  });

  it("persists nothing, so a cleared secret is really gone", () => {
    // `adminAuthState` is the whole state of the gate. If it ever reaches
    // storage, "cleared" stops meaning cleared and the in-memory-only ruling
    // (Queue #252 Item 3) is silently reversed.
    const source = require("fs").readFileSync(
      require("path").join(__dirname, "..", "lib", "adminAuthState.ts"),
      "utf8"
    );
    expect(source).not.toMatch(/localStorage|sessionStorage|document\.cookie/);
  });
});
