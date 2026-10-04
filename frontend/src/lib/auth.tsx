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
import type { Organization, SessionContext, User } from "./types";

interface AuthState {
  status: "loading" | "authenticated" | "anonymous";
  user: User | null;
  organizations: Organization[];
  activeOrganizationId: string | null;
  activeOrganization: Organization | null;
  isDevLogin: boolean;
  login: (email: string, displayName?: string) => Promise<void>;
  logout: () => void;
  setActiveOrganization: (organizationId: string) => void;
  refresh: () => Promise<void>;
  applyUser: (user: User) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
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

  const login = useCallback(
    async (email: string, displayName?: string) => {
      const tokens = await api.auth.devLogin(email, displayName);
      tokenStore.set(tokens.access_token);
      setStatus("loading");
      await loadSession();
    },
    [loadSession],
  );

  const logout = useCallback(() => {
    tokenStore.clear();
    activeOrgStore.clear();
    setSession(null);
    setActiveOrganizationId(null);
    setStatus("anonymous");
  }, []);

  const setActiveOrganization = useCallback(
    (organizationId: string) => {
      activeOrgStore.set(organizationId);
      setActiveOrganizationId(organizationId);
      void api.auth.updateMe({ default_organization_id: organizationId }).catch(() => undefined);
    },
    [],
  );

  const value = useMemo<AuthState>(() => {
    const organizations = session?.organizations ?? [];
    return {
      status,
      user: session?.user ?? null,
      organizations,
      activeOrganizationId,
      activeOrganization:
        organizations.find((organization) => organization.id === activeOrganizationId) ?? null,
      isDevLogin: true,
      login,
      logout,
      setActiveOrganization,
      refresh: loadSession,
      applyUser: (user: User) => setSession((current) => (current ? { ...current, user } : current)),
    };
  }, [status, session, activeOrganizationId, login, logout, setActiveOrganization, loadSession]);

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
