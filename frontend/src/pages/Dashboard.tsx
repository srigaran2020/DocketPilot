import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowRight, ArrowUpRight, BookOpen, Briefcase, CalendarDays, FileCheck2, FilePen, Gavel, Inbox, MessageSquareText, Sparkles } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { DateTile, DaysChip, KindPill, StatusPill } from "@/components/legal";
import { Button, Card, CardHeader, Empty, ErrorNote, FadeIn, PageHeader, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { docName, greeting, isoDay, niceDate, store } from "@/lib/utils";

const QUICK = [
  { icon: FilePen, title: "Draft a document", text: "Petition, application, notice or reply", ask: "Draft a ", tone: "from-seal/15 to-seal/0 text-seal" },
  { icon: MessageSquareText, title: "Ask a legal question", text: "Answers from real judgments and Acts", ask: "What does the law say about ", tone: "from-brand-2/15 to-brand-2/0 text-brand-2" },
  { icon: BookOpen, title: "Find a section", text: "Central Acts, searched by topic", to: "/research", tone: "from-brass/20 to-brass/0 text-brass-ink" },
  { icon: FileCheck2, title: "Check citations", text: "Paste text; wrong citations get fixed", to: "/verify", tone: "from-ok/15 to-ok/0 text-ok" },
];

function Stat({ label, value, icon: Icon, accent, loading, to }: { label: string; value: number; icon: any; accent: string; loading: boolean; to: string }) {
  return (
    <Link to={to} className="card group relative overflow-hidden p-5 transition hover:-translate-y-0.5 hover:shadow-pop">
      <div className={`absolute inset-x-0 top-0 h-1 ${accent}`} />
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[12.5px] font-medium text-mute">{label}</p>
          {loading ? <Skeleton className="mt-2 h-9 w-14" /> : <p className="mt-1 font-display text-[38px] font-semibold leading-none text-ink">{value}</p>}
        </div>
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-raised text-ink-2 ring-1 ring-line transition group-hover:text-brand"><Icon className="h-5 w-5" /></div>
      </div>
      <p className="absolute bottom-4 right-5 flex items-center gap-1 text-[12.5px] font-medium text-brand-2 opacity-0 transition group-hover:opacity-100">Open <ArrowRight className="h-3.5 w-3.5" /></p>
    </Link>
  );
}

export default function Dashboard() {
  const { me } = useAuth();
  const nav = useNavigate();
  const cases = useQuery({ queryKey: ["cases"], queryFn: () => api<any[]>("/cases") });
  const cal = useQuery({ queryKey: ["calendar"], queryFn: () => api<any>("/calendar") });
  const desk = useQuery({ queryKey: ["dashboard"], queryFn: () => api<any>("/dashboard") });
  const loading = cases.isLoading || cal.isLoading || desk.isLoading;
  const today = isoDay(new Date());
  const upcoming = (cal.data?.events || []).filter((e: any) => e.status === "open" && e.date >= today).slice(0, 7);
  const hearings = (cal.data?.due_this_week || []).filter((e: any) => e.kind === "hearing").length;
  const waiting = desk.data?.drafts_needing_action || [];
  // "Adv. R. Meenakshi" -> "Meenakshi": skip titles and initials
  const first = (me?.full_name || "").split(/\s+/).find(w => w.replace(/\./g, "").length > 1 && !/^(adv|dr|mr|ms|mrs)\.?$/i.test(w)) || "";
  const quick = (q: (typeof QUICK)[number]) => { if (q.ask) { store.sset("dp_prefill", q.ask); nav("/ask"); } else nav(q.to!); };

  return (
    <>
      <PageHeader eyebrow={new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
        title={<>{greeting()}{first ? `, ${first}` : ""}</>} subtitle="Here is your docket for today."
        actions={<Button icon={Sparkles} onClick={() => nav("/ask")}>Ask DocketPilot</Button>} />
      <ErrorNote error={cases.error || cal.error || desk.error} />

      {!loading && (cases.data || []).length === 0 && (
        <FadeIn className="mb-6">
          <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-brass/30 bg-gradient-to-r from-brass-soft to-transparent px-6 py-5">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-surface text-brass-ink shadow-card"><Sparkles className="h-5 w-5" /></div>
            <div className="flex-1"><p className="h-display text-[17px]">New here? Start with your first case papers.</p>
              <p className="text-[13.5px] text-ink-2">Attach them in the chat: the case file, parties and hearing dates are created for you.</p></div>
            <Button variant="secondary" onClick={() => nav("/guide")}>Open the guide</Button>
          </div>
        </FadeIn>
      )}

      <div className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {QUICK.map((q, i) => (
          <motion.button key={q.title} onClick={() => quick(q)} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
            className="card group flex items-start gap-3.5 p-4 text-left transition hover:-translate-y-0.5 hover:border-line-2 hover:shadow-pop" data-testid={`quick-${i}`}>
            <div className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br ${q.tone}`}><q.icon className="h-5 w-5" /></div>
            <div className="min-w-0 flex-1"><p className="font-semibold text-ink">{q.title}</p><p className="text-[13px] text-mute">{q.text}</p></div>
            <ArrowUpRight className="h-4 w-4 text-mute opacity-0 transition group-hover:opacity-100" />
          </motion.button>
        ))}
      </div>

      <div className="mb-7 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="Active cases" value={(cases.data || []).length} icon={Briefcase} accent="bg-brand-2" loading={loading} to="/cases" />
        <Stat label="Hearings in the next 7 days" value={hearings} icon={Gavel} accent="bg-seal" loading={loading} to="/calendar" />
        <Stat label="Drafts waiting for you" value={waiting.length} icon={Inbox} accent="bg-brass" loading={loading} to="/cases" />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.5fr_1fr]">
        <Card>
          <CardHeader icon={CalendarDays} title="Coming up" subtitle="Hearings, deadlines and reminders"
            action={<Button variant="ghost" size="sm" onClick={() => nav("/calendar")}>Calendar <ArrowRight className="h-3.5 w-3.5" /></Button>} />
          <div className="px-5 pb-5">
            {loading ? <div className="space-y-3">{[0, 1, 2].map(i => <Skeleton key={i} className="h-16" />)}</div>
              : upcoming.length ? (
                <ol className="relative space-y-1 before:absolute before:bottom-6 before:left-[26px] before:top-6 before:w-px before:bg-line">
                  {upcoming.map((e: any, i: number) => (
                    <motion.li key={e.id} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}>
                      <Link to={`/cases/${e.matter_id}`} className="relative flex items-center gap-4 rounded-xl p-2 transition hover:bg-raised">
                        <DateTile iso={e.date} />
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium text-ink">{e.title}</p>
                          <p className="truncate text-[13px] text-mute">{e.case}{e.petitioner ? ` · ${e.petitioner}` : ""}</p>
                        </div>
                        <div className="hidden flex-col items-end gap-1 sm:flex"><KindPill kind={e.kind} label={e.kind_label} /><DaysChip iso={e.date} /></div>
                      </Link>
                    </motion.li>
                  ))}
                </ol>
              ) : <Empty icon={CalendarDays} title="No dates yet">Attach a case paper and its dates go on the calendar automatically.</Empty>}
          </div>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader icon={Inbox} title="On your desk" subtitle="Drafts that need your review" />
            <div className="px-3 pb-3">
              {loading ? <div className="space-y-2 px-2 pb-2">{[0, 1].map(i => <Skeleton key={i} className="h-12" />)}</div>
                : waiting.length ? waiting.map((r: any) => (
                  <Link key={r.id} to={`/drafts/${r.id}`} className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition hover:bg-raised">
                    <div className="grid h-9 w-9 place-items-center rounded-lg bg-warn-soft text-warn"><FilePen className="h-4 w-4" /></div>
                    <div className="min-w-0 flex-1"><p className="truncate text-[14px] font-medium">v{r.version} · {docName(r.template, r)}</p><p className="truncate text-[12.5px] text-mute">{r.matter}</p></div>
                    <StatusPill status={r.status} />
                  </Link>
                )) : <div className="px-2 pb-2"><Empty icon={Inbox} title="Nothing waiting">You're all caught up.</Empty></div>}
            </div>
          </Card>
          <Card>
            <CardHeader icon={Briefcase} title="Recent cases" action={<Button variant="ghost" size="sm" onClick={() => nav("/cases")}>All</Button>} />
            <div className="px-3 pb-3">
              {loading ? <div className="space-y-2 px-2 pb-2">{[0, 1, 2].map(i => <Skeleton key={i} className="h-11" />)}</div>
                : (cases.data || []).length ? (cases.data || []).slice(0, 5).map((c: any) => (
                  <Link key={c.id} to={`/cases/${c.id}`} className="block rounded-xl px-3 py-2.5 transition hover:bg-raised">
                    <p className="truncate text-[14px] font-medium">{c.case_number || c.title}</p>
                    <p className="truncate text-[12.5px] text-mute">{c.petitioner ? `${c.petitioner}${c.respondent ? " v. " + c.respondent : ""}` : "Parties not read yet"}
                      {c.next_hearing ? ` · next hearing ${niceDate(c.next_hearing)}` : ""}</p>
                  </Link>
                )) : <div className="px-2 pb-2"><Empty icon={Briefcase} title="No cases yet" /></div>}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
