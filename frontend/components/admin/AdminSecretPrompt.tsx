"use client";

import { useState } from "react";

/**
 * #6024 — the admin secret box, lifted out of `AdminAuthProvider`.
 *
 * It is its own component for two reasons. It now has a second state to draw
 * (the previous secret was rejected), and the provider's own state is only
 * reachable by typing, so a prompt that lives inside the provider cannot be
 * rendered in either state by a test. This one can.
 */
export default function AdminSecretPrompt({
  rejected,
  onSubmit,
}: {
  /** True when this prompt is showing because the server refused the last secret. */
  rejected: boolean;
  onSubmit: (secret: string) => void;
}) {
  const [input, setInput] = useState("");

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-deep px-4">
      <div className="bg-surface-card border border-surface-border rounded-xl p-6 w-full max-w-sm shadow-sm">
        <h2 className="text-base font-semibold text-text-primary mb-1">
          Admin Access
        </h2>
        {rejected ? (
          <p className="text-xs text-accent-warning mb-4">
            That secret was rejected by the server. Check it and enter it again
            — nothing is wrong with the site.
          </p>
        ) : (
          <p className="text-xs text-text-muted mb-4">
            Enter the admin secret to continue. It lives in memory for this tab
            only and is cleared on reload — re-enter each session by design.
          </p>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!input.trim()) return;
            onSubmit(input.trim());
          }}
        >
          <input
            type="password"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Secret"
            autoFocus
            className="w-full px-3 py-2 rounded-lg border border-surface-border bg-surface-elevated text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/40 mb-3"
          />
          <button
            type="submit"
            className="w-full px-4 py-2 rounded-lg bg-text-primary text-text-inverse text-sm font-medium hover:opacity-90 transition-opacity"
          >
            Enter
          </button>
        </form>
      </div>
    </div>
  );
}
