// #1279 V1 — the "Sign in with email" control is DELETED from UserMenu.
//
// Alex ruled "delete it permanently" (2026-08-28). The backend half is
// `backend/tests/integration/test_route_auth_email_signin_deleted.py`: the
// endpoint that minted a 30-day session token from an email address alone is
// gone from the router and its `ENABLE_INSECURE_EMAIL_SIGN_IN` opt-in with it.
// This file is the half a person can see — the menu item that pointed at it.
//
// ── WHY THIS RENDERS INSTEAD OF GREPPING ──
//
// The obvious guard is `expect(source).not.toContain("Sign in with email")`,
// and it is the guard that does not work. A source scan stays green when the
// string moves to a constant, an i18n key, or a child component — and it stays
// green when the component stops rendering at all, which is the failure a
// deletion test is least able to notice. So the component is rendered and the
// assertion is made against the markup a reader would receive.
//
// ── WHY IT RENDERS 32 TIMES ──
//
// The control was two clicks deep: `showProviders` gates the provider menu and
// `showEmailInput` gates the input inside it, so the default render shows
// neither and a single render proves nothing. Rather than hard-code "force the
// second useState" — which passes silently the day someone reorders the hooks —
// this walks the component's entire boolean state space: every subset of the
// `useState(false)` hooks is forced true in turn, and the assertion is made
// against all 32 resulting markups at once. Reordering the hooks cannot hide a
// state from it, and adding one only widens the sweep.
//
// The control (gotcha #43, both directions) is that Google and Apple must still
// paint in that sweep. Without it, a component that threw, returned null, or
// lost its whole dropdown would satisfy every "email is absent" assertion here.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as fs from "fs";
import * as path from "path";

jest.mock("@/components/AuthProvider", () => ({
  useAuthContext: () => mockAuth,
}));
jest.mock("@/lib/firebase", () => ({ preloadFirebaseAuth: () => {} }));

let mockAuth: Record<string, unknown> = {};

import UserMenu from "../../components/UserMenu";

const SIGNED_OUT = {
  user: null,
  isAuthenticated: false,
  isAuthAvailable: true,
  authError: null,
  signInWithGoogle: async () => {},
  signInWithApple: async () => {},
  signOut: async () => {},
  getToken: async () => null,
  isLoading: false,
};

/**
 * Render `UserMenu` once per subset of its `useState(false)` hooks, with the
 * hooks in that subset initialised to `true`.
 *
 * Only boolean-`false` hooks are flipped: `emailInput` holds a string, and
 * forcing `true` into it would render a state the component can never reach.
 */
function renderEveryBooleanState(): string[] {
  const realUseState = React.useState;

  // Discovery pass: how many hooks are there, and which start as `false`?
  const initials: unknown[] = [];
  let probe = jest
    .spyOn(React, "useState")
    .mockImplementation(((init?: unknown) => {
      initials.push(init);
      return (realUseState as (i?: unknown) => [unknown, unknown])(init);
    }) as typeof React.useState);
  renderToStaticMarkup(React.createElement(UserMenu));
  probe.mockRestore();

  const flippable = initials
    .map((v, i) => (v === false ? i : -1))
    .filter((i) => i >= 0);

  expect(flippable.length).toBeGreaterThanOrEqual(2);

  const markups: string[] = [];
  for (let mask = 0; mask < 1 << flippable.length; mask++) {
    const forced = new Set(
      flippable.filter((_, bit) => (mask >> bit) & 1),
    );
    let call = -1;
    const spy = jest
      .spyOn(React, "useState")
      .mockImplementation(((init?: unknown) => {
        call += 1;
        const value = forced.has(call) ? true : init;
        return (realUseState as (i?: unknown) => [unknown, unknown])(value);
      }) as typeof React.useState);
    try {
      markups.push(renderToStaticMarkup(React.createElement(UserMenu)));
    } finally {
      spy.mockRestore();
    }
  }
  return markups;
}

describe("UserMenu, signed out: every reachable state", () => {
  let markups: string[];
  let all: string;

  beforeAll(() => {
    mockAuth = SIGNED_OUT;
    markups = renderEveryBooleanState();
    all = markups.join("\n<<<RENDER BOUNDARY>>>\n");
  });

  it("renders the supported providers somewhere in the sweep (control)", () => {
    // If this fails, every absence assertion below is vacuous.
    expect(markups.some((m) => m.includes("Continue with Google"))).toBe(true);
    expect(markups.some((m) => m.includes("Continue with Apple"))).toBe(true);
    // The sweep reaches the busy state too, where the trigger reads
    // "Signing in..." — so the trigger is asserted by role, not by its label.
    expect(markups.every((m) => m.includes('aria-haspopup="true"'))).toBe(true);
  });

  it("never offers to sign the reader in with an email address", () => {
    expect(all).not.toContain("Sign in with email");
    expect(all.toLowerCase()).not.toContain("email address");
  });

  it("paints no email input anywhere", () => {
    expect(all).not.toContain('type="email"');
  });

  it("keeps the rest of the menu intact (control)", () => {
    expect(markups.some((m) => m.includes("About Bain Luck"))).toBe(true);
  });
});

describe("UserMenu, signed in", () => {
  it("still renders the account menu, and still has no email sign-in", () => {
    mockAuth = {
      ...SIGNED_OUT,
      isAuthenticated: true,
      user: {
        uid: "u1",
        email: "someone@example.com",
        displayName: "Someone",
        photoURL: null,
      },
    };
    const markups = renderEveryBooleanState();
    const all = markups.join("\n");
    expect(markups.some((m) => m.includes("Preferences"))).toBe(true);
    expect(markups.some((m) => m.includes("Sign out"))).toBe(true);
    expect(all).not.toContain("Sign in with email");
    expect(all).not.toContain('type="email"');
  });
});

// ---------------------------------------------------------------------------
// The call chain behind the button — the half a render cannot see.
//
// `renderToStaticMarkup` proves the control is not painted. It cannot prove the
// function it called is gone, because a dead export paints nothing. These read
// the source, which is the right instrument for "this symbol does not exist"
// and the wrong one for "this text is not shown" — hence both halves.
// ---------------------------------------------------------------------------

const read = (...parts: string[]) =>
  fs.readFileSync(path.join(__dirname, "..", "..", ...parts), "utf8");

describe("the signInWithEmail call chain is gone", () => {
  it.each([
    ["lib/firebase.ts", ["signInWithEmail", "email-sign-in"]],
    ["hooks/useAuth.ts", ["signInWithEmail"]],
    ["components/AuthProvider.tsx", ["signInWithEmail"]],
    ["components/UserMenu.tsx", ["signInWithEmail", "emailInput", "showEmailInput"]],
  ])("%s carries none of its symbols", (file, needles) => {
    const src = read(...file.split("/"));
    for (const needle of needles as string[]) {
      expect(src).not.toContain(needle);
    }
    // Control: the file was actually read and is not empty.
    expect(src.length).toBeGreaterThan(200);
  });

  it("the OAuth entry points survive in the same files (control)", () => {
    expect(read("lib", "firebase.ts")).toContain("signInWithGoogle");
    expect(read("hooks", "useAuth.ts")).toContain("signInWithApple");
    expect(read("components", "AuthProvider.tsx")).toContain("signInWithGoogle");
  });
});
