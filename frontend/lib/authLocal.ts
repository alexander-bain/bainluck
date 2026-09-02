/**
 * The auth facts that are readable WITHOUT the Firebase client — build-time env
 * vars and one localStorage record. Nothing in here awaits, fetches, or opens a
 * popup, and nothing in here imports `lib/firebase.ts`.
 *
 * LAT-P206 — this module exists so that `hooks/useAuth.ts` can answer "is auth
 * configured, and is anyone signed in?" without dragging the whole sign-in
 * implementation into the entry chunk of every page.
 *
 * `useAuth` already refuses to touch Firebase for a reader who has never signed
 * in (the `hasPreviouslySignedIn()` early return, which predates this change and
 * is what makes the deferral honest rather than a byte shuffle). But the refusal
 * was a RUNTIME decision made by a module that had already been DOWNLOADED: a
 * static `import ... from "@/lib/firebase"` puts the Google popup flow, the
 * Apple popup flow, the GIS loader, the backend custom-token exchange and the
 * sign-out path into the first load of `/` whether or not the reader can reach
 * any of them. Splitting the two cheap functions out lets the import that
 * carries the other 19 kB become a dynamic one, behind the same early return.
 *
 * Rule for this file: only add something here if it can be answered with no
 * network and no SDK. Anything that awaits belongs in `lib/firebase.ts`.
 */

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

/** localStorage key for backend-only auth fallback (Safari ITP). */
export const BACKEND_AUTH_KEY = "bainluck_backendAuth";

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

/**
 * Backend-only auth data stored in localStorage when the Firebase client SDK
 * can't communicate with identitytoolkit.googleapis.com (Safari ITP).
 */
export interface BackendAuthData {
  uid: string;
  email: string | null;
  displayName: string | null;
  photoURL: string | null;
  idToken: string;
  expiresAt: number; // Unix ms
}

/** Store backend auth data in localStorage as fallback. */
export function storeBackendAuth(data: BackendAuthData): void {
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
export function loadBackendAuth(): BackendAuthData | null {
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

/** Clear backend auth data. */
export function clearBackendAuth(): void {
  try {
    localStorage.removeItem(BACKEND_AUTH_KEY);
  } catch {
    // ignore
  }
}

/**
 * Get backend auth user info (for use by the useAuth hook when Firebase
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
