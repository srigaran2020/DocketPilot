import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CalendarDays, Download, FilePen, FileText, Lock, RefreshCcw, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { DateTile, DaysChip, StatusPill } from "@/components/legal";
import { PaperIntake } from "@/components/papers";
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, Input, Label, PageHeader, Skeleton, Textarea } from "@/components/ui";
import { api, download } from "@/lib/api";
import { DOC_SUGGESTIONS, S138_DOCS, docName, store } from "@/lib/utils";

export default function CaseDetail() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const matter = useQuery({ queryKey: ["matter", id], queryFn: () => api<any>("/matters/" + id) });
  const cases = useQuery({ queryKey: ["cases"], queryFn: () => api<any[]>("/cases") });
  const card = (cases.data || []).find(c => c.id === id) || {};
  const [docType, setDocType] = useState("");
  const [ins, setIns] = useState("");
  const draft = useMutation({
    mutationFn: () => { const wf = S138_DOCS[docType.trim()] || "general";
      return api(`/matters/${id}/drafts`, { json: { workflow: wf, doc_type: wf === "general" ? docType.trim() : null, instructions: ins.trim() || null } }); },
    onSuccess: d => { toast.success("Drafting started", { description: "Reading papers, researching and checking citations." }); nav(`/drafts/${d.id}`); },
  });
  const reread = useMutation({
    mutationFn: () => api(`/cases/${id}/reread`, { method: "POST" }),
    onSuccess: r => { toast.success(`${r.events.length} new date(s) found`); qc.invalidateQueries({ queryKey: ["matter", id] }); qc.invalidateQueries({ queryKey: ["calendar"] }); },
  });
  const m = matter.data;
  const dates = (m?.reminders || []).slice().sort((a: any, b: any) => (a.due_date < b.due_date ? -1 : 1));

  if (matter.isLoading) return <div className="space-y-4"><Skeleton className="h-12 w-80" /><Skeleton className="h-64" /></div>;
  if (matter.error) return <ErrorNote error={matter.error} />;

  return (
    <>
      <Link to="/cases" className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-mute hover:text-ink"><ArrowLeft className="h-4 w-4" />All cases</Link>
      <PageHeader eyebrow={[card.court, card.case_type].filter(Boolean).join(" · ") || "Case file"} title={card.case_number || m.title}
        subtitle={card.petitioner ? <><b className="text-ink-2">{card.petitioner}</b>{card.respondent && <> <span className="text-mute">versus</span> <b className="text-ink-2">{card.respondent}</b></>}</> : "Parties not read yet"}
        actions={<Button variant="secondary" icon={Sparkles} onClick={() => { store.sset("dp_chat_matter", id); nav("/ask"); }}>Ask about this case</Button>} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.45fr_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader icon={FilePen} title="Draft a document" subtitle="From this case's papers; every citation is checked before you see it." />
            <form className="space-y-4 px-5 pb-5" onSubmit={e => { e.preventDefault(); draft.mutate(); }}>
              <div><Label htmlFor="dtp">Document</Label>
                <Input id="dtp" list="doclist" value={docType} onChange={e => setDocType(e.target.value)} placeholder="e.g. Bail application, Divorce petition, Reply to legal notice" required />
                <datalist id="doclist">{DOC_SUGGESTIONS.map(x => <option key={x} value={x} />)}</datalist>
                <div className="mt-2 flex flex-wrap gap-1.5">{DOC_SUGGESTIONS.slice(0, 6).map(x => (
                  <button type="button" key={x} onClick={() => setDocType(x)} className="rounded-full border border-line px-2.5 py-1 text-[12px] text-ink-2 transition hover:border-brand-2/50 hover:bg-brand-soft hover:text-brand">{x}</button>))}</div></div>
              <div><Label htmlFor="ins" hint="(optional if the papers say it all)">What should it say?</Label>
                <Textarea id="ins" rows={3} value={ins} onChange={e => setIns(e.target.value)} className="min-h-[90px] font-sans"
                  placeholder="Facts, relief you want, anything the papers don't cover. Names are masked before the AI sees them." /></div>
              <ErrorNote error={draft.error} />
              <div className="flex items-center gap-3"><Button type="submit" variant="seal" icon={FilePen} loading={draft.isPending}>Draft it</Button>
                <span className="flex items-center gap-1.5 text-[12.5px] text-mute"><Lock className="h-3.5 w-3.5" />Usually one to three minutes</span></div>
            </form>
          </Card>

          <Card>
            <CardHeader icon={FileText} title="Case papers" subtitle={`${m.documents.length} paper(s) on file`} />
            <div className="space-y-4 px-5 pb-5">
              {m.documents.length > 0 && (
                <div className="overflow-hidden rounded-xl border border-line">{m.documents.map((d: any) => (
                  <div key={d.id || d.filename} className="flex items-center gap-3 border-b border-line px-4 py-3 last:border-0">
                    <FileText className="h-4 w-4 text-mute" /><span className="flex-1 truncate font-medium">{d.filename}</span>
                    <span className="text-[12.5px] text-mute">{d.pages} page(s)</span><Badge tone="ok"><Lock className="h-3 w-3" />{d.masks.length} hidden</Badge>
                  </div>))}</div>)}
              <PaperIntake matterId={id} compact onDone={r => { if (r.matter.id !== id) nav(`/cases/${r.matter.id}`); else qc.invalidateQueries({ queryKey: ["matter", id] }); }} />
            </div>
          </Card>

          <Card>
            <CardHeader icon={FilePen} title="Drafts" />
            <div className="px-3 pb-3">
              {m.drafts.length ? m.drafts.map((d: any) => (
                <Link key={d.id} to={`/drafts/${d.id}`} className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition hover:bg-raised">
                  <span className="rounded-md bg-raised px-2 py-0.5 font-mono text-[12px] ring-1 ring-line">v{d.version}</span>
                  <span className="flex-1 truncate font-medium">{docName(d.template, d)}</span><StatusPill status={d.status} />
                </Link>)) : <div className="px-2 pb-2"><Empty icon={FilePen} title="No drafts yet">Use “Draft a document” above.</Empty></div>}
            </div>
          </Card>
        </div>

        <Card className="h-fit xl:sticky xl:top-24">
          <CardHeader icon={CalendarDays} title="Case calendar" subtitle="Each date keeps the line it came from" />
          <div className="px-5 pb-5">
            {dates.length ? (
              <div className="space-y-2">{dates.map((r: any) => (
                <div key={r.id} className={`flex items-start gap-3 rounded-xl border border-line p-3 ${r.status === "done" ? "opacity-55" : ""}`}>
                  <DateTile iso={r.due_date} size="sm" />
                  <div className="min-w-0 flex-1"><p className="font-medium leading-snug">{r.title}</p>
                    {r.source && <p className="mt-1 line-clamp-2 text-[12.5px] italic text-mute">“{r.source}”</p>}</div>
                  <DaysChip iso={r.due_date} done={r.status === "done"} />
                </div>))}</div>
            ) : <Empty icon={CalendarDays} title="No dates yet">Dates in the papers appear here automatically.</Empty>}
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" icon={RefreshCcw} loading={reread.isPending} onClick={() => reread.mutate()}>Read dates again</Button>
              {dates.length > 0 && <Button variant="secondary" size="sm" icon={Download}
                onClick={() => download(`/matters/${id}/reminders.ics`, "case-dates.ics").catch(e => toast.error(e.message))}>Add to phone calendar</Button>}
            </div>
            <ErrorNote error={reread.error} />
          </div>
        </Card>
      </div>
    </>
  );
}
