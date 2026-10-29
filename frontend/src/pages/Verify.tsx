import { useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { FileCheck2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Passage, ReleaseBanner, Stamp, statuteNote } from "@/components/legal";
import { Badge, Button, Card, CardHeader, Dots, Empty, ErrorNote, Input, Label, PageHeader, Switch, Textarea } from "@/components/ui";
import { api } from "@/lib/api";

export default function Verify() {
  const [text, setText] = useState("");
  const [date, setDate] = useState("");
  const [llm, setLlm] = useState(true);
  const v = useMutation({ mutationFn: () => api("/verify", { json: { text, relevant_date: date || null, use_llm: llm } }) });
  const r = v.data;
  return (
    <>
      <PageHeader eyebrow="Second pair of eyes" title="Check a document" subtitle="Paste any draft. Every citation, quotation and section reference is checked against the library." />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader icon={FileCheck2} title="Paste the text" />
          <div className="space-y-4 px-5 pb-5">
            <Textarea value={text} onChange={e => setText(e.target.value)} placeholder="Paste the draft here…" className="min-h-[340px] font-display text-[14.5px]" data-testid="verify-text" />
            <div className="flex flex-wrap items-end gap-4">
              <div><Label htmlFor="rd">Relevant date</Label><Input id="rd" type="date" value={date} onChange={e => setDate(e.target.value)} className="w-44" /></div>
              <Switch id="llm" checked={llm} onChange={setLlm} label="Use the AI judge for propositions" />
              <Button className="ml-auto" icon={ShieldCheck} disabled={!text.trim()} loading={v.isPending} onClick={() => v.mutate()} data-testid="verify-go">Check this draft</Button>
            </div>
            <span className="text-[12px] text-mute">{text.trim() ? `${text.trim().split(/\s+/).length} words` : ""}</span>
          </div>
        </Card>
        <div>
          <ErrorNote error={v.error} />
          {v.isPending && <Card className="flex items-center gap-3 p-6"><Dots /><span className="text-[14px] text-ink-2">Checking citations, quotes and sections…</span></Card>}
          {!r && !v.isPending && <Empty icon={ShieldCheck} title="Results appear here">Green is verified, amber needs a look, red is wrong.</Empty>}
          {r && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <ReleaseBanner release={r.release} />
              <Card className="divide-y divide-line">
                {r.citations.map((c: any, i: number) => (
                  <div key={i} className="flex items-start gap-3 p-4"><Stamp colour={c.colour} />
                    <div className="min-w-0 flex-1 space-y-1.5"><p className="font-mono text-[13px]">{c.raw}</p><p className="text-[13.5px] text-ink-2">{c.reason}</p>
                      {(c.quotes || []).map((q: any, j: number) => <p key={j} className="text-[12.5px] text-mute"><Badge>quote</Badge> {q.status.replace(/_/g, " ")} {q.reason}</p>)}
                      {c.proposition && <><p className="text-[12.5px] text-mute"><Badge>supports?</Badge> {c.proposition.label.replace(/_/g, " ")} {c.proposition.reason}</p>
                        {c.proposition.passage && <Passage>{c.proposition.passage}</Passage>}</>}</div></div>))}
                {r.statutes.map((s: any, i: number) => (
                  <div key={"s" + i} className="flex items-start gap-3 p-4"><Stamp colour={s.colour} /><div><p className="font-mono text-[13px]">{s.raw}</p><p className="text-[12.5px] text-mute">{statuteNote(s)}</p></div></div>))}
                {!r.citations.length && !r.statutes.length && <p className="p-4 text-[13.5px] text-mute">No citations or section references found.</p>}
              </Card>
              {r.notice && <p className="mt-3 text-[12.5px] text-mute">{r.notice}</p>}
            </motion.div>)}
        </div>
      </div>
    </>
  );
}
