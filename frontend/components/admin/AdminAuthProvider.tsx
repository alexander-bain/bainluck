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
  adminAuthAccount,
  adminAuthClear,
  adminAuthRefreshToken,
  adminAuthSubmit,
  type AdminAuthMode,
} from "@/lib/adminAuthState";
import {
  hasStoredAccountSession,
  probeAdminAccount,
} from "@/lib/adminAccountSession";
import { adminFetchJSON } from "@/lib/adminFetch";
import { BACKEND_AUTH_KEY } from "@/lib/firebase";
import { SIGNED_IN_MARKER } from "@/hooks/useAuth";

/** How often the account token is re-minted. Firebase ID tokens last an hour. */
const ACCOUNT_TOKEN_REFRESH_MS = 10 * 60 * 1000;

interface AdminAuthContextValue {
  secret: string;
  /** Which credential this tab is presenting — `account` since #5952. */
  mode: AdminAuthMode;
  /** The signed-in admin's email as the SERVER resolved it, or null. Display only. */
  email: string | null;
  /**
   * #6024: drop the credential this tab is holding and go back to the prompt.
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

    // #5952: before falling back to the prompt, ask the server whether the
    // account this browser is already signed in with is an admin. This is the
    // ship — Alex opens /admin and it opens, with no second password.
    //
    // The typed secret is still here and still works: it is what a lane, a
    // second machine, or Alex-with-no-session uses, and it is the fallback for
    // every way the account path can say no. Nothing about the account path is
    // persisted either; the token is minted fresh from the account session on
    // each load, which is what makes a reload survive without storing anything.
    let cancelled = false;
    (async () => {
      try {
        if (hasStoredAccountSession(SIGNED_IN_MARKER, BACKEND_AUTH_KEY)) {
          const session = await probeAdminAccount({
            getToken: async () => (await import("@/lib/firebase")).getIdToken(),
            whoami: (token) => adminFetchJSON("/api/admin/whoami", token),
          });
          if (!cancelled && session) {
            setAuth(adminAuthAccount(session.token, session.email));
          }
        }
      } finally {
        // ALWAYS, on every path. `checking` renders "Loading admin..." and
        // nothing else clears it, so anything that escapes this block — a
        // chunk that fails to load, a rejected dynamic import, a future edit
        // that adds an unguarded await — strands the reader on a spinner with
        // no prompt and no error. The prompt is the safe resting state; the
        // account path is an optimisation on top of it, and an optimisation
        // must never be able to take the fallback down with it.
        if (!cancelled) setChecking(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  // #5952: keep the account token fresh. A Firebase ID token expires in an
  // hour and /admin is a tab that stays open all day; without this the
  // dashboard would start 403ing mid-afternoon and read as a rejected
  // credential. `getIdToken` returns the cached token until it is near expiry,
  // so this is almost always free. `adminAuthRefreshToken` is a no-op unless
  // the tab is actually on the account path.
  useEffect(() => {
    if (auth.mode !== "account" || !auth.secret) return;
    let cancelled = false;

    const refresh = async () => {
      try {
        const token = await (await import("@/lib/firebase")).getIdToken();
        if (!cancelled) setAuth((prev) => adminAuthRefreshToken(prev, token));
      } catch {
        // A failed refresh is not a failed session: the current token is still
        // valid until it is not, and the server is the one that decides.
      }
    };

    const timer = setInterval(refresh, ACCOUNT_TOKEN_REFRESH_MS);
    // Coming back to a tab left open past the token's life is the common case,
    // so refresh on focus too rather than waiting out the interval.
    window.addEventListener("focus", refresh);
    return () => {
      cancelled = true;
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [auth.mode, auth.secret]);

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
    <AdminAuthContext.Provider
      value={{
        secret: auth.secret,
        mode: auth.mode,
        email: auth.email,
        clearSecret,
      }}
    >
      {children}
    </AdminAuthContext.Provider>
  );
}
