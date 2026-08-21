// Queue 390 — C-2063-REVIEW finding 1 (P1): the admin bearer captured at mount
// outlives the session that justified it.
//
// The defect: `AdminAuthProvider` probes `/api/admin/whoami` ONCE in a
// mount-time effect with `[]` deps, stores the bearer in React state, never
// subscribes to auth changes, and has no path that clears it. The provider is
// mounted under the persistent `/admin` layout, so the real header `UserMenu`
// can call `signOut()` while it stays mounted — and the old bearer keeps
// authorizing labeling afterwards. The reviewer replayed a real 30-day backend
// session token across the logout boundary: it verified before, and verified
// unchanged after (`exp - iat = 2,592,000`).
//
// WHY THIS TESTS A REDUCER AND NOT THE COMPONENT, said plainly rather than
// discovered later: this suite runs `testEnvironment: 'node'` with no jsdom and
// no @testing-library, and `renderToStaticMarkup` does not run effects — so
// there is no way here to mount a provider, fire an auth change and observe
// state. Rather than write a test that asserts the shape of the fix (which is
// what a source-scan alone would be), the credential lifecycle is extracted into
// a pure module that CAN be exhaustively tested, and a structural test below
// pins the provider to it. The reducer holds the decision; the component holds
// only the wiring.

import {
  NO_ADMIN_IDENTITY,
  adminIdentityAfterAuthChange,
  type AdminIdentityState,
} from "@/lib/adminIdentitySession";

const SIGNED_IN: AdminIdentityState = {
  uid: "firebase-uid-alex",
  token: "alex.session.jwt",
  email: "alex@example.com",
};

describe("adminIdentityAfterAuthChange", () => {
  it("clears the captured bearer on logout", () => {
    // THE specimen. Before this fix the provider had no code path that could
    // reach this state at all.
    expect(adminIdentityAfterAuthChange(SIGNED_IN, null)).toEqual(
      NO_ADMIN_IDENTITY,
    );
  });

  it("clears the captured bearer when the account switches", () => {
    // admin -> civilian, without an intervening logout. The old bearer must not
    // survive into a session that did not earn it.
    expect(
      adminIdentityAfterAuthChange(SIGNED_IN, "firebase-uid-someone-else"),
    ).toEqual(NO_ADMIN_IDENTITY);
  });

  it("does not emit the old bearer once cleared, even on a repeat null", () => {
    const cleared = adminIdentityAfterAuthChange(SIGNED_IN, null);
    expect(adminIdentityAfterAuthChange(cleared, null)).toEqual(
      NO_ADMIN_IDENTITY,
    );
    expect(adminIdentityAfterAuthChange(cleared, null).token).toBeNull();
  });

  // ---- the other direction (gotcha #43) ----
  //
  // A reducer that cleared unconditionally would pass every assertion above and
  // log Alex out on every auth-state emission — Firebase fires one on load, on
  // token refresh, and on tab focus. That is a broken feature wearing a security
  // fix's clothes.

  it("keeps a live session when the SAME principal re-emits", () => {
    expect(adminIdentityAfterAuthChange(SIGNED_IN, SIGNED_IN.uid)).toEqual(
      SIGNED_IN,
    );
  });

  it("returns the identical object for an unchanged principal", () => {
    // Referential stability matters: the provider puts this in context, and a
    // fresh object on every token refresh would re-render every admin page.
    expect(adminIdentityAfterAuthChange(SIGNED_IN, SIGNED_IN.uid)).toBe(
      SIGNED_IN,
    );
  });

  it("stays empty when there was never an identity", () => {
    expect(adminIdentityAfterAuthChange(NO_ADMIN_IDENTITY, null)).toBe(
      NO_ADMIN_IDENTITY,
    );
  });

  it("does not invent an identity when a signed-out provider sees a uid", () => {
    // A uid arriving is not a grant. Only a whoami probe can grant, because only
    // the server knows whether that uid holds the admin role.
    expect(
      adminIdentityAfterAuthChange(NO_ADMIN_IDENTITY, "firebase-uid-alex"),
    ).toEqual(NO_ADMIN_IDENTITY);
  });
});

// --------------------------------------------------------------------------
// The wiring. Without this, every assertion above could pass against a module
// nothing imports — the reducer would be correct and the provider still broken.
// This is the one thing a node-environment suite genuinely cannot observe
// behaviourally, so it is read from the source rather than asserted about it.
// --------------------------------------------------------------------------

import { readFileSync } from "fs";
import { join } from "path";

describe("AdminAuthProvider is bound to the live principal", () => {
  const source = readFileSync(
    join(__dirname, "../../components/admin/AdminAuthProvider.tsx"),
    "utf8",
  );

  it("subscribes to auth changes", () => {
    expect(source).toContain("onAuthChange");
  });

  it("routes every identity transition through the reducer", () => {
    expect(source).toContain("adminIdentityAfterAuthChange");
  });

  it("no longer holds the token in a setter that nothing can clear", () => {
    // The shipped shape was `setIdentityToken` / `setIdentityEmail`: two
    // independent setters, no owner, and no path that reset either.
    expect(source).not.toContain("setIdentityToken");
    expect(source).not.toContain("setIdentityEmail");
  });

  it("unsubscribes on unmount", () => {
    expect(source).toMatch(/unsubscribe\?\.\(\)|unsub\(\)/);
  });
});

describe("backend-only sign-out is observable", () => {
  const source = readFileSync(
    join(__dirname, "../../lib/firebase.ts"),
    "utf8",
  );

  it("clearBackendAuth notifies subscribers", () => {
    // The Safari-ITP path has no Firebase user, so onAuthStateChanged never
    // fires for it. Without an explicit notification a backend-only sign-out is
    // completely silent — which is how the revoked admin kept labeling.
    const clearFn = source.slice(
      source.indexOf("function clearBackendAuth"),
      source.indexOf("function clearBackendAuth") + 400,
    );
    expect(clearFn).toContain("notifyBackendAuthChange");
  });

  it("onAuthChange registers a backend-auth listener and removes it", () => {
    expect(source).toContain("backendAuthListeners.add");
    expect(source).toContain("backendAuthListeners.delete");
  });
});
