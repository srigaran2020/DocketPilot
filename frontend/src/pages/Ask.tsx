import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUp, BookMarked, CalendarClock, Check, ChevronDown, Copy, FilePen, FileText, Gavel, Paperclip, Scale, ShieldCheck, Trash2, Wand2,
} from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useDropzone } from "react-dropzone";
import { Link } from "react-router-dom";
import { CitationHover, DateTile, DaysChip, Passage, Stamp } from "@/components/legal";
import { ACCEPT, FiledSummary, MaskReview, previewPaper } from "@/components/papers";
import { Badge, Button, Card, Dots, Kbd, Select, Switch } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, docName, store } from "@/lib/utils";

type Msg = { role: "user" | "assistant" | "system"; content?: string; kind?: string; error?: string; note?: string; [k: string]: any };

const STARTERS = [
  { icon: Paperclip, title: "Add case papers", text: "Filed under the right case; hearing dates go on your calendar.", ask: "__attach__" },
  { icon: CalendarClock, title: "When is my next hearing?", text: "Answered from your calendar, never guessed.", ask: "When is my next hearing?" },
  { icon: FilePen, title: "Draft any document", text: "From this case's papers, every citation checked.", ask: "Draft a petition for this case" },
  { icon: Gavel, title: "Strengths and strategy", text: "What helps, what hurts, and what to do next.", ask: "What are the strengths, weaknesses and the best strategy for this case?" },
  { icon: Scale, title: "Ask the law", text: "Answers only from real judgments and statutes.", ask: "Can the accused rebut the presumption under Section 139, and on what standard?" },
  { icon: ShieldCheck, title: "Check citations", text: "Paste any text; wrong citations come back corrected.", ask: "Verify this: " },
];
const STAGES = ["Hiding names on this machine", "Searching judgments and Acts", "Writing the answer", "Checking every citation", "Removing anything unsupported"];

// **bold**, citations as hover cards; no HTML from the model is ever rendered.
function inline(text: string, cits: any[], pin: (c: any) => void): ReactNode[] {
  const raws = cits.map(c => c.raw).filter(Boolean).sort((a, b) => b.length - a.length);
  const out: ReactNode[] = [];
  const bold = (s: string, key: string) => s.split(/\*\*(.+?)\*\*/g).map((p, i) => (i % 2 ? <b key={key + i}>{p}</b> : <Fragment key={key + i}>{p}</Fragment>));
  let rest = text, k = 0;
  while (rest) {
    let best = -1, hit = "";
    for (const r of raws) { const i = rest.indexOf(r); if (i >= 0 && (best < 0 || i < best)) { best = i; hit = r; } }
    if (best < 0) { out.push(...bold(rest, "t" + k++)); break; }
    out.push(...bold(rest.slice(0, best), "t" + k++));
    const c = cits.find(x => x.raw === hit);
    out.push(<CitationHover key={"c" + k++} c={c} onPin={() => pin(c)}>{hit}</CitationHover>);
    rest = rest.slice(best + hit.length);
  }
  return out;
}
function Answer({ text, report, pin }: { text: string; report?: any; pin: (c: any) => void }) {
  const cits = report?.citations || [];
  return (
    <div className="prose-answer text-[15px] leading-[1.75] text-ink">
      {String(text || "").split(/\n{2,}/).map((b, i) => {
        const lines = b.split("\n").filter(l => l.trim());
        if (!lines.length) return null;
        const isB = (l: string) => /^\s*[-•*]\s+/.test(l);
        if (lines.filter(isB).length >= lines.length - 1 && lines.some(isB)) {
          const lead = isB(lines[0]) ? null : lines.shift();
          return <Fragment key={i}>{lead && <p>{inline(lead, cits, pin)}</p>}<ul>{lines.map((l, j) => <li key={j}>{inline(l.replace(/^\s*[-•*]\s+/, ""), cits, pin)}</li>)}</ul></Fragment>;
        }
        return <p key={i}>{lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l, cits, pin)}</Fragment>)}</p>;
      })}
    </div>
  );
}

function CheckedLine({ m }: { m: Msg }) {
  const [open, setOpen] = useState(false);
  const rep = m.verification; if (!rep) return null;
  const n = rep.checked ?? ((rep.citations || []).length + (rep.statutes || []).length); if (!n) return null;
  const ch: any[] = m.corrections || rep.corrections || [];
  const fixed = ch.filter(c => c.action === "replace").length, removed = ch.filter(c => c.action === "remove").length;
  return (
    <div className="mt-4 rounded-xl border border-ok/20 bg-ok-soft/60" data-testid="checked">
      <button onClick={() => ch.length && setOpen(!open)} className="flex w-full items-center gap-2 px-3.5 py-2 text-left text-[13px] font-medium text-ok">
        <ShieldCheck className="h-4 w-4" />{n} reference{n > 1 ? "s" : ""} checked{fixed ? ` · ${fixed} corrected` : ""}{removed ? ` · ${removed} removed` : ""}
        {ch.length > 0 && <ChevronDown className={cn("ml-auto h-4 w-4 transition", open && "rotate-180")} />}
      </button>
      <AnimatePresence>{open && (
        <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
          <div className="space-y-1.5 border-t border-ok/15 px-3.5 py-2.5 text-[13px] text-ink-2">
            {ch.map((c, i) => <p key={i}>{c.action === "replace" ? <>Corrected <s className="text-mute">{c.original}</s> → <b>{c.replacement}</b></> : <>Removed <s className="text-mute">{c.original}</s></>}
              <span className="text-mute"> — {c.reason}</span></p>)}
          </div>
        </motion.div>)}
      </AnimatePresence>
    </div>
  );
}

function Pending({ text }: { text?: string }) {
  const [i, setI] = useState(0);
  useEffect(() => { if (text) return; const t = setInterval(() => setI(x => Math.min(x + 1, STAGES.length - 1)), 3200); return () => clearInterval(t); }, [text]);
  return (
    <div className="flex items-center gap-3 text-[14px] text-ink-2"><Dots />
      <AnimatePresence mode="wait"><motion.span key={text || i} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}>{text || STAGES[i] + "…"}</motion.span></AnimatePresence>
    </div>
  );
}

function BotCard({ m, children }: { m: Msg; children: ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3" data-testid="bot-msg">
      <img src="/logo.png" alt="" className="mt-1 h-8 w-8 shrink-0 rounded-full ring-1 ring-line" />
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-line bg-surface px-5 py-4 shadow-card">
        <p className="mb-2 font-mono text-[10.5px] uppercase tracking-[.16em] text-seal">DocketPilot{m.matter ? ` · ${m.matter}` : ""}</p>
        {children}
      </div>
    </motion.div>
  );
}

export default function Ask() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const key = "dp_chat_" + (me?.id || "anon");
  const [log, setLog] = useState<Msg[]>(() => { try { return JSON.parse(store.get(key, "[]")); } catch { return []; } });
  const [pending, setPending] = useState<string | null | false>(false);
  const [text, setText] = useState(() => { const p = store.sget("dp_prefill"); store.sdel("dp_prefill"); return p; });
  const [current, setCurrent] = useState(() => store.sget("dp_chat_matter"));
  const [simple, setSimple] = useState(() => store.sget("dp_simple") === "1");
  const [side, setSide] = useState<{ title: string; sub?: string; text?: string; reason?: string; good?: any[] } | null>(null);
  const cases = useQuery({ queryKey: ["cases"], queryFn: () => api<any[]>("/cases") });
  const ta = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => { store.set(key, JSON.stringify(log.filter(m => m.kind !== "attach").slice(-60))); }, [log, key]);
  useEffect(() => { store.sset("dp_chat_matter", current); }, [current]);
  useEffect(() => { store.sset("dp_simple", simple ? "1" : "0"); }, [simple]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [log, pending]);
  useEffect(() => { if (ta.current) { ta.current.style.height = "auto"; ta.current.style.height = Math.min(ta.current.scrollHeight, 200) + "px"; } }, [text]);
  useEffect(() => { if (text) ta.current?.focus(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const push = (m: Msg) => setLog(l => [...l, m]);
  const pinCitation = useCallback((c: any) => {
    const p = c.proposition || {};
    setSide({ title: c.raw, sub: p.page ? `Page ${p.page}` : undefined, text: p.passage, reason: c.reason, good: c.good_law });
  }, []);
  const showChunk = async (id: string) => {
    const p = await api("/chunks/" + id);
    setSide({ title: p.title, sub: `${p.court} · ${p.year} · page ${p.page}`, text: p.text });
  };

  // Poll running drafts so the card turns into "ready" by itself
  useEffect(() => {
    const running = log.map((m, i) => [m, i] as const).filter(([m]) => m.kind === "draft_started" && (!m.draft || m.draft.status === "running"));
    if (!running.length) return;
    const t = setTimeout(async () => {
      for (const [m, i] of running) {
        try { const d = await api("/drafts/" + m.draft_id); setLog(l => l.map((x, j) => (j === i ? { ...x, draft: d } : x))); } catch { /* keep polling */ }
      }
    }, 4000);
    return () => clearTimeout(t);
  }, [log]);

  const attach = async (files: File[]) => {
    for (const f of files) {
      push({ role: "user", content: `📎 ${f.name}` });
      setPending(`Reading ${f.name}, finding the case number and hiding names on this machine…`);
      try { const pv = await previewPaper(f, current); push({ role: "assistant", kind: "attach", pv }); }
      catch (e) { push({ role: "assistant", error: (e as Error).message }); }
      setPending(false);
    }
  };
  const { getRootProps, getInputProps, isDragActive, open: openFiles } = useDropzone({ onDrop: attach, accept: ACCEPT, noClick: true, noKeyboard: true });

  const send = async (override?: string) => {
    const q = (override ?? text).trim(); if (!q || pending !== false) return;
    setText("");
    const next = [...log, { role: "user" as const, content: q }];
    setLog(next); setPending(null);
    const history = next.filter(m => (m.role === "user" && !String(m.content).startsWith("📎")) || (m.role === "assistant" && !m.kind && !m.error && m.content))
      .map(m => ({ role: m.role, content: m.content })).slice(-12);
    try {
      const r = await api("/ask", { json: { messages: history, matter_id: current || null, style: simple ? "simple" : "expert" } });
      const add: Msg[] = [];
      if (r.created_matter) { qc.invalidateQueries({ queryKey: ["cases"] }); add.push({ role: "system", note: `Opened a new case file: ${r.matter}` }); }
      else if (r.switched_matter) add.push({ role: "system", note: `Using case: ${r.matter}` });
      if (r.matter_id && r.matter_id !== current) setCurrent(r.matter_id);
      add.push({ role: "assistant", content: r.answer || "", kind: ["answer", "dates", "message"].includes(r.type) ? undefined : r.type,
        verification: r.verification, corrections: r.corrections, corrected_text: r.corrected_text, sources: r.sources,
        matter: r.matter, matter_id: r.matter_id, reminder: r.reminder, cases: r.cases, draft_id: r.draft_id });
      if (r.type === "scheduled") qc.invalidateQueries({ queryKey: ["calendar"] });
      setLog(l => [...l, ...add]);
    } catch (e) { push({ role: "assistant", error: (e as Error).message }); }
    setPending(false);
    ta.current?.focus();
  };

  const starter = (s: (typeof STARTERS)[number]) => {
    if (s.ask === "__attach__") return openFiles();
    if (s.ask.endsWith(" ")) { setText(s.ask); ta.current?.focus(); } else send(s.ask);
  };
  const caseList = cases.data || [];
  const currentCase = useMemo(() => caseList.find(c => c.id === current), [caseList, current]);

  const renderMsg = (m: Msg, i: number) => {
    if (m.role === "user") return (
      <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end" data-testid="user-msg">
        <div className="max-w-[82%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand px-4 py-2.5 text-[15px] text-[rgb(var(--on-brand))] shadow-card">{m.content}</div>
      </motion.div>);
    if (m.role === "system") return <div key={i} className="flex justify-center"><span className="rounded-full border border-dashed border-line-2 px-3 py-1 text-[12px] text-mute">{m.note}</span></div>;
    if (m.error) return <BotCard key={i} m={m}><p className="text-[14px] text-bad">{m.error}</p></BotCard>;
    if (m.kind === "attach") return (
      <BotCard key={i} m={m}><MaskReview pv={m.pv} onFiled={r => {
        setLog(l => l.map((x, j) => (j === i ? { role: "assistant", kind: "filed", result: r, matter: r.matter.case_number || r.matter.title } : x)));
        qc.invalidateQueries({ queryKey: ["cases"] }); setCurrent(r.matter.id);
      }} /></BotCard>);
    if (m.kind === "filed") return <BotCard key={i} m={m}><FiledSummary r={m.result} /></BotCard>;
    if (m.kind === "scheduled") return (
      <BotCard key={i} m={m}><Answer text={m.content || ""} pin={pinCitation} />
        <div className="mt-3 flex items-center gap-3 rounded-xl border border-line bg-raised p-3"><DateTile iso={m.reminder.due} />
          <div className="flex-1"><p className="font-medium">{m.reminder.title}</p><DaysChip iso={m.reminder.due} /></div>
          <Link to="/calendar"><Button variant="secondary" size="sm">Open calendar</Button></Link></div>
      </BotCard>);
    if (m.kind === "draft_started") {
      const d = m.draft || { status: "running" };
      return (
        <BotCard key={i} m={m}>
          {d.status === "running" ? (<div className="space-y-3"><Pending text="Reading the papers, researching, drafting and checking every citation… (one to three minutes)" />
            <Link to={`/drafts/${m.draft_id}`} className="text-[13px] font-medium text-brand-2 hover:underline">Watch progress →</Link></div>)
            : d.status === "failed" ? <p className="text-bad">The draft could not be completed. {d.error}</p>
            : (<div><p className="text-[15px]">Your <b>{docName(d.template, d)}</b> (v{d.version}) is ready.</p><CheckedLine m={{ role: "assistant", verification: d.verification }} />
              <Link to={`/drafts/${m.draft_id}`} className="mt-3 inline-block"><Button size="sm" icon={FileText}>Open, review and approve</Button></Link></div>)}
        </BotCard>);
    }
    if (m.kind === "similar") return (
      <BotCard key={i} m={m}><Answer text={m.content || ""} pin={pinCitation} />
        <div className="mt-3 space-y-2">{(m.cases || []).map((s: any) => (
          <button key={s.chunk_id} onClick={() => showChunk(s.chunk_id)} className="flex w-full items-center gap-3 rounded-xl border border-line px-3 py-2.5 text-left transition hover:border-brass/50 hover:bg-raised">
            <Badge tone={s.outcome === "unknown" ? "idle" : "brass"}>{s.outcome}</Badge>
            <span className="min-w-0 flex-1"><span className="block truncate text-[14px] font-medium">{s.label}</span><span className="text-[12.5px] text-mute">{s.court} · {s.year}</span></span>
          </button>))}</div>
      </BotCard>);
    return (
      <BotCard key={i} m={m}>
        <Answer text={m.content || ""} report={m.verification} pin={pinCitation} />
        {m.kind === "verification" && m.corrected_text && (
          <div className="mt-4"><div className="mb-2 flex items-center"><b className="text-[13.5px]">Corrected text</b>
            <Button variant="ghost" size="sm" icon={Copy} className="ml-auto" onClick={() => navigator.clipboard?.writeText(m.corrected_text)}>Copy</Button></div>
            <Passage>{m.corrected_text}</Passage></div>)}
        <CheckedLine m={m} />
        {(m.sources || []).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">{m.sources.map((s: any) => (
            <button key={s.chunk_id} onClick={() => showChunk(s.chunk_id)} data-testid="source-chip"
              className="inline-flex max-w-[260px] items-center gap-1.5 rounded-full border border-line bg-raised px-3 py-1 text-[12.5px] text-ink-2 transition hover:border-brass/60 hover:text-ink">
              <BookMarked className="h-3.5 w-3.5 text-brass-ink" /><span className="truncate">{String(s.label).split(",")[0]}</span></button>))}</div>)}
      </BotCard>);
  };

  return (
    <div {...getRootProps()} className="relative">
      <input {...getInputProps()} data-testid="chat-file" />
      <AnimatePresence>{isDragActive && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-40 grid place-items-center bg-brand/10 backdrop-blur-sm">
          <div className="rounded-2xl border-2 border-dashed border-brand-2 bg-surface px-10 py-8 text-center shadow-pop">
            <Paperclip className="mx-auto mb-2 h-7 w-7 text-brand" /><p className="h-display text-xl">Drop case papers to file them</p>
            <p className="text-[13.5px] text-mute">Names are hidden on this machine first.</p></div>
        </motion.div>)}</AnimatePresence>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0">
          <div className="sticky top-16 z-20 -mx-1 mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface px-3 py-2.5 shadow-card
            before:absolute before:-top-4 before:left-0 before:right-0 before:h-4 before:bg-bg before:content-['']">
            <div className="flex min-w-[220px] flex-1 items-center gap-2"><span className="text-[12.5px] font-medium text-mute">Case</span>
              <Select value={current} onChange={e => setCurrent(e.target.value)} className="h-9 py-1.5 text-[13.5px]" aria-label="Case" data-testid="case-select">
                <option value="">All cases / general</option>{caseList.map(c => <option key={c.id} value={c.id}>{c.label || c.title}</option>)}
              </Select></div>
            <Switch id="simple" checked={simple} onChange={setSimple} label="Explain simply" />
            <Button variant="ghost" size="sm" icon={Trash2} onClick={() => setLog([])} disabled={!log.length}>New conversation</Button>
          </div>

          <div className="space-y-5 pb-44">
            {!log.length && pending === false ? (
              <div className="pt-4">
                <div className="mb-8 text-center">
                  <div className="relative mx-auto mb-4 h-16 w-16"><div className="absolute inset-0 animate-pulse rounded-full bg-brass/20 blur-xl" />
                    <img src="/logo.png" alt="" className="relative h-16 w-16 rounded-full ring-4 ring-surface" /></div>
                  <h2 className="h-display text-[30px]">How can I help{currentCase ? " with this case" : ""}?</h2>
                  <p className="mx-auto mt-1 max-w-lg text-[14.5px] text-mute">Add papers, ask the law, draft, check citations or manage hearing dates. Every citation is checked before you see it.</p>
                </div>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {STARTERS.map((s, i) => (
                    <motion.button key={s.title} onClick={() => starter(s)} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                      className="card group flex items-start gap-3.5 p-4 text-left transition hover:-translate-y-0.5 hover:border-brass/40 hover:shadow-pop" data-testid={`starter-${i}`}>
                      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand transition group-hover:bg-brand group-hover:text-[rgb(var(--on-brand))]"><s.icon className="h-[18px] w-[18px]" /></div>
                      <div><p className="font-semibold text-ink">{s.title}</p><p className="text-[13px] text-mute">{s.text}</p></div>
                    </motion.button>))}
                </div>
              </div>
            ) : log.map(renderMsg)}
            {pending !== false && <BotCard m={{ role: "assistant" }}><Pending text={pending || undefined} /></BotCard>}
            <div ref={end} />
          </div>
        </div>

        <aside className="hidden xl:block">
          <div className="sticky top-24 space-y-4">
            <Card className="overflow-hidden">
              <div className="flex items-center gap-2 border-b border-line px-4 py-3"><BookMarked className="h-4 w-4 text-brass-ink" /><p className="h-display text-[15px]">Source</p></div>
              <div className="p-4">
                <AnimatePresence mode="wait">
                  {side ? (
                    <motion.div key={side.title} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} data-testid="source-panel">
                      <p className="font-display text-[15px] font-semibold leading-snug">{side.title}</p>
                      {side.sub && <p className="mt-0.5 text-[12.5px] text-mute">{side.sub}</p>}
                      {side.reason && <p className="mt-2 text-[13px] text-ink-2">{side.reason}</p>}
                      {side.text && <Passage className="mt-3 max-h-[52vh]">{side.text}</Passage>}
                      {(side.good || []).length > 0 && <div className="mt-3 space-y-1">{side.good!.map((g, i) => <p key={i} className="text-[12.5px] text-mute">{g.signal} by {g.by} ({g.year})</p>)}</div>}
                    </motion.div>
                  ) : <p className="text-[13.5px] text-mute">Hover any underlined citation to preview it, or click it (or a source chip) to read the passage here.</p>}
                </AnimatePresence>
              </div>
            </Card>
            <Card className="p-4">
              <p className="mb-2 flex items-center gap-2 text-[13px] font-semibold text-ink"><Wand2 className="h-4 w-4 text-seal" />What the marks mean</p>
              <div className="space-y-2 text-[12.5px] text-ink-2">
                <p className="flex items-center gap-2"><Stamp colour="green" />found and supports the point</p>
                <p className="flex items-center gap-2"><Stamp colour="amber" />look at it yourself</p>
                <p className="flex items-center gap-2"><Stamp colour="red" />wrong; fix before filing</p>
              </div>
            </Card>
          </div>
        </aside>
      </div>

      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 lg:left-[var(--sidebar,252px)]">
        <div className="mx-auto max-w-[1440px] bg-gradient-to-t from-bg via-bg/95 to-transparent px-4 pb-5 pt-10 sm:px-6 lg:px-10">
          <div className="pointer-events-auto xl:mr-[364px]">
            <div className="flex items-end gap-2 rounded-2xl border border-line-2 bg-surface p-2 shadow-pop transition focus-within:border-brand-2 focus-within:shadow-[0_0_0_4px_rgb(var(--brand)/.12),0_12px_40px_-12px_rgb(10_20_18/.35)]">
              <button onClick={openFiles} className="grid h-10 w-10 shrink-0 place-items-center rounded-xl text-ink-2 transition hover:bg-line/60 hover:text-ink" aria-label="Attach case papers" data-testid="attach">
                <Paperclip className="h-5 w-5" /></button>
              <textarea ref={ta} value={text} onChange={e => setText(e.target.value)} rows={1} data-testid="composer"
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                placeholder="Ask a question, draft a document, or set a reminder…"
                className="max-h-[200px] min-h-[40px] flex-1 resize-none bg-transparent px-1 py-2 text-[15px] leading-relaxed outline-none placeholder:text-mute" aria-label="Message" />
              <button onClick={() => send()} disabled={!text.trim() || pending !== false} aria-label="Send" data-testid="send"
                className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-seal text-white shadow transition hover:brightness-110 disabled:bg-line-2 disabled:text-mute disabled:shadow-none">
                {pending !== false ? <Dots className="scale-75" /> : <ArrowUp className="h-5 w-5" />}</button>
            </div>
            <div className="mt-2 flex flex-wrap justify-between gap-2 px-2 text-[11.5px] text-mute">
              <span className="flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-ok" />Names hidden before the AI sees them · citations checked and corrected automatically</span>
              <span className="hidden items-center gap-1.5 sm:flex"><Kbd>Enter</Kbd> send <Kbd>Shift Enter</Kbd> new line</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
