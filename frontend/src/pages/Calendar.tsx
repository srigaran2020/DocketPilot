import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { CalendarPlus, Check, ChevronLeft, ChevronRight, MousePointerClick, Trash2, Undo2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { DateTile, DaysChip, KIND_BAR, KindPill, Passage } from "@/components/legal";
import { Badge, Button, Card, CardHeader, ErrorNote, Input, PageHeader, Select, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { cn, isoDay, parseDay, shortCase } from "@/lib/utils";

const WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function CalendarPage() {
  const qc = useQueryClient();
  const now = new Date();
  const [month, setMonth] = useState(new Date(now.getFullYear(), now.getMonth(), 1));
  const [selId, setSelId] = useState<string | null>(null);
  const [dayList, setDayList] = useState<string | null>(null);
  const gridStart = useMemo(() => { const g = new Date(month); g.setDate(1 - ((month.getDay() + 6) % 7)); return g; }, [month]);
  const gridEnd = useMemo(() => { const g = new Date(gridStart); g.setDate(g.getDate() + 41); return g; }, [gridStart]);
  const cal = useQuery({ queryKey: ["calendar", isoDay(gridStart)], queryFn: () => api<any>(`/calendar?start=${isoDay(gridStart)}&end=${isoDay(gridEnd)}`) });
  const cases = useQuery({ queryKey: ["cases"], queryFn: () => api<any[]>("/cases") });
  const events: any[] = cal.data?.events || [];
  const byDay = useMemo(() => { const m: Record<string, any[]> = {}; events.forEach(e => (m[e.date] = m[e.date] || []).push(e)); return m; }, [events]);
  const sel = events.find(e => e.id === selId);
  const refresh = () => qc.invalidateQueries({ queryKey: ["calendar"] });
  const toggle = useMutation({ mutationFn: (e: any) => api("/reminders/" + e.id, { method: "PATCH", json: { status: e.status === "done" ? "open" : "done" } }), onSuccess: refresh });
  const del = useMutation({ mutationFn: (e: any) => api("/reminders/" + e.id, { method: "DELETE" }), onSuccess: () => { setSelId(null); toast("Date removed"); refresh(); } });
  const add = useMutation({
    mutationFn: (f: { m: string; t: string; d: string }) => api("/reminders", { json: { matter_id: f.m, title: f.t, date: f.d } }),
    onSuccess: (_r, f) => { toast.success("Added to the calendar"); setMonth(new Date(f.d.slice(0, 7) + "-01T00:00:00")); refresh(); },
  });
  const todayIso = isoDay(now);

  return (
    <>
      <PageHeader eyebrow="Hearings, deadlines and reminders" title="Calendar" subtitle="Dates read from your papers, each linked to the sentence it came from." />
      {(cal.data?.due_this_week || []).length > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-2 rounded-xl border border-seal/20 bg-seal-soft/50 px-4 py-3">
          <span className="mr-1 text-[13px] font-semibold text-seal">This week</span>
          {cal.data.due_this_week.map((e: any) => (
            <button key={e.id} onClick={() => { setSelId(e.id); setDayList(null); }} className="rounded-lg border border-line bg-surface px-2.5 py-1 text-[12.5px] shadow-sm transition hover:border-seal/40">
              <b>{parseDay(e.date).toLocaleDateString("en-IN", { weekday: "short", day: "numeric" })}</b> {e.case} · {e.title}</button>))}
        </div>
      )}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_330px]">
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
            <Button variant="secondary" size="icon" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))} aria-label="Previous month"><ChevronLeft className="h-4 w-4" /></Button>
            <Button variant="secondary" size="icon" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))} aria-label="Next month"><ChevronRight className="h-4 w-4" /></Button>
            <h2 className="h-display ml-2 text-[20px]">{month.toLocaleDateString("en-IN", { month: "long", year: "numeric" })}</h2>
            <Button variant="ghost" size="sm" onClick={() => setMonth(new Date(now.getFullYear(), now.getMonth(), 1))}>Today</Button>
            <div className="ml-auto flex flex-wrap gap-1.5"><Badge tone="seal">Hearing</Badge><Badge tone="warn">Deadline</Badge><Badge tone="ok">Filing · notice · order</Badge><Badge>Reminder</Badge></div>
          </div>
          {cal.isLoading ? <Skeleton className="m-4 h-[540px]" /> : (
            <div className="grid grid-cols-7" data-testid="cal-grid">
              {WD.map(d => <div key={d} className="border-b border-line bg-raised/60 px-2 py-2 text-center text-[11px] font-medium uppercase tracking-wider text-mute">{d}</div>)}
              {Array.from({ length: 42 }, (_, i) => {
                const d = new Date(gridStart); d.setDate(gridStart.getDate() + i);
                const k = isoDay(d), evs = byDay[k] || [], other = d.getMonth() !== month.getMonth(), today = k === todayIso;
                return (
                  <div key={k} className={cn("min-h-[108px] border-b border-r border-line p-1.5 transition [&:nth-child(7n+7)]:border-r-0", other ? "bg-raised/40" : "bg-surface hover:bg-raised/50")}>
                    <div className={cn("mb-1 grid h-7 w-7 place-items-center rounded-full text-[13px] font-semibold", today ? "bg-seal text-white" : other ? "text-line-2" : "text-ink-2")}>{d.getDate()}</div>
                    <div className="space-y-1">
                      {evs.slice(0, 3).map(e => (
                        <motion.button layout key={e.id} onClick={() => { setSelId(e.id); setDayList(null); }} title={`${e.case} · ${e.title}`}
                          className={cn("block w-full truncate rounded-md border-l-[3px] px-1.5 py-0.5 text-left text-[11.5px] font-medium transition hover:brightness-95",
                            KIND_BAR[e.kind] || "border-l-line-2 bg-line/60 text-ink-2", e.status === "done" && "line-through opacity-50", selId === e.id && "ring-2 ring-brand-2/50")}>
                          <b>{shortCase(e.case)}</b> {e.title}</motion.button>))}
                      {evs.length > 3 && <button onClick={() => { setDayList(k); setSelId(null); }} className="px-1.5 text-[11.5px] font-medium text-brand-2 hover:underline">+{evs.length - 3} more</button>}
                    </div>
                  </div>);
              })}
            </div>)}
          <ErrorNote error={cal.error} />
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Details" />
            <div className="px-5 pb-5" data-testid="cal-details">
              {sel ? (
                <motion.div key={sel.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
                  <div className="flex items-center gap-3"><DateTile iso={sel.date} /><div><p className="font-semibold leading-snug">{sel.title}</p>
                    <div className="mt-1 flex items-center gap-2"><KindPill kind={sel.kind} label={sel.kind_label} /><DaysChip iso={sel.date} done={sel.status === "done"} /></div></div></div>
                  <Link to={`/cases/${sel.matter_id}`} className="block font-medium text-brand-2 hover:underline">{sel.case}{sel.petitioner ? ` · ${sel.petitioner}` : ""}</Link>
                  {sel.source && <Passage>{sel.source}</Passage>}
                  {sel.warn_on && <p className="text-[12.5px] text-mute">Reminder from {sel.warn_on}</p>}
                  <div className="flex gap-2"><Button size="sm" icon={sel.status === "done" ? Undo2 : Check} loading={toggle.isPending} onClick={() => toggle.mutate(sel)}>{sel.status === "done" ? "Mark not done" : "Mark done"}</Button>
                    <Button size="sm" variant="danger" icon={Trash2} onClick={() => { if (confirm("Delete this date from the calendar?")) del.mutate(sel); }}>Delete</Button></div>
                </motion.div>
              ) : dayList ? (
                <div className="space-y-1">{(byDay[dayList] || []).map(e => <button key={e.id} onClick={() => setSelId(e.id)} className="block w-full rounded-lg px-2 py-1.5 text-left text-[13.5px] hover:bg-raised">{e.case} · {e.title}</button>)}</div>
              ) : <div className="flex flex-col items-center rounded-xl border border-dashed border-line-2 bg-raised/60 p-6 text-center text-[13.5px] text-mute"><MousePointerClick className="mb-2 h-5 w-5" />Click any date on the calendar.</div>}
            </div>
          </Card>
          <Card>
            <CardHeader icon={CalendarPlus} title="Add a reminder" />
            <form className="space-y-3 px-5 pb-5" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); add.mutate({ m: String(f.get("m")), t: String(f.get("t")), d: String(f.get("d")) }); e.currentTarget.reset(); }}>
              <Select name="m" required aria-label="Case"><option value="">Choose a case…</option>{(cases.data || []).map(c => <option key={c.id} value={c.id}>{c.label || c.title}</option>)}</Select>
              <Input name="t" placeholder="e.g. Hearing - cross-examination" required aria-label="Title" />
              <Input name="d" type="date" required aria-label="Date" />
              <Button type="submit" className="w-full" loading={add.isPending}>Add to calendar</Button>
              <ErrorNote error={add.error} />
              <p className="text-[12.5px] text-mute">Tip: in the chat you can type “Remind me about the hearing on 12 November”.</p>
            </form>
          </Card>
        </div>
      </div>
    </>
  );
}
