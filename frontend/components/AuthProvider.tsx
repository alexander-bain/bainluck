/**
 * AuthProvider - React context for authentication state.
 *
 * Wraps the app and provides auth state to all components via useAuthContext().
 * Integrates with the analytics provider to set user identity on login.
 * Wires up the API client auth token getter for authenticated requests.
 */

"use client";

import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useAuth, type AuthUser } from "@/hooks/useAuth";
import { useAnalyticsContext } from "@/components/Analytics/AnalyticsProvider";
import { setAuthTokenGetter } from "@/lib/api";

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAuthAvailable: boolean;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const analytics = useAnalyticsContext();

  // Wire up the API client's auth token getter
  useEffect(() => {
    if (auth.isAuthenticated) {
      setAuthTokenGetter(auth.getToken);
    } else {
      setAuthTokenGetter(null);
    }

    return () => {
      setAuthTokenGetter(null);
    };
  }, [auth.isAuthenticated, auth.getToken]);

  // Sync auth state with analytics
  useEffect(() => {
    if (auth.isLoading) return;

    if (auth.user) {
      analytics.setUser(auth.user.uid);
    } else {
      analytics.setUser(undefined);
    }
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
