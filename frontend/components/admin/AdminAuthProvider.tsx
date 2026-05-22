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

const STORAGE_KEY = "bainluck_admin_secret";

export function useAdminAuth(): AdminAuthContextValue {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error("useAdminAuth must be used inside AdminAuthProvider");
  return ctx;
}

export default function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [secret, setSecret] = useState<string | null>(null);
  const [input, setInput] = useState("");

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      setSecret(stored);
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get("secret");
    if (fromUrl) {
      localStorage.setItem(STORAGE_KEY, fromUrl);
      setSecret(fromUrl);
    }
  }, []);

  if (!secret) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-deep px-4">
        <div className="bg-surface-card border border-surface-border rounded-xl p-6 w-full max-w-sm shadow-sm">
          <h2 className="text-base font-semibold text-text-primary mb-1">
            Admin Access
          </h2>
          <p className="text-xs text-text-muted mb-4">
            Enter the admin secret to continue.
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
