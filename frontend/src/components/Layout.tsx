import { Link, NavLink, Outlet } from "react-router-dom";
import { isStaff, useAuth } from "../lib/auth";
import { Button } from "./ui";

export default function Layout() {
  const { me, signOut } = useAuth();
  const navClass = ({ isActive }: { isActive: boolean }) =>
    `rounded px-2 py-1 text-sm ${isActive ? "bg-slate-100 font-medium" : "text-slate-600 hover:text-slate-900"}`;

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-2">
          <Link to="/" className="font-semibold text-indigo-700">EvalAssist</Link>
          <span className="text-sm text-slate-500">{me?.college_name}</span>
          <nav className="flex gap-1">
            {isStaff(me) ? (
              <>
                <NavLink to="/" end className={navClass}>Exams</NavLink>
                <NavLink to="/my-papers" className={navClass}>My papers</NavLink>
              </>
            ) : (
              <NavLink to="/" end className={navClass}>My papers</NavLink>
            )}
            {me?.role === "admin" && <NavLink to="/users" className={navClass}>Users</NavLink>}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="text-slate-600">
              {me?.full_name}{me?.employee_id && ` (${me.employee_id})`} · <span className="capitalize">{me?.role}</span>
            </span>
            <Button variant="ghost" onClick={signOut}>Sign out</Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
