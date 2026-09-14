"use client";

import { Lock } from "lucide-react";

import { useAdminAuth } from "@/components/admin/AdminAuthProvider";

/**
 * #6024 — what an admin page shows when the server refused this tab's secret.
 *
 * The thing it replaces was a red box printing `Admin API error 403: Invalid
 * admin secret` beneath a Critical health badge: a diagnostic string, a wrong
 * verdict, and no way out. This says whose problem it is, says the site is not
 * implicated, and carries the control that fixes it.
 *
 * The button clears the in-memory secret, which returns the whole admin section
 * to the prompt — so it recovers every sub-page at once, not just the one that
 * happened to be open. Nothing is persisted and no request is retried behind
 * the reader's back; the server judges the next secret exactly as it judged
 * this one.
 */
export default function AdminAuthNotice() {
  const { clearSecret, mode, email } = useAdminAuth();
  const onAccount = mode === "account";

  return (
    <div className="flex flex-wrap items-center gap-3 text-sm bg-surface-elevated border border-surface-border rounded-lg p-3">
      <Lock className="w-4 h-4 text-text-muted shrink-0" />
      {/* #5952: on the account path there is no secret to blame, and saying
          there is sends the reader hunting for a password they never entered.
          The likeliest cause by far is a sign-in that has expired. */}
      <span className="text-text-secondary">
        {onAccount
          ? `The ${email ?? "account"} sign-in was not accepted for admin.`
          : "The admin secret entered in this tab was rejected."}{" "}
        Nothing here could be loaded, so none of it is a statement about the
        site.
      </span>
      <button
        type="button"
        onClick={() => clearSecret({ rejected: true })}
        className="px-3 py-1.5 rounded-lg bg-text-primary text-text-inverse text-xs font-medium hover:opacity-90 transition-opacity"
      >
        {onAccount ? "Use the admin secret" : "Re-enter admin secret"}
      </button>
    </div>
  );
}
