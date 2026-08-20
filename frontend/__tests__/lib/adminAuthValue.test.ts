// Queue 386 Item 2 (Alex ruling 2026-08-20) — the admin auth context value.
//
// Two of the four fields here are security properties, not presentation, and
// both are asserted in BOTH directions (gotcha #43):
//
//  1. `secret` NEVER carries a session JWT. Twenty admin call sites read it and
//     some build query strings with it; a JWT there is a 30-day credential in
//     browser history, the Referer header and the access log — the leak Queue
//     #252 Item 3 removed `?secret=` to close.
//  2. `identityAdmin` means "running WITHOUT a pasted token". It drives whether
//     the UI offers token entry, so the both-present case must read as the
//     token case or the way back to token-only tools disappears.

import { deriveAdminAuthValue } from "../../lib/adminAuthValue";

const JWT = "eyJhbGciOiJIUzI1NiJ9.session.jwt";
const TOKEN = "pasted-admin-token";

describe("deriveAdminAuthValue (Queue 386 Item 2)", () => {
  test("identity session: no secret, identityAdmin, JWT is the bearer", () => {
    const v = deriveAdminAuthValue({
      secret: null,
      identityToken: JWT,
      identityEmail: "alex@example.com",
    });
    expect(v.secret).toBe("");
    expect(v.identityAdmin).toBe(true);
    expect(v.authToken).toBe(JWT);
    expect(v.identityEmail).toBe("alex@example.com");
  });

  test("pasted token: identityAdmin is false and the token is the bearer", () => {
    const v = deriveAdminAuthValue({
      secret: TOKEN,
      identityToken: null,
      identityEmail: null,
    });
    expect(v.secret).toBe(TOKEN);
    expect(v.identityAdmin).toBe(false);
    expect(v.authToken).toBe(TOKEN);
  });

  test("both present: the pasted token wins and identityAdmin goes false", () => {
    // The stronger credential, and the one the person explicitly chose. If
    // identityAdmin stayed true here the UI would keep offering token entry to
    // someone who already entered a token.
    const v = deriveAdminAuthValue({
      secret: TOKEN,
      identityToken: JWT,
      identityEmail: "alex@example.com",
    });
    expect(v.secret).toBe(TOKEN);
    expect(v.identityAdmin).toBe(false);
    expect(v.authToken).toBe(TOKEN);
  });

  test("the session JWT never reaches `secret`, in any combination", () => {
    // The invariant stated as a sweep rather than as one case, because the way
    // this breaks is someone "simplifying" secret to `secret ?? identityToken`.
    for (const secret of [null, TOKEN]) {
      for (const identityToken of [null, JWT]) {
        const v = deriveAdminAuthValue({
          secret,
          identityToken,
          identityEmail: null,
        });
        expect(v.secret).not.toBe(JWT);
        expect(v.secret).not.toContain("eyJ");
      }
    }
  });

  test("neither credential: empty strings, not undefined", () => {
    // Call sites do `if (authToken)` and `Bearer ${secret}`. `undefined` would
    // stringify into the header as the literal text "undefined".
    const v = deriveAdminAuthValue({
      secret: null,
      identityToken: null,
      identityEmail: null,
    });
    expect(v.secret).toBe("");
    expect(v.authToken).toBe("");
    expect(v.identityAdmin).toBe(false);
  });
});
