import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { Confidence, ScriptStatus } from "../lib/types";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-indigo-300",
  secondary: "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 disabled:text-slate-400",
  danger: "bg-white text-red-700 border border-red-300 hover:bg-red-50",
  ghost: "text-slate-600 hover:bg-slate-100",
};

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}

export const inputClass =
  "w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-lg border border-slate-200 bg-white p-4 shadow-sm ${className}`}>{children}</div>;
}

const CONFIDENCE_STYLE: Record<Confidence, string> = {
  green: "bg-emerald-100 text-emerald-800 ring-emerald-300",
  yellow: "bg-amber-100 text-amber-800 ring-amber-300",
  red: "bg-rose-100 text-rose-800 ring-rose-300",
};

const CONFIDENCE_LABEL: Record<Confidence, string> = {
  green: "Green · likely right",
  yellow: "Yellow · check",
  red: "Red · grade carefully",
};

export function ConfidenceBadge({ value, long = false }: { value: Confidence; long?: boolean }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${CONFIDENCE_STYLE[value]}`}>
      {long ? CONFIDENCE_LABEL[value] : value}
    </span>
  );
}

const STATUS_STYLE: Record<ScriptStatus, string> = {
  uploaded: "bg-slate-100 text-slate-700",
  queued: "bg-slate-100 text-slate-700",
  processing: "bg-sky-100 text-sky-800",
  ready: "bg-indigo-100 text-indigo-800",
  reviewed: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
};

const STATUS_LABEL: Record<ScriptStatus, string> = {
  uploaded: "Uploaded",
  queued: "Waiting for AI",
  processing: "AI reading…",
  ready: "Ready to review",
  reviewed: "Reviewed",
  failed: "Failed",
};

export function StatusBadge({ value }: { value: ScriptStatus }) {
  return (
    <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[value]}`}>
      {STATUS_LABEL[value]}
    </span>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="text-sm text-rose-700">{error instanceof Error ? error.message : String(error)}</p>;
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return <p className="p-6 text-sm text-slate-500">{label}</p>;
}
