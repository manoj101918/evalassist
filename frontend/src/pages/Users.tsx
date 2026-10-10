import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Role, UserRow } from "../lib/types";
import { Button, Card, ErrorText, Spinner, inputClass } from "../components/ui";

const EMPTY = { full_name: "", employee_id: "", email: "", role: "teacher" as Role, password: "" };

export default function Users() {
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<UserRow[]>("/users") });
  const [form, setForm] = useState(EMPTY);
  const [created, setCreated] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () =>
      api.send("POST", "/users", {
        ...form,
        employee_id: form.employee_id.trim() || null,
        email: form.email.trim() || null,
      }),
    onSuccess: () => {
      setCreated(`${form.full_name} can now sign in with ${form.employee_id.trim().toUpperCase() || form.email}.`);
      setForm(EMPTY);
      qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setCreated(null);
    create.mutate();
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Users</h1>
      <Card>
        <h2 className="mb-2 font-medium">Add a teacher or coordinator</h2>
        <form onSubmit={submit} className="grid grid-cols-1 gap-2 sm:grid-cols-6 sm:items-end">
          <label className="text-sm">Name
            <input className={inputClass} required value={form.full_name}
                   onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </label>
          <label className="text-sm">Employee ID
            <input className={inputClass} required={form.role === "teacher"} value={form.employee_id}
                   placeholder="e.g. EMP1024" onChange={(e) => setForm({ ...form, employee_id: e.target.value })} />
          </label>
          <label className="text-sm">Email <span className="text-slate-400">(optional)</span>
            <input className={inputClass} type="email" value={form.email}
                   onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </label>
          <label className="text-sm">Role
            <select className={inputClass} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              <option value="teacher">Teacher</option>
              <option value="coordinator">Exam coordinator</option>
              <option value="admin">Admin</option>
            </select>
          </label>
          <label className="text-sm">Temporary password
            <input className={inputClass} type="text" minLength={8} required value={form.password}
                   onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </label>
          <Button type="submit" disabled={create.isPending}>Add user</Button>
        </form>
        <ErrorText error={create.error} />
        {created && <p className="mt-2 text-sm text-emerald-700">{created}</p>}
      </Card>
      <Card>
        {users.isLoading ? <Spinner /> : (
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500">
              <tr><th className="py-1">Name</th><th>Employee ID</th><th>Email</th><th>Role</th></tr>
            </thead>
            <tbody>
              {users.data?.map((u) => (
                <tr key={u.id} className="border-t border-slate-100">
                  <td className="py-1.5">{u.full_name}</td>
                  <td className="font-mono">{u.employee_id ?? "–"}</td>
                  <td>{u.email ?? "–"}</td>
                  <td className="capitalize">{u.role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <ErrorText error={users.error} />
      </Card>
    </div>
  );
}
