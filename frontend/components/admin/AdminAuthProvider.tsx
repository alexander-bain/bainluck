"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from "react";

interface AdminAuthContextValue {
  secret: string;
}

const AdminAuthContext = createContext<AdminAuthContextValue | null>(null);

export function useAdminAuth(): AdminAuthContextValue {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error("useAdminAuth must be used inside AdminAuthProvider");
  return ctx;
}

export default function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [secret, setSecret] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    // SECURITY (Queue #252 Item 3, C-ADHOC-4): admin token is in-memory only.
    // It is NEVER written to localStorage or sessionStorage — it lives in
    // React state for this tab session and is lost on reload by design (that's
    // the feature: no persistent credential on disk, no cross-tab leakage).
    // The prior localStorage persistence (bainluck_admin_secret) is removed.
    // Defensively clear any stale persisted copy left by the pre-existing
    // shared provider (a0368f76 → 05189102) so old browsers do not retain it.
    try {
      localStorage.removeItem("bainluck_admin_secret");
      sessionStorage.removeItem("bainluck_admin_secret");
    } catch {
      // no-op: storage may be unavailable, but in-memory secret still works
    }

    // Strip any stale ?secret= left in the URL (leaks via history/Referer).
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.has("secret")) {
        params.delete("secret");
        const clean =
          window.location.pathname +
          (params.toString() ? `?${params.toString()}` : "") +
          window.location.hash;
        window.history.replaceState(null, "", clean);
      }
    } catch {
      // no-op: URL cleanup is best-effort
    }

    // No auto-restore from storage: token must be re-entered each session.
    // Firebase auth state does NOT restore the admin secret (separate credential).
    setChecking(false);
  }, []);

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-deep">
        <div className="text-sm text-text-muted animate-pulse">Loading admin...</div>
      </div>
    );
  }

  if (!secret) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-deep px-4">
        <div className="bg-surface-card border border-surface-border rounded-xl p-6 w-full max-w-sm shadow-sm">
          <h2 className="text-base font-semibold text-text-primary mb-1">
            Admin Access
          </h2>
          <p className="text-xs text-text-muted mb-4">
            Enter the admin secret to continue. It lives in memory for this tab
            only and is cleared on reload — re-enter each session by design.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!input.trim()) return;
              setSecret(input.trim());
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

  return (
    <AdminAuthContext.Provider value={{ secret }}>
      {children}
    </AdminAuthContext.Provider>
  );
}
