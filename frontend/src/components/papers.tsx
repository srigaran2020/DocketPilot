import { useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { CalendarPlus, EyeOff, FileText, FolderOpen, Lock, Plus, UploadCloud } from "lucide-react";
import { useState } from "react";
import { useDropzone } from "react-dropzone";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DateTile, DaysChip, KindPill } from "./legal";
import { Badge, Button, Dots, ErrorNote, Input } from "./ui";

export const ACCEPT = { "application/pdf": [".pdf"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"], "text/plain": [".txt"] };

export async function previewPaper(file: File, matterId?: string | null) {
  const fd = new FormData();
  fd.append("file", file);
  if (matterId) fd.append("matter_id", matterId);
  return api("/papers/preview", { method: "POST", body: fd });
}

export function DropZone({ onFiles, compact, label }: { onFiles: (f: File[]) => void; compact?: boolean; label?: string }) {
  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({ onDrop: onFiles, accept: ACCEPT, noClick: true });
  return (
    <div {...getRootProps()} data-testid="dropzone"
      className={cn("group relative flex items-center gap-4 rounded-xl border-2 border-dashed transition",
        isDragActive ? "border-brand-2 bg-brand-soft" : "border-line-2 bg-raised/60 hover:border-brand-2/60",
        compact ? "px-4 py-3" : "flex-col justify-center px-6 py-10 text-center")}>
      <input {...getInputProps()} data-testid="file-input" />
      <div className={cn("grid place-items-center rounded-2xl bg-surface text-brand shadow-card", compact ? "h-10 w-10" : "h-14 w-14")}>
        <UploadCloud className={compact ? "h-5 w-5" : "h-6 w-6"} />
      </div>
      <div className={compact ? "flex-1" : ""}>
        <p className="font-medium text-ink">{isDragActive ? "Drop to read the papers" : label || "Drag case papers here"}</p>
        <p className="text-[13px] text-mute">PDF, Word or text. Names are hidden on this machine before any AI sees them.</p>
      </div>
      <Button type="button" variant="secondary" size="sm" icon={Plus} onClick={open}>Choose files</Button>
    </div>
  );
}

// Review what will be masked, then file it under the right case.
export function MaskReview({ pv, onFiled }: { pv: any; onFiled: (r: any) => void }) {
  const [unmask, setUnmask] = useState<Set<number>>(new Set());
  const [extra, setExtra] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const qc = useQueryClient();
  const t = pv.target;
  const file = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await api("/papers/confirm", { json: { preview_id: pv.preview_id, unmask: [...unmask].map(k => pv.entities[k].value), extra: extra.trim() ? [["PERSON", extra.trim()]] : [] } });
      qc.invalidateQueries();
      toast.success(`Filed under ${r.matter.case_number || r.matter.title}`, { description: `${r.masked} item(s) hidden · ${r.events.length} date(s) added to the calendar` });
      onFiled(r);
    } catch (e) { setErr(e); setBusy(false); }
  };
  return (
    <div data-testid="mask-review">
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-raised px-4 py-3">
        <FolderOpen className="h-5 w-5 text-brand" />
        <span className="text-[13.5px] text-mute">Filing under</span>
        <b className="text-ink">{t.label}</b>
        <Badge tone={t.new ? "ok" : "idle"}>{t.new ? "New case file" : "Existing case"}</Badge>
      </div>
      <p className="mb-3 flex items-center gap-2 text-[13.5px] text-ink-2"><Lock className="h-4 w-4 text-brand" />
        These are replaced with placeholders before anything reaches the AI. Untick anything that isn't private.</p>
      <div className="overflow-hidden rounded-xl border border-line">
        {pv.entities.length ? pv.entities.map((e: any, k: number) => {
          const kept = !unmask.has(k);
          return (
            <label key={k} className={cn("flex cursor-pointer items-center gap-3 border-b border-line px-4 py-2.5 last:border-0 transition", kept ? "bg-surface" : "bg-raised opacity-60")}>
              <input type="checkbox" checked={kept} className="h-4 w-4 accent-[rgb(var(--brand-2))]"
                onChange={() => setUnmask(s => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; })} />
              <span className="w-28 shrink-0 font-mono text-[11px] uppercase tracking-wider text-mute">{e.type}</span>
              <span className={cn("flex-1 truncate text-[14px]", !kept && "line-through")}>{e.value}</span>
              <span className="rounded-md bg-brass-soft px-2 py-0.5 font-mono text-[12px] text-[rgb(var(--brass))]">{e.placeholder}</span>
            </label>
          );
        }) : <p className="px-4 py-3 text-[13.5px] text-mute">Nothing private found in this paper.</p>}
      </div>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <Input icon={EyeOff} value={extra} onChange={e => setExtra(e.target.value)} placeholder="Anything missed? Type it exactly as written" className="flex-1" />
        <Button onClick={file} loading={busy} data-testid="file-it">{busy ? "Filing and reading dates…" : "File it"}</Button>
      </div>
      <div className="mt-3"><ErrorNote error={err} /></div>
    </div>
  );
}

export function FiledSummary({ r }: { r: any }) {
  const m = r.matter;
  return (
    <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} data-testid="filed">
      <p className="text-[14.5px]">Filed <b>{r.masked}</b> hidden item(s) under{" "}
        <Link to={`/cases/${m.id}`} className="font-semibold text-brand-2 underline-offset-2 hover:underline">{m.case_number || m.title}</Link>
        {r.new_case && <Badge tone="ok" className="ml-2">New case file</Badge>}</p>
      {m.petitioner && <p className="mt-1 text-[13.5px] text-mute">{m.petitioner}{m.respondent ? ` v. ${m.respondent}` : ""}{m.court ? ` · ${m.court}` : ""}</p>}
      {r.events.length > 0 ? (
        <div className="mt-4">
          <p className="mb-2 flex items-center gap-2 text-[13.5px] font-medium text-ink"><CalendarPlus className="h-4 w-4 text-seal" />Added {r.events.length} date(s) to your calendar</p>
          <div className="space-y-2">
            {r.events.map((e: any, i: number) => (
              <div key={i} className="flex items-center gap-3 rounded-lg border border-line bg-surface px-3 py-2">
                <DateTile iso={e.date} size="sm" />
                <div className="min-w-0 flex-1"><p className="truncate text-[14px] font-medium">{e.title}</p><KindPill kind={e.kind} /></div>
                <DaysChip iso={e.date} />
              </div>
            ))}
          </div>
        </div>
      ) : <p className="mt-2 text-[13.5px] text-mute">No dates found in this paper.</p>}
      {r.warning && <div className="mt-3"><ErrorNote error={r.warning} /></div>}
    </motion.div>
  );
}

// Full flow for a page: drop -> reading -> review -> filed
export function PaperIntake({ matterId, onDone, compact }: { matterId?: string | null; onDone?: (r: any) => void; compact?: boolean }) {
  const [state, setState] = useState<{ step: "idle" | "reading" | "review" | "filed"; name?: string; pv?: any; r?: any; err?: unknown }>({ step: "idle" });
  const start = async (files: File[]) => {
    const f = files[0]; if (!f) return;
    setState({ step: "reading", name: f.name });
    try { setState({ step: "review", name: f.name, pv: await previewPaper(f, matterId) }); }
    catch (e) { setState({ step: "idle", err: e }); }
  };
  return (
    <div className="space-y-4">
      {state.step === "idle" && <><DropZone onFiles={start} compact={compact} /><ErrorNote error={state.err} /></>}
      {state.step === "reading" && (
        <div className="flex items-center gap-4 rounded-xl border border-line bg-raised px-5 py-4">
          <FileText className="h-5 w-5 text-brand" /><div className="flex-1"><p className="font-medium">Reading {state.name}</p>
            <p className="text-[13px] text-mute">Finding the case number and hiding names on this machine…</p></div><Dots />
        </div>
      )}
      {state.step === "review" && <MaskReview pv={state.pv} onFiled={r => { setState({ step: "filed", r }); onDone?.(r); }} />}
      {state.step === "filed" && (
        <div className="space-y-4"><FiledSummary r={state.r} />
          <Button variant="secondary" size="sm" icon={Plus} onClick={() => setState({ step: "idle" })}>Add another paper</Button></div>
      )}
    </div>
  );
}
