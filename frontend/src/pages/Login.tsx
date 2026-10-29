import { motion } from "framer-motion";
import { ArrowRight, BadgeCheck, CalendarClock, FileSignature, Lock, Mail, Scale, ShieldCheck, User, Building2, MessageSquareText } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button, ErrorNote, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const FEATURES = [
  { icon: ShieldCheck, title: "Fake-citation shield", text: "Wrong citations are corrected or removed before you see them." },
  { icon: FileSignature, title: "Drafts in minutes", text: "Notices, petitions, replies and applications, ready in Word." },
  { icon: Lock, title: "Private by design", text: "Client names are masked before any AI sees them." },
  { icon: CalendarClock, title: "Never miss a date", text: "Hearing dates read from your papers onto your calendar." },
  { icon: MessageSquareText, title: "One conversation", text: "Questions, drafts, dates and citation checks in one chat." },
  { icon: Scale, title: "Precedent finder", text: "Supreme Court and High Court judgments in seconds." },
];

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

export default function Login({ mode }: { mode: "signin" | "signup" }) {
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
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="grain relative hidden overflow-hidden bg-[#0c2f29] px-14 py-12 text-white lg:flex lg:flex-col">
        <div className="pointer-events-none absolute -left-40 -top-40 h-[520px] w-[520px] rounded-full bg-[#1f6b5d] opacity-40 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-48 right-[-120px] h-[520px] w-[520px] rounded-full bg-[#c2410c] opacity-[.18] blur-3xl" />
        <div className="pointer-events-none absolute bottom-[-140px] right-[-40px] select-none font-display text-[520px] leading-none text-white/[.04]">§</div>
        <div className="relative flex items-center gap-3">
          <img src="/logo.png" alt="" className="h-14 w-14 rounded-full ring-2 ring-[#f2c56b]/60" />
          <span className="font-mark text-[28px] font-bold tracking-[.08em]">DocketPilot</span>
        </div>
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="relative mt-auto max-w-[620px]">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[.06] px-3 py-1 text-[12px] text-[#d8e6df]">
            <BadgeCheck className="h-3.5 w-3.5 text-[#f2c56b]" />Every citation checked before you see it
          </div>
          <h1 className="font-display text-[44px] font-semibold leading-[1.06] tracking-[-.02em]">
            Indian legal research and drafting, <em className="font-normal text-[#f2c56b]">verified line by line.</em>
          </h1>
          <p className="mt-4 max-w-[520px] text-[15.5px] leading-relaxed text-[#c9ddd5]">An agentic AI system for research, drafting, anti-hallucination verification and case management.</p>
          <div className="mt-9 grid grid-cols-2 gap-3">
            {FEATURES.map((f, i) => (
              <motion.div key={f.title} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + i * 0.05 }}
                className="rounded-xl border border-white/10 bg-white/[.04] p-4 backdrop-blur-sm transition hover:border-[#f2c56b]/40 hover:bg-white/[.07]">
                <f.icon className="mb-2.5 h-5 w-5 text-[#f2a15b]" />
                <p className="font-display text-[15.5px] font-semibold">{f.title}</p>
                <p className="mt-0.5 text-[13px] leading-snug text-[#b9d2c9]">{f.text}</p>
              </motion.div>
            ))}
          </div>
        </motion.div>
        <p className="relative mt-10 text-[12px] uppercase tracking-[.16em] text-[#86a99d]">Research prototype</p>
      </section>

      <section className="flex items-center justify-center bg-surface px-6 py-12">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-[380px]">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <img src="/logo.png" alt="" className="h-11 w-11 rounded-full" /><span className="font-mark text-[22px] font-bold tracking-[.06em] text-brand">DocketPilot</span>
          </div>
          <div className="mb-7 grid grid-cols-2 rounded-xl bg-raised p-1 ring-1 ring-line">
            {([["signin", "Sign in", "/login"], ["signup", "Create account", "/signup"]] as const).map(([m, l, to]) => (
              <Link key={m} to={to} className={cn("rounded-lg py-2 text-center text-[13.5px] font-medium transition", mode === m ? "bg-surface text-ink shadow-sm" : "text-mute hover:text-ink")}>{l}</Link>
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
        </motion.div>
      </section>
    </div>
  );
}
