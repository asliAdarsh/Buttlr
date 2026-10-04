/**
 * Firebase Authentication (client side).
 *
 * The values below are *public* by design — Firebase ships them to every browser — so they come
 * from `VITE_FIREBASE_*` rather than a secret. The backend verifies the ID tokens these calls
 * produce; nothing here is trusted on its own.
 *
 * When the config is absent the app falls back to the development issuer so it still runs
 * offline, and `firebaseConfigured` tells the UI which path is available.
 */

import { initializeApp, type FirebaseApp, type FirebaseOptions } from "firebase/app";
import {
  browserLocalPersistence,
  createUserWithEmailAndPassword,
  getAuth,
  GoogleAuthProvider,
  onIdTokenChanged,
  setPersistence,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  updateProfile,
  type Auth,
} from "firebase/auth";

const envConfig: FirebaseOptions = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
  measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID,
};

/** The three fields Firebase actually requires before it can sign anyone in. */
export const firebaseOptions: FirebaseOptions | null =
  envConfig.apiKey && envConfig.authDomain && envConfig.projectId ? envConfig : null;

export const firebaseConfigured = firebaseOptions !== null;

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

export function firebaseAuth(): Auth | null {
  if (!firebaseOptions) return null;
  if (!auth) {
    app = app ?? initializeApp(firebaseOptions);
    auth = getAuth(app);
    void setPersistence(auth, browserLocalPersistence);
  }
  return auth;
}

/**
 * Keeps the API token store in step with Firebase: every refresh (they expire hourly) and every
 * sign-out is mirrored where the HTTP layer reads it.
 */
export function watchIdToken(onToken: (token: string | null) => void): () => void {
  const instance = firebaseAuth();
  if (!instance) return () => undefined;
  return onIdTokenChanged(instance, async (user) => {
    onToken(user ? await user.getIdToken() : null);
  });
}

export async function signInWithPassword(email: string, password: string): Promise<string> {
  const instance = firebaseAuth();
  if (!instance) throw new Error("Firebase is not configured for this deployment.");
  const credential = await signInWithEmailAndPassword(instance, email.trim(), password);
  return credential.user.getIdToken();
}

export async function signUpWithPassword(
  email: string,
  password: string,
  displayName?: string,
): Promise<string> {
  const instance = firebaseAuth();
  if (!instance) throw new Error("Firebase is not configured for this deployment.");
  const credential = await createUserWithEmailAndPassword(instance, email.trim(), password);
  if (displayName?.trim()) {
    await updateProfile(credential.user, { displayName: displayName.trim() });
  }
  return credential.user.getIdToken(true);
}

export async function signInWithGoogle(): Promise<string> {
  const instance = firebaseAuth();
  if (!instance) throw new Error("Firebase is not configured for this deployment.");
  const credential = await signInWithPopup(instance, new GoogleAuthProvider());
  return credential.user.getIdToken();
}

export async function signOutOfFirebase(): Promise<void> {
  const instance = firebaseAuth();
  if (instance) await signOut(instance);
}

/** Translate the SDK's error codes into something a person can act on. */
export function firebaseErrorMessage(error: unknown): string {
  const code = (error as { code?: string })?.code ?? "";
  switch (code) {
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
      return "That email and password don't match an account.";
    case "auth/email-already-in-use":
      return "An account with that email already exists — sign in instead.";
    case "auth/weak-password":
      return "Choose a password with at least 6 characters.";
    case "auth/invalid-email":
      return "That doesn't look like an email address.";
    case "auth/too-many-requests":
      return "Too many attempts. Wait a moment and try again.";
    case "auth/popup-closed-by-user":
    case "auth/cancelled-popup-request":
      return "The sign-in window was closed before it finished.";
    case "auth/popup-blocked":
      return "Your browser blocked the sign-in window. Allow pop-ups and try again.";
    case "auth/operation-not-allowed":
      return "That sign-in method is switched off in the Firebase console.";
    case "auth/unauthorized-domain":
      return "This domain isn't authorised for sign-in in the Firebase console.";
    default:
      return error instanceof Error && error.message
        ? error.message
        : "Sign-in failed. Please try again.";
  }
}
