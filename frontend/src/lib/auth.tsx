import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError, activeOrgStore, tokenStore } from "./api";
import {
  firebaseConfigured,
  firebaseErrorMessage,
  signInWithGoogle,
  signInWithPassword,
  signOutOfFirebase,
  signUpWithPassword,
  watchIdToken,
} from "./firebase";
import { useMeta } from "./queries";
import type { Organization, SessionContext, User } from "./types";

export type AuthMode = "dev" | "firebase";

interface AuthState {
  status: "loading" | "authenticated" | "anonymous";
  /** How the visitor signs in: the server decides, not the client. */
  authMode: AuthMode;
  /** Whether this build has a Firebase config to sign in with. */
  firebaseAvailable: boolean;
  user: User | null;
  organizations: Organization[];
  activeOrganizationId: string | null;
  activeOrganization: Organization | null;
  login: (email: string, displayName?: string) => Promise<void>;
  loginWithPassword: (
    email: string,
    password: string,
    options?: { create?: boolean; displayName?: string },
  ) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  logout: () => void;
  setActiveOrganization: (organizationId: string) => void;
  refresh: () => Promise<void>;
  applyUser: (user: User) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const meta = useMeta();
  const authMode: AuthMode = meta.data?.auth_mode === "firebase" ? "firebase" : "dev";

  const [status, setStatus] = useState<AuthState["status"]>(
    tokenStore.get() ? "loading" : "anonymous",
  );
  const [session, setSession] = useState<SessionContext | null>(null);
  const [activeOrganizationId, setActiveOrganizationId] = useState<string | null>(
    activeOrgStore.get(),
  );

  const loadSession = useCallback(async () => {
    if (!tokenStore.get()) {
      setSession(null);
      setStatus("anonymous");
      return;
    }
    try {
      const next = await api.auth.session();
      setSession(next);
      setStatus("authenticated");
      setActiveOrganizationId((current) => {
        const ids = next.organizations.map((organization) => organization.id);
        const valid = current && ids.includes(current) ? current : (ids[0] ?? null);
        if (valid) activeOrgStore.set(valid);
        else activeOrgStore.clear();
        return valid;
      });
    } catch (error) {
      if (error instanceof ApiError && error.isUnauthorized) tokenStore.clear();
      setSession(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  // Firebase owns the token lifetime once it is the auth mode: every refresh and sign-out is
  // mirrored into the store the HTTP layer reads, and a restored session is picked up on load.
  // Guarded on the mode, because a build can carry a Firebase config while the API still uses
  // the development issuer — and then the listener's initial `null` must not sign anyone out.
  useEffect(() => {
    if (authMode !== "firebase" || !firebaseConfigured) return;
    return watchIdToken((token) => {
      if (token) {
        tokenStore.set(token);
        void loadSession();
        return;
      }
      tokenStore.clear();
      setSession(null);
      setStatus("anonymous");
    });
  }, [authMode, loadSession]);

  const login = useCallback(
    async (email: string, displayName?: string) => {
      const tokens = await api.auth.devLogin(email, displayName);
      tokenStore.set(tokens.access_token);
      setStatus("loading");
      await loadSession();
    },
    [loadSession],
  );

  const loginWithPassword = useCallback(
    async (email: string, password: string, options?: { create?: boolean; displayName?: string }) => {
      try {
        const token = options?.create
          ? await signUpWithPassword(email, password, options.displayName)
          : await signInWithPassword(email, password);
        tokenStore.set(token);
        setStatus("loading");
        await loadSession();
      } catch (error) {
        throw new Error(firebaseErrorMessage(error));
      }
    },
    [loadSession],
  );

  const loginWithGoogle = useCallback(async () => {
    try {
      const token = await signInWithGoogle();
      tokenStore.set(token);
      setStatus("loading");
      await loadSession();
    } catch (error) {
      throw new Error(firebaseErrorMessage(error));
    }
  }, [loadSession]);

  const logout = useCallback(() => {
    void signOutOfFirebase();
    tokenStore.clear();
    activeOrgStore.clear();
    setSession(null);
    setActiveOrganizationId(null);
    setStatus("anonymous");
  }, []);

  const setActiveOrganization = useCallback((organizationId: string) => {
    activeOrgStore.set(organizationId);
    setActiveOrganizationId(organizationId);
    void api.auth.updateMe({ default_organization_id: organizationId }).catch(() => undefined);
  }, []);

  const value = useMemo<AuthState>(() => {
    const organizations = session?.organizations ?? [];
    return {
      status,
      authMode,
      firebaseAvailable: firebaseConfigured,
      user: session?.user ?? null,
      organizations,
      activeOrganizationId,
      activeOrganization:
        organizations.find((organization) => organization.id === activeOrganizationId) ?? null,
      login,
      loginWithPassword,
      loginWithGoogle,
      logout,
      setActiveOrganization,
      refresh: loadSession,
      applyUser: (user: User) => setSession((current) => (current ? { ...current, user } : current)),
    };
  }, [
    status,
    authMode,
    session,
    activeOrganizationId,
    login,
    loginWithPassword,
    loginWithGoogle,
    logout,
    setActiveOrganization,
    loadSession,
  ]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}

/** Resolves the active organization id, throwing a clear error when none is selected. */
export function useActiveOrgId(): string {
  const { activeOrganizationId } = useAuth();
  if (!activeOrganizationId) {
    throw new Error("No active organization. Create or select one first.");
  }
  return activeOrganizationId;
}
