/**
 * useAuth - Hook for Firebase authentication state management.
 *
 * Provides reactive auth state, a function to initialize the Google
 * Sign-In button, sign-out, and a getToken() function for API calls.
 *
 * When Firebase is not configured, all values indicate
 * "not authenticated" and auth methods are no-ops.
 */

"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  isFirebaseConfigured,
  initGoogleSignInButton,
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
  initGoogleButton: (container: HTMLElement) => void;
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

  // Callback for when Google sign-in returns a Firebase token
  const handleGoogleToken = useCallback(async (idToken: string) => {
    tokenRef.current = idToken;
    await registerWithBackend(idToken);
  }, []);

  // Initialize Google Sign-In button in a container element.
  // Call this with a DOM element ref to render Google's button.
  const initGoogleButton = useCallback(
    (container: HTMLElement) => {
      if (!isAuthAvailable) return;
      initGoogleSignInButton(container, handleGoogleToken).catch((err) => {
        console.error("[Auth] Failed to initialize Google button:", err);
      });
    },
    [isAuthAvailable, handleGoogleToken]
  );

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
    initGoogleButton,
    signOut,
    getToken,
  };
}
