/**
 * useAuth - Hook for Firebase authentication state management.
 *
 * Provides reactive auth state, sign-in/sign-out methods,
 * and a getToken() function for authenticated API calls.
 *
 * Uses redirect-based sign-in (not popup) to avoid Safari ITP issues.
 * On page load after redirect, checks for redirect result and
 * registers the user with the backend.
 *
 * When Firebase is not configured, all values indicate
 * "not authenticated" and auth methods are no-ops.
 */

"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  isFirebaseConfigured,
  signInWithGoogle as firebaseSignInWithGoogle,
  checkRedirectResult,
  signOut as firebaseSignOut,
  getIdToken,
  onAuthChange,
  type FirebaseUser,
} from "@/lib/firebase";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface AuthUser {
  uid: string;
  email: string | null;
  displayName: string | null;
  photoURL: string | null;
}

interface UseAuthResult {
  /** Current authenticated user (null if not signed in) */
  user: AuthUser | null;
  /** Whether auth state is still loading */
  isLoading: boolean;
  /** Whether the user is authenticated */
  isAuthenticated: boolean;
  /** Whether Firebase Auth is configured (env vars set) */
  isAuthAvailable: boolean;
  /** Sign in with Google (redirects to Google, then back). */
  signInWithGoogle: () => Promise<void>;
  /** Sign out. */
  signOut: () => Promise<void>;
  /** Get a fresh ID token for API calls. Returns null if not authenticated. */
  getToken: () => Promise<string | null>;
}

function mapFirebaseUser(fbUser: FirebaseUser | null): AuthUser | null {
  if (!fbUser) return null;
  return {
    uid: fbUser.uid,
    email: fbUser.email,
    displayName: fbUser.displayName,
    photoURL: fbUser.photoURL,
  };
}

/**
 * Register or update user on backend. Best-effort — doesn't affect
 * client-side auth state if it fails.
 */
async function registerWithBackend(idToken: string): Promise<void> {
  try {
    const response = await fetch(`${API_URL}/api/auth/google`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken }),
    });

    if (!response.ok) {
      const text = await response.text().catch(() => "");
      console.warn(`Backend auth registration failed (${response.status}): ${text}`);
    }
  } catch (backendError) {
    console.warn("Backend auth registration unreachable:", backendError);
  }
}

export function useAuth(): UseAuthResult {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const isAuthAvailable = isFirebaseConfigured();
  const tokenRef = useRef<string | null>(null);
  const redirectChecked = useRef(false);

  // Subscribe to Firebase auth state
  useEffect(() => {
    if (!isAuthAvailable) {
      setIsLoading(false);
      return;
    }

    const unsubscribe = onAuthChange((fbUser) => {
      console.log("[Auth]", fbUser ? `signed in as ${fbUser.email}` : "not signed in");
      setUser(mapFirebaseUser(fbUser));
      setIsLoading(false);
    });

    return unsubscribe;
  }, [isAuthAvailable]);

  // Check for redirect result on page load (after returning from Google)
  useEffect(() => {
    if (!isAuthAvailable || redirectChecked.current) return;
    redirectChecked.current = true;

    checkRedirectResult().then(async (idToken) => {
      if (idToken) {
        console.log("[Auth] Redirect sign-in completed, registering with backend");
        tokenRef.current = idToken;
        await registerWithBackend(idToken);
      }
    });
  }, [isAuthAvailable]);

  // Sign in with Google (redirect — page navigates away)
  const signInWithGoogle = useCallback(async (): Promise<void> => {
    if (!isAuthAvailable) return;
    await firebaseSignInWithGoogle();
  }, [isAuthAvailable]);

  // Sign out
  const signOut = useCallback(async (): Promise<void> => {
    await firebaseSignOut();
    tokenRef.current = null;
    setUser(null);
  }, []);

  // Get fresh token for API calls
  const getToken = useCallback(async (): Promise<string | null> => {
    if (!isAuthAvailable || !user) return null;
    const token = await getIdToken();
    tokenRef.current = token;
    return token;
  }, [isAuthAvailable, user]);

  return {
    user,
    isLoading,
    isAuthenticated: !!user,
    isAuthAvailable,
    signInWithGoogle,
    signOut,
    getToken,
  };
}
