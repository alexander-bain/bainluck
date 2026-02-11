/**
 * Firebase configuration and initialization.
 *
 * Firebase Auth is used for session management.
 * Google sign-in uses Google Identity Services (GIS) rendered button,
 * which returns a Google ID token (JWT). This is passed to Firebase
 * via signInWithCredential using GoogleAuthProvider.credential(idToken).
 *
 * The ID token flow avoids the auth/network-request-failed error that
 * occurs with the access token flow on Safari, because Firebase can
 * process ID tokens without making additional network calls to Google.
 */

import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithCredential,
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

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

/**
 * Check if Firebase is configured (env vars are set).
 */
export function isFirebaseConfigured(): boolean {
  return Boolean(
    process.env.NEXT_PUBLIC_FIREBASE_API_KEY &&
    process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN &&
    process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID &&
    GOOGLE_CLIENT_ID
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
 * Load Google Identity Services script.
 */
let gisLoaded = false;
let gisLoadPromise: Promise<void> | null = null;

function loadGIS(): Promise<void> {
  if (gisLoaded) return Promise.resolve();
  if (gisLoadPromise) return gisLoadPromise;

  gisLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      gisLoaded = true;
      resolve();
    };
    script.onerror = () => reject(new Error("Failed to load Google Identity Services"));
    document.head.appendChild(script);
  });

  return gisLoadPromise;
}

/**
 * Initialize Google Sign-In and render the button in a container element.
 *
 * Uses google.accounts.id (Sign In With Google) which returns a Google
 * ID token (JWT) instead of an access token. The ID token is passed to
 * Firebase via GoogleAuthProvider.credential(idToken), which avoids the
 * additional network round-trip that access tokens require.
 *
 * @param container - DOM element to render the Google button into
 * @param onFirebaseToken - Called with the Firebase ID token on successful sign-in
 */
export async function initGoogleSignInButton(
  container: HTMLElement,
  onFirebaseToken: (token: string) => void
): Promise<void> {
  const authInstance = getFirebaseAuth();
  if (!authInstance || !GOOGLE_CLIENT_ID) {
    console.error("[Firebase] Auth not initialized or missing GOOGLE_CLIENT_ID");
    return;
  }

  await loadGIS();

  // @ts-expect-error - google.accounts is loaded dynamically
  const google = window.google;
  if (!google?.accounts?.id) {
    console.error("[Firebase] Google Identity Services not available");
    return;
  }

  // Initialize GIS with ID token callback
  google.accounts.id.initialize({
    client_id: GOOGLE_CLIENT_ID,
    callback: async (response: { credential?: string; select_by?: string }) => {
      if (!response.credential) {
        console.error("[Firebase] No credential in Google response");
        return;
      }

      try {
        console.log("[Firebase] Got Google ID token, signing into Firebase...");
        const credential = GoogleAuthProvider.credential(response.credential);
        const result = await signInWithCredential(authInstance, credential);
        console.log("[Firebase] Sign-in succeeded for", result.user.email);
        const firebaseToken = await result.user.getIdToken();
        onFirebaseToken(firebaseToken);
      } catch (error: unknown) {
        const authError = error as { code?: string; message?: string };
        console.error(
          "[Firebase] signInWithCredential failed:",
          authError.code,
          authError.message
        );
      }
    },
    ux_mode: "popup",
  });

  // Render Google's Sign-In button in the container
  google.accounts.id.renderButton(container, {
    type: "standard",
    theme: "outline",
    size: "medium",
    text: "signin",
    shape: "pill",
  });

  console.log("[Firebase] Google Sign-In button rendered");
}

/**
 * Sign out the current user.
 */
export async function signOut(): Promise<void> {
  const authInstance = getFirebaseAuth();
  if (!authInstance) return;
  await firebaseSignOut(authInstance);

  // Also revoke Google's session
  try {
    // @ts-expect-error - google.accounts is loaded dynamically
    window.google?.accounts?.id?.disableAutoSelect();
  } catch {
    // GIS not loaded, nothing to revoke
  }
}

/**
 * Get the current user's ID token (for API calls).
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
