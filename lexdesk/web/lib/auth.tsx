"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, onSessionExpired, refreshSession, setAccessToken } from "./api";

export type Role = "admin" | "partner" | "lawyer" | "paralegal" | "receptionist" | "accountant" | "client";

export type User = {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  role: Role;
  role_display: string;
  title: string;
  mfa_enabled: boolean;
  is_platform_operator: boolean;
  firm: { id: number; name: string; slug: string; code: string } | null;
};

type LoginResult = { done: true } | { mfa: string };

type AuthState = {
  user: User | null;
  ready: boolean;
  mfaSetupRequired: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  verifyMfa: (token: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
  acceptSession: (body: any) => void;
};

const AuthContext = createContext<AuthState | null>(null);

export const FEE_EARNERS: Role[] = ["partner", "lawyer", "paralegal"];
export const MANAGERS: Role[] = ["admin", "partner"];
export const isManager = (u: User | null) => !!u && MANAGERS.includes(u.role);
export const isFeeEarner = (u: User | null) => !!u && FEE_EARNERS.includes(u.role);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [mfaSetupRequired, setMfaSetupRequired] = useState(false);

  const acceptSession = useCallback((body: any) => {
    setAccessToken(body.access);
    if (body.user) setUser(body.user);
    setMfaSetupRequired(Boolean(body.mfa_setup_required));
  }, []);

  const reload = useCallback(async () => {
    setUser(await api<User>("/auth/me/"));
  }, []);

  useEffect(() => {
    // Returning visitor: the refresh cookie (if any) restores the session.
    refreshSession()
      .then(async (ok) => {
        if (ok) await reload().catch(() => setUser(null));
      })
      .finally(() => setReady(true));
    return onSessionExpired(() => {
      setAccessToken(null);
      setUser(null);
    });
  }, [reload]);

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      const body = await api<any>("/auth/login/", { method: "POST", body: { email, password } });
      if (body.mfa_required) return { mfa: body.mfa_token };
      acceptSession(body);
      return { done: true };
    },
    [acceptSession],
  );

  const verifyMfa = useCallback(
    async (token: string, code: string) => {
      acceptSession(await api<any>("/auth/mfa/verify/", { method: "POST", body: { mfa_token: token, code } }));
    },
    [acceptSession],
  );

  const logout = useCallback(async () => {
    await api("/auth/logout/", { method: "POST" }).catch(() => undefined);
    // Nothing privileged stays on the device after signing out.
    await import("./offline").then((m) => m.clearOffline()).catch(() => undefined);
    try {
      localStorage.removeItem("lexdesk.offline.user");
    } catch {
      /* ignore */
    }
    setAccessToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, ready, mfaSetupRequired, login, verifyMfa, logout, reload, acceptSession }),
    [user, ready, mfaSetupRequired, login, verifyMfa, logout, reload, acceptSession],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

/** Where someone lands after signing in. */
export function homeFor(user: User) {
  if (user.is_platform_operator) return "/platform";
  return user.role === "client" ? "/portal" : "/dashboard";
}
