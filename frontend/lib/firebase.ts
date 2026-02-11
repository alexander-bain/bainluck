/**
 * Firebase configuration and initialization.
 *
 * Firebase Auth is used for session management.
 * Google sign-in uses Google Identity Services (GIS) directly,
 * bypassing Firebase's broken signInWithPopup/signInWithRedirect.
 * The Google credential is passed to Firebase via signInWithCredential.
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
 * Sign in with Google using Google Identity Services.
 * Opens Google's own sign-in UI, then passes the credential to Firebase.
 * Returns the Firebase ID token on success.
 */
export async function signInWithGoogle(): Promise<string | null> {
  const authInstance = getFirebaseAuth();
  if (!authInstance || !GOOGLE_CLIENT_ID) {
    console.error("[Firebase] Auth not initialized or missing GOOGLE_CLIENT_ID");
    return null;
  }

  try {
    await loadGIS();
    console.log("[Firebase] GIS loaded, requesting Google credential...");

    // Use Google's token client to get an ID token
    const idToken = await new Promise<string>((resolve, reject) => {
      // @ts-expect-error - google.accounts is loaded dynamically
      const google = window.google;
      if (!google?.accounts?.id) {
        reject(new Error("Google Identity Services not available"));
        return;
      }

      google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (response: { credential: string }) => {
          if (response.credential) {
            resolve(response.credential);
          } else {
            reject(new Error("No credential in Google response"));
          }
        },
        cancel_on_tap_outside: false,
      });

      // Prompt the user (shows One Tap or account chooser)
      google.accounts.id.prompt((notification: { isNotDisplayed: () => boolean; isSkippedMoment: () => boolean }) => {
        if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
          // One Tap didn't display — fall back to button-based flow
          // This can happen if the user previously dismissed One Tap
          console.log("[Firebase] One Tap not available, using manual prompt...");
          reject(new Error("ONE_TAP_UNAVAILABLE"));
        }
      });
    });

    console.log("[Firebase] Got Google credential, signing in to Firebase...");

    // Create Firebase credential from Google ID token
    const credential = GoogleAuthProvider.credential(idToken);
    const result = await signInWithCredential(authInstance, credential);
    console.log("[Firebase] Sign-in succeeded for", result.user.email);

    const firebaseToken = await result.user.getIdToken();
    return firebaseToken;
  } catch (error: unknown) {
    const err = error as Error;

    // If One Tap isn't available, try the OAuth popup flow via GIS
    if (err.message === "ONE_TAP_UNAVAILABLE") {
      return signInWithGoogleOAuth();
    }

    console.error("[Firebase] Sign-in error:", error);
    return null;
  }
}

/**
 * Fallback: use Google OAuth2 token client (opens consent popup).
 * Used when One Tap is not available.
 */
async function signInWithGoogleOAuth(): Promise<string | null> {
  const authInstance = getFirebaseAuth();
  if (!authInstance || !GOOGLE_CLIENT_ID) return null;

  try {
    await loadGIS();

    const accessToken = await new Promise<string>((resolve, reject) => {
      // @ts-expect-error - google.accounts is loaded dynamically
      const google = window.google;
      if (!google?.accounts?.oauth2) {
        reject(new Error("Google OAuth2 not available"));
        return;
      }

      const client = google.accounts.oauth2.initTokenClient({
        client_id: GOOGLE_CLIENT_ID,
        scope: "email profile",
        callback: (response: { access_token?: string; error?: string }) => {
          if (response.error) {
            reject(new Error(response.error));
          } else if (response.access_token) {
            resolve(response.access_token);
          } else {
            reject(new Error("No access token"));
          }
        },
      });

      console.log("[Firebase] Opening Google OAuth consent...");
      client.requestAccessToken();
    });

    // Create Firebase credential from access token
    const credential = GoogleAuthProvider.credential(null, accessToken);
    const result = await signInWithCredential(authInstance, credential);
    console.log("[Firebase] OAuth sign-in succeeded for", result.user.email);

    const firebaseToken = await result.user.getIdToken();
    return firebaseToken;
  } catch (error) {
    console.error("[Firebase] OAuth sign-in error:", error);
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
