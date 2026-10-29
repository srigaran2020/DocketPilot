import * as HoverCard from "@radix-ui/react-hover-card";
import { AlertTriangle, CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { cn, daysFrom, parseDay, relDays } from "@/lib/utils";
import { Badge, type Tone } from "./ui";

export type Colour = "green" | "amber" | "red";
const COLOUR_TEXT: Record<string, string> = { green: "Verified", amber: "Check", red: "Problem" };
const COLOUR_ICON = { green: CheckCircle2, amber: AlertTriangle, red: XCircle };

export function Stamp({ colour, children }: { colour: Colour | string; children?: ReactNode }) {
  const Icon = COLOUR_ICON[colour as Colour] || AlertTriangle;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11.5px] font-semibold uppercase tracking-wide ring-1 ring-inset",
      colour === "green" && "bg-ok-soft text-ok ring-ok/25", colour === "amber" && "bg-warn-soft text-warn ring-warn/30", colour === "red" && "bg-bad-soft text-bad ring-bad/25")}>
      <Icon className="h-3.5 w-3.5" />{children ?? COLOUR_TEXT[colour] ?? colour}
    </span>
  );
}

const STATUS_TONE: Record<string, Tone> = { approved: "ok", awaiting_approval: "warn", blocked: "bad", failed: "bad", running: "brand" };
export const StatusPill = ({ status }: { status: string }) =>
  <Badge tone={STATUS_TONE[status] || "idle"} dot>{String(status).replace(/_/g, " ")}</Badge>;

const KIND_TONE: Record<string, Tone> = { hearing: "seal", deadline: "warn", rule: "warn", filing: "ok", notice: "ok", order: "ok", user: "idle", other: "idle" };
export const kindTone = (k: string): Tone => KIND_TONE[k] || "idle";
export const KindPill = ({ kind, label }: { kind: string; label?: string }) =>
  <Badge tone={kindTone(kind)} className="capitalize">{label || kind}</Badge>;
export const KIND_BAR: Record<string, string> = {
  hearing: "border-l-seal bg-seal-soft text-seal", deadline: "border-l-warn bg-warn-soft text-warn", rule: "border-l-warn bg-warn-soft text-warn",
  filing: "border-l-ok bg-ok-soft text-ok", notice: "border-l-ok bg-ok-soft text-ok", order: "border-l-ok bg-ok-soft text-ok",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function DateTile({ iso, size = "md" }: { iso: string; size?: "sm" | "md" }) {
  const d = parseDay(iso), past = daysFrom(iso) < 0;
  return (
    <div className={cn("shrink-0 overflow-hidden rounded-lg border text-center shadow-sm", past ? "border-line-2 opacity-70" : "border-line-2",
      size === "md" ? "w-[54px]" : "w-[44px]")}>
      <div className={cn("py-0.5 font-mono text-[10px] font-medium uppercase tracking-widest text-white", past ? "bg-mute" : "bg-seal")}>{MONTHS[d.getMonth()]}</div>
      <div className={cn("bg-surface font-display font-semibold leading-tight text-ink", size === "md" ? "py-1 text-[22px]" : "py-0.5 text-[17px]")}>{d.getDate()}</div>
    </div>
  );
}
export function DaysChip({ iso, done }: { iso: string; done?: boolean }) {
  const n = daysFrom(iso);
  if (done) return <Badge tone="idle">Done</Badge>;
  return <span className={cn("whitespace-nowrap text-[12.5px] font-medium", n >= 0 && n <= 7 ? "text-seal" : n < 0 ? "text-mute" : "text-ink-2")}>{relDays(iso)}</span>;
}

export const Passage = ({ children, className }: { children: ReactNode; className?: string }) =>
  <div className={cn("max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border-l-[3px] border-brass bg-brass-soft/40 px-4 py-3 font-display text-[14px] leading-relaxed text-ink", className)}>{children}</div>;

// One line explaining a citation verdict
export function whyColour(c: any) {
  const parts = [({ VERIFIED: "Case found", PARTIAL: "Partly matched", NOT_FOUND: "Not in our library", CONFLICT: "Points to a different case" } as Record<string, string>)[c.verdict] || c.verdict];
  const badQ = (c.quotes || []).find((q: any) => q.status !== "exact");
  if (badQ) parts.push("quote " + badQ.status.replace(/_/g, " "));
  const p = c.proposition || {};
  if (p.label && p.label !== "supports") parts.push("proposition " + p.label.replace(/_/g, " "));
  if (c.good_law?.length) parts.push("later treatment noted");
  return parts.join(" · ");
}
export const statuteNote = (s: any) =>
  (({ in_force: "In force on that date", not_yet_in_force: "Not yet in force on that date", repealed: "Repealed: " + s.message,
    earlier_version_not_stored: "Wording on that date differs from today", act_not_in_store: "Act not in library yet", not_found: "Section does not exist" } as Record<string, string>)[s.status] || s.message)
  + (s.quote_check === "differs" ? " · quoted text differs" : "");

// Hovering a citation shows the passage it rests on; clicking pins it in the side panel.
export function CitationHover({ c, children, onPin }: { c: any; children: ReactNode; onPin?: () => void }) {
  const p = c.proposition || {};
  return (
    <HoverCard.Root openDelay={180} closeDelay={80}>
      <HoverCard.Trigger asChild>
        <button type="button" onClick={onPin}
          className={cn("rounded-sm border-b-2 px-0.5 text-left transition hover:bg-brass-soft/60",
            c.colour === "green" && "border-ok", c.colour === "amber" && "border-warn bg-warn-soft/60", c.colour === "red" && "border-bad bg-bad-soft/60",
            !c.colour && "border-brand-2/50 border-dotted")}>
          {children}
        </button>
      </HoverCard.Trigger>
      <HoverCard.Portal>
        <HoverCard.Content side="top" sideOffset={8} className="z-50 w-[380px] rounded-xl border border-line bg-surface p-4 shadow-pop">
          <div className="mb-2 flex items-center gap-2">
            {c.colour && <Stamp colour={c.colour} />}
            <span className="text-[12px] text-mute">{whyColour(c)}</span>
          </div>
          <p className="font-display text-[14.5px] font-semibold leading-snug text-ink">{c.raw}</p>
          {p.passage ? <Passage className="mt-3 max-h-40 text-[13px]">{p.passage}</Passage>
            : <p className="mt-2 text-[13px] text-mute">{c.reason}</p>}
          {p.page && <p className="mt-2 text-[12px] text-mute">Page {p.page} · click to pin in the side panel</p>}
        </HoverCard.Content>
      </HoverCard.Portal>
    </HoverCard.Root>
  );
}

export const ReleaseBanner = ({ release, approvedAt }: { release?: string; approvedAt?: string | null }) => {
  if (!release && !approvedAt) return null;
  const cfg = approvedAt ? { tone: "ok", title: `Approved${approvedAt ? " on " + String(approvedAt).slice(0, 10) : ""}`, sub: "Real names restored. Word file ready to download." }
    : release === "clear" ? { tone: "ok", title: "Clear to approve", sub: "Every citation and section was checked." }
    : release === "needs_acknowledgement" ? { tone: "warn", title: "Needs your sign-off", sub: "Tick the amber items you have checked yourself." }
    : { tone: "bad", title: "Blocked", sub: "Fix the red items in the text, then re-check." };
  return (
    <div className={cn("mb-6 flex items-center gap-4 rounded-xl border px-5 py-4",
      cfg.tone === "ok" && "border-ok/25 bg-ok-soft", cfg.tone === "warn" && "border-warn/30 bg-warn-soft", cfg.tone === "bad" && "border-bad/25 bg-bad-soft")}>
      <div className={cn("grid h-11 w-11 place-items-center rounded-full bg-surface shadow-sm", cfg.tone === "ok" && "text-ok", cfg.tone === "warn" && "text-warn", cfg.tone === "bad" && "text-bad")}>
        <ShieldCheck className="h-6 w-6" />
      </div>
      <div>
        <p className={cn("h-display text-[18px]", cfg.tone === "ok" && "text-ok", cfg.tone === "warn" && "text-warn", cfg.tone === "bad" && "text-bad")}>{cfg.title}</p>
        <p className="text-[13.5px] text-ink-2">{cfg.sub}</p>
      </div>
    </div>
  );
};
