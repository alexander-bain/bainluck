/**
 * useAuth - Hook for Firebase authentication state management.
 *
 * Provides reactive auth state, sign-in/sign-out methods,
 * and a getToken() function for authenticated API calls.
 *
 * Uses popup-first auth with redirect fallback for Safari.
 * On page load, checks for redirect result and registers with backend.
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
  /** Sign in with Google (popup, with redirect fallback). */
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
      console.warn(`[Auth] Backend registration failed (${response.status}): ${text}`);
    } else {
      console.log("[Auth] Backend registration succeeded");
    }
  } catch (backendError) {
    console.warn("[Auth] Backend unreachable:", backendError);
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

  // Sign in with Google (popup with redirect fallback)
  const signInWithGoogle = useCallback(async (): Promise<void> => {
    if (!isAuthAvailable) return;

    try {
      const idToken = await firebaseSignInWithGoogle();

      // If popup succeeded (idToken returned), register with backend
      if (idToken) {
        tokenRef.current = idToken;
        await registerWithBackend(idToken);
      }
      // If null, either user cancelled or redirect is happening
    } catch (error) {
      console.error("[Auth] Sign-in error:", error);
    }
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
