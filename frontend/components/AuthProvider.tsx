/**
 * AuthProvider - React context for authentication state.
 *
 * Wraps the app and provides auth state to all components via useAuthContext().
 * Integrates with the analytics provider to set user identity on login.
 * Wires up the API client auth token getter for authenticated requests.
 */

"use client";

import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";
import { useAuth, type AuthUser } from "@/hooks/useAuth";
import { useAnalyticsContext } from "@/components/Analytics/AnalyticsProvider";
import { setAuthTokenGetter } from "@/lib/api";

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAuthAvailable: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithApple: () => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const analytics = useAnalyticsContext();

  // Wire up the API client's auth token getter DURING RENDER (not in useEffect).
  //
  // Why: React fires child effects before parent effects. If we set the token
  // getter in a useEffect, SWR's initial fetch in a child component (e.g.,
  // MyTeamsFeed) fires BEFORE this effect runs, causing the first API request
  // to go without an auth token. By setting it during render, the token getter
  // is available before any child effects fire.
  //
  // This is safe because setAuthTokenGetter just assigns a module-level
  // variable — no DOM mutations or observable side effects.
  setAuthTokenGetter(auth.isAuthenticated ? auth.getToken : null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      setAuthTokenGetter(null);
    };
  }, []);

  // Sync auth state with analytics and track login/logout
  const prevUserRef = useRef<string | null>(null);
  useEffect(() => {
    if (auth.isLoading) return;

    const prevUid = prevUserRef.current;
    const currentUid = auth.user?.uid ?? null;

    if (auth.user) {
      analytics.setUser(auth.user.uid);
      if (prevUid === null && currentUid !== null) {
        analytics.track('login', { method: 'firebase' });
      }
    } else {
      analytics.setUser(undefined);
      if (prevUid !== null && currentUid === null) {
        analytics.track('logout', {});
      }
    }

    prevUserRef.current = currentUid;
  }, [auth.user, auth.isLoading, analytics]);

  return (
    <AuthContext.Provider value={auth}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Hook to access auth context.
 * Must be used within an AuthProvider.
 */
export function useAuthContext(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuthContext must be used within an AuthProvider");
  }
  return context;
}
