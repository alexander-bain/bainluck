/**
 * Firebase configuration and initialization.
 *
 * Firebase Auth is used for Google (and later Apple) Sign-In.
 * The app works fully without Firebase configured — auth features
 * are hidden when env vars are not set.
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
 * Sign in with Google via popup.
 * Returns the Firebase ID token for backend verification.
 */
export async function signInWithGoogle(): Promise<string | null> {
  const authInstance = getFirebaseAuth();
  if (!authInstance) return null;

  try {
    const provider = new GoogleAuthProvider();
    const result = await signInWithPopup(authInstance, provider);
    const idToken = await result.user.getIdToken();
    return idToken;
  } catch (error: unknown) {
    // User cancelled the popup or other error
    const firebaseError = error as { code?: string };
    if (firebaseError.code === "auth/popup-closed-by-user") {
      return null; // User cancelled — not an error
    }
    console.error("Google sign-in failed:", error);
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
    // Not configured — immediately call with null and return no-op unsubscribe
    callback(null);
    return () => {};
  }
  return onAuthStateChanged(authInstance, callback);
}

export type { FirebaseUser };
