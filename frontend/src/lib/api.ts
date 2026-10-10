import { supabase } from "./supabase";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => (d as { msg?: string }).msg ?? String(d)).join("; ");
    }
  }
  return fallback;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { ...(await authHeader()), ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, errorMessage(body, `${res.status} ${res.statusText}`));
  }
  return res;
}

export const api = {
  async get<T>(path: string): Promise<T> {
    return (await request(path)).json();
  },
  async send<T>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<T> {
    const res = await request(path, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return res.status === 204 ? (undefined as T) : res.json();
  },
  async upload<T>(path: string, form: FormData): Promise<T> {
    return (await request(path, { method: "POST", body: form })).json();
  },
  async download(path: string, fallbackName: string): Promise<void> {
    const res = await request(path);
    const disposition = res.headers.get("Content-Disposition") ?? "";
    const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallbackName;
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  },
};
