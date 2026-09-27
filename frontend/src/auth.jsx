import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";

const AuthContext = createContext(null);
const TOKEN_KEY = "bhoomi_setu_token";
const USER_KEY = "bhoomi_setu_user";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const saved = sessionStorage.getItem(USER_KEY);
    return saved ? JSON.parse(saved) : null;
  });

  const store = useCallback((profile) => {
    sessionStorage.setItem(USER_KEY, JSON.stringify(profile));
    setUser(profile);
    return profile;
  }, []);

  const signOut = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
    setUser(null);
  }, []);

  /**
   * Re-read the identity from the server.
   *
   * The cached copy is only a convenience for the first paint. A role can change
   * while a session is open, so a stale copy would keep offering pages the server
   * now refuses. Refreshing on mount keeps the menu honest, and a rejected
   * session is signed out rather than left in a half-working state.
   */
  const refresh = useCallback(async () => {
    if (!sessionStorage.getItem(TOKEN_KEY)) return null;
    try {
      return store(await api.me());
    } catch (error) {
      if ([401, 403].includes(error?.response?.status)) signOut();
      return null;
    }
  }, [store, signOut]);

  useEffect(() => { refresh(); }, [refresh]);

  const value = useMemo(() => ({
    user,
    refresh,
    async signIn(email, password) {
      const session = await api.login({ email, password });
      sessionStorage.setItem(TOKEN_KEY, session.access_token);
      return store(await api.me());
    },
    signOut,
  }), [user, refresh, store, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
