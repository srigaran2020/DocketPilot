import * as DialogP from "@radix-ui/react-dialog";
import { motion, useScroll, useTransform } from "framer-motion";
import {
  ArrowRight, BadgeCheck, Banknote, BookOpenCheck, Building2, CalendarClock, ChevronLeft, ChevronRight, FileSignature, Gavel, HeartHandshake,
  Home, Lock, Mail, MessageSquareText, ScanSearch, ShieldCheck, User, Users, X, type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import heroDraft from "@/assets/hero-draft.jpg";
import productShot from "@/assets/product-answer.jpg";
import { Button, ErrorNote, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------- content (DocketPilot's own words and measured numbers)
const SCENARIOS: { tag: string; icon: LucideIcon; title: string; text: string }[] = [
  { tag: "Family", icon: HeartHandshake, title: "A divorce petition on the ground of cruelty",
    text: "Drop in the petition papers. DocketPilot reads the parties and dates, drafts from the papers and checks every judgment it cites." },
  { tag: "Cheque bounce", icon: Banknote, title: "A notice under Section 138 before time runs out",
    text: "The notice and complaint follow fixed, rule-checked templates, and every statutory deadline goes straight onto your calendar." },
  { tag: "Criminal", icon: Gavel, title: "A bail application due this week",
    text: "Research answers come only from real judgments and sections in force on the date that matters, each one verified before you read it." },
  { tag: "Property", icon: Home, title: "A tenant who will not return the deposit",
    text: "Ask in plain words, get the relevant sections and precedents, then turn the answer into a legal notice in one step." },
  { tag: "Consumer", icon: ScanSearch, title: "A defective product and a refused refund",
    text: "Find the right section of the Act by topic, read it as it stood on any date, and draft the complaint from the facts you give." },
  { tag: "Employment", icon: Users, title: "Unpaid wages for two months",
    text: "Similar past cases come with their outcome and court, so you can see how comparable disputes were decided before you advise." },
];
const STEPS: { icon: LucideIcon; title: string; text: string }[] = [
  { icon: FileSignature, title: "Add the case papers", text: "PDF, Word or text. The case number, parties and every date are read for you." },
  { icon: Lock, title: "Names stay on your machine", text: "Identities are masked before any AI call; real names return only in your approved file." },
  { icon: MessageSquareText, title: "Ask, research or draft", text: "One conversation for questions, drafts, strategy, similar cases and reminders." },
  { icon: ShieldCheck, title: "Verified before you see it", text: "Every citation is checked against the judgment; wrong ones are fixed or removed." },
];
const STATS = [
  { value: "22,767", label: "Judgments with full text", note: "Supreme Court and five High Court benches" },
  { value: "79", label: "Central Acts", note: "8,558 sections, each with its dates in force" },
  { value: "99.6%", label: "Faulty citations caught", note: "on 756 corrupted citations" },
  { value: "87%", label: "Lower cost per answer", note: "than giving the model whole judgments" },
];

// ---------------------------------------------------------------- sign-in panel
function GoogleButton({ onError }: { onError: (e: unknown) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState(false);
  const { signIn } = useAuth();
  const nav = useNavigate();
  useEffect(() => {
    let cancelled = false;
    (async () => {
      let cfg: any = {};
      try { cfg = await api("/auth/config"); } catch { /* no google */ }
      if (!cfg.google_client_id || cancelled) return;
      setEnabled(true);
      const draw = () => {
        const g = (window as any).google;
        g.accounts.id.initialize({ client_id: cfg.google_client_id, callback: async (r: any) => {
          try { await signIn(await api("/auth/google", { json: { credential: r.credential } })); nav("/dashboard"); } catch (e) { onError(e); }
        } });
        if (box.current) g.accounts.id.renderButton(box.current, { theme: "outline", size: "large", width: 360, text: "continue_with", shape: "pill" });
      };
      if ((window as any).google?.accounts) return draw();
      const s = document.createElement("script"); s.src = "https://accounts.google.com/gsi/client"; s.async = true; s.onload = draw; document.head.appendChild(s);
    })();
    return () => { cancelled = true; };
  }, [nav, onError, signIn]);
  if (!enabled) return null;
  return (<>
    <div className="my-5 flex items-center gap-3 text-[12px] text-mute"><span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" /></div>
    <div ref={box} className="flex justify-center" />
  </>);
}

function AuthForm({ mode }: { mode: "signin" | "signup" }) {
  const up = mode === "signup";
  const { signIn } = useAuth();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true); setErr(null);
    try {
      const t = up
        ? await api("/auth/signup", { json: { email: f.get("u"), password: f.get("p"), full_name: f.get("n"), chambers: f.get("c") || null } })
        : await api("/auth/login", { method: "POST", body: new URLSearchParams({ username: String(f.get("u")), password: String(f.get("p")) }) });
      await signIn(t); nav("/dashboard");
    } catch (x) { setErr(x); setBusy(false); }
  };
  return (
    <div>
      <div className="mb-7 grid grid-cols-2 rounded-xl bg-raised p-1 ring-1 ring-line">
        {([["signin", "Sign in", "/login"], ["signup", "Create account", "/signup"]] as const).map(([m, l, to]) => (
          <Link key={m} to={to} replace className={cn("rounded-lg py-2 text-center text-[13.5px] font-medium transition", mode === m ? "bg-surface text-ink shadow-sm" : "text-mute hover:text-ink")}>{l}</Link>
        ))}
      </div>
      <h2 className="h-display text-[30px] text-ink">{up ? "Start free" : "Welcome back"}</h2>
      <p className="mb-6 mt-1 text-[14px] text-mute">{up ? "Your cases stay private to your account." : "Sign in to your chambers' workspace."}</p>
      <form onSubmit={submit} className="space-y-3" data-testid="auth-form">
        {up && <Input icon={User} name="n" placeholder="Your name" autoComplete="name" required aria-label="Your name" />}
        <Input icon={Mail} name="u" type="email" placeholder="Email" autoComplete={up ? "email" : "username"} required aria-label="Email" />
        <Input icon={Lock} name="p" type="password" placeholder={up ? "Password (at least 8 characters)" : "Password"} minLength={up ? 8 : 1}
          autoComplete={up ? "new-password" : "current-password"} required aria-label="Password" />
        {up && <Input icon={Building2} name="c" placeholder="Chambers or firm (optional)" autoComplete="organization" aria-label="Chambers" />}
        <Button type="submit" size="lg" className="w-full" loading={busy}>{up ? "Create account" : "Sign in"}{!busy && <ArrowRight className="h-4 w-4" />}</Button>
        <ErrorNote error={err} />
      </form>
      <GoogleButton onError={setErr} />
      <p className="mt-6 text-center text-[12.5px] text-mute">You stay signed in on this device until you sign out.</p>
    </div>
  );
}

function AuthSheet({ mode }: { mode?: "signin" | "signup" }) {
  const nav = useNavigate();
  return (
    <DialogP.Root open={!!mode} onOpenChange={o => { if (!o) nav("/", { replace: true }); }}>
      <DialogP.Portal>
        <DialogP.Overlay className="fixed inset-0 z-50 bg-[rgb(4_14_12/.55)] backdrop-blur-[3px]" />
        <DialogP.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[460px] flex-col overflow-y-auto bg-surface px-8 py-8 shadow-pop focus:outline-none sm:px-10"
          aria-describedby={undefined}
          onOpenAutoFocus={e => { e.preventDefault(); setTimeout(() => document.querySelector<HTMLInputElement>("[data-testid=auth-form] input")?.focus(), 50); }}>
          <motion.div initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ type: "spring", damping: 28, stiffness: 260 }}>
            <div className="mb-10 flex items-center justify-between">
              <div className="flex items-center gap-2.5"><img src="/logo.png" alt="" className="h-9 w-9 rounded-full" />
                <DialogP.Title className="font-mark text-[19px] font-bold tracking-[.06em] text-brand">DocketPilot</DialogP.Title></div>
              <DialogP.Close className="rounded-lg p-2 text-mute transition hover:bg-line/60 hover:text-ink" aria-label="Close"><X className="h-5 w-5" /></DialogP.Close>
            </div>
            {mode && <AuthForm mode={mode} />}
          </motion.div>
        </DialogP.Content>
      </DialogP.Portal>
    </DialogP.Root>
  );
}

// ---------------------------------------------------------------- page sections
function Nav() {
  const [solid, setSolid] = useState(false);
  useEffect(() => { const f = () => setSolid(window.scrollY > 40); f(); window.addEventListener("scroll", f); return () => window.removeEventListener("scroll", f); }, []);
  const links = [["#how", "How it works"], ["#work", "What it does"], ["#product", "Overview"], ["#numbers", "Results"]];
  return (
    <header className={cn("fixed inset-x-0 top-0 z-40 transition-all duration-300", solid ? "border-b border-line bg-white/90 shadow-sm backdrop-blur-md" : "bg-transparent")}>
      <div className="mx-auto flex h-[72px] max-w-[1240px] items-center gap-6 px-5 sm:px-8">
        <a href="#top" className="flex items-center gap-2.5" onClick={e => { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
          <img src="/logo.png" alt="" className={cn("h-9 w-9 rounded-full ring-2 transition", solid ? "ring-brand/20" : "ring-[#f2c56b]/60")} />
          <span className={cn("font-mark text-[19px] font-bold tracking-[.06em] transition", solid ? "text-brand" : "text-white")}>DocketPilot</span>
        </a>
        <nav className="mx-auto hidden items-center gap-8 md:flex" aria-label="Sections">
          {links.map(([h, l]) => (
            <a key={h} href={h} onClick={e => { e.preventDefault(); document.querySelector(h)?.scrollIntoView({ behavior: "smooth" }); }}
              className={cn("text-[14px] font-medium transition", solid ? "text-ink-2 hover:text-brand" : "text-white/80 hover:text-white")}>{l}</a>))}
        </nav>
        <div className="ml-auto flex items-center gap-2 md:ml-0">
          <Link to="/login" className={cn("rounded-lg px-3.5 py-2 text-[14px] font-medium transition", solid ? "text-ink hover:bg-line/60" : "text-white hover:bg-white/10")} data-testid="nav-signin">Sign in</Link>
          <Link to="/signup" className={cn("hidden rounded-lg px-4 py-2 text-[14px] font-semibold transition sm:inline-flex", solid ? "bg-brand text-white hover:bg-brand-2" : "bg-white text-brand hover:bg-white/90")}>Start free</Link>
        </div>
      </div>
    </header>
  );
}

function Hero() {
  const { scrollY } = useScroll();
  const y = useTransform(scrollY, [0, 700], [0, 120]);
  return (
    <section id="top" className="relative flex min-h-[640px] items-center overflow-hidden bg-[#071f1b] pt-[72px] lg:min-h-[86vh]">
      <motion.div style={{ y }} className="pointer-events-none absolute inset-y-0 right-[-6%] w-[78%] lg:w-[64%]">
        <img src={heroDraft} alt="" className="h-full w-full rotate-[-4deg] scale-110 object-cover object-left-top opacity-[.55] [filter:sepia(.25)_saturate(.8)]" />
      </motion.div>
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,#071f1b_0%,#071f1b_32%,rgba(7,31,27,.86)_52%,rgba(7,31,27,.35)_100%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(70%_60%_at_15%_20%,rgba(31,107,93,.45),transparent_70%)]" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-[#071f1b] to-transparent" />
      <div className="relative mx-auto w-full max-w-[1240px] px-5 py-20 sm:px-8">
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="max-w-[620px]">
          <span className="mb-6 inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/[.07] px-3 py-1.5 text-[13px] text-[#d8e6df] backdrop-blur">
            <BadgeCheck className="h-4 w-4 text-[#f2c56b]" />Every citation checked against the judgment</span>
          <h1 className="font-display text-[44px] font-semibold leading-[1.04] tracking-[-.02em] text-white sm:text-[60px]">
            Legal research and drafting,<br /><em className="font-normal text-[#f2c56b]">verified line by line.</em></h1>
          <p className="mt-6 max-w-[540px] text-[17px] leading-relaxed text-[#c9ddd5]">
            DocketPilot reads your case papers, finds the law in Indian judgments and Central Acts, drafts the document, and checks every citation before you see it. Client names never leave your machine.</p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link to="/signup" className="inline-flex h-12 items-center gap-2 rounded-lg bg-white px-6 text-[15px] font-semibold text-brand shadow-lg transition hover:bg-[#f4f1ea]" data-testid="hero-cta">
              Start free <ArrowRight className="h-4 w-4" /></Link>
            <a href="#how" onClick={e => { e.preventDefault(); document.querySelector("#how")?.scrollIntoView({ behavior: "smooth" }); }}
              className="inline-flex h-12 items-center rounded-lg border border-white/25 px-6 text-[15px] font-medium text-white transition hover:bg-white/10">See how it works</a>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function Eyebrow({ children, dark }: { children: string; dark?: boolean }) {
  return <p className={cn("mb-3 font-mono text-[12px] uppercase tracking-[.2em]", dark ? "text-[#9fbcb2]" : "text-brand-2")}>{children}</p>;
}

function HowItWorks() {
  return (
    <section id="how" className="bg-white py-24">
      <div className="mx-auto max-w-[1240px] px-5 sm:px-8">
        <Eyebrow>How it works</Eyebrow>
        <h2 className="h-display max-w-[640px] text-[38px] leading-tight text-[#0c2f29]">From case papers to a filing you can trust.</h2>
        <div className="mt-12 grid gap-px overflow-hidden rounded-2xl bg-[#e3ebe7] sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <motion.div key={s.title} initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-60px" }} transition={{ delay: i * 0.08 }}
              className="bg-white p-7">
              <div className="mb-6 flex items-center justify-between">
                <div className="grid h-12 w-12 place-items-center rounded-xl bg-[#0c2f29] text-[#f2c56b]"><s.icon className="h-5 w-5" /></div>
                <span className="font-display text-[34px] font-semibold text-[#e3ebe7]">0{i + 1}</span>
              </div>
              <p className="text-[17px] font-semibold text-[#0c2f29]">{s.title}</p>
              <p className="mt-2 text-[14.5px] leading-relaxed text-[#4d5b56]">{s.text}</p>
            </motion.div>))}
        </div>
      </div>
    </section>
  );
}

function Scenarios() {
  const row = useRef<HTMLDivElement>(null);
  const scroll = (d: number) => row.current?.scrollBy({ left: d * (row.current.clientWidth * 0.8), behavior: "smooth" });
  return (
    <section id="work" className="bg-[#f6f8f7] py-24">
      <div className="mx-auto max-w-[1240px] px-5 sm:px-8">
        <Eyebrow>Real matters, real work</Eyebrow>
        <div className="flex flex-wrap items-end gap-6">
          <div className="max-w-[640px] flex-1">
            <h2 className="h-display text-[38px] leading-tight text-[#0c2f29]">What lands on an advocate's desk.</h2>
            <p className="mt-3 text-[16.5px] text-[#4d5b56]">The everyday matters of Indian practice, and what DocketPilot does with each of them.</p>
          </div>
          <div className="ml-auto flex gap-2">
            <button onClick={() => scroll(-1)} className="grid h-11 w-11 place-items-center rounded-full border border-[#cfdcd6] bg-white text-[#0c2f29] transition hover:border-[#0c2f29]" aria-label="Previous"><ChevronLeft className="h-5 w-5" /></button>
            <button onClick={() => scroll(1)} className="grid h-11 w-11 place-items-center rounded-full border border-[#cfdcd6] bg-white text-[#0c2f29] transition hover:border-[#0c2f29]" aria-label="Next"><ChevronRight className="h-5 w-5" /></button>
          </div>
        </div>
        <div ref={row} tabIndex={0} role="region" aria-label="Everyday matters (scroll sideways)" className="mt-10 flex snap-x snap-mandatory gap-6 overflow-x-auto pb-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {SCENARIOS.map((s, i) => (
            <motion.article key={s.title} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.06 }}
              className="group relative flex h-[440px] w-[86%] shrink-0 snap-start flex-col overflow-hidden rounded-2xl bg-[#071f1b] p-7 text-white sm:w-[360px]">
              <div className="pointer-events-none absolute left-1/2 top-[-30%] h-[420px] w-[180px] -translate-x-1/2 rotate-[18deg] bg-gradient-to-b from-[#9fd9c6]/30 to-transparent blur-2xl transition duration-500 group-hover:from-[#f2c56b]/30" />
              <div className="relative mx-auto mt-10 grid h-32 w-32 place-items-center rounded-[34%] border border-white/10 bg-gradient-to-br from-[#1f6b5d] to-[#0c2f29] shadow-[0_20px_60px_-10px_rgba(31,107,93,.7)] transition duration-500 group-hover:scale-105">
                <s.icon className="h-14 w-14 text-[#f2c56b]" strokeWidth={1.4} />
              </div>
              <div className="relative mt-auto">
                <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[.2em] text-[#9fbcb2]">{s.tag}</p>
                <h3 className="text-[18px] font-semibold leading-snug">{s.title}</h3>
                <p className="mt-3 text-[14px] leading-relaxed text-[#b9d2c9]">{s.text}</p>
              </div>
            </motion.article>))}
        </div>
      </div>
    </section>
  );
}

function Product() {
  return (
    <section id="product" className="relative overflow-hidden bg-[#071f1b] py-24">
      <div className="pointer-events-none absolute left-1/2 top-0 h-[480px] w-[900px] -translate-x-1/2 rounded-full bg-[#1f6b5d] opacity-25 blur-3xl" />
      <div className="relative mx-auto max-w-[1240px] px-5 sm:px-8">
        <Eyebrow dark>Overview</Eyebrow>
        <h2 className="h-display max-w-[720px] text-[38px] leading-tight text-white">One workspace for every case.</h2>
        <p className="mt-4 max-w-[700px] text-[16.5px] leading-relaxed text-[#b9d2c9]">
          Ask in plain words, attach papers, draft and approve, all in one conversation. Hover any citation to read the passage it rests on. Nothing is final until you approve it.</p>
        <motion.div initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-80px" }} transition={{ duration: 0.7 }}
          className="mt-12 overflow-hidden rounded-2xl border border-white/10 bg-[#0e2a25] shadow-[0_40px_120px_-30px_rgba(0,0,0,.8)]">
          <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3">
            <span className="h-3 w-3 rounded-full bg-[#ff5f57]" /><span className="h-3 w-3 rounded-full bg-[#febc2e]" /><span className="h-3 w-3 rounded-full bg-[#28c840]" />
            <span className="mx-auto rounded-md bg-white/[.06] px-4 py-1 font-mono text-[12px] text-[#9fbcb2]">127.0.0.1 · DocketPilot</span>
          </div>
          <img src={productShot} alt="DocketPilot answering a legal question with verified citations and the source passage" className="block w-full" loading="lazy" />
        </motion.div>
        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {[[ShieldCheck, "Fake-citation shield", "Wrong citations are corrected or removed before you see them."],
            [CalendarClock, "Never miss a date", "Hearing dates are read from your papers onto your calendar."],
            [BookOpenCheck, "Sources you can open", "Every answer links to the judgment passage or section it relies on."]].map(([Icon, t, d]) => {
            const I = Icon as LucideIcon;
            return (
              <div key={t as string} className="rounded-xl border border-white/10 bg-white/[.03] p-5">
                <I className="mb-3 h-5 w-5 text-[#f2c56b]" /><p className="font-semibold text-white">{t as string}</p><p className="mt-1 text-[14px] text-[#9fbcb2]">{d as string}</p>
              </div>);
          })}
        </div>
      </div>
    </section>
  );
}

function Numbers() {
  return (
    <section id="numbers" className="bg-white py-24">
      <div className="mx-auto max-w-[1240px] px-5 sm:px-8">
        <Eyebrow>Results</Eyebrow>
        <h2 className="h-display max-w-[720px] text-[38px] leading-tight text-[#0c2f29]">Built on Indian law, measured honestly.</h2>
        <p className="mt-3 max-w-[700px] text-[16.5px] text-[#4d5b56]">A library of open Supreme Court and High Court judgments and India Code, with every number below measured on the running system.</p>
        <div className="mt-14 grid sm:grid-cols-2 lg:grid-cols-4">
          {STATS.map((s, i) => (
            <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.08 }}
              className={cn("px-6 py-6", i > 0 && "lg:border-l", i % 2 === 1 && "sm:border-l", "border-[#e3ebe7]")}>
              <p className="text-[15px] text-[#4d5b56]">{s.label}</p>
              <p className="mt-4 font-display text-[54px] font-semibold leading-none tracking-[-.02em] text-[#0c2f29]">{s.value}</p>
              <p className="mt-3 text-[13px] text-[#6b7873]">{s.note}</p>
            </motion.div>))}
        </div>
      </div>
    </section>
  );
}

function Closing() {
  return (
    <section className="bg-white pb-24">
      <div className="mx-auto max-w-[1240px] px-5 sm:px-8">
        <div className="relative overflow-hidden rounded-3xl bg-[#0c2f29] px-8 py-14 text-center sm:px-16">
          <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-[#1f6b5d] opacity-50 blur-3xl" />
          <h2 className="h-display relative text-[34px] text-white sm:text-[40px]">Bring your next case.</h2>
          <p className="relative mx-auto mt-3 max-w-[520px] text-[16px] text-[#b9d2c9]">Create a free account and add your first papers. The case file, parties and hearing dates are set up for you.</p>
          <div className="relative mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/signup" className="inline-flex h-12 items-center gap-2 rounded-lg bg-white px-6 text-[15px] font-semibold text-brand transition hover:bg-[#f4f1ea]">Start free <ArrowRight className="h-4 w-4" /></Link>
            <Link to="/login" className="inline-flex h-12 items-center rounded-lg border border-white/25 px-6 text-[15px] font-medium text-white transition hover:bg-white/10">Sign in</Link>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="bg-[#071f1b] text-[#9fbcb2]">
      <div className="mx-auto flex max-w-[1240px] flex-wrap items-center gap-6 px-5 py-10 sm:px-8">
        <div className="flex items-center gap-3"><img src="/logo.png" alt="" className="h-10 w-10 rounded-full ring-2 ring-[#f2c56b]/40" />
          <div><p className="font-mark text-[17px] font-bold tracking-[.06em] text-white">DocketPilot</p>
            <p className="text-[12.5px]">An agentic AI system for Indian legal research, drafting, verification and case management.</p></div></div>
        <div className="ml-auto flex flex-wrap items-center gap-5 text-[13.5px]">
          <span className="flex items-center gap-1.5"><Lock className="h-4 w-4" />Runs on your machine</span>
          <span className="flex items-center gap-1.5"><ShieldCheck className="h-4 w-4" />Citations verified</span>
        </div>
      </div>
      <div className="border-t border-white/10">
        <div className="mx-auto flex max-w-[1240px] flex-wrap justify-between gap-3 px-5 py-5 text-[12.5px] sm:px-8">
          <span>Research prototype</span><span>© {new Date().getFullYear()} DocketPilot</span>
        </div>
      </div>
    </footer>
  );
}

export default function Login({ mode }: { mode?: "signin" | "signup" }) {
  // The home page is designed in light court green and white; restore the user's theme when they leave it.
  useEffect(() => {
    const el = document.documentElement, wasDark = el.classList.contains("dark");
    el.classList.remove("dark");
    return () => { if (wasDark) el.classList.add("dark"); };
  }, []);
  return (
    <div className="min-h-screen bg-white">
      <Nav />
      <main>
        <Hero />
        <HowItWorks />
        <Scenarios />
        <Product />
        <Numbers />
        <Closing />
      </main>
      <Footer />
      <AuthSheet mode={mode} />
    </div>
  );
}
