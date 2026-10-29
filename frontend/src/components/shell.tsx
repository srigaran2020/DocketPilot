import * as Dropdown from "@radix-ui/react-dropdown-menu";
import * as TooltipP from "@radix-ui/react-tooltip";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { AnimatePresence, motion } from "framer-motion";
import {
  BookOpen, Briefcase, CalendarDays, ChevronsLeft, ChevronsRight, FileCheck2, HelpCircle, LayoutDashboard, LogOut, Menu, MessageSquareText,
  Moon, Search, Settings, Sun, X, type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { cn, initials, store } from "@/lib/utils";
import { Kbd, Tip } from "./ui";

export const NAV: { to: string; label: string; icon: LucideIcon; hint: string }[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, hint: "Today's docket" },
  { to: "/ask", label: "Ask DocketPilot", icon: MessageSquareText, hint: "Chat for questions, drafts and dates" },
  { to: "/cases", label: "Cases", icon: Briefcase, hint: "Case files, papers and drafts" },
  { to: "/calendar", label: "Calendar", icon: CalendarDays, hint: "Hearings and deadlines" },
  { to: "/research", label: "Research", icon: BookOpen, hint: "Judgments, Acts and citations" },
  { to: "/verify", label: "Check a document", icon: FileCheck2, hint: "Verify every citation in a text" },
];

function Brand({ collapsed }: { collapsed?: boolean }) {
  return (
    <div className={cn("flex items-center gap-3 px-4 pb-5 pt-5", collapsed && "justify-center px-0")}>
      <img src="/logo.png" alt="" className="h-9 w-9 shrink-0 rounded-full ring-2 ring-[#f2c56b]/50" />
      {!collapsed && (
        <div className="min-w-0">
          <div className="font-mark text-[18px] font-bold tracking-[.06em] text-white">DocketPilot</div>
          <div className="text-[10.5px] uppercase tracking-[.16em] text-[#9fbcb2]">Research & drafting</div>
        </div>
      )}
    </div>
  );
}

function NavItems({ collapsed, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  return (
    <nav className="flex-1 space-y-1 px-3" aria-label="Main">
      {NAV.map(n => {
        const link = (
          <NavLink key={n.to} to={n.to} onClick={onNavigate}
            className={({ isActive }) => cn(
              "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-[14px] font-medium transition",
              isActive ? "bg-white/[.09] text-white shadow-[inset_0_0_0_1px_rgb(255_255_255/.07)]" : "text-[#b9d2c9] hover:bg-white/[.05] hover:text-white",
              collapsed && "justify-center px-0")}>
            {({ isActive }) => (<>
              {isActive && <motion.span layoutId="navbar" className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r bg-[#f2a15b]" />}
              <n.icon className={cn("h-[18px] w-[18px] shrink-0", isActive ? "text-[#f2c56b]" : "text-[#86a99d] group-hover:text-[#d8e6df]")} />
              {!collapsed && <span className="truncate">{n.label}</span>}
            </>)}
          </NavLink>
        );
        return collapsed ? <Tip key={n.to} label={n.label} side="right">{link}</Tip> : link;
      })}
    </nav>
  );
}

function Sidebar({ collapsed, setCollapsed }: { collapsed: boolean; setCollapsed: (v: boolean) => void }) {
  return (
    <aside className={cn("sticky top-0 hidden h-screen shrink-0 flex-col border-r border-black/20 bg-[#0c2f29] transition-[width] duration-200 lg:flex",
      collapsed ? "w-[72px]" : "w-[252px]")}>
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(120%_60%_at_0%_0%,rgb(242_197_107/.10),transparent_60%)]" />
      <Brand collapsed={collapsed} />
      <NavItems collapsed={collapsed} />
      <div className="space-y-1 px-3 pb-4">
        <NavLink to="/guide" className={({ isActive }) => cn("flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] text-[#b9d2c9] hover:bg-white/[.05] hover:text-white",
          isActive && "bg-white/[.09] text-white", collapsed && "justify-center px-0")}>
          <HelpCircle className="h-[18px] w-[18px] text-[#86a99d]" />{!collapsed && "How to use"}
        </NavLink>
        <button onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? "Expand menu" : "Collapse menu"}
          className={cn("flex w-full items-center gap-3 rounded-lg px-3 py-2 text-[13px] text-[#86a99d] hover:bg-white/[.05] hover:text-white", collapsed && "justify-center px-0")}>
          {collapsed ? <ChevronsRight className="h-[18px] w-[18px]" /> : <><ChevronsLeft className="h-[18px] w-[18px]" />Collapse</>}
        </button>
        {!collapsed && <p className="px-3 pt-2 text-[11px] uppercase tracking-[.14em] text-[#86a99d]">Research prototype</p>}
      </div>
    </aside>
  );
}

function UserMenu() {
  const { me, signOut } = useAuth();
  const nav = useNavigate();
  return (
    <Dropdown.Root>
      <Dropdown.Trigger className="flex items-center gap-2.5 rounded-full p-0.5 pr-3 transition hover:bg-line/60" aria-label="Account menu" data-testid="user-menu">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-brand-2 to-brand text-[12px] font-semibold text-[rgb(var(--on-brand))]">{initials(me?.full_name)}</span>
        <span className="hidden text-left leading-tight sm:block"><span className="block text-[13px] font-medium text-ink">{me?.full_name}</span>
          <span className="block text-[11.5px] capitalize text-mute">{me?.role}</span></span>
      </Dropdown.Trigger>
      <Dropdown.Portal>
        <Dropdown.Content align="end" sideOffset={8} className="z-50 w-60 rounded-xl border border-line bg-surface p-1.5 shadow-pop">
          <div className="px-3 py-2"><p className="text-[13.5px] font-medium">{me?.full_name}</p><p className="truncate text-[12px] text-mute">{me?.email}</p></div>
          <Dropdown.Separator className="my-1 h-px bg-line" />
          <Dropdown.Item onSelect={() => nav("/account")} className="flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] outline-none data-[highlighted]:bg-line/60">
            <Settings className="h-4 w-4 text-mute" />Account and password</Dropdown.Item>
          <Dropdown.Item onSelect={() => nav("/guide")} className="flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] outline-none data-[highlighted]:bg-line/60">
            <HelpCircle className="h-4 w-4 text-mute" />How to use</Dropdown.Item>
          <Dropdown.Separator className="my-1 h-px bg-line" />
          <Dropdown.Item onSelect={() => { signOut(); nav("/login"); }} className="flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] text-bad outline-none data-[highlighted]:bg-bad-soft">
            <LogOut className="h-4 w-4" />Sign out</Dropdown.Item>
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}

function CommandPalette({ open, setOpen }: { open: boolean; setOpen: (v: boolean) => void }) {
  const nav = useNavigate();
  const cases = useQuery({ queryKey: ["cases"], queryFn: () => api<any[]>("/cases"), enabled: open });
  const go = (to: string, prefill?: string) => { if (prefill) store.sset("dp_prefill", prefill); setOpen(false); nav(to); };
  const item = "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-[14px] text-ink-2 aria-selected:bg-brand-soft aria-selected:text-ink";
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[70] flex items-start justify-center bg-[rgb(6_14_12/.45)] px-4 pt-[14vh] backdrop-blur-[2px]"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setOpen(false)}>
          <motion.div initial={{ y: -8, scale: 0.98 }} animate={{ y: 0, scale: 1 }} exit={{ y: -8, scale: 0.98 }} onClick={e => e.stopPropagation()}
            className="w-full max-w-xl overflow-hidden rounded-2xl border border-line bg-surface shadow-pop">
            <Command label="Command menu" loop>
              <div className="flex items-center gap-3 border-b border-line px-4">
                <Search className="h-4 w-4 text-mute" />
                <Command.Input autoFocus placeholder="Search pages and cases, or type a question…" className="h-14 flex-1 bg-transparent text-[15px] outline-none placeholder:text-mute" />
                <Kbd>Esc</Kbd>
              </div>
              <Command.List className="max-h-[52vh] overflow-auto p-2">
                <Command.Empty className="px-3 py-6 text-center text-[13.5px] text-mute">No match. Press Enter on “Ask DocketPilot” to ask it.</Command.Empty>
                <Command.Group heading="Go to" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-mute">
                  {NAV.map(n => <Command.Item key={n.to} value={n.label + " " + n.hint} onSelect={() => go(n.to)} className={item}>
                    <n.icon className="h-4 w-4 text-brand-2" /><span className="flex-1">{n.label}</span><span className="text-[12px] text-mute">{n.hint}</span></Command.Item>)}
                </Command.Group>
                <Command.Group heading="Actions" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-mute">
                  <Command.Item value="draft a document petition notice" onSelect={() => go("/ask", "Draft a ")} className={item}><MessageSquareText className="h-4 w-4 text-seal" />Draft a document</Command.Item>
                  <Command.Item value="next hearing date" onSelect={() => go("/ask", "When is my next hearing?")} className={item}><CalendarDays className="h-4 w-4 text-seal" />When is my next hearing?</Command.Item>
                  <Command.Item value="verify citations check" onSelect={() => go("/verify")} className={item}><FileCheck2 className="h-4 w-4 text-seal" />Check citations in a document</Command.Item>
                  <Command.Item value="find section act statute" onSelect={() => go("/research")} className={item}><BookOpen className="h-4 w-4 text-seal" />Find a section of an Act</Command.Item>
                </Command.Group>
                {(cases.data || []).length > 0 && (
                  <Command.Group heading="Cases" className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-mute">
                    {(cases.data || []).slice(0, 12).map(c => (
                      <Command.Item key={c.id} value={`${c.case_number || c.title} ${c.petitioner || ""} ${c.respondent || ""}`} onSelect={() => go(`/cases/${c.id}`)} className={item}>
                        <Briefcase className="h-4 w-4 text-mute" /><span className="flex-1 truncate">{c.case_number || c.title}</span>
                        <span className="truncate text-[12px] text-mute">{c.petitioner}</span></Command.Item>))}
                  </Command.Group>
                )}
              </Command.List>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

const CRUMBS: Record<string, string> = { dashboard: "Dashboard", ask: "Ask DocketPilot", cases: "Cases", calendar: "Calendar", research: "Research",
  verify: "Check a document", guide: "How to use", account: "Account", drafts: "Draft" };

export function AppShell({ children, wide }: { children: ReactNode; wide?: boolean }) {
  const [collapsed, setCollapsed] = useState(() => store.get("dp_nav") === "1");
  const [mobile, setMobile] = useState(false);
  const [palette, setPalette] = useState(false);
  const { theme, toggle } = useTheme();
  const loc = useLocation();
  useEffect(() => {
    store.set("dp_nav", collapsed ? "1" : "0");
    document.documentElement.style.setProperty("--sidebar", collapsed ? "72px" : "252px");
  }, [collapsed]);
  useEffect(() => setMobile(false), [loc.pathname]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette(p => !p); } if (e.key === "Escape") setPalette(false); };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, []);
  const section = loc.pathname.split("/")[1] || "dashboard";
  return (
    <TooltipP.Provider>
      <div className="flex min-h-screen">
        <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} />
        <AnimatePresence>
          {mobile && (
            <motion.div className="fixed inset-0 z-50 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <div className="absolute inset-0 bg-black/40" onClick={() => setMobile(false)} />
              <motion.aside initial={{ x: -280 }} animate={{ x: 0 }} exit={{ x: -280 }} transition={{ type: "spring", damping: 30, stiffness: 300 }}
                className="absolute inset-y-0 left-0 flex w-[268px] flex-col bg-[#0c2f29]">
                <button onClick={() => setMobile(false)} className="absolute right-3 top-5 rounded-lg p-1.5 text-[#b9d2c9]" aria-label="Close menu"><X className="h-5 w-5" /></button>
                <Brand /><NavItems onNavigate={() => setMobile(false)} />
              </motion.aside>
            </motion.div>
          )}
        </AnimatePresence>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line/80 bg-bg/80 px-4 backdrop-blur-md sm:px-6 lg:px-8">
            <button className="rounded-lg p-2 text-ink-2 hover:bg-line/60 lg:hidden" onClick={() => setMobile(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>
            <div className="hidden items-center gap-2 text-[13.5px] text-mute md:flex">
              <span>DocketPilot</span><span className="text-line-2">/</span><span className="font-medium text-ink">{CRUMBS[section] || "Dashboard"}</span>
            </div>
            <button onClick={() => setPalette(true)} data-testid="open-palette"
              className="ml-auto flex h-9 w-full max-w-[340px] items-center gap-2.5 rounded-lg border border-line-2 bg-surface px-3 text-[13.5px] text-mute shadow-sm transition hover:border-ink-2/30">
              <Search className="h-4 w-4" /><span className="flex-1 text-left">Search or jump to…</span><Kbd>Ctrl K</Kbd>
            </button>
            <Tip label={theme === "dark" ? "Light mode" : "Dark mode"}>
              <button onClick={toggle} className="grid h-9 w-9 place-items-center rounded-lg text-ink-2 transition hover:bg-line/60" aria-label="Toggle theme" data-testid="theme">
                {theme === "dark" ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
              </button>
            </Tip>
            <UserMenu />
          </header>
          <main className={cn("mx-auto w-full flex-1 px-4 pb-16 pt-8 sm:px-6 lg:px-10", wide ? "max-w-[1440px]" : "max-w-[1240px]")}>{children}</main>
        </div>
        <CommandPalette open={palette} setOpen={setPalette} />
      </div>
    </TooltipP.Provider>
  );
}
