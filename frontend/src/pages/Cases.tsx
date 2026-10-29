import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Briefcase, FolderPlus, Gavel, Paperclip, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { StatusPill } from "@/components/legal";
import { PaperIntake } from "@/components/papers";
import { Badge, Button, Card, Dialog, Empty, ErrorNote, Input, PageHeader, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { daysFrom, niceDate } from "@/lib/utils";

export default function Cases() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const cases = useQuery({ queryKey: ["cases"], queryFn: () => api<any[]>("/cases") });
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<"all" | "soon" | "drafts">("all");
  const [addOpen, setAddOpen] = useState(false);
  const [manual, setManual] = useState(false);
  const create = useMutation({
    mutationFn: (f: { title: string; court: string }) => api("/matters", { json: { title: f.title, court: f.court || null } }),
    onSuccess: m => { qc.invalidateQueries({ queryKey: ["cases"] }); nav(`/cases/${m.id}`); },
  });
  const rows = useMemo(() => (cases.data || []).filter(c => {
    const hay = [c.case_number, c.title, c.petitioner, c.respondent, c.court, c.case_type].join(" ").toLowerCase();
    if (q && !hay.includes(q.toLowerCase())) return false;
    if (filter === "soon") return c.next_hearing && daysFrom(c.next_hearing) >= 0 && daysFrom(c.next_hearing) <= 14;
    if (filter === "drafts") return c.latest_draft_status === "awaiting_approval" || c.latest_draft_status === "blocked";
    return true;
  }), [cases.data, q, filter]);

  return (
    <>
      <PageHeader eyebrow="Case files" title="Cases" subtitle="Every matter with its parties, court, next hearing, papers and drafts."
        actions={<><Button variant="secondary" icon={FolderPlus} onClick={() => setManual(true)}>New case file</Button>
          <Button icon={Paperclip} onClick={() => setAddOpen(true)} data-testid="add-papers">Add case papers</Button></>} />

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
          <Input icon={Search} value={q} onChange={e => setQ(e.target.value)} placeholder="Search by case number, party or court" className="min-w-[240px] flex-1" aria-label="Search cases" />
          <div className="flex gap-1 rounded-lg bg-raised p-1 ring-1 ring-line">
            {([["all", "All"], ["soon", "Hearing in 14 days"], ["drafts", "Draft needs review"]] as const).map(([k, l]) => (
              <button key={k} onClick={() => setFilter(k)} className={`rounded-md px-3 py-1.5 text-[12.5px] font-medium transition ${filter === k ? "bg-surface text-ink shadow-sm" : "text-mute hover:text-ink"}`}>{l}</button>
            ))}
          </div>
        </div>
        {cases.isLoading ? <div className="space-y-2 p-4">{[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-14" />)}</div>
          : cases.error ? <div className="p-4"><ErrorNote error={cases.error} /></div>
          : rows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[14px]">
                <thead><tr className="border-b border-line bg-raised/60 text-[11.5px] uppercase tracking-wider text-mute">
                  <th className="px-4 py-2.5 font-medium">Case</th><th className="px-4 py-2.5 font-medium">Parties</th><th className="px-4 py-2.5 font-medium">Court · type</th>
                  <th className="px-4 py-2.5 font-medium">Next hearing</th><th className="px-4 py-2.5 font-medium">Papers</th><th className="px-4 py-2.5 font-medium">Latest draft</th></tr></thead>
                <tbody>
                  {rows.map((c, i) => {
                    const soon = c.next_hearing && daysFrom(c.next_hearing) >= 0 && daysFrom(c.next_hearing) <= 7;
                    return (
                      <motion.tr key={c.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.02 }}
                        onClick={() => nav(`/cases/${c.id}`)} className="cursor-pointer border-b border-line transition last:border-0 hover:bg-raised">
                        <td className="px-4 py-3.5"><div className="flex items-center gap-3">
                          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand"><Gavel className="h-4 w-4" /></div>
                          <Link to={`/cases/${c.id}`} className="font-semibold text-ink hover:text-brand-2" onClick={e => e.stopPropagation()}>{c.case_number || c.title}</Link></div></td>
                        <td className="px-4 py-3.5 text-ink-2">{c.petitioner ? <>{c.petitioner}{c.respondent && <span className="text-mute"> v. </span>}{c.respondent}</> : <span className="text-mute">Not read yet</span>}</td>
                        <td className="px-4 py-3.5 text-mute">{[c.court, c.case_type].filter(Boolean).join(" · ") || "—"}</td>
                        <td className="px-4 py-3.5">{c.next_hearing ? <span className={soon ? "font-semibold text-seal" : "font-medium"}>{niceDate(c.next_hearing)}</span> : <span className="text-mute">—</span>}</td>
                        <td className="px-4 py-3.5"><Badge>{c.documents}</Badge></td>
                        <td className="px-4 py-3.5">{c.latest_draft_status ? <StatusPill status={c.latest_draft_status} /> : <span className="text-mute">—</span>}</td>
                      </motion.tr>);
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-6"><Empty icon={Briefcase} title={q || filter !== "all" ? "No case matches" : "No cases yet"}
              action={!q && filter === "all" && <Button icon={Paperclip} onClick={() => setAddOpen(true)}>Add case papers</Button>}>
              {q || filter !== "all" ? "Try another search or filter." : "Add papers and the case file, parties and dates are created for you."}</Empty></div>
          )}
      </Card>

      <Dialog open={addOpen} onOpenChange={setAddOpen} title="Add case papers" description="DocketPilot reads the case number, files the paper and adds its dates to your calendar." wide>
        <PaperIntake onDone={() => qc.invalidateQueries({ queryKey: ["cases"] })} />
      </Dialog>
      <Dialog open={manual} onOpenChange={setManual} title="Open a case file by hand" description="Use this when you have no papers yet.">
        <form className="space-y-3" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); create.mutate({ title: String(f.get("t")), court: String(f.get("c") || "") }); }}>
          <Input name="t" placeholder="Case number or your label" required aria-label="Case number" />
          <Input name="c" placeholder="Court (optional)" aria-label="Court" />
          <ErrorNote error={create.error} />
          <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={() => setManual(false)}>Cancel</Button><Button type="submit" loading={create.isPending}>Open case file</Button></div>
        </form>
      </Dialog>
    </>
  );
}
