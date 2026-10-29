// Thin client for the FastAPI backend. Same endpoints and token storage as the original single-page app.
let token: string | null = null;
try { token = localStorage.getItem("dp_token") || sessionStorage.getItem("dp_token"); } catch { /* storage blocked */ }

let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn; };
export const getToken = () => token;
export function saveToken(t: string | null) {
  token = t;
  try { t ? localStorage.setItem("dp_token", t) : localStorage.removeItem("dp_token"); } catch { /* ignore */ }
}

type Opts = { method?: string; json?: unknown; body?: BodyInit; headers?: Record<string, string> };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers || {}) };
  if (token) headers.Authorization = "Bearer " + token;
  let body = opts.body;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  const r = await fetch(path, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  if (r.status === 401 && !path.startsWith("/auth/")) { onUnauthorized(); throw new Error("Please sign in again"); }
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    const d = (data as any)?.detail;
    throw new Error(d ? (typeof d === "string" ? d : JSON.stringify(d)) : r.statusText);
  }
  return data as T;
}

export async function download(path: string, name: string) {
  const r = await fetch(path, { headers: token ? { Authorization: "Bearer " + token } : {} });
  if (!r.ok) throw new Error(((await r.json().catch(() => ({}))) as any).detail || r.statusText);
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}
