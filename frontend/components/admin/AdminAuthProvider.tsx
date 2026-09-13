"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";

import AdminSecretPrompt from "@/components/admin/AdminSecretPrompt";
import {
  ADMIN_AUTH_INITIAL,
  adminAuthClear,
  adminAuthSubmit,
} from "@/lib/adminAuthState";

interface AdminAuthContextValue {
  secret: string;
  /**
   * #6024: drop the secret this tab is holding and go back to the prompt.
   *
   * A secret is accepted into state on nothing but being non-empty — the server
   * is the only judge, and it judges on the first real request. Until this
   * existed there was no way back from a wrong one: every page 403'd, the
   * dashboard called it Critical, and the only recovery was knowing that a
   * reload clears in-memory state. Now the 403 itself offers the way back.
   *
   * `rejected` marks the prompt so it says why it is showing.
   */
  clearSecret: (opts?: { rejected?: boolean }) => void;
}

const AdminAuthContext = createContext<AdminAuthContextValue | null>(null);

export function useAdminAuth(): AdminAuthContextValue {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error("useAdminAuth must be used inside AdminAuthProvider");
  return ctx;
}

export default function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState(ADMIN_AUTH_INITIAL);
  const [checking, setChecking] = useState(true);

  const clearSecret = useCallback(
    (opts?: { rejected?: boolean }) => setAuth(adminAuthClear(opts)),
    []
  );

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

  if (!auth.secret) {
    return (
      <AdminSecretPrompt
        rejected={auth.rejected}
        onSubmit={(value) => setAuth(adminAuthSubmit(value))}
      />
    );
  }

  return (
    <AdminAuthContext.Provider value={{ secret: auth.secret, clearSecret }}>
      {children}
    </AdminAuthContext.Provider>
  );
}
