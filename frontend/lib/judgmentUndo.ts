/**
 * Undoing a ranking judgment from the web — the two-door DELETE (#2178).
 *
 * ## The two doors, and why one request cannot try both
 *
 * `DELETE /api/admin/ranking-judgments/{id}` authorizes two ways
 * (`admin_judgments.py`, "Two doors, and the reason there are two"):
 *
 *   * **owner** — `Authorization: Bearer <the USER's token>`. The server
 *     resolves an identity and compares it to the row's `reviewer`. No admin
 *     credential is involved, requested, or checked.
 *   * **operator** — `Authorization: Bearer <ADMIN_TOKEN>` **plus** the
 *     `X-Admin-Destructive-Token` header. The strong attended gate.
 *
 * Both doors want the `Authorization` header and want different things in it, so
 * a single request can only ever attempt one. Hence a sequence: owner first,
 * operator as the fallback.
 *
 * ## What #2178 actually was
 *
 * `ReviewTab` sent ADMIN_TOKEN in `Authorization` (so `verify_id_token` could
 * not resolve an identity — owner door shut) and passed no destructive token to
 * `adminFetch`, which sends that header only when a 4th argument is given
 * (operator door shut). Every undo on web 403'd. It opened NEITHER door, which
 * is why it did not read as "wrong credential" to anyone: there was no door it
 * was nearly through.
 *
 * The phone was already right — `APIClient.swift`'s `authTokenProvider`
 * attaches the backend session token — and that half was fixed in UX-P125 item
 * 3a. This module carries the same pattern across to the web.
 *
 * ## Why this is a module and not fifteen lines inside the component
 *
 * Ruling 005, extract-on-touch, for the reason `calibrationPopulation` records:
 * `ReviewTab` is a `"use client"` component behind SWR, the frontend jest
 * environment is `node` with **no jsdom**, so a guard cannot render it, press
 * `u`, and look at the wire. A test that re-implemented the header assembly
 * would assert against a COPY of the logic — and a copy is exactly what let the
 * bug ship unnoticed. Here the guard calls the real function, and `adminFetch`
 * stays in the path so the header the server reads is the header under test.
 *
 * ## The owner door will rarely open FROM THE WEB, and that is not a bug here
 *
 * `ReviewTab`'s submit posts `reviewer: "alex"`. The server resolves only the
 * literal `"native"` to the caller's email, and `_judgment_owner` treats any
 * value without an `@` as unattributed — so a row the web just wrote has no
 * owner and no identity can equal `""`. The owner attempt is still made first:
 * it is the correct and cheapest door for rows that DO have an owner (anything
 * graded from the phone), and leading with it keeps the destructive prompt off
 * that path entirely. Changing what the POST stamps would change who owns every
 * future row — a data-semantics decision, not a client fix.
 */
import { adminFetch } from "./adminFetch";

export type UndoOutcome =
  | { ok: true; via: "owner" | "operator" }
  | { ok: false; detail: string };

export interface UndoDeps {
  /** API origin, e.g. `process.env.NEXT_PUBLIC_API_URL`. */
  apiUrl: string;
  /** ADMIN_TOKEN, used for the OPERATOR door only. */
  secret: string;
  /** The signed-in user's Firebase ID token or backend session token. */
  getIdToken: () => Promise<string | null>;
  /** Prompts once per tab; `null` means the operator declined. */
  requireDestructiveToken: () => string | null;
  /** Drop a rejected token so a mistyped value can be re-entered. */
  clearDestructiveToken: () => void;
}

/** The server's own sentence when it has one — it is more useful than ours. */
async function readDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
  } catch {
    // Not JSON, or an empty body. Fall through to the status line.
  }
  return `Undo failed (${res.status}).`;
}

/**
 * Delete one ranking judgment, trying the owner door and then the operator door.
 *
 * Never throws for an HTTP refusal — a refusal is a value, because the caller
 * has to decide whether to mutate local state and the old code's habit of not
 * looking at all is half of what made #2178 invisible.
 */
export async function deleteRankingJudgment(
  judgmentId: number,
  deps: UndoDeps
): Promise<UndoOutcome> {
  const path = `/api/admin/ranking-judgments/${judgmentId}`;

  // ── Door 1: OWNER. The user's own token, never ADMIN_TOKEN. ──────────────
  let ownerDetail = "";
  const token = await deps.getIdToken();
  if (token) {
    const res = await fetch(`${deps.apiUrl}${path}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) return { ok: true, via: "owner" };
    ownerDetail = await readDetail(res);
  }

  // ── Door 2: OPERATOR. Attended by construction. ──────────────────────────
  const destructiveToken = deps.requireDestructiveToken();
  if (!destructiveToken) {
    // Prefer the owner door's refusal when there was one: "recorded by another
    // reviewer" tells the reader what happened, where the credential error is
    // what sent #2178 hunting for a missing token.
    return {
      ok: false,
      detail: ownerDetail || "Undo needs the second token. Nothing was removed.",
    };
  }

  const res = await adminFetch(
    path,
    deps.secret,
    { method: "DELETE" },
    destructiveToken
  );
  if (res.ok) return { ok: true, via: "operator" };
  if (res.status === 403) deps.clearDestructiveToken();
  return { ok: false, detail: ownerDetail || (await readDetail(res)) };
}
