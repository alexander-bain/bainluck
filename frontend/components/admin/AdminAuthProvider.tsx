"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import { getAuth, onAuthStateChanged } from "firebase/auth";

interface AdminAuthContextValue {
  secret: string;
}

const AdminAuthContext = createContext<AdminAuthContextValue | null>(null);

const STORAGE_KEY = "bainluck_admin_secret";

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
    // 1. Check localStorage
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      setSecret(stored);
      setChecking(false);
      return;
    }

    // SECURITY (Queue #252 Item 3): the ?secret= URL-param path is removed.
    // A secret in the URL leaks via browser history, the Referer header, and
    // shared links, and was being persisted straight into localStorage. The
    // admin token must be entered once via the form below (or already present in
    // localStorage). If a stale ?secret= is present in the URL, strip it so it
    // does not linger in history for this tab.
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

    // 2. Check if user is signed in via Firebase — auto-use stored secret
    try {
      const auth = getAuth();
      const unsub = onAuthStateChanged(auth, (user) => {
        if (user) {
          // Signed-in user — check if we have a secret stored from a prior session
          const s = localStorage.getItem(STORAGE_KEY);
          if (s) setSecret(s);
        }
        setChecking(false);
      });
      return unsub;
    } catch {
      setChecking(false);
    }
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
            Enter the admin secret to continue. This only needs to be done once.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!input.trim()) return;
              localStorage.setItem(STORAGE_KEY, input.trim());
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
