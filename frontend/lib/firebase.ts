/**
 * Firebase configuration and initialization.
 *
 * Firebase Auth is used for Google (and later Apple) Sign-In.
 * The app works fully without Firebase configured — auth features
 * are hidden when env vars are not set.
 *
 * Uses signInWithPopup with authDomain set to our own domain.
 * The Next.js rewrite in next.config.mjs proxies /__/auth/* to
 * Firebase, making the popup same-origin and avoiding Safari ITP.
 */

import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut as firebaseSignOut,
  onAuthStateChanged,
  type Auth,
  type User as FirebaseUser,
} from "firebase/auth";

// Firebase config from environment variables.
// authDomain uses our own domain (not *.firebaseapp.com) to avoid
// Safari ITP cross-origin issues. The /__/auth/* path is proxied
// to Firebase via Next.js rewrites.
const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: typeof window !== "undefined" ? window.location.host : process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
};

/**
 * Check if Firebase is configured (env vars are set).
 * When not configured, auth UI is hidden and the app works anonymously.
 */
export function isFirebaseConfigured(): boolean {
  return Boolean(
    process.env.NEXT_PUBLIC_FIREBASE_API_KEY &&
    process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN &&
    process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID
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
 * Sign in with Google via popup.
 * Returns the Firebase ID token for backend verification.
 * With authDomain set to our own domain, popup is same-origin
 * and works in Safari without ITP issues.
 */
export async function signInWithGoogle(): Promise<string | null> {
  const authInstance = getFirebaseAuth();
  if (!authInstance) {
    console.error("[Firebase] Auth not initialized");
    return null;
  }

  try {
    const provider = new GoogleAuthProvider();
    console.log("[Firebase] Opening sign-in popup (same-origin)...");
    const result = await signInWithPopup(authInstance, provider);
    console.log("[Firebase] Sign-in succeeded for", result.user.email);
    const idToken = await result.user.getIdToken();
    return idToken;
  } catch (error: unknown) {
    const firebaseError = error as { code?: string };
    if (firebaseError.code === "auth/popup-closed-by-user" ||
        firebaseError.code === "auth/cancelled-popup-request") {
      console.log("[Firebase] User cancelled sign-in");
      return null;
    }
    console.error("[Firebase] Sign-in error:", firebaseError.code, error);
    throw error;
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
    callback(null);
    return () => {};
  }
  return onAuthStateChanged(authInstance, callback);
}

export type { FirebaseUser };
