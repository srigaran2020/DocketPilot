import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, getToken, saveToken, setUnauthorizedHandler } from "./api";

export type Me = { id: string; email: string; full_name: string; role: string; chambers?: string | null };
type Auth = { me: Me | null; ready: boolean; signIn: (t: { access_token: string }) => Promise<void>; signOut: () => void; refreshMe: () => Promise<void> };

const Ctx = createContext<Auth>(null as unknown as Auth);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const qc = useQueryClient();

  const signOut = useCallback(() => {
    try { if (me) localStorage.removeItem("dp_chat_" + me.id); sessionStorage.clear(); } catch { /* ignore */ }
    try { (window as any).google?.accounts?.id?.disableAutoSelect(); } catch { /* ignore */ }
    saveToken(null); setMe(null); qc.clear();
  }, [me, qc]);

  useEffect(() => { setUnauthorizedHandler(() => { saveToken(null); setMe(null); }); }, []);

  // Renew the week-long token on each visit so an active user is never asked to sign in again.
  useEffect(() => {
    (async () => {
      if (getToken()) {
        try { saveToken((await api("/auth/refresh", { method: "POST" })).access_token); setMe(await api("/auth/me")); }
        catch { saveToken(null); }
      }
      setReady(true);
    })();
  }, []);

  const signIn = useCallback(async (t: { access_token: string }) => { saveToken(t.access_token); setMe(await api("/auth/me")); }, []);
  const refreshMe = useCallback(async () => { setMe(await api("/auth/me")); }, []);

  return <Ctx.Provider value={{ me, ready, signIn, signOut, refreshMe }}>{children}</Ctx.Provider>;
}
