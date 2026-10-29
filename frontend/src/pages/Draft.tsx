import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowLeft, BookMarked, Check, ClipboardCheck, Download, FileSearch, Gavel, ListChecks, Loader2, Pencil, ScrollText, ShieldCheck } from "lucide-react";
import { Fragment, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "@/components/toast";
import { CitationHover, Passage, ReleaseBanner, Stamp, StatusPill, statuteNote, whyColour } from "@/components/legal";
import { Badge, Button, Card, CardHeader, ErrorNote, PageHeader, Skeleton, Tabs, TabList, TabPanel, Textarea } from "@/components/ui";
import { api, download } from "@/lib/api";
import { cn, docName } from "@/lib/utils";

const STEPS = [["orchestrator", "Plan"], ["document_analysis", "Read papers"], ["research", "Research"], ["drafting", "Draft"],
  ["verification", "Verify"], ["strategy_risk", "Checklist"], ["monitoring", "Deadlines"]];

function Running({ d }: { d: any }) {
  const done = new Set((d.graph_trace || d.trace || []).map((t: any) => t.node));
  const active = STEPS.findIndex(([k]) => !done.has(k));
  return (
    <Card className="p-8">
      <div className="mx-auto max-w-2xl text-center">
        <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-brand-soft text-brand"><Loader2 className="h-7 w-7 animate-spin" /></div>
        <h2 className="h-display text-[24px]">Preparing your draft</h2>
        <p className="mt-1 text-[14px] text-mute">Reading the papers, researching, drafting and checking every citation. Usually one to three minutes.</p>
      </div>
      <ol className="mx-auto mt-8 grid max-w-3xl grid-cols-7 gap-2" data-testid="draft-steps">
        {STEPS.map(([k, l], i) => {
          const isDone = done.has(k), isActive = i === active;
          return (
            <li key={k} className="flex flex-col items-center text-center">
              <div className="relative flex w-full items-center">
                <div className={cn("h-0.5 flex-1", i === 0 ? "bg-transparent" : isDone || isActive ? "bg-brand-2" : "bg-line")} />
                <motion.div animate={isActive ? { scale: [1, 1.12, 1] } : {}} transition={{ repeat: Infinity, duration: 1.4 }}
                  className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-full border-2 text-[13px] font-semibold",
                    isDone ? "border-brand-2 bg-brand-2 text-[rgb(var(--on-brand))]" : isActive ? "border-seal bg-seal-soft text-seal" : "border-line-2 bg-surface text-mute")}>
                  {isDone ? <Check className="h-4 w-4" /> : i + 1}
                </motion.div>
                <div className={cn("h-0.5 flex-1", i === STEPS.length - 1 ? "bg-transparent" : isDone ? "bg-brand-2" : "bg-line")} />
              </div>
              <span className={cn("mt-2 text-[12px] font-medium", isDone ? "text-ink" : isActive ? "text-seal" : "text-mute")}>{l}</span>
            </li>);
        })}
      </ol>
    </Card>
  );
}

function DraftText({ text, citations, onPick }: { text: string; citations: any[]; onPick: (id: string) => void }) {
  const nodes = useMemo(() => {
    const raws = citations.map(c => c.raw).filter(Boolean).sort((a, b) => b.length - a.length);
    const ph = (s: string, k: string) => s.split(/\b([A-Z]+(?:_[A-Z]+)*_\d+)\b/g).map((p, i) => (i % 2
      ? <mark key={k + i} className="rounded bg-brass-soft px-1 font-mono text-[12.5px] text-brass-ink">{p}</mark> : <Fragment key={k + i}>{p}</Fragment>));
    const out: ReactNode[] = [];
    let rest = text, n = 0;
    while (rest) {
      let best = -1, hit = "";
      for (const r of raws) { const i = rest.indexOf(r); if (i >= 0 && (best < 0 || i < best)) { best = i; hit = r; } }
      if (best < 0) { out.push(...ph(rest, "r" + n++)); break; }
      out.push(...ph(rest.slice(0, best), "r" + n++));
      const c = citations.find(x => x.raw === hit);
      out.push(<CitationHover key={"c" + n++} c={c} onPin={() => onPick(c.id)}>{hit}</CitationHover>);
      rest = rest.slice(best + hit.length);
    }
    return out;
  }, [text, citations, onPick]);
  return <div className="legalpad max-h-[72vh] overflow-auto rounded-xl border border-line" data-testid="draft-text">{nodes}</div>;
}

export default function Draft() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["draft", id], queryFn: () => api<any>("/drafts/" + id), refetchInterval: d => (d.state.data?.status === "running" ? 4000 : false) });
  const [pick, setPick] = useState<string | null>(null);
  const [chunk, setChunk] = useState<any>(null);
  const [editing, setEditing] = useState(false);
  const [edit, setEdit] = useState("");
  const [ack, setAck] = useState<Set<string>>(new Set());
  const revise = useMutation({ mutationFn: () => api(`/drafts/${id}/revise`, { json: { text: edit } }),
    onSuccess: () => { setEditing(false); toast.success("Re-checking the edited text"); qc.invalidateQueries({ queryKey: ["draft", id] }); } });
  const approve = useMutation({ mutationFn: () => api(`/drafts/${id}/approve`, { json: { acknowledged: [...ack] } }),
    onSuccess: () => { toast.success("Approved", { description: "Real names restored. Word file ready." }); qc.invalidateQueries(); } });

  const d = q.data;
  if (q.isLoading) return <div className="space-y-4"><Skeleton className="h-12 w-96" /><Skeleton className="h-[60vh]" /></div>;
  if (q.error) return <ErrorNote error={q.error} />;
  const head = (
    <>
      <Link to={`/cases/${d.matter_id}`} className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-mute hover:text-ink"><ArrowLeft className="h-4 w-4" />Back to case</Link>
      <PageHeader eyebrow={`Draft v${d.version}`} title={docName(d.template, d)} actions={<StatusPill status={d.status} />} />
    </>);
  if (d.status === "running") return <>{head}<Running d={d} /></>;

  const rep = d.verification || { citations: [], statutes: [] };
  const needAck: string[] = rep.items_needing_acknowledgement || [];
  const editable = ["awaiting_approval", "blocked"].includes(d.status);
  const sel = rep.citations.find((c: any) => c.id === pick);
  const counts = { green: 0, amber: 0, red: 0 } as Record<string, number>;
  [...rep.citations, ...rep.statutes].forEach((c: any) => { counts[c.colour] = (counts[c.colour] || 0) + 1; });

  return (
    <>
      {head}
      {d.error && <div className="mb-4"><ErrorNote error={d.error} /></div>}
      <ReleaseBanner release={rep.release} approvedAt={d.status === "approved" ? d.approved_at || "today" : null} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(340px,1fr)]">
        <div className="min-w-0 space-y-6">
          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
              <ScrollText className="h-4 w-4 text-brand" /><p className="h-display text-[16px]">The draft</p>
              <span className="text-[12.5px] text-mute">Hover a citation to preview its proof; click to pin it.</span>
              <div className="ml-auto flex items-center gap-2">
                <Badge tone="ok">{counts.green} verified</Badge>{counts.amber > 0 && <Badge tone="warn">{counts.amber} check</Badge>}{counts.red > 0 && <Badge tone="bad">{counts.red} problem</Badge>}
                {editable && !editing && <Button variant="secondary" size="sm" icon={Pencil} onClick={() => { setEdit(d.redacted_text || ""); setEditing(true); }}>Edit</Button>}
              </div>
            </div>
            <div className="p-4">
              {editing ? (
                <div className="space-y-3"><Textarea value={edit} onChange={e => setEdit(e.target.value)} className="min-h-[56vh] font-display text-[15px] leading-[28px]" />
                  <div className="flex gap-2"><Button onClick={() => revise.mutate()} loading={revise.isPending} icon={ShieldCheck}>Re-check edited text</Button>
                    <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button></div><ErrorNote error={revise.error} /></div>
              ) : <DraftText text={d.redacted_text || ""} citations={rep.citations} onPick={id => { setPick(id); setChunk(null); }} />}
            </div>
          </Card>

          <Card>
            <CardHeader icon={FileSearch} title="Facts read from the papers" subtitle="Each fact keeps the sentence that supports it" />
            <div className="px-5 pb-5">
              <div className="overflow-hidden rounded-xl border border-line">{Object.entries(d.facts || {}).map(([k, v]) => (
                <div key={k} className="grid grid-cols-[minmax(120px,32%)_1fr] gap-4 border-b border-line px-4 py-3 last:border-0">
                  <span className="text-[13px] capitalize text-mute">{k.replace(/_/g, " ")}</span>
                  <div><p className="font-medium">{String(v)}</p>{(d.fact_sources || {})[k]?.quote && <p className="mt-0.5 text-[12.5px] italic text-mute">“{d.fact_sources[k].quote}”</p>}</div>
                </div>))}</div>
            </div>
          </Card>
        </div>

        <div className="space-y-6 xl:sticky xl:top-24 xl:h-fit">
          <Card>
            <CardHeader icon={BookMarked} title="Evidence" subtitle="What the selected citation rests on" />
            <div className="px-5 pb-5" data-testid="evidence">
              {sel ? (
                <motion.div key={sel.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
                  <div className="flex items-center gap-2"><Stamp colour={sel.colour} /><b className="font-display">{String(sel.verdict).replace("_", " ").toLowerCase()}</b></div>
                  <p className="text-[13.5px] text-ink-2">{sel.reason}</p>
                  {(sel.quotes || []).map((qq: any, i: number) => <p key={i} className="text-[13px]"><Badge>quote</Badge> <b>{qq.status.replace(/_/g, " ")}</b> <span className="text-mute">{qq.reason}</span></p>)}
                  {sel.proposition?.label && <><p className="text-[13px]"><Badge>supports?</Badge> <b>{sel.proposition.label.replace(/_/g, " ")}</b> <span className="text-mute">{sel.proposition.reason}</span></p>
                    {sel.proposition.passage && <><Passage>{sel.proposition.passage}</Passage><p className="text-[12.5px] text-mute">Page {sel.proposition.page}. {sel.proposition.explanation}</p></>}</>}
                  {(sel.good_law || []).length > 0 && <div><p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-mute">Later treatment · signal only</p>
                    {sel.good_law.map((g: any, i: number) => <p key={i} className="text-[12.5px] text-mute">{g.signal} by {g.by} ({g.year})</p>)}</div>}
                </motion.div>
              ) : chunk ? (
                <div className="space-y-2"><p className="font-display font-semibold">{chunk.title}</p><p className="text-[12.5px] text-mute">{chunk.court} · {chunk.year} · page {chunk.page}</p><Passage>{chunk.text}</Passage></div>
              ) : <p className="rounded-xl border border-dashed border-line-2 bg-raised/60 p-4 text-[13.5px] text-mute">Select a citation in the draft or in the check list.</p>}
            </div>
          </Card>

          {editable && (
            <Card className="border-brand-2/30">
              <CardHeader icon={ClipboardCheck} title="Sign-off" subtitle="Nothing leaves DocketPilot until you approve it" />
              <div className="space-y-3 px-5 pb-5">
                {rep.release === "blocked" && <ErrorNote error="Blocked. Edit the draft to fix the red items, then re-check." />}
                {needAck.map(i => (
                  <label key={i} className="flex cursor-pointer items-start gap-3 rounded-xl border border-warn/30 bg-warn-soft/60 p-3 text-[13.5px]">
                    <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[rgb(var(--warn))]" checked={ack.has(i)}
                      onChange={() => setAck(s => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n; })} />
                    <span>I have personally checked item <b>{i}</b></span></label>))}
                <Button className="w-full" size="lg" icon={ShieldCheck} disabled={rep.release === "blocked"} loading={approve.isPending} onClick={() => approve.mutate()} data-testid="approve">
                  Approve and prepare Word file</Button>
                <ErrorNote error={approve.error} />
              </div>
            </Card>
          )}
          {d.status === "approved" && (
            <Card className="border-ok/30 p-5">
              <p className="h-display text-[17px] text-ok">Approved</p><p className="mb-4 text-[13.5px] text-ink-2">Real names restored. Includes a removable verification page.</p>
              <Button icon={Download} className="w-full" onClick={() => download(`/drafts/${id}/download`, `draft-v${d.version}.docx`).catch(e => toast.error(e.message))}>Download .docx</Button>
            </Card>
          )}

          <Card>
            <Tabs defaultValue="check">
              <div className="px-5 pt-5"><TabList tabs={[{ value: "check", label: "Checks", icon: ShieldCheck, count: rep.citations.length + rep.statutes.length },
                { value: "list", label: d.template === "general" ? "Still needed" : "Ingredients", icon: ListChecks, count: (d.checklist || []).length },
                { value: "prec", label: "Precedent", icon: Gavel, count: (d.similar_cases || []).length }]} /></div>
              <TabPanel value="check" className="mt-3 px-3 pb-3">
                {rep.citations.map((c: any) => (
                  <button key={c.id} onClick={() => { setPick(c.id); setChunk(null); }} className={cn("flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition hover:bg-raised", pick === c.id && "bg-brand-soft")}>
                    <Stamp colour={c.colour} /><span className="min-w-0"><span className="block truncate font-mono text-[12.5px] text-ink">{c.raw}</span><span className="text-[12.5px] text-mute">{whyColour(c)}</span></span></button>))}
                {rep.statutes.map((s: any, i: number) => (
                  <div key={i} className="flex items-start gap-3 px-3 py-2.5"><Stamp colour={s.colour} /><span className="min-w-0"><span className="block font-mono text-[12.5px]">{s.raw}</span><span className="text-[12.5px] text-mute">{statuteNote(s)}</span></span></div>))}
                {!rep.citations.length && !rep.statutes.length && <p className="px-3 py-2 text-[13.5px] text-mute">No citations or sections in this draft.</p>}
              </TabPanel>
              <TabPanel value="list" className="mt-3 px-3 pb-3">
                {(d.checklist || []).map((e: any, i: number) => (
                  <div key={i} className="flex items-start gap-3 px-3 py-2.5"><Stamp colour={({ satisfied: "green", unclear: "amber", missing: "red" } as any)[e.status]} />
                    <span><span className="block text-[14px] font-medium">{e.title}</span><span className="text-[12.5px] text-mute">{e.evidence}</span></span></div>))}
              </TabPanel>
              <TabPanel value="prec" className="mt-3 px-3 pb-3">
                {(d.similar_cases || []).map((s: any) => (
                  <button key={s.chunk_id} onClick={async () => { setPick(null); setChunk(await api("/chunks/" + s.chunk_id)); }}
                    className="flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition hover:bg-raised">
                    <Badge tone={s.outcome === "unknown" ? "idle" : "brass"}>{s.outcome}</Badge>
                    <span className="min-w-0"><span className="block truncate text-[14px] font-medium">{s.label}</span>
                      <span className="text-[12.5px] text-mute">{s.court} · {s.year}{s.outcome_confidence < 0.5 ? " · low confidence" : ""}</span></span></button>))}
              </TabPanel>
            </Tabs>
          </Card>
        </div>
      </div>
    </>
  );
}
