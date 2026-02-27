/**
 * Firebase configuration and initialization.
 *
 * Google sign-in uses Google Identity Services (GIS) to get an access token
 * via OAuth popup. Apple sign-in uses Apple's JS SDK to get an id_token
 * via popup. Both then try Firebase signInWithCredential. If that fails
 * (e.g., Safari ITP blocking Identity Platform), falls back to exchanging
 * the token through our backend for a Firebase custom token.
 *
 * Safari ITP can block requests to identitytoolkit.googleapis.com, which
 * affects both signInWithCredential AND signInWithCustomToken. When both
 * fail, we fall back to a "backend-only" auth mode where the backend
 * verifies the token and we store the session locally.
 *
 * PERFORMANCE: Firebase SDK (~200KB) is loaded lazily via dynamic import()
 * so it doesn't block initial page render. The SDK loads on first auth
 * interaction (sign-in click or auth state check).
 */

// Type-only imports — erased at compile time, zero bundle cost
import type { FirebaseApp } from "firebase/app";
import type { Auth, User as FirebaseUser } from "firebase/auth";

// Firebase config from environment variables
const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
};

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// localStorage key for backend-only auth fallback (Safari ITP)
const BACKEND_AUTH_KEY = "bainluck_backendAuth";

/**
 * Check if Firebase is configured (env vars are set).
 * Pure env-var check — no SDK needed.
 */
export function isFirebaseConfigured(): boolean {
  return Boolean(
    process.env.NEXT_PUBLIC_FIREBASE_API_KEY &&
    process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN &&
    process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID &&
    GOOGLE_CLIENT_ID
  );
}

// Lazy-initialized singletons
let app: FirebaseApp | null = null;
let auth: Auth | null = null;

/**
 * Lazily load and initialize Firebase app.
 */
async function getFirebaseApp(): Promise<FirebaseApp | null> {
  if (!isFirebaseConfigured()) return null;
  if (app) return app;

  const { initializeApp, getApps } = await import("firebase/app");
  const existingApps = getApps();
  if (existingApps.length > 0) {
    app = existingApps[0];
  } else {
    app = initializeApp(firebaseConfig);
  }
  return app;
}

/**
 * Lazily load and initialize Firebase Auth.
 *
 * Explicitly sets browserLocalPersistence (localStorage) instead of the
 * default indexedDBLocalPersistence. Safari's ITP aggressively clears
 * IndexedDB for cross-origin resources (Firebase uses identitytoolkit.
 * googleapis.com), causing sign-out on hard refresh. localStorage is
 * far more stable across Safari restarts and hard refreshes.
 */
async function getFirebaseAuth(): Promise<Auth | null> {
  if (auth) return auth;
  const firebaseApp = await getFirebaseApp();
  if (!firebaseApp) return null;
  const {
    initializeAuth,
    browserLocalPersistence,
    browserPopupRedirectResolver,
    getAuth: getAuthDefault,
    indexedDBLocalPersistence,
  } = await import("firebase/auth");

  // Try to use initializeAuth with explicit localStorage persistence.
  // browserPopupRedirectResolver is required for signInWithPopup/signInWithRedirect
  // (not included by default with initializeAuth, unlike getAuth).
  // If auth was already initialized (e.g., by another import), fall back
  // to getAuth() which returns the existing instance.
  try {
    auth = initializeAuth(firebaseApp, {
      persistence: [browserLocalPersistence, indexedDBLocalPersistence],
      popupRedirectResolver: browserPopupRedirectResolver,
    });
  } catch {
    // Auth already initialized — use existing instance
    auth = getAuthDefault(firebaseApp);
  }
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

  const tokenPromise = new Promise<string>((resolve, reject) => {
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
      error_callback: (error: { type: string; message?: string }) => {
        // Fires when popup is closed, blocked, or fails before OAuth starts.
        // Without this handler, closing the popup hangs the promise forever.
        reject(new Error(`Google popup ${error.type}: ${error.message || "closed or blocked"}`));
      },
    });

    client.requestAccessToken();
  });

  // Safety net: 2-minute timeout covers slow typists but catches truly stuck popups
  return withTimeout(tokenPromise, 120000, "Google sign-in popup");
}

/**
 * Race a promise against a timeout. Rejects with TimeoutError if the
 * timeout fires first.
 */
function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`${label} timed out after ${ms}ms`));
    }, ms);

    promise.then(
      (val) => { clearTimeout(timer); resolve(val); },
      (err) => { clearTimeout(timer); reject(err); }
    );
  });
}

/**
 * Backend-only auth data stored in localStorage when Firebase client SDK
 * can't communicate with identitytoolkit.googleapis.com (Safari ITP).
 */
interface BackendAuthData {
  uid: string;
  email: string | null;
  displayName: string | null;
  photoURL: string | null;
  idToken: string;
  expiresAt: number; // Unix ms
}

/**
 * Store backend auth data in localStorage as fallback.
 */
function storeBackendAuth(data: BackendAuthData): void {
  try {
    localStorage.setItem(BACKEND_AUTH_KEY, JSON.stringify(data));
  } catch {
    // localStorage full or blocked — ignore
  }
}

/**
 * Load backend auth data from localStorage.
 * Returns null if expired or missing.
 */
function loadBackendAuth(): BackendAuthData | null {
  try {
    const raw = localStorage.getItem(BACKEND_AUTH_KEY);
    if (!raw) return null;
    const data: BackendAuthData = JSON.parse(raw);
    // Expired? Give 5 min buffer
    if (Date.now() > data.expiresAt - 5 * 60 * 1000) return null;
    return data;
  } catch {
    return null;
  }
}

/**
 * Clear backend auth data.
 */
function clearBackendAuth(): void {
  try {
    localStorage.removeItem(BACKEND_AUTH_KEY);
  } catch {
    // ignore
  }
}

/**
 * Get backend auth user info (for use by useAuth hook when Firebase
 * onAuthStateChanged doesn't fire after backend-only sign-in).
 */
export function getBackendAuthUser(): {
  uid: string;
  email: string | null;
  displayName: string | null;
  photoURL: string | null;
  idToken: string;
} | null {
  const data = loadBackendAuth();
  if (!data) return null;
  return {
    uid: data.uid,
    email: data.email,
    displayName: data.displayName,
    photoURL: data.photoURL,
    idToken: data.idToken,
  };
}

/**
 * Backend exchange response shape (shared by Google and Apple endpoints).
 */
interface BackendExchangeData {
  custom_token?: string;
  id_token?: string;
  uid?: string;
  email?: string;
  name?: string;
  picture?: string;
  expires_in?: number;
}

/**
 * Handle tier 2+3 of the auth flow: backend custom token → signInWithCustomToken,
 * falling back to backend-only auth if Firebase client SDK is fully blocked.
 *
 * Shared by Google and Apple sign-in flows. Returns the ID token on success,
 * null on failure.
 */
async function handleBackendExchange(
  authInstance: Auth,
  backendData: BackendExchangeData
): Promise<string | null> {
  if (!backendData?.uid) {
    console.error("[Firebase] No uid in backend response");
    return null;
  }

  const { signInWithCustomToken } = await import("firebase/auth");

  // ALWAYS store backend auth as a safety net BEFORE trying signInWithCustomToken.
  // On Safari, signInWithCustomToken may succeed momentarily but the Firebase
  // session can be killed by ITP. Having backend auth stored means the
  // onAuthChange listener can recover when Firebase reports no user.
  if (backendData.id_token) {
    storeBackendAuth({
      uid: backendData.uid,
      email: backendData.email || null,
      displayName: backendData.name || null,
      photoURL: backendData.picture || null,
      idToken: backendData.id_token,
      expiresAt: Date.now() + (backendData.expires_in || 3600) * 1000,
    });
  }

  // Try signInWithCustomToken (also needs identitytoolkit — may fail on Safari)
  if (backendData.custom_token) {
    try {
      const result = await withTimeout(
        signInWithCustomToken(authInstance, backendData.custom_token),
        4000,
        "signInWithCustomToken"
      );
      console.log(
        "[Firebase] signInWithCustomToken succeeded for",
        result.user.email || result.user.uid
      );
      // Note: we do NOT clear backend auth here. Safari ITP can kill the
      // Firebase session at any time, and we need the fallback available.
      return await result.user.getIdToken();
    } catch (customTokenError: unknown) {
      const ctError = customTokenError as { code?: string; message?: string };
      console.warn(
        "[Firebase] signInWithCustomToken also failed:",
        ctError.message || ctError.code,
        "- using backend-only auth"
      );
    }
  }

  // Backend-only auth (Safari ITP fully blocks Firebase)
  // Backend auth was already stored above. Return the token.
  if (backendData.id_token) {
    console.log(
      "[Firebase] Using backend-only auth for",
      backendData.email || backendData.uid
    );
    return backendData.id_token;
  }

  console.error("[Firebase] Backend response missing id_token for fallback auth");
  return null;
}

/**
 * Sign in with Google.
 *
 * Opens the Google OAuth consent popup via GIS, then tries three approaches:
 * 1. signInWithCredential (standard Firebase — works on Chrome/Firefox)
 * 2. Backend custom token → signInWithCustomToken (works when #1 blocked)
 * 3. Backend-only auth (when identitytoolkit.googleapis.com is fully blocked
 *    by Safari ITP — stores auth data in localStorage, API calls use
 *    the backend-issued token directly)
 *
 * Returns the Firebase/backend ID token on success, null on failure.
 */
export async function signInWithGoogle(): Promise<string | null> {
  const authInstance = await getFirebaseAuth();
  if (!authInstance || !GOOGLE_CLIENT_ID) {
    console.error("[Firebase] Auth not initialized or missing GOOGLE_CLIENT_ID");
    return null;
  }

  const {
    GoogleAuthProvider,
    signInWithCredential,
  } = await import("firebase/auth");

  try {
    console.log("[Firebase] Opening Google sign-in popup...");
    const accessToken = await getGoogleAccessToken();
    console.log("[Firebase] Got Google access token");

    // Attempt 1: signInWithCredential (fast timeout — Safari ITP blocks this)
    try {
      const credential = GoogleAuthProvider.credential(null, accessToken);
      const result = await withTimeout(
        signInWithCredential(authInstance, credential),
        4000,
        "signInWithCredential"
      );
      console.log("[Firebase] signInWithCredential succeeded for", result.user.email);
      return await result.user.getIdToken();
    } catch (credError: unknown) {
      const authError = credError as { code?: string; message?: string };
      console.warn(
        "[Firebase] signInWithCredential failed:",
        authError.message || authError.code,
        "- trying backend exchange..."
      );
    }

    // Attempt 2+3: Exchange via backend → custom token → fallback
    let backendData: BackendExchangeData | null = null;

    try {
      const resp = await withTimeout(
        fetch(`${API_URL}/api/auth/google-access-token`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ access_token: accessToken }),
        }),
        8000,
        "backend token exchange"
      );

      if (!resp.ok) {
        const text = await resp.text().catch(() => "");
        console.error("[Firebase] Backend token exchange failed:", resp.status, text);
        return null;
      }

      backendData = await resp.json();
    } catch (fetchError) {
      console.error("[Firebase] Backend exchange fetch failed:", fetchError);
      return null;
    }

    return await handleBackendExchange(authInstance, backendData!);
  } catch (error) {
    console.error("[Firebase] Sign-in error:", error);
    return null;
  }
}

/**
 * Sign in with Apple.
 *
 * Uses Firebase's signInWithPopup with OAuthProvider('apple.com').
 * Firebase handles the Apple OAuth flow through its own verified domain
 * (bainluck-26a47.firebaseapp.com), so no domain verification is needed
 * on bainluck.com.
 *
 * Falls back to backend exchange if signInWithPopup fails (e.g., Safari ITP).
 *
 * Returns the Firebase/backend ID token on success, null on failure.
 */
export async function signInWithApple(): Promise<string | null> {
  const authInstance = await getFirebaseAuth();
  if (!authInstance) {
    console.error("[Firebase] Auth not initialized");
    return null;
  }

  try {
    console.log("[Firebase] Opening Apple sign-in popup via Firebase...");

    // Firebase signInWithPopup with Apple OAuthProvider
    const { OAuthProvider, signInWithPopup } = await import("firebase/auth");
    const provider = new OAuthProvider("apple.com");
    provider.addScope("email");
    provider.addScope("name");

    console.log("[Firebase] Opening Apple sign-in popup...");
    const result = await withTimeout(
      signInWithPopup(authInstance, provider),
      120000, // 2 min — user may be slow typing Apple ID password
      "signInWithPopup (Apple)"
    );

    console.log(
      "[Firebase] Apple signInWithPopup succeeded for",
      result.user.email || result.user.uid
    );

    const idToken = await result.user.getIdToken();

    // Register with backend (best-effort — captures name, creates DB user)
    const appleCredential = OAuthProvider.credentialFromResult(result);
    const appleIdToken = appleCredential?.idToken;
    if (appleIdToken) {
      fetch(`${API_URL}/api/auth/apple`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: appleIdToken }),
      }).catch(() => {});
    }

    return idToken;
  } catch (error) {
    console.error("[Firebase] Apple sign-in error:", error);
    return null;
  }
}

/**
 * Sign out the current user.
 */
export async function signOut(): Promise<void> {
  const authInstance = await getFirebaseAuth();
  if (authInstance) {
    const { signOut: firebaseSignOut } = await import("firebase/auth");
    await firebaseSignOut(authInstance);
  }

  // Clear backend-only auth
  clearBackendAuth();

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
 * Checks Firebase first, then backend-only auth fallback.
 */
export async function getIdToken(): Promise<string | null> {
  const authInstance = await getFirebaseAuth();
  if (authInstance?.currentUser) {
    try {
      return await authInstance.currentUser.getIdToken();
    } catch {
      // Fall through to backend auth check
    }
  }

  // Backend-only auth fallback (Safari ITP)
  const backendAuth = loadBackendAuth();
  if (backendAuth) {
    return backendAuth.idToken;
  }

  return null;
}

/**
 * Subscribe to auth state changes.
 * Returns a Promise that resolves to an unsubscribe function.
 * The callback fires once Firebase SDK is loaded and auth state is known.
 *
 * Also checks for backend-only auth (Safari ITP fallback) if Firebase
 * reports no user.
 */
export async function onAuthChange(
  callback: (user: FirebaseUser | null) => void
): Promise<() => void> {
  const authInstance = await getFirebaseAuth();
  if (!authInstance) {
    // Check backend-only auth before reporting null
    const backendAuth = loadBackendAuth();
    if (backendAuth) {
      // Create a minimal user-like object for the callback
      callback({
        uid: backendAuth.uid,
        email: backendAuth.email,
        displayName: backendAuth.displayName,
        photoURL: backendAuth.photoURL,
      } as FirebaseUser);
    } else {
      callback(null);
    }
    return () => {};
  }

  const { onAuthStateChanged } = await import("firebase/auth");
  const unsub = onAuthStateChanged(authInstance, (fbUser) => {
    if (fbUser) {
      callback(fbUser);
    } else {
      // Firebase says no user — check backend-only auth fallback
      const backendAuth = loadBackendAuth();
      if (backendAuth) {
        callback({
          uid: backendAuth.uid,
          email: backendAuth.email,
          displayName: backendAuth.displayName,
          photoURL: backendAuth.photoURL,
        } as FirebaseUser);
      } else {
        callback(null);
      }
    }
  });
  return unsub;
}

export type { FirebaseUser };
