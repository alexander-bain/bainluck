/**
 * useAuth - Hook for Firebase authentication state management.
 *
 * Provides reactive auth state, sign-in/sign-out methods,
 * and a getToken() function for authenticated API calls.
 *
 * Performance optimization: Firebase SDK (~200KB) is only loaded when
 * there's a previously-signed-in user (localStorage marker) or when
 * the user explicitly clicks Sign In. Anonymous visitors pay zero
 * Firebase cost on initial page load.
 *
 * LAT-P206 — and now they pay zero cost for our OWN Firebase glue either.
 * The gate below ("no previous sign-in ⇒ don't touch Firebase") was already
 * here, but it was a decision taken by code that had already been downloaded:
 * a static import of `@/lib/firebase` put the Google popup flow, the Apple
 * popup flow, the GIS script loader, the backend custom-token exchange and the
 * sign-out path into the entry chunk of every page, `/` included. The two
 * questions this hook must answer during render — is auth configured, is there
 * a stored backend session — come from `@/lib/authLocal`, which is env vars and
 * one localStorage read. Everything else is `await import("@/lib/firebase")`,
 * reached only down a path this hook has already decided to take.
 *
 * Why the deferral is real rather than a byte shuffle (the LAT-P205 rule: a
 * deferral is only a cut if the branch is UNREACHABLE on a cold load):
 *   - the mount effect returns before `onAuthChange` when there is no
 *     `bainluck_previouslySignedIn` marker and no stored backend session,
 *     which is every first-run reader `/` is graded on;
 *   - `signInWithGoogle` / `signInWithApple` / `signOut` need a click;
 *   - `getToken` returns null unless `user` is already set.
 * The chunk is therefore absent from a cold run's fetch list, not merely absent
 * from the entry set — `cold-load.mjs` prints that list and it was checked.
 *
 * Popup blockers: the sign-in path is warmed one tap early. `UserMenu` calls
 * `preloadFirebaseAuth()` when the provider dropdown OPENS, which now pulls
 * this chunk as well as the SDK, so the provider click still finds both
 * resident and `signInWithPopup` is not preceded by a fresh network wait.
 *
 * When Firebase is not configured, all values indicate
 * "not authenticated" and auth methods are no-ops.
 */

"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { getBackendAuthUser, isFirebaseConfigured } from "@/lib/authLocal";
import type { FirebaseUser } from "@/lib/firebase";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// localStorage key indicating user has previously signed in.
// When absent, Firebase SDK loading is deferred until explicit sign-in.
const SIGNED_IN_MARKER = "bainluck_previouslySignedIn";

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
  authError: string | null;
  signInWithGoogle: () => Promise<void>;
  signInWithApple: () => Promise<void>;
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

/**
 * Check if user has previously signed in (localStorage marker).
 * Safe for SSR — returns false when window is undefined.
 */
function hasPreviouslySignedIn(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem(SIGNED_IN_MARKER) === "true";
  } catch {
    return false;
  }
}

function setSignedInMarker(value: boolean): void {
  if (typeof window === "undefined") return;
  try {
    if (value) {
      localStorage.setItem(SIGNED_IN_MARKER, "true");
    } else {
      localStorage.removeItem(SIGNED_IN_MARKER);
    }
  } catch {
    // localStorage unavailable (private browsing, etc.)
  }
}

export function useAuth(): UseAuthResult {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const isAuthAvailable = isFirebaseConfigured();
  const tokenRef = useRef<string | null>(null);

  // Subscribe to Firebase auth state.
  //
  // Performance optimization: If the user has never signed in before
  // (no localStorage marker), skip Firebase SDK loading entirely.
  // This saves ~200KB parse + 200-300ms for anonymous visitors.
  // The SDK will be loaded on-demand when they click Sign In.
  useEffect(() => {
    if (!isAuthAvailable) {
      setIsLoading(false);
      return;
    }

    // Check for backend auth data first (Safari ITP fallback)
    const backendUser = getBackendAuthUser();
    if (backendUser) {
      setUser({
        uid: backendUser.uid,
        email: backendUser.email,
        displayName: backendUser.displayName,
        photoURL: backendUser.photoURL,
      });
      setIsLoading(false);
      setSignedInMarker(true);
      // Still subscribe to Firebase for token refresh, but don't block
    }

    // If no previous sign-in, skip Firebase SDK loading
    if (!hasPreviouslySignedIn() && !backendUser) {
      console.log("[Auth] No previous sign-in detected, deferring Firebase SDK");
      setIsLoading(false);
      return;
    }

    // User has previously signed in — load Firebase and subscribe.
    // This is the one place the heavy module is reached without a click, and
    // it is below the early return above, so a first-run reader never gets here.
    let unsubscribe: (() => void) | null = null;
    let cancelled = false;

    import("@/lib/firebase").then(({ onAuthChange }) =>
      onAuthChange((fbUser) => {
        if (cancelled) return;
        console.log("[Auth]", fbUser ? `signed in as ${fbUser.email}` : "not signed in");
        if (fbUser) {
          setUser(mapFirebaseUser(fbUser));
          setSignedInMarker(true);
        } else {
          const backendFallback = getBackendAuthUser();
          if (backendFallback) {
            console.log("[Auth] Firebase says null but backend auth is valid — keeping session for", backendFallback.email);
          } else {
            setUser(null);
          }
        }
        setIsLoading(false);
      })
    ).then((unsub) => {
      if (cancelled) {
        unsub();
      } else {
        unsubscribe = unsub;
      }
    });

    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, [isAuthAvailable]);

  // Sign in with Google popup, then register with backend
  const signInWithGoogle = useCallback(async (): Promise<void> => {
    if (!isAuthAvailable) return;
    setAuthError(null);

    try {
      const { signInWithGoogle: firebaseSignInWithGoogle } = await import("@/lib/firebase");
      const idToken = await firebaseSignInWithGoogle();
      if (idToken) {
        tokenRef.current = idToken;
        setSignedInMarker(true);

        registerWithBackend(idToken);

        const backendUser = getBackendAuthUser();
        if (backendUser) {
          console.log("[Auth] Setting user state from backend auth:", backendUser.email);
          setUser({
            uid: backendUser.uid,
            email: backendUser.email,
            displayName: backendUser.displayName,
            photoURL: backendUser.photoURL,
          });
        }
      } else {
        setAuthError("Sign-in didn't complete. Please try again.");
      }
    } catch (error) {
      console.error("[Auth] Sign-in error:", error);
      const msg = error instanceof Error ? error.message : "Unknown error";
      if (msg.includes("popup_closed") || msg.includes("popup closed")) {
        setAuthError("Sign-in was cancelled. Please try again.");
      } else if (msg.includes("popup_blocked") || msg.includes("blocked")) {
        setAuthError("Pop-up was blocked. Please allow pop-ups for this site.");
      } else {
        setAuthError("Sign-in failed. Please try again.");
      }
    }
  }, [isAuthAvailable]);

  // Sign in with Apple popup, then register with backend
  const signInWithApple = useCallback(async (): Promise<void> => {
    if (!isAuthAvailable) return;

    try {
      const {
        signInWithApple: firebaseSignInWithApple,
        getCurrentFirebaseUser,
      } = await import("@/lib/firebase");
      const idToken = await firebaseSignInWithApple();
      if (idToken) {
        tokenRef.current = idToken;
        setSignedInMarker(true);

        // Register with backend (best-effort, don't block user state update)
        registerWithBackend(idToken);

        // Try backend auth data first (Safari ITP fallback)
        const backendUser = getBackendAuthUser();
        if (backendUser) {
          console.log("[Auth] Setting user state from backend auth (Apple):", backendUser.email);
          setUser({
            uid: backendUser.uid,
            email: backendUser.email,
            displayName: backendUser.displayName,
            photoURL: backendUser.photoURL,
          });
        } else {
          // signInWithPopup succeeded — read user directly from Firebase Auth.
          // onAuthStateChanged may not be subscribed yet (first-time sign-in
          // defers Firebase SDK loading), so we read currentUser directly.
          const fbUser = await getCurrentFirebaseUser();
          if (fbUser) {
            console.log("[Auth] Setting user state from Firebase currentUser (Apple):", fbUser.email);
            setUser(mapFirebaseUser(fbUser));
          }
        }
      }
    } catch (error) {
      console.error("[Auth] Apple sign-in error:", error);
    }
  }, [isAuthAvailable]);

  // Sign out
  const signOut = useCallback(async (): Promise<void> => {
    const { signOut: firebaseSignOut } = await import("@/lib/firebase");
    await firebaseSignOut();
    tokenRef.current = null;
    setUser(null);
    setSignedInMarker(false);
  }, []);

  // Get fresh token for API calls
  const getToken = useCallback(async (): Promise<string | null> => {
    if (!isAuthAvailable || !user) return null;
    const { getIdToken } = await import("@/lib/firebase");
    const token = await getIdToken();
    tokenRef.current = token;
    return token;
  }, [isAuthAvailable, user]);

  return {
    user,
    isLoading,
    isAuthenticated: !!user,
    isAuthAvailable,
    authError,
    signInWithGoogle,
    signInWithApple,
    signOut,
    getToken,
  };
}
