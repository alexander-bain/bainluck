"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import { getIdToken, onAuthChange } from "@/lib/firebase";
import { deriveAdminAuthValue } from "@/lib/adminAuthValue";
import {
  NO_ADMIN_IDENTITY,
  adminIdentityAfterAuthChange,
  adminIdentityAfterProbe,
  adminIdentityEpochAfterAuthChange,
  adminIdentityProbeIsCurrent,
  stampAdminIdentityProbe,
  type AdminIdentityEpochState,
  type AdminIdentityProbeStamp,
  type AdminIdentityState,
} from "@/lib/adminIdentitySession";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AdminAuthContextValue {
  /**
   * The pasted ADMIN_TOKEN, or `""` when the session is admin BY IDENTITY.
   *
   * Semantics are deliberately unchanged from before Queue 386 Item 2: this is
   * the shared admin token and nothing else. A session JWT is never assigned
   * here, for two reasons — pages that gate on `if (!secret)` keep their honest
   * current behaviour, and no page can accidentally put a JWT into a query
   * string, which is exactly how `?secret=` leaked through browser history and
   * the Referer header (Queue #252 Item 3).
   */
  secret: string;
  /** True when the signed-in user carries the server-side admin role. */
  identityAdmin: boolean;
  /** The email of the identity admin, when known. */
  identityEmail: string | null;
  /**
   * The bearer to send on admin requests: the pasted token when there is one,
   * otherwise the session JWT. Pages opt into identity auth by reading THIS
   * instead of `secret`.
   */
  authToken: string;
}

const AdminAuthContext = createContext<AdminAuthContextValue | null>(null);

export function useAdminAuth(): AdminAuthContextValue {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error("useAdminAuth must be used inside AdminAuthProvider");
  return ctx;
}

interface WhoAmI {
  is_admin?: boolean;
  via?: string | null;
  email?: string | null;
}

export default function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [secret, setSecret] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [checking, setChecking] = useState(true);
  // Identity admin (Queue 386 Item 2, Alex ruling 2026-08-20).
  //
  // ONE piece of state, not three (Queue 390, C-2063-REVIEW finding 1 — P1).
  // The token, the email and the UID they belong to are a single fact about a
  // single session, and splitting them is what let the credential outlive the
  // principal: there were two setters, no owner, and nothing that could clear
  // them together. Bundled, "whose credential is this?" is answerable, and the
  // reducer in lib/adminIdentitySession.ts is the only thing that answers it.
  const [identity, setIdentity] =
    useState<AdminIdentityState>(NO_ADMIN_IDENTITY);
  const identityToken = identity.token;
  const identityEmail = identity.email;
  const authEpochRef = useRef<AdminIdentityEpochState>({
    epoch: 0,
    uid: null,
  });
  const [showTokenEntry, setShowTokenEntry] = useState(false);

  useEffect(() => {
    let cancelled = false;

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

    // Identity probe. /api/admin/whoami deliberately answers 200 with
    // is_admin:false rather than 403, so "not an admin" and "the API is down"
    // stay distinguishable here instead of collapsing into one prompt.
    //
    // No auto-restore of the TOKEN from storage: it must be re-entered each
    // session. Identity is different in kind — it is the browser's existing
    // sign-in, not a credential this app persisted.
    const probe = async (stamp: AdminIdentityProbeStamp) => {
      try {
        const token = await getIdToken();
        if (
          cancelled ||
          !adminIdentityProbeIsCurrent(authEpochRef.current, stamp)
        ) {
          return;
        }
        if (token) {
          const res = await fetch(`${API_URL}/api/admin/whoami`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!cancelled && res.ok) {
            const data: WhoAmI = await res.json();
            if (!cancelled && data.is_admin && data.via === "identity") {
              const granted: AdminIdentityState = {
                uid: stamp.uid,
                token,
                email: data.email ?? null,
              };
              setIdentity((current) =>
                adminIdentityAfterProbe(
                  current,
                  authEpochRef.current,
                  stamp,
                  granted,
                ),
              );
            }
          }
        }
      } catch {
        // Any failure here falls back to the secret prompt. An identity probe
        // that cannot complete must never be able to GRANT access — only to
        // skip a prompt it could not justify skipping.
      }
    };

    // Bind the credential to the LIVE principal (Queue 390, finding 1).
    //
    // The old effect probed once with `[]` deps and stopped. The provider is
    // mounted under the persistent /admin layout, so the header's `signOut()`
    // runs while it stays alive: Firebase and backend storage were cleared, the
    // React state holding the bearer was not, and that bearer kept authorizing
    // labeling for the full 30-day token life. `onAuthChange` now also fires on
    // BACKEND-ONLY sign-out (see lib/firebase.ts), which is the path Firebase
    // itself cannot report.
    //
    // Clearing is synchronous and happens BEFORE any re-probe: the window
    // between "we know the session changed" and "we know what it changed to"
    // must not be a window in which the old credential is still emitted.
    let unsubscribe: (() => void) | null = null;
    let lastUid: string | null | undefined; // undefined = no emission yet

    onAuthChange((user) => {
      if (cancelled) return;
      const uid = user?.uid ?? null;
      const first = lastUid === undefined;
      const changed = !first && uid !== lastUid;
      lastUid = uid;

      // The epoch is the authorization boundary, not a timing optimization.
      // Logout and account switch both advance it before state is cleared, so
      // even an already-arriving whoami response from the old principal cannot
      // restore its bearer. Same-principal refresh emissions preserve it.
      authEpochRef.current = adminIdentityEpochAfterAuthChange(
        authEpochRef.current,
        uid,
      );

      setIdentity((current) => adminIdentityAfterAuthChange(current, uid));

      if (first || changed) {
        // Re-probe for the NEW principal. A uid is not a grant — only the
        // server knows whether it holds the admin role.
        if (uid) {
          const stamp = stampAdminIdentityProbe(authEpochRef.current);
          if (!stamp) {
            if (!cancelled) setChecking(false);
            return;
          }
          void probe(stamp).then(() => {
            if (!cancelled) setChecking(false);
          });
          return;
        }
      }
      if (!cancelled) setChecking(false);
    })
      .then((unsub) => {
        if (cancelled) {
          unsub();
          return;
        }
        unsubscribe = unsub;
      })
      .catch(() => {
        // Subscription failure must not strand the UI on the loading state.
        if (!cancelled) setChecking(false);
      });

    return () => {
      cancelled = true;
      authEpochRef.current = {
        epoch: authEpochRef.current.epoch + 1,
        uid: null,
      };
      unsubscribe?.();
    };
  }, []);

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-deep">
        <div className="text-sm text-text-muted animate-pulse">Loading admin...</div>
      </div>
    );
  }

  const tokenEntryForm = (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!input.trim()) return;
        setSecret(input.trim());
        setInput("");
        setShowTokenEntry(false);
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
  );

  if (!secret && !identityToken) {
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
          {tokenEntryForm}
        </div>
      </div>
    );
  }

  const value: AdminAuthContextValue = deriveAdminAuthValue({
    secret,
    identityToken,
    identityEmail,
  });

  return (
    <AdminAuthContext.Provider value={value}>
      {/*
        Identity mode reaches the pages that read `authToken`. Tools still wired
        to the token-only `secret` need the real thing, so the way in stays one
        click away rather than one reload away.
      */}
      {value.identityAdmin && (
        <div className="text-xs text-text-muted border-b border-surface-border px-4 py-2 flex flex-wrap items-center gap-x-2 gap-y-1">
          <span>
            Signed in as{" "}
            <span className="text-text-secondary font-medium">
              {identityEmail || "admin"}
            </span>{" "}
            — admin by identity.
          </span>
          {showTokenEntry ? (
            <span className="w-full max-w-xs pt-2">{tokenEntryForm}</span>
          ) : (
            <button
              type="button"
              onClick={() => setShowTokenEntry(true)}
              className="underline hover:text-text-secondary cursor-pointer"
            >
              Enter admin token
            </button>
          )}
        </div>
      )}
      {children}
    </AdminAuthContext.Provider>
  );
}
