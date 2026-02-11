/**
 * useAuth - Hook for Firebase authentication state management.
 *
 * Provides reactive auth state, sign-in/sign-out methods,
 * and a getToken() function for authenticated API calls.
 *
 * When Firebase is not configured, all values indicate
 * "not authenticated" and auth methods are no-ops.
 */

"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  isFirebaseConfigured,
  signInWithGoogle as firebaseSignInWithGoogle,
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
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAuthAvailable: boolean;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
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

  // Sign in with Google popup, then register with backend
  const signInWithGoogle = useCallback(async (): Promise<void> => {
    if (!isAuthAvailable) return;

    try {
      const idToken = await firebaseSignInWithGoogle();
      if (idToken) {
        tokenRef.current = idToken;
        await registerWithBackend(idToken);
      }
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
