/**
 * Firebase configuration and initialization.
 *
 * Firebase Auth is used for Google (and later Apple) Sign-In.
 * The app works fully without Firebase configured — auth features
 * are hidden when env vars are not set.
 *
 * Uses signInWithPopup with signInWithRedirect as fallback
 * for browsers that block cross-origin popup communication (Safari ITP).
 */

import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithRedirect,
  getRedirectResult,
  signOut as firebaseSignOut,
  onAuthStateChanged,
  type Auth,
  type User as FirebaseUser,
} from "firebase/auth";

// Firebase config from environment variables
const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
};

/**
 * Check if Firebase is configured (env vars are set).
 * When not configured, auth UI is hidden and the app works anonymously.
 */
export function isFirebaseConfigured(): boolean {
  return Boolean(
    firebaseConfig.apiKey &&
    firebaseConfig.authDomain &&
    firebaseConfig.projectId
  );
}

// Initialize Firebase app (singleton)
let app: FirebaseApp | null = null;
let auth: Auth | null = null;

function getFirebaseApp(): FirebaseApp | null {
  if (!isFirebaseConfigured()) return null;
  if (app) return app;

  const existingApps = getApps();
  if (existingApps.length > 0) {
    app = existingApps[0];
  } else {
    app = initializeApp(firebaseConfig);
  }
  return app;
}

export function getFirebaseAuth(): Auth | null {
  if (auth) return auth;
  const firebaseApp = getFirebaseApp();
  if (!firebaseApp) return null;
  auth = getAuth(firebaseApp);
  return auth;
}

/**
 * Sign in with Google. Tries popup first, falls back to redirect
 * if popup is blocked (Safari ITP).
 *
 * Returns the Firebase ID token on popup success, or null if
 * falling back to redirect (page navigates away).
 */
export async function signInWithGoogle(): Promise<string | null> {
  const authInstance = getFirebaseAuth();
  if (!authInstance) {
    console.error("[Firebase] Auth not initialized");
    return null;
  }

  const provider = new GoogleAuthProvider();

  // Try popup first
  try {
    console.log("[Firebase] Attempting signInWithPopup...");
    const result = await signInWithPopup(authInstance, provider);
    const idToken = await result.user.getIdToken();
    console.log("[Firebase] Popup sign-in succeeded");
    return idToken;
  } catch (error: unknown) {
    const firebaseError = error as { code?: string };
    const code = firebaseError.code || "";

    // User closed the popup — not an error
    if (code === "auth/popup-closed-by-user" || code === "auth/cancelled-popup-request") {
      console.log("[Firebase] User cancelled popup");
      return null;
    }

    // Popup blocked — fall back to redirect
    if (code === "auth/popup-blocked" || code === "auth/operation-not-supported-in-this-environment") {
      console.log("[Firebase] Popup blocked, falling back to redirect...");
      try {
        await signInWithRedirect(authInstance, provider);
        // Page navigates away — this line won't execute
      } catch (redirectError) {
        console.error("[Firebase] Redirect also failed:", redirectError);
      }
      return null;
    }

    // Some other error
    console.error("[Firebase] Sign-in error:", code, error);
    throw error;
  }
}

/**
 * Check for a redirect result after returning from Google sign-in.
 * Returns the Firebase ID token if a redirect sign-in just completed.
 */
export async function checkRedirectResult(): Promise<string | null> {
  const authInstance = getFirebaseAuth();
  if (!authInstance) return null;

  try {
    const result = await getRedirectResult(authInstance);
    if (result?.user) {
      const idToken = await result.user.getIdToken();
      console.log("[Firebase] Redirect result: signed in as", result.user.email);
      return idToken;
    }
    return null;
  } catch (error: unknown) {
    console.error("[Firebase] Redirect result error:", error);
    return null;
  }
}

/**
 * Sign out the current user.
 */
export async function signOut(): Promise<void> {
  const authInstance = getFirebaseAuth();
  if (!authInstance) return;
  await firebaseSignOut(authInstance);
}

/**
 * Get the current user's ID token (for API calls).
 * Returns null if not signed in.
 */
export async function getIdToken(): Promise<string | null> {
  const authInstance = getFirebaseAuth();
  if (!authInstance?.currentUser) return null;

  try {
    return await authInstance.currentUser.getIdToken();
  } catch {
    return null;
  }
}

/**
 * Subscribe to auth state changes.
 * Returns an unsubscribe function.
 */
export function onAuthChange(
  callback: (user: FirebaseUser | null) => void
): () => void {
  const authInstance = getFirebaseAuth();
  if (!authInstance) {
    // Not configured — immediately call with null and return no-op unsubscribe
    callback(null);
    return () => {};
  }
  return onAuthStateChanged(authInstance, callback);
}

export type { FirebaseUser };
