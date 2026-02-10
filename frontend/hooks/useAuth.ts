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
  /** Current authenticated user (null if not signed in) */
  user: AuthUser | null;
  /** Whether auth state is still loading */
  isLoading: boolean;
  /** Whether the user is authenticated */
  isAuthenticated: boolean;
  /** Whether Firebase Auth is configured (env vars set) */
  isAuthAvailable: boolean;
  /** Sign in with Google. Returns true on success. */
  signInWithGoogle: () => Promise<boolean>;
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
      setUser(mapFirebaseUser(fbUser));
      setIsLoading(false);
    });

    return unsubscribe;
  }, [isAuthAvailable]);

  // Sign in with Google
  const signInWithGoogle = useCallback(async (): Promise<boolean> => {
    if (!isAuthAvailable) return false;

    try {
      const idToken = await firebaseSignInWithGoogle();
      if (!idToken) return false; // User cancelled

      // Verify with backend and create/update user
      const response = await fetch(`${API_URL}/api/auth/google`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: idToken }),
      });

      if (!response.ok) {
        console.error("Backend auth verification failed:", response.status);
        await firebaseSignOut();
        return false;
      }

      tokenRef.current = idToken;
      return true;
    } catch (error) {
      console.error("Sign-in error:", error);
      return false;
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
