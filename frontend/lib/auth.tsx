import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { api, clearToken, getToken, setToken } from "./api";
import type { AuthResponse, User } from "./types";

interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  demo: () => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadFromStorage = useCallback(() => {
    const stored = getToken();
    if (stored) {
      setTokenState(stored);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  const refreshUser = useCallback(async () => {
    if (!getToken()) return;
    try {
      const me = await api<User>("/auth/me");
      setUser(me);
    } catch {
      clearToken();
      setUser(null);
      setTokenState(null);
    }
  }, []);

  useEffect(() => {
    if (token) {
      refreshUser();
    }
  }, [token, refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api<AuthResponse>("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const signup = useCallback(
    async (name: string, email: string, password: string) => {
      const res = await api<AuthResponse>("/auth/signup", {
        method: "POST",
        body: { name, email, password },
      });
      setToken(res.access_token);
      setUser(res.user);
    },
    []
  );

  const demo = useCallback(async () => {
    const res = await api<AuthResponse>("/auth/demo", { method: "POST" });
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    setTokenState(null);
  }, []);

  const value = useMemo(
    () => ({ user, token, loading, login, signup, demo, logout, refreshUser }),
    [user, token, loading, login, signup, demo, logout, refreshUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}