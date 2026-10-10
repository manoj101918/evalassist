import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "./supabase";
import { api } from "./api";
import type { Me } from "./types";

interface AuthState {
  session: Session | null;
  loading: boolean;
  me: Me | undefined;
  meError: Error | null;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const queryClient = useQueryClient();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  const meQuery = useQuery({
    queryKey: ["me", session?.user.id],
    queryFn: () => api.get<Me>("/me"),
    enabled: !!session,
    retry: false,
  });

  const signOut = async () => {
    await supabase.auth.signOut();
    queryClient.clear();
  };

  return (
    <AuthContext.Provider
      value={{ session, loading, me: meQuery.data, meError: meQuery.error, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export const isStaff = (me: Me | undefined) => me?.role === "admin" || me?.role === "coordinator";
