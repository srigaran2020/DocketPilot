import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...v: ClassValue[]) => twMerge(clsx(v));

export const store = {
  get(k: string, fallback = "") { try { return localStorage.getItem(k) ?? fallback; } catch { return fallback; } },
  set(k: string, v: string) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
  sget(k: string, fallback = "") { try { return sessionStorage.getItem(k) ?? fallback; } catch { return fallback; } },
  sset(k: string, v: string) { try { sessionStorage.setItem(k, v); } catch { /* ignore */ } },
  sdel(k: string) { try { sessionStorage.removeItem(k); } catch { /* ignore */ } },
};

const startOfToday = () => { const t = new Date(); t.setHours(0, 0, 0, 0); return t; };
export const parseDay = (iso: string) => new Date(String(iso).slice(0, 10) + "T00:00:00");
export const isoDay = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const daysFrom = (iso: string) => Math.round((parseDay(iso).getTime() - startOfToday().getTime()) / 86400000);
export function relDays(iso: string) {
  const n = daysFrom(iso);
  return n < 0 ? `${-n} day${n === -1 ? "" : "s"} ago` : n === 0 ? "Today" : n === 1 ? "Tomorrow" : `In ${n} days`;
}
export const niceDate = (iso: string) => parseDay(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
export const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };

// "H.M.O.P. No. 214 of 2026" -> "214/2026" so calendar chips stay short
export const shortCase = (s?: string) => {
  const m = String(s || "").match(/(\d{1,6})\s*(?:of|\/)\s*((?:19|20)\d{2})/);
  return m ? `${m[1]}/${m[2]}` : String(s || "").slice(0, 14);
};
export const initials = (name?: string) =>
  String(name || "?").replace(/^(adv\.?|dr\.?|mr\.?|ms\.?)\s+/i, "").split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join("").toUpperCase();

export const docName = (t: string, d?: { doc_type?: string | null }) =>
  (d && d.doc_type) || ({ demand_notice: "Cheque bounce notice (s.138)", complaint: "Cheque bounce complaint (s.138)", general: "Draft" } as Record<string, string>)[t]
  || String(t).replace(/_/g, " ");

export const S138_DOCS: Record<string, string> = { "Cheque bounce notice (s.138)": "demand_notice", "Cheque bounce complaint (s.138)": "complaint" };
export const DOC_SUGGESTIONS = ["Legal notice", "Reply to legal notice", "Bail application", "Anticipatory bail application", "Petition to quash FIR",
  "Divorce petition", "Mutual consent divorce petition", "Maintenance petition", "Domestic violence complaint", "Plaint (money recovery suit)",
  "Written statement", "Interim injunction application", "Consumer complaint", "Affidavit", "Vakalatnama", "Appeal memorandum",
  "Revision petition", "Writ petition", "Rent agreement", "Sale agreement", "Cheque bounce notice (s.138)", "Cheque bounce complaint (s.138)"];
