import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { BookOpen, ChevronDown, Clock3, Gavel, Quote, Search, Scale } from "lucide-react";
import { useState } from "react";
import { Passage, Stamp } from "@/components/legal";
import { Badge, Button, Card, Empty, ErrorNote, Input, PageHeader, Select, Skeleton, Tabs, TabList, TabPanel } from "@/components/ui";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

function Judgments() {
  const [mode, setMode] = useState("hybrid_rerank");
  const [court, setCourt] = useState("");
  const s = useMutation({ mutationFn: (q: string) => { const qs = new URLSearchParams({ q, mode }); if (court) qs.set("court_level", court); return api("/search?" + qs); } });
  return (
    <div className="space-y-5">
      <form className="flex flex-col gap-2 md:flex-row" onSubmit={e => { e.preventDefault(); s.mutate(String(new FormData(e.currentTarget).get("q"))); }}>
        <Input icon={Search} name="q" placeholder="e.g. presumption under section 139 can be rebutted" className="flex-1" required aria-label="Search judgments" />
        <Select value={mode} onChange={e => setMode(e.target.value)} className="md:w-40" aria-label="Mode"><option value="hybrid_rerank">Best match</option><option value="hybrid">Balanced</option><option value="lexical">Exact words</option></Select>
        <Select value={court} onChange={e => setCourt(e.target.value)} className="md:w-40" aria-label="Court"><option value="">All courts</option><option value="SC">Supreme Court</option><option value="HC">High Courts</option></Select>
        <Button type="submit" loading={s.isPending} icon={Search}>Search</Button>
      </form>
      <ErrorNote error={s.error} />
      {s.isPending && <div className="space-y-3">{[0, 1, 2].map(i => <Skeleton key={i} className="h-28" />)}</div>}
      {s.data && (<>
        <p className="flex flex-wrap items-center gap-2 text-[12.5px] text-mute"><Clock3 className="h-3.5 w-3.5" />{s.data.hits.length} passages ·
          {Object.entries(s.data.timings).map(([k, v]) => ` ${k.replace("_ms", "")} ${Math.round(v as number)} ms`).join(" ·")}{s.data.notice ? ` · ${s.data.notice}` : ""}</p>
        {s.data.hits.length ? s.data.hits.map((h: any, i: number) => (
          <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} className="rounded-xl border border-line p-4">
            <div className="mb-2 flex flex-wrap items-start gap-2"><Gavel className="mt-0.5 h-4 w-4 text-brand" /><p className="h-display flex-1 text-[16px]">{h.title}</p>
              {(h.citations || []).map((c: string) => <Badge key={c} tone="brass">{c}</Badge>)}</div>
            <p className="mb-2 text-[12.5px] text-mute">{h.court} · {h.year} · page {h.page}</p><Passage>{h.text}</Passage>
          </motion.div>)) : <Empty icon={Search} title="No results">Try different words or the "Exact words" mode.</Empty>}
      </>)}
    </div>
  );
}

function Acts({ acts }: { acts: any[] }) {
  const [open, setOpen] = useState<number | null>(0);
  const s = useMutation({ mutationFn: (f: { q: string; act: string }) => { const qs = new URLSearchParams({ q: f.q }); if (f.act) qs.set("act", f.act); return api<any[]>("/statutes/search?" + qs); } });
  return (
    <div className="space-y-5">
      <form className="flex flex-col gap-2 md:flex-row" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); setOpen(0); s.mutate({ q: String(f.get("q")), act: String(f.get("act") || "") }); }}>
        <Input icon={BookOpen} name="q" placeholder="e.g. anticipatory bail · divorce cruelty · specific performance" className="flex-1" required aria-label="Topic" />
        <Select name="act" className="md:w-64" aria-label="Act"><option value="">All Acts</option>{acts.map(a => <option key={a.short_name} value={a.short_name}>{a.title.replace(/^The /, "")}</option>)}</Select>
        <Button type="submit" loading={s.isPending}>Find</Button>
      </form>
      <ErrorNote error={s.error} />
      {s.isPending && <div className="space-y-2">{[0, 1, 2].map(i => <Skeleton key={i} className="h-14" />)}</div>}
      {s.data && (s.data.length ? (
        <div className="overflow-hidden rounded-xl border border-line" data-testid="section-results">{s.data.map((x, i) => (
          <div key={i} className="border-b border-line last:border-0">
            <button onClick={() => setOpen(open === i ? null : i)} className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-raised">
              <span className="rounded-md bg-brand-soft px-2 py-0.5 font-mono text-[12px] font-medium text-brand">s.{x.section}</span>
              <span className="min-w-0 flex-1"><span className="block truncate font-medium">{x.heading || "Section " + x.section}</span><span className="text-[12.5px] text-mute">{x.act_title.replace(/^The /, "")}</span></span>
              <ChevronDown className={cn("h-4 w-4 text-mute transition", open === i && "rotate-180")} /></button>
            {open === i && <div className="px-4 pb-4"><Passage>{x.text}</Passage>{x.source_url && <p className="mt-2 text-[12px] text-mute">Source: India Code · {x.source_url}</p>}</div>}
          </div>))}</div>
      ) : <Empty icon={BookOpen} title="No section matched">Try other words.</Empty>)}
    </div>
  );
}

function AsOnDate({ acts }: { acts: any[] }) {
  const s = useMutation({ mutationFn: (f: { act: string; sec: string; on: string }) => api(`/statutes/${encodeURIComponent(f.act)}/${encodeURIComponent(f.sec.trim())}${f.on ? "?on=" + f.on : ""}`) });
  const r = s.data, c = r ? (r.status === "in_force" ? "green" : r.status === "not_found" ? "red" : "amber") : "green";
  return (
    <div className="space-y-5">
      <form className="grid grid-cols-1 gap-2 md:grid-cols-[110px_1fr_170px_auto]" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); s.mutate({ act: String(f.get("act")), sec: String(f.get("sec")), on: String(f.get("on") || "") }); }}>
        <Input name="sec" placeholder="Section" required aria-label="Section" />
        <Select name="act" required aria-label="Act">{acts.map(a => <option key={a.short_name} value={a.short_name}>{a.title.replace(/^The /, "")}</option>)}</Select>
        <Input name="on" type="date" aria-label="As on date" />
        <Button type="submit" loading={s.isPending}>Look up</Button>
      </form>
      <ErrorNote error={s.error} />
      {r && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-3 rounded-xl border border-line p-4">
          <div className="flex items-center gap-2"><Stamp colour={c} /><p className="h-display text-[16px]">{r.heading}</p></div>
          <p className="text-[13.5px] text-mute">{r.message}</p>
          {r.text && <Passage>{r.text}</Passage>}
          {r.amendments?.length > 0 && <div><p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-mute">Amendment ledger · unverified</p>
            {r.amendments.map((a: any, i: number) => <p key={i} className="text-[13px] text-ink-2"><Badge className="mr-2">{a.effective || "—"}</Badge>{a.note}</p>)}</div>}
          {r.source_url && <p className="text-[12px] text-mute">Source: {r.source_url}</p>}
        </motion.div>)}
    </div>
  );
}

function CitationLookup() {
  const s = useMutation({ mutationFn: (c: string) => api("/citations/lookup?c=" + encodeURIComponent(c)) });
  return (
    <div className="space-y-5">
      <form className="flex flex-col gap-2 md:flex-row" onSubmit={e => { e.preventDefault(); s.mutate(String(new FormData(e.currentTarget).get("c"))); }}>
        <Input icon={Quote} name="c" placeholder="[2020] 1 S.C.R. 395 · 2023 INSC 123" className="flex-1" required aria-label="Citation" />
        <Button type="submit" loading={s.isPending}>Look up</Button>
      </form>
      <ErrorNote error={s.error} />
      {s.data && (s.data.found ? s.data.matches.map((m: any, i: number) => (
        <div key={i} className="flex items-start gap-3 rounded-xl border border-ok/25 bg-ok-soft/40 p-4"><Stamp colour="green" />
          <div><p className="h-display text-[16px]">{m.title}</p><p className="text-[12.5px] text-mute">{m.court} · {m.decision_date || m.year} · via {m.origin}</p></div></div>))
        : <div className="flex items-start gap-3 rounded-xl border border-warn/30 bg-warn-soft/50 p-4"><Stamp colour="amber" />
          <p className="text-[14px]">Not found in our library. That does not prove the case doesn't exist.</p></div>)}
    </div>
  );
}

export default function Research() {
  const acts = useQuery({ queryKey: ["acts"], queryFn: () => api<any[]>("/acts"), staleTime: Infinity });
  return (
    <>
      <PageHeader eyebrow="Library" title="Research" subtitle="Search Supreme Court and High Court judgments, find sections of Central Acts, and confirm a citation exists." />
      <Card className="p-5">
        <Tabs defaultValue="j">
          <TabList tabs={[{ value: "j", label: "Judgments", icon: Gavel }, { value: "a", label: "Find a section", icon: BookOpen },
            { value: "d", label: "Section as on a date", icon: Clock3 }, { value: "c", label: "Citation lookup", icon: Scale }]} />
          <TabPanel value="j"><Judgments /></TabPanel>
          <TabPanel value="a"><Acts acts={acts.data || []} /></TabPanel>
          <TabPanel value="d"><AsOnDate acts={acts.data || []} /></TabPanel>
          <TabPanel value="c"><CitationLookup /></TabPanel>
        </Tabs>
      </Card>
    </>
  );
}
