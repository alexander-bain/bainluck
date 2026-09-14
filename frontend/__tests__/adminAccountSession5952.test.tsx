/**
 * #5952 — /admin opens on the Google account already signed into Bain Luck.
 *
 * There is no jsdom in this project's jest setup and component tests render
 * with `renderToStaticMarkup`, so the clickable half of the provider is not
 * reachable here. That is exactly why the decisions live in pure modules:
 * `lib/adminAccountSession.ts` decides whether a server answer is a grant, and
 * `lib/adminAuthState.ts` decides what the tab holds afterwards. Both are
 * asserted directly, and the components are asserted to draw what they produce.
 *
 * The bar these tests are written against: it must be impossible to open the
 * dashboard without the server having said `authorized: true` for this token.
 */

import { renderToStaticMarkup } from "react-dom/server";

import {
  hasStoredAccountSession,
  probeAdminAccount,
  readWhoami,
} from "@/lib/adminAccountSession";
import {
  ADMIN_AUTH_INITIAL,
  adminAuthAccount,
  adminAuthClear,
  adminAuthRefreshToken,
  adminAuthSubmit,
} from "@/lib/adminAuthState";
import AdminSecretPrompt from "@/components/admin/AdminSecretPrompt";

const ALEX = "alex.bain@gmail.com";
const TOKEN = "google-account-id-token";

/** A server that authorizes, and records what it was asked. */
function authorizingServer(email: string | null = ALEX) {
  const seen: string[] = [];
  return {
    seen,
    whoami: async (token: string) => {
      seen.push(token);
      return { authorized: true, method: "account", email };
    },
  };
}

/** A server that refuses, the way `adminFetchJSON` refuses: by throwing. */
function refusingServer(status = 403) {
  return {
    whoami: async () => {
      throw Object.assign(new Error(`Admin API error ${status}`), { status });
    },
  };
}

describe("#5952 the browser asks the server, and never decides for itself", () => {
  it("a signed-in admin account yields a session with no password typed", async () => {
    const server = authorizingServer();
    const session = await probeAdminAccount({
      getToken: async () => TOKEN,
      whoami: server.whoami,
    });

    expect(session).toEqual({ token: TOKEN, email: ALEX });
    // And the token it validated is the token it will send.
    expect(server.seen).toEqual([TOKEN]);
  });

  it("a signed-in reader who is not an admin gets nothing", async () => {
    const session = await probeAdminAccount({
      getToken: async () => "an-ordinary-readers-token",
      whoami: refusingServer(403).whoami,
    });

    expect(session).toBeNull();
  });

  it("a signed-out browser is never even asked", async () => {
    let asked = false;
    const session = await probeAdminAccount({
      getToken: async () => null,
      whoami: async () => {
        asked = true;
        return { authorized: true };
      },
    });

    expect(session).toBeNull();
    expect(asked).toBe(false);
  });

  it("an unreachable API is not an admin session", async () => {
    const session = await probeAdminAccount({
      getToken: async () => TOKEN,
      whoami: async () => {
        throw new TypeError("Failed to fetch");
      },
    });

    expect(session).toBeNull();
  });

  it("a token that cannot be minted is not an admin session", async () => {
    const session = await probeAdminAccount({
      getToken: async () => {
        throw new Error("firebase unavailable");
      },
      whoami: async () => ({ authorized: true, email: ALEX }),
    });

    expect(session).toBeNull();
  });
});

describe("#5952 only an explicit server grant opens the dashboard", () => {
  // This block is the fail-open seam. Every case here is a 200 — the request
  // succeeded — and none of them is an authorization.
  it.each([
    ["an unrelated JSON document", { events: [] }],
    ["a body that forgot the field", { method: "account", email: ALEX }],
    ["authorized as a truthy string", { authorized: "true", email: ALEX }],
    ["authorized as 1", { authorized: 1, email: ALEX }],
    ["authorized: false but an admin email", { authorized: false, email: ALEX }],
    ["a bare email", { email: ALEX }],
    ["null", null],
    ["a string", "authorized"],
    ["an array", [{ authorized: true }]],
  ])("%s does not grant admin", (_label, body) => {
    expect(readWhoami(body, TOKEN)).toBeNull();
  });

  it("the one shape that does grant is `authorized: true`", () => {
    expect(readWhoami({ authorized: true, email: ALEX }, TOKEN)).toEqual({
      token: TOKEN,
      email: ALEX,
    });
  });

  it("an authorized answer with no email still grants — the email is display only", () => {
    expect(readWhoami({ authorized: true }, TOKEN)).toEqual({
      token: TOKEN,
      email: null,
    });
    expect(readWhoami({ authorized: true, email: "" }, TOKEN)).toEqual({
      token: TOKEN,
      email: null,
    });
  });
});

describe("#5952 the tab's credential state", () => {
  it("an account session carries the token as the bearer and the email as a label", () => {
    expect(adminAuthAccount(TOKEN, ALEX)).toEqual({
      secret: TOKEN,
      mode: "account",
      email: ALEX,
      rejected: false,
    });
  });

  it("the secret path is untouched and stays labelled as the secret path", () => {
    expect(ADMIN_AUTH_INITIAL.mode).toBe("secret");
    expect(adminAuthSubmit("s3cret").mode).toBe("secret");
    expect(adminAuthSubmit("s3cret").email).toBeNull();
  });

  it("a refreshed token replaces the bearer, keeping the session", () => {
    const before = adminAuthAccount(TOKEN, ALEX);
    const after = adminAuthRefreshToken(before, "a-fresher-token");

    expect(after.secret).toBe("a-fresher-token");
    expect(after.mode).toBe("account");
    expect(after.email).toBe(ALEX);
  });

  it("a refresh NEVER upgrades a typed secret into an account session", () => {
    // The trap this guards: the reader typed the secret, then a timer left over
    // from a previous account session fires with a token. Silently swapping the
    // credential under them would make the sidebar lie about who they are and
    // would send a token they did not choose to send.
    const typed = adminAuthSubmit("s3cret");
    expect(adminAuthRefreshToken(typed, "a-fresh-account-token")).toBe(typed);

    const prompt = adminAuthClear();
    expect(adminAuthRefreshToken(prompt, "a-fresh-account-token")).toBe(prompt);
  });

  it("a refresh with nothing to refresh is inert", () => {
    const session = adminAuthAccount(TOKEN, ALEX);
    expect(adminAuthRefreshToken(session, null)).toBe(session);
    expect(adminAuthRefreshToken(session, TOKEN)).toBe(session);
  });

  it("signing out of admin returns to the prompt and drops the identity", () => {
    expect(adminAuthClear()).toEqual({
      secret: null,
      mode: "secret",
      email: null,
      rejected: false,
    });
  });
});

describe("#5952 the SDK is not loaded to discover there is no session", () => {
  const store: Record<string, string> = {};

  beforeAll(() => {
    // These suites run in jest's node environment: there is no `window`, and
    // `hasStoredAccountSession` returns false without one. Stubbing only
    // `localStorage` made the two positive cases fail for the SSR reason rather
    // than the reason under test — a passing assertion about the wrong thing.
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: globalThis,
    });
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: {
        getItem: (k: string) => (k in store ? store[k] : null),
        setItem: (k: string, v: string) => {
          store[k] = v;
        },
        removeItem: (k: string) => {
          delete store[k];
        },
      },
    });
  });

  beforeEach(() => {
    for (const k of Object.keys(store)) delete store[k];
  });

  it("is false for a browser that has never signed in", () => {
    expect(hasStoredAccountSession("marker", "backend")).toBe(false);
  });

  it("is true on the previously-signed-in marker", () => {
    store.marker = "true";
    expect(hasStoredAccountSession("marker", "backend")).toBe(true);
  });

  it("is true on a stored backend session (the Safari path)", () => {
    store.backend = JSON.stringify({ uid: "u", idToken: "t" });
    expect(hasStoredAccountSession("marker", "backend")).toBe(true);
  });

  it("a marker set to anything but true is not a session", () => {
    store.marker = "false";
    expect(hasStoredAccountSession("marker", "backend")).toBe(false);
  });
});

describe("#5952 the reader is never asked for a password they do not have", () => {
  it("the prompt still exists for the secret path and still works", () => {
    // The ship removes the SECOND password for Alex; it does not remove the
    // secret, which is what a lane or a second machine uses.
    const html = renderToStaticMarkup(
      <AdminSecretPrompt rejected={false} onSubmit={() => {}} />
    );
    expect(html).toContain('type="password"');
  });

  it("no module in the account path ever reads a password field", () => {
    // A structural assertion, because the bug it forbids would be invisible in
    // behaviour: an account path that also collected a secret would satisfy
    // every other test here while defeating the entire point of the issue.
    const fs = require("fs") as typeof import("fs");
    const path = require("path") as typeof import("path");
    const source = fs.readFileSync(
      path.join(__dirname, "..", "lib", "adminAccountSession.ts"),
      "utf8"
    );
    // Comments first. The module's own docstring explains that it holds no
    // allowlist and asks for no password, so a raw substring scan matches the
    // prose that promises the opposite of what it is looking for — it failed on
    // the correct implementation. Only executable text can answer this.
    const code = source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
    expect(code).not.toMatch(/password/i);
    expect(code).not.toContain("ADMIN_TOKEN");
    // ...and it forms no opinion of its own about who is an admin.
    expect(code).not.toContain("@gmail");
    expect(code).not.toMatch(/allowlist/i);
    // Guards the guard: stripping must not have emptied the file.
    expect(code).toContain("export async function probeAdminAccount");
  });
});
