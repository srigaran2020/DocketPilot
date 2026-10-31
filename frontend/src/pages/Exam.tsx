import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { BarChart3, BookOpenCheck, Check, ChevronLeft, ChevronRight, Clock3, GraduationCap, Play, RotateCcw, Timer, X, Zap } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Passage } from "@/components/legal";
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, Input, Label, PageHeader, Select, Skeleton, Tabs, TabList, TabPanel } from "@/components/ui";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Q = { id: number; kind: string; question: string; options: string[]; answer: number; subject: string; act: string; section: string;
  heading: string; where: string; excerpt: string; source_url: string };
type Subject = { name: string; acts: string[]; sections: number; note: string; coverage: "full" | "partial" | "none" };

const PASS = 45; // AIBE pass mark for General/OBC (40% for SC/ST); check the current Bar Council notification
const KIND_LABEL: Record<string, string> = { which_section: "Find the section", which_heading: "What does it deal with", which_act: "Which Act", period: "Time limit" };
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

function useClock(running: boolean) {
  const [t, setT] = useState(0);
  useEffect(() => { if (!running) return; const id = setInterval(() => setT(x => x + 1), 1000); return () => clearInterval(id); }, [running]);
  return [t, setT] as const;
}

function bySubject(qs: Q[], picks: (number | null)[]) {
  const out: Record<string, [number, number]> = {};
  qs.forEach((q, i) => { const r = (out[q.subject] ||= [0, 0]); r[1]++; if (picks[i] === q.answer) r[0]++; });
  return out;
}

function useSave() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (b: any) => api("/exam/attempts", { json: b }), onSuccess: () => qc.invalidateQueries({ queryKey: ["exam-progress"] }) });
}

/** The section the answer comes from: shown after answering, so every answer can be checked in the bare Act. */
function Source({ q }: { q: Q }) {
  return (
    <div className="mt-4 rounded-xl border border-line bg-raised p-4">
      <p className="mb-2 text-[13px] font-medium text-ink">{q.where} <span className="font-normal text-mute">· {q.heading}</span></p>
      <Passage>{q.excerpt}</Passage>
      <p className="mt-2 text-[12px] text-mute">Source: India Code{q.source_url ? <> · <a className="underline underline-offset-2 hover:text-ink" href={q.source_url} target="_blank" rel="noreferrer">open the section</a></> : null} · not reviewed by a lawyer</p>
    </div>
  );
}

function Option({ text, i, state, onClick, disabled }: { text: string; i: number; state: "idle" | "picked" | "right" | "wrong"; onClick: () => void; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled} data-testid="exam-option"
      className={cn("flex w-full items-start gap-3 rounded-xl border px-4 py-3 text-left text-[14.5px] transition",
        state === "idle" && "border-line hover:border-brand/40 hover:bg-raised",
        state === "picked" && "border-brand bg-brand-soft",
        state === "right" && "border-ok/50 bg-ok-soft",
        state === "wrong" && "border-bad/40 bg-bad-soft")}>
      <span className="mt-px grid h-6 w-6 shrink-0 place-items-center rounded-md border border-line-2 bg-surface font-mono text-[12px]">{"ABCD"[i]}</span>
      <span className="flex-1">{text}</span>
      {state === "right" && <Check className="h-4 w-4 text-ok" />}{state === "wrong" && <X className="h-4 w-4 text-bad" />}
    </button>
  );
}

function Result({ qs, picks, seconds, onAgain }: { qs: Q[]; picks: (number | null)[]; seconds: number; onAgain: () => void }) {
  const right = qs.filter((q, i) => picks[i] === q.answer).length;
  const pct = Math.round((100 * right) / qs.length);
  const subj = Object.entries(bySubject(qs, picks)).sort((a, b) => a[1][0] / a[1][1] - b[1][0] / b[1][1]);
  const wrong = qs.map((q, i) => ({ q, p: picks[i] })).filter(x => x.p !== x.q.answer);
  const [open, setOpen] = useState<number | null>(null);
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-5" data-testid="exam-result">
      <Card className="flex flex-wrap items-center gap-6 p-6">
        <div><p className="text-[12px] uppercase tracking-[.14em] text-mute">Score</p><p className="font-display text-[44px] leading-none">{right}<span className="text-[22px] text-mute"> / {qs.length}</span></p></div>
        <div><Badge tone={pct >= PASS ? "ok" : "bad"} dot>{pct}% · {pct >= PASS ? "above" : "below"} the {PASS}% pass mark</Badge>
          <p className="mt-2 text-[12.5px] text-mute">Time {mmss(seconds)} · AIBE pass mark is 45% (40% for SC/ST); check the current notification.</p></div>
        <Button className="ml-auto" variant="secondary" icon={RotateCcw} onClick={onAgain}>New set</Button>
      </Card>
      {subj.length > 1 && <Card><CardHeader icon={BarChart3} title="By subject" subtitle="Weakest first" />
        <div className="space-y-2.5 px-5 pb-5">{subj.map(([s, [c, t]]) => <Bar key={s} label={s} c={c} t={t} />)}</div></Card>}
      {wrong.length > 0 && <Card><CardHeader icon={BookOpenCheck} title={`Review ${wrong.length} wrong or skipped`} subtitle="Read the section each answer comes from" />
        <div className="divide-y divide-line">{wrong.map(({ q, p }, i) => (
          <div key={q.id} className="px-5 py-3">
            <button className="w-full text-left" onClick={() => setOpen(open === i ? null : i)}>
              <p className="text-[14px]">{q.question}</p>
              <p className="mt-1 text-[12.5px]"><span className="text-bad">{p == null ? "Skipped" : `Your answer: ${q.options[p]}`}</span> · <span className="text-ok">Right: {q.options[q.answer]}</span></p>
            </button>
            {open === i && <Source q={q} />}
          </div>))}</div></Card>}
    </motion.div>
  );
}

function Bar({ label, c, t }: { label: string; c: number; t: number }) {
  const pct = t ? Math.round((100 * c) / t) : 0;
  return (
    <div>
      <div className="mb-1 flex justify-between text-[13px]"><span>{label}</span><span className="tabular-nums text-mute">{c}/{t} · {pct}%</span></div>
      <div className="h-2 overflow-hidden rounded-full bg-line"><div className={cn("h-full rounded-full", pct >= PASS ? "bg-ok" : "bg-bad")} style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

/** Practice: answer is shown straight away with its section. Mock: answers stay hidden until the test is submitted. */
function Runner({ qs, mode, minutes, subject, onAgain }: { qs: Q[]; mode: "practice" | "mock"; minutes?: number; subject: string | null; onAgain: () => void }) {
  const [i, setI] = useState(0);
  const [picks, setPicks] = useState<(number | null)[]>(() => qs.map(() => null));
  const [done, setDone] = useState(false);
  const [t] = useClock(!done);
  const save = useSave();
  const left = minutes ? minutes * 60 - t : null;
  const finish = () => {
    if (done) return;
    setDone(true);
    save.mutate({ mode, subject, total: qs.length, correct: qs.filter((q, k) => picks[k] === q.answer).length, seconds: t, by_subject: bySubject(qs, picks) });
  };
  useEffect(() => { if (left !== null && left <= 0) finish(); });
  if (done) return <Result qs={qs} picks={picks} seconds={t} onAgain={onAgain} />;
  const q = qs[i], picked = picks[i], revealed = mode === "practice" && picked !== null;
  const answered = picks.filter(p => p !== null).length;
  return (
    <div className={cn("grid gap-5", mode === "mock" && "lg:grid-cols-[1fr_260px]")}>
      <Card className="p-6" data-testid="exam-question">
        <div className="mb-4 flex flex-wrap items-center gap-2 text-[12.5px] text-mute">
          <span className="font-medium text-ink">Question {i + 1} of {qs.length}</span><Badge>{q.subject}</Badge><Badge tone="brass">{KIND_LABEL[q.kind]}</Badge>
          <span className="ml-auto inline-flex items-center gap-1 tabular-nums"><Clock3 className="h-3.5 w-3.5" />{left !== null ? `${mmss(Math.max(left, 0))} left` : mmss(t)}</span>
        </div>
        <p className="h-display mb-5 text-[19px] leading-snug">{q.question}</p>
        <div className="space-y-2.5">{q.options.map((o, k) => (
          <Option key={k} text={o} i={k} disabled={revealed}
            state={revealed ? (k === q.answer ? "right" : k === picked ? "wrong" : "idle") : k === picked ? "picked" : "idle"}
            onClick={() => setPicks(p => p.map((x, j) => (j === i ? k : x)))} />))}</div>
        {revealed && <><p className={cn("mt-4 text-[14px] font-medium", picked === q.answer ? "text-ok" : "text-bad")}>{picked === q.answer ? "Correct." : `Not quite. The answer is ${q.options[q.answer]}.`}</p><Source q={q} /></>}
        <div className="mt-6 flex items-center gap-2">
          <Button variant="ghost" icon={ChevronLeft} disabled={i === 0} onClick={() => setI(i - 1)}>Back</Button>
          {i < qs.length - 1 ? <Button className="ml-auto" onClick={() => setI(i + 1)} data-testid="exam-next">Next <ChevronRight className="h-4 w-4" /></Button>
            : <Button className="ml-auto" onClick={finish} data-testid="exam-finish">{mode === "mock" ? "Submit test" : "See score"}</Button>}
        </div>
      </Card>
      {mode === "mock" && <Card className="h-fit p-4">
        <p className="mb-3 text-[13px] text-mute">{answered} of {qs.length} answered</p>
        <div className="grid grid-cols-8 gap-1.5 lg:grid-cols-6">{qs.map((_, k) => (
          <button key={k} onClick={() => setI(k)} aria-label={`Question ${k + 1}`}
            className={cn("h-8 rounded-md text-[12px] tabular-nums transition", k === i ? "bg-brand text-white" : picks[k] !== null ? "bg-brand-soft text-brand" : "bg-raised text-mute hover:text-ink")}>{k + 1}</button>))}</div>
        <Button className="mt-4 w-full" variant="secondary" onClick={finish}>Submit test</Button>
      </Card>}
    </div>
  );
}

function Practice({ subjects }: { subjects: Subject[] }) {
  const usable = subjects.filter(s => s.sections > 0);
  const [subject, setSubject] = useState(usable[0]?.name || "");
  const [n, setN] = useState(10);
  const [run, setRun] = useState(0);
  const quiz = useMutation({ mutationFn: () => api<{ questions: Q[] }>("/exam/quiz", { json: { subject, n } }) });
  if (quiz.data && run) return <Runner key={run} qs={quiz.data.questions} mode="practice" subject={subject} onAgain={() => { setRun(0); quiz.reset(); }} />;
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
      <Card className="p-6">
        <CardHeader icon={BookOpenCheck} title="Practise one subject" subtitle="See the answer and its section after every question" className="px-0 pt-0" />
        <div className="space-y-4">
          <div><Label htmlFor="ps">Subject</Label><Select id="ps" value={subject} onChange={e => setSubject(e.target.value)}>{usable.map(s => <option key={s.name}>{s.name}</option>)}</Select></div>
          <div><Label htmlFor="pn">Questions</Label><Select id="pn" value={n} onChange={e => setN(Number(e.target.value))} className="w-32">{[10, 20, 30].map(x => <option key={x}>{x}</option>)}</Select></div>
          <ErrorNote error={quiz.error} />
          <Button icon={Play} loading={quiz.isPending} disabled={!subject} onClick={() => quiz.mutate(undefined, { onSuccess: () => setRun(Date.now()) })} data-testid="exam-start">Start</Button>
        </div>
      </Card>
      <Coverage subjects={subjects} />
    </div>
  );
}

function Coverage({ subjects }: { subjects: Subject[] }) {
  return (
    <Card>
      <CardHeader icon={GraduationCap} title="AIBE subjects" subtitle={`${subjects.filter(s => s.sections).length} of ${subjects.length} have questions from the bare Acts`} />
      <div className="max-h-[420px] divide-y divide-line overflow-auto focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40" tabIndex={0} role="region" aria-label="AIBE subjects and coverage">{subjects.map(s => (
        <div key={s.name} className="flex items-start gap-3 px-5 py-2.5">
          <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", s.coverage === "full" ? "bg-ok" : s.coverage === "partial" ? "bg-warn" : "bg-line-2")} />
          <div className="min-w-0 flex-1"><p className="text-[13.5px]">{s.name}</p>{s.note && <p className="text-[12px] text-mute">{s.note}</p>}</div>
          <span className="text-[12px] tabular-nums text-mute">{s.sections ? `${s.sections} sections` : "none yet"}</span>
        </div>))}</div>
    </Card>
  );
}

function Mock() {
  const [minutes, setMinutes] = useState(210);
  const [run, setRun] = useState(0);
  const quiz = useMutation({ mutationFn: () => api<{ questions: Q[] }>("/exam/quiz", { json: { n: 100 } }) });
  if (quiz.data && run) return <Runner key={run} qs={quiz.data.questions} mode="mock" minutes={minutes} subject={null} onAgain={() => { setRun(0); quiz.reset(); }} />;
  return (
    <Card className="max-w-2xl p-6">
      <CardHeader icon={Timer} title="Full mock test" subtitle="100 questions spread across every covered subject, answers shown after you submit" className="px-0 pt-0" />
      <ul className="mb-5 list-disc space-y-1 pl-5 text-[13.5px] text-ink-2">
        <li>Like the AIBE: 100 multiple-choice questions, one mark each, no negative marking.</li>
        <li>The real exam is open book (bare Acts without notes), so these questions test finding and knowing sections.</li>
        <li>Questions come straight from the bare Acts in the library. No AI writes them.</li>
      </ul>
      <div className="mb-5"><Label htmlFor="mm" hint="Set your own limit">Time (minutes)</Label><Input id="mm" type="number" min={10} max={300} value={minutes} onChange={e => setMinutes(Number(e.target.value) || 210)} className="w-32" /></div>
      <ErrorNote error={quiz.error} />
      <Button icon={Play} loading={quiz.isPending} onClick={() => quiz.mutate(undefined, { onSuccess: () => setRun(Date.now()) })} data-testid="mock-start">Start mock test</Button>
    </Card>
  );
}

/** Open-book skill: given a topic, type the section number before the clock runs out. */
function Drill({ subjects }: { subjects: Subject[] }) {
  const usable = subjects.filter(s => s.sections > 0);
  const [subject, setSubject] = useState(usable[0]?.name || "");
  const quiz = useMutation({ mutationFn: () => api<{ questions: Q[] }>("/exam/quiz", { json: { subject, n: 10, kinds: ["which_section"] } }) });
  const [i, setI] = useState(0);
  const [typed, setTyped] = useState("");
  const [results, setResults] = useState<boolean[]>([]);
  const [shown, setShown] = useState(false);
  const [t, setT] = useClock(!!quiz.data && !shown && results.length < (quiz.data?.questions.length || 0));
  const save = useSave();
  const input = useRef<HTMLInputElement>(null);
  const qs = quiz.data?.questions || [];
  const q = qs[i];
  const LIMIT = 45;
  const answer = q ? q.options[q.answer].replace("Section ", "") : "";
  const check = () => {
    if (!q || shown) return;
    const ok = typed.trim().replace(/^(s\.?|sec(tion)?\.?)\s*/i, "").toLowerCase() === answer.toLowerCase();
    setResults(r => [...r, ok]); setShown(true);
  };
  useEffect(() => { if (q && !shown && t >= LIMIT) check(); });
  const next = () => {
    if (i + 1 >= qs.length) {
      const correct = results.filter(Boolean).length;
      save.mutate({ mode: "drill", subject, total: qs.length, correct, seconds: 0, by_subject: { [subject]: [correct, qs.length] } });
      setI(qs.length);
      return;
    }
    setI(i + 1); setTyped(""); setShown(false); setT(0); setTimeout(() => input.current?.focus(), 0);
  };
  if (!quiz.data) return (
    <Card className="max-w-2xl p-6">
      <CardHeader icon={Zap} title="Speed drill: find the section" subtitle={`You get a topic and ${LIMIT} seconds to type its section number. Trains the open-book skill.`} className="px-0 pt-0" />
      <div className="mb-5"><Label htmlFor="ds">Subject</Label><Select id="ds" value={subject} onChange={e => setSubject(e.target.value)}>{usable.map(s => <option key={s.name}>{s.name}</option>)}</Select></div>
      <ErrorNote error={quiz.error} />
      <Button icon={Zap} loading={quiz.isPending} onClick={() => { setI(0); setResults([]); setShown(false); setTyped(""); setT(0); quiz.mutate(); }}>Start drill</Button>
    </Card>
  );
  if (i >= qs.length) return (
    <Card className="max-w-2xl p-6" data-testid="drill-result">
      <p className="font-display text-[40px]">{results.filter(Boolean).length}<span className="text-[20px] text-mute"> / {qs.length}</span></p>
      <p className="mb-4 text-[13.5px] text-mute">sections found in time</p>
      <Button variant="secondary" icon={RotateCcw} onClick={() => quiz.reset()}>Another drill</Button>
    </Card>
  );
  const topic = q.question.match(/“(.+)”/)?.[1] || q.heading;
  return (
    <Card className="max-w-2xl p-6">
      <div className="mb-4 flex items-center gap-2 text-[12.5px] text-mute"><span className="font-medium text-ink">{i + 1} of {qs.length}</span><Badge>{q.where.split(", ").slice(1).join(", ").replace(/^The /, "")}</Badge>
        <span className={cn("ml-auto tabular-nums", LIMIT - t <= 10 && !shown && "text-bad")}><Clock3 className="mr-1 inline h-3.5 w-3.5" />{shown ? "–" : `${Math.max(LIMIT - t, 0)} s`}</span></div>
      <p className="mb-1 text-[13px] text-mute">Which section deals with</p>
      <p className="h-display mb-5 text-[21px]">“{topic}”</p>
      <form className="flex gap-2" onSubmit={e => { e.preventDefault(); shown ? next() : check(); }}>
        <Input ref={input} autoFocus value={typed} onChange={e => setTyped(e.target.value)} placeholder="e.g. 103" className="w-40 font-mono" aria-label="Section number" disabled={shown} />
        <Button type="submit">{shown ? (i + 1 < qs.length ? "Next" : "Finish") : "Check"}</Button>
      </form>
      {shown && <><p className={cn("mt-4 text-[14px] font-medium", results[results.length - 1] ? "text-ok" : "text-bad")}>{results[results.length - 1] ? "Found it." : `It is Section ${answer}.`}</p><Source q={q} /></>}
    </Card>
  );
}

function Progress() {
  const p = useQuery({ queryKey: ["exam-progress"], queryFn: () => api<any>("/exam/progress") });
  if (p.isLoading) return <Skeleton className="h-60" />;
  if (!p.data?.recent.length) return <Empty icon={BarChart3} title="No attempts yet">Finish a practice set, mock test or drill to see your weak subjects here.</Empty>;
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
      <Card><CardHeader icon={BarChart3} title="Accuracy by subject" subtitle="All attempts, weakest first" />
        <div className="space-y-2.5 px-5 pb-5">{p.data.subjects.map((s: any) => <Bar key={s.subject} label={s.subject} c={s.correct} t={s.total} />)}</div></Card>
      <Card><CardHeader icon={Clock3} title="Recent attempts" />
        <div className="divide-y divide-line">{p.data.recent.map((r: any, i: number) => (
          <div key={i} className="flex items-center gap-3 px-5 py-2.5 text-[13.5px]">
            <Badge tone={r.mode === "mock" ? "brand" : r.mode === "drill" ? "brass" : "idle"}>{r.mode}</Badge>
            <span className="min-w-0 flex-1 truncate">{r.subject || "All subjects"}</span>
            <span className="tabular-nums">{r.correct}/{r.total}</span>
            <span className="w-24 text-right text-[12px] text-mute">{new Date(r.at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</span>
          </div>))}</div></Card>
    </div>
  );
}

export default function Exam() {
  const s = useQuery({ queryKey: ["exam-subjects"], queryFn: () => api<Subject[]>("/exam/subjects") });
  const subjects = useMemo(() => s.data || [], [s.data]);
  return (
    <>
      <PageHeader eyebrow="All India Bar Examination" title="Exam prep"
        subtitle="Practice questions and mock tests for the AIBE, made straight from the bare Acts in the library. Every answer shows the section it comes from." />
      <ErrorNote error={s.error} />
      {s.isLoading ? <Skeleton className="h-72" /> : (
        <Tabs defaultValue="practice">
          <TabList tabs={[{ value: "practice", label: "Practice", icon: BookOpenCheck }, { value: "mock", label: "Mock test", icon: Timer },
            { value: "drill", label: "Speed drill", icon: Zap }, { value: "progress", label: "Progress", icon: BarChart3 }]} className="max-w-full overflow-x-auto" />
          <TabPanel value="practice"><Practice subjects={subjects} /></TabPanel>
          <TabPanel value="mock"><Mock /></TabPanel>
          <TabPanel value="drill"><Drill subjects={subjects} /></TabPanel>
          <TabPanel value="progress"><Progress /></TabPanel>
        </Tabs>)}
      <p className="mt-8 text-[12px] text-mute">Practice questions, not past AIBE papers. Built from India Code text; not reviewed by a lawyer. Constitution, PIL and case-law topics are not covered yet.</p>
    </>
  );
}
