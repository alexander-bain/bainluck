/**
 * The second token for destructive admin operations (Queue 315 Item 2 / Queue 332 Item 1).
 *
 * Nine directly-destructive routes were wired through `_check_admin_destructive` in
 * Queue 332, and four of them are called from this admin UI: label-pass undo,
 * team-cluster verdict, team-cluster undo, and matching-override delete. They now
 * require `X-Admin-Destructive-Token` in addition to the ordinary admin bearer, so
 * without this module those four buttons would simply 403.
 *
 * WHY sessionStorage AND A PROMPT, rather than the localStorage treatment the admin
 * token gets: the standing ruling is that destructive operations are ATTENDED. A second
 * token persisted next to the first is not a second factor — it is one factor stored
 * twice, and an unattended tab left open would carry full destructive authority for as
 * long as it lived. Holding it per-tab, entered on first destructive use, means the
 * person doing the destroying is present at the moment of destruction, which is the
 * property the ruling is actually about.
 */

const SESSION_KEY = "bainluck_admin_destructive_token";

/**
 * Return the destructive token, prompting once per tab if it is not yet held.
 * Returns `null` when the operator dismisses the prompt — callers must treat that
 * as "do not perform the destructive action" rather than falling back to a
 * single-token request, which would only produce a confusing 403.
 */
export function requireDestructiveToken(): string | null {
  if (typeof window === "undefined") return null;

  const held = window.sessionStorage.getItem(SESSION_KEY);
  if (held) return held;

  const entered = window.prompt(
    "This is a destructive operation and needs the second token.\n\n" +
      "Paste $ADMIN_TOKEN_DESTRUCTIVE (kept for this tab only):"
  );
  const trimmed = (entered || "").trim();
  if (!trimmed) return null;

  window.sessionStorage.setItem(SESSION_KEY, trimmed);
  return trimmed;
}

/** Drop the held token — use after a 403 so a mistyped value can be re-entered. */
export function clearDestructiveToken(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(SESSION_KEY);
}
