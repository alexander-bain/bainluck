/**
 * Firebase configuration and initialization.
 *
 * Google sign-in uses Google Identity Services (GIS) to get an access token
 * via OAuth popup. Then tries Firebase signInWithCredential. If that fails
 * (e.g., Safari ITP blocking Identity Platform), falls back to exchanging
 * the access token through our backend for a Firebase custom token.
 */

import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithCredential,
  signInWithCustomToken,
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
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
 * Get a Google access token via GIS OAuth popup.
 */
async function getGoogleAccessToken(): Promise<string> {
  await loadGIS();

  return new Promise<string>((resolve, reject) => {
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

    client.requestAccessToken();
  });
}

/**
 * Sign in with Google.
 *
 * Opens the Google OAuth consent popup via GIS, then:
 * 1. Tries signInWithCredential (standard Firebase approach)
 * 2. If that fails, exchanges the access token through our backend
 *    for a Firebase custom token, then uses signInWithCustomToken
 *
 * Returns the Firebase ID token on success, null on failure.
 */
export async function signInWithGoogle(): Promise<string | null> {
  const authInstance = getFirebaseAuth();
  if (!authInstance || !GOOGLE_CLIENT_ID) {
    console.error("[Firebase] Auth not initialized or missing GOOGLE_CLIENT_ID");
    return null;
  }

  try {
    console.log("[Firebase] Opening Google sign-in popup...");
    const accessToken = await getGoogleAccessToken();
    console.log("[Firebase] Got Google access token");

    // Attempt 1: Try signInWithCredential directly
    try {
      const credential = GoogleAuthProvider.credential(null, accessToken);
      const result = await signInWithCredential(authInstance, credential);
      console.log("[Firebase] signInWithCredential succeeded for", result.user.email);
      return await result.user.getIdToken();
    } catch (credError: unknown) {
      const authError = credError as { code?: string; message?: string };
      console.warn(
        "[Firebase] signInWithCredential failed:",
        authError.code,
        "- trying backend exchange..."
      );
    }

    // Attempt 2: Exchange access token via backend for custom token
    try {
      const resp = await fetch(`${API_URL}/api/auth/google-access-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_token: accessToken }),
      });

      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        console.error("[Firebase] Backend token exchange failed:", resp.status, text);
        return null;
      }

      const data = await resp.json();
      const customToken = data.custom_token;

      if (!customToken) {
        console.error("[Firebase] No custom token in backend response");
        return null;
      }

      const result = await signInWithCustomToken(authInstance, customToken);
      console.log("[Firebase] signInWithCustomToken succeeded for", result.user.email || result.user.uid);
      return await result.user.getIdToken();
    } catch (backendError) {
      console.error("[Firebase] Backend exchange fallback failed:", backendError);
      return null;
    }
  } catch (error) {
    console.error("[Firebase] Sign-in error:", error);
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
