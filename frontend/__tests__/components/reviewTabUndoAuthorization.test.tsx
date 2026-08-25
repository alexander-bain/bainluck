/**
 * #2178 — the web ReviewTab's judgment undo opened NEITHER authorization door.
 *
 * `DELETE /api/admin/ranking-judgments/{id}` authorizes two ways, and the two
 * are MUTUALLY EXCLUSIVE in the `Authorization` header, so one request cannot
 * attempt both:
 *
 *   * OWNER    — `Authorization: Bearer <the USER's token>`, no admin credential
 *   * OPERATOR — `Authorization: Bearer <ADMIN_TOKEN>` + `X-Admin-Destructive-Token`
 *
 * The shipped call sent ADMIN_TOKEN in `Authorization` (so the server could not
 * resolve an identity — owner door shut) and omitted the destructive header
 * (operator door shut). Every undo on web 403'd. Because the result was never
 * `.ok`-checked, the UI popped the history entry anyway: the undo LOOKED like it
 * worked while the row stayed in the database.
 *
 * ## What this asserts against, and why it is not the component
 *
 * The frontend jest environment is `node` with **no jsdom** (every component
 * test here uses `renderToStaticMarkup`), so a guard cannot render ReviewTab,
 * press `u`, and read the wire. The two-door sequence therefore lives in
 * `lib/judgmentUndo.ts` (ruling 005, extract-on-touch) and this calls the REAL
 * function with the REAL `adminFetch` in the path — so the header the server
 * reads is the header under test. A guard that rebuilt the request itself would
 * assert against a copy of the logic, and a copy is precisely what let this ship
 * unnoticed.
 *
 * The load-bearing case is `never sends the #2178 shape`: it fails on the exact
 * request the bug sent, whichever door a future refactor happens to prefer.
 */
import { deleteRankingJudgment } from "@/lib/judgmentUndo";
import { DESTRUCTIVE_TOKEN_HEADER } from "@/lib/adminFetch";

const API_URL = "http://api.test";
const ADMIN_TOKEN = "ADMIN_TOKEN_VALUE";
const USER_TOKEN = "user-session-token";
const JUDGMENT_ID = 4242;

interface Recorded {
  url: string;
  method: string;
  headers: Record<string, string>;
}

let recorded: Recorded[] = [];
let clearDestructiveToken: jest.Mock;
let requireDestructiveToken: jest.Mock;

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

/** Responses are consumed in order, one per request. */
function installFetch(responses: Response[]) {
  const queue = [...responses];
  global.fetch = jest.fn(async (url: unknown, init?: RequestInit) => {
    recorded.push({
      url: String(url),
      method: (init?.method || "GET").toUpperCase(),
      headers: { ...((init?.headers as Record<string, string>) || {}) },
    });
    return queue.shift() || jsonResponse({ status: "deleted" });
  }) as unknown as typeof fetch;
}

function headerOf(r: Recorded, name: string): string | undefined {
  const key = Object.keys(r.headers).find(
    (k) => k.toLowerCase() === name.toLowerCase()
  );
  return key ? r.headers[key] : undefined;
}

function deps() {
  return {
    apiUrl: API_URL,
    secret: ADMIN_TOKEN,
    getIdToken: async () => USER_TOKEN,
    requireDestructiveToken,
    clearDestructiveToken,
  };
}

beforeEach(() => {
  recorded = [];
  clearDestructiveToken = jest.fn();
  requireDestructiveToken = jest.fn();
});

describe("#2178 judgment undo — the two authorization doors", () => {
  it("takes the OWNER door with the user's token, not ADMIN_TOKEN", async () => {
    installFetch([jsonResponse({ status: "deleted", id: JUDGMENT_ID })]);

    const outcome = await deleteRankingJudgment(JUDGMENT_ID, deps());

    expect(outcome).toEqual({ ok: true, via: "owner" });
    expect(recorded).toHaveLength(1);
    expect(recorded[0].method).toBe("DELETE");
    expect(recorded[0].url).toBe(
      `${API_URL}/api/admin/ranking-judgments/${JUDGMENT_ID}`
    );

    // The whole point: the USER's token, which is what lets the server resolve
    // an identity. This is the header `APIClient.swift` sends from the phone.
    expect(headerOf(recorded[0], "Authorization")).toBe(`Bearer ${USER_TOKEN}`);
    expect(headerOf(recorded[0], "Authorization")).not.toContain(ADMIN_TOKEN);

    // The owner door is not an attended destructive operation, so it must not
    // cost a prompt.
    expect(requireDestructiveToken).not.toHaveBeenCalled();
    expect(headerOf(recorded[0], DESTRUCTIVE_TOKEN_HEADER)).toBeUndefined();
  });

  it("falls back to the OPERATOR door, actually sending the destructive header", async () => {
    requireDestructiveToken.mockReturnValue("DESTRUCTIVE_VALUE");
    installFetch([
      jsonResponse({ detail: "Invalid admin secret" }, 403), // owner door shut
      jsonResponse({ status: "deleted", id: JUDGMENT_ID }), // operator door open
    ]);

    const outcome = await deleteRankingJudgment(JUDGMENT_ID, deps());

    expect(outcome).toEqual({ ok: true, via: "operator" });
    expect(recorded).toHaveLength(2);

    const operator = recorded[1];
    expect(operator.method).toBe("DELETE");
    expect(headerOf(operator, "Authorization")).toBe(`Bearer ${ADMIN_TOKEN}`);
    // The header whose absence was half the bug.
    expect(headerOf(operator, DESTRUCTIVE_TOKEN_HEADER)).toBe("DESTRUCTIVE_VALUE");
  });

  it("never sends the #2178 shape: ADMIN_TOKEN with no destructive header", async () => {
    requireDestructiveToken.mockReturnValue("DESTRUCTIVE_VALUE");
    installFetch([
      jsonResponse({ detail: "Invalid admin secret" }, 403),
      jsonResponse({ status: "deleted", id: JUDGMENT_ID }),
    ]);

    await deleteRankingJudgment(JUDGMENT_ID, deps());

    expect(recorded.length).toBeGreaterThan(0);
    for (const req of recorded) {
      const auth = headerOf(req, "Authorization") || "";
      const destructive = headerOf(req, DESTRUCTIVE_TOKEN_HEADER);
      const carriesIdentity = auth !== "" && !auth.includes(ADMIN_TOKEN);
      // Every request must open one door or the other. The bug's request opened
      // neither, and no test noticed.
      expect(carriesIdentity || Boolean(destructive)).toBe(true);
    }
  });

  it("keeps the OWNERSHIP refusal rather than the credential error", async () => {
    // The operator escalation is declined, so nothing is removed — and the
    // sentence the reader gets is the one that says WHY.
    requireDestructiveToken.mockReturnValue(null);
    const ownership =
      "This judgment was recorded by another reviewer, or is not yours to remove.";
    installFetch([jsonResponse({ detail: ownership }, 403)]);

    const outcome = await deleteRankingJudgment(JUDGMENT_ID, deps());

    expect(outcome.ok).toBe(false);
    expect(outcome).toMatchObject({ detail: ownership });
    expect(recorded).toHaveLength(1);
  });

  it("reports a refusal instead of reporting success — the row is still there", async () => {
    requireDestructiveToken.mockReturnValue("WRONG_VALUE");
    installFetch([
      jsonResponse({ detail: "Invalid admin secret" }, 403),
      jsonResponse({ detail: "destructive token mismatch" }, 403),
    ]);

    const outcome = await deleteRankingJudgment(JUDGMENT_ID, deps());

    // `ok: false` is the contract the component keys its local state off. The
    // old code had no such value to read, which is why a 403 still popped the
    // history entry and the undo looked like it had worked.
    expect(outcome.ok).toBe(false);
    // A rejected second token is dropped so a mistyped value can be re-entered
    // rather than wedging the tab.
    expect(clearDestructiveToken).toHaveBeenCalled();
  });

  it("goes straight to the operator door when nobody is signed in", async () => {
    requireDestructiveToken.mockReturnValue("DESTRUCTIVE_VALUE");
    installFetch([jsonResponse({ status: "deleted", id: JUDGMENT_ID })]);

    const outcome = await deleteRankingJudgment(JUDGMENT_ID, {
      ...deps(),
      getIdToken: async () => null,
    });

    expect(outcome).toEqual({ ok: true, via: "operator" });
    // No identity to present, so no pointless owner attempt.
    expect(recorded).toHaveLength(1);
    expect(headerOf(recorded[0], DESTRUCTIVE_TOKEN_HEADER)).toBe("DESTRUCTIVE_VALUE");
  });

  it("surfaces the server's own sentence when the body is not JSON", async () => {
    requireDestructiveToken.mockReturnValue("DESTRUCTIVE_VALUE");
    const notJson = {
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("not json");
      },
    } as unknown as Response;
    installFetch([notJson, notJson]);

    const outcome = await deleteRankingJudgment(JUDGMENT_ID, deps());

    expect(outcome).toEqual({ ok: false, detail: "Undo failed (500)." });
  });
});
