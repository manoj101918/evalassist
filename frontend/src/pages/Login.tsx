import { useState, type FormEvent } from "react";
import { supabase } from "../lib/supabase";
import { api } from "../lib/api";
import { Button, Card, ErrorText, inputClass } from "../components/ui";

interface Tokens { access_token: string; refresh_token: string }

export default function Login() {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // The API resolves an employee ID to the account and signs in; we then adopt the session.
      const tokens = await api.send<Tokens>("POST", "/auth/login", { login, password });
      const { error } = await supabase.auth.setSession(tokens);
      if (error) throw error;
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto mt-24 max-w-sm">
      <h1 className="mb-1 text-2xl font-semibold text-indigo-700">EvalAssist</h1>
      <p className="mb-6 text-sm text-slate-600">AI-assisted evaluation of answer scripts</p>
      <Card>
        <form onSubmit={submit} className="space-y-3">
          <label className="block text-sm">
            Employee ID
            <input className={inputClass} required value={login} autoFocus autoComplete="username"
                   placeholder="e.g. EMP1024" onChange={(e) => setLogin(e.target.value)} />
            <span className="text-xs text-slate-500">Admins can sign in with their email.</span>
          </label>
          <label className="block text-sm">
            Password
            <input className={inputClass} type="password" required value={password} autoComplete="current-password"
                   onChange={(e) => setPassword(e.target.value)} />
          </label>
          <ErrorText error={error} />
          <Button type="submit" disabled={busy} className="w-full">{busy ? "Signing in…" : "Sign in"}</Button>
        </form>
      </Card>
    </div>
  );
}
