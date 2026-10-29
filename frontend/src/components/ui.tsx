import * as DialogP from "@radix-ui/react-dialog";
import * as SwitchP from "@radix-ui/react-switch";
import * as TabsP from "@radix-ui/react-tabs";
import * as TooltipP from "@radix-ui/react-tooltip";
import { motion } from "framer-motion";
import { Loader2, X, type LucideIcon } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------- Button
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "seal" | "danger" | "subtle";
  size?: "sm" | "md" | "lg" | "icon";
  loading?: boolean;
  icon?: LucideIcon;
};
export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button(
  { variant = "primary", size = "md", loading, icon: Icon, className, children, disabled, ...p }, ref) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 font-medium whitespace-nowrap rounded-lg transition-all duration-150 select-none",
        "disabled:opacity-50 disabled:pointer-events-none active:scale-[.98]",
        size === "sm" && "h-8 px-3 text-[13px]",
        size === "md" && "h-10 px-4 text-[14px]",
        size === "lg" && "h-12 px-6 text-[15px]",
        size === "icon" && "h-9 w-9",
        variant === "primary" && "bg-brand text-[rgb(var(--on-brand))] shadow-[0_1px_0_rgb(0_0_0/.15),inset_0_1px_0_rgb(255_255_255/.12)] hover:bg-brand-2",
        variant === "seal" && "bg-seal text-white shadow-[0_1px_0_rgb(0_0_0/.15),inset_0_1px_0_rgb(255_255_255/.15)] hover:brightness-110",
        variant === "secondary" && "bg-surface text-ink border border-line-2 hover:border-ink-2/40 hover:bg-raised shadow-sm",
        variant === "ghost" && "text-ink-2 hover:bg-line/60 hover:text-ink",
        variant === "subtle" && "bg-brand-soft text-brand hover:bg-brand-soft/70",
        variant === "danger" && "text-bad hover:bg-bad-soft",
        className,
      )}
      {...p}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon ? <Icon className={cn(size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4")} /> : null}
      {children}
    </button>
  );
});

// ---------------------------------------------------------------- Card
export function Card({ className, children, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("card", className)} {...p}>{children}</div>;
}
export function CardHeader({ title, subtitle, icon: Icon, action, className }:
  { title: ReactNode; subtitle?: ReactNode; icon?: LucideIcon; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start gap-3 px-5 pt-5 pb-3", className)}>
      {Icon && <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand"><Icon className="h-[18px] w-[18px]" /></div>}
      <div className="min-w-0 flex-1">
        <h2 className="h-display text-[17px] leading-tight text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-[13px] text-mute">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

// ---------------------------------------------------------------- Inputs
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { icon?: LucideIcon }>(
  function Input({ className, icon: Icon, ...p }, ref) {
    if (!Icon) return <input ref={ref} className={cn("field", className)} {...p} />;
    return (
      <div className={cn("relative", className)}>
        <Icon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-mute" />
        <input ref={ref} className="field pl-9" {...p} />
      </div>
    );
  });
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...p }, ref) { return <textarea ref={ref} className={cn("field min-h-[120px] resize-y leading-relaxed", className)} {...p} />; });
export function Select({ className, children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn("field appearance-none bg-[length:14px] bg-[right_12px_center] bg-no-repeat pr-9", className)}
      style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23708079' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")" }}
      {...p}>{children}</select>
  );
}
export function Label({ children, hint, htmlFor }: { children: ReactNode; hint?: ReactNode; htmlFor?: string }) {
  return <label htmlFor={htmlFor} className="mb-1.5 block text-[13px] font-medium text-ink-2">{children}{hint && <span className="ml-1 font-normal text-mute">{hint}</span>}</label>;
}

export function Switch({ checked, onChange, label, id }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; id: string }) {
  return (
    <label htmlFor={id} className="inline-flex cursor-pointer items-center gap-2.5 text-[13.5px] text-ink-2">
      <SwitchP.Root id={id} checked={checked} onCheckedChange={onChange} aria-label={typeof label === "string" ? label : undefined}
        className="relative h-[22px] w-[38px] rounded-full bg-line-2 transition-colors data-[state=checked]:bg-brand-2">
        <SwitchP.Thumb className="block h-[18px] w-[18px] translate-x-[2px] rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[18px]" />
      </SwitchP.Root>
      {label}
    </label>
  );
}

// ---------------------------------------------------------------- Badges and status
const TONES = {
  ok: "bg-ok-soft text-ok ring-ok/20", warn: "bg-warn-soft text-warn ring-warn/25", bad: "bg-bad-soft text-bad ring-bad/20",
  brand: "bg-brand-soft text-brand ring-brand/15", seal: "bg-seal-soft text-seal ring-seal/20", brass: "bg-brass-soft text-brass-ink ring-brass/25",
  idle: "bg-line/60 text-ink-2 ring-line-2",
};
export type Tone = keyof typeof TONES;
export function Badge({ tone = "idle", children, className, dot }: { tone?: Tone; children: ReactNode; className?: string; dot?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[12px] font-medium ring-1 ring-inset whitespace-nowrap", TONES[tone], className)}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}{children}
    </span>
  );
}

// ---------------------------------------------------------------- Tabs
export const Tabs = TabsP.Root;
export function TabList({ tabs, className }: { tabs: { value: string; label: ReactNode; icon?: LucideIcon; count?: number }[]; className?: string }) {
  return (
    <TabsP.List className={cn("inline-flex gap-1 rounded-xl border border-line bg-raised p-1", className)}>
      {tabs.map(t => (
        <TabsP.Trigger key={t.value} value={t.value}
          className="inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-[13.5px] font-medium text-mute transition hover:text-ink data-[state=active]:bg-surface data-[state=active]:text-ink data-[state=active]:shadow-sm">
          {t.icon && <t.icon className="h-4 w-4" />}{t.label}
          {t.count !== undefined && <span className="rounded-full bg-line px-1.5 text-[11px] text-ink-2">{t.count}</span>}
        </TabsP.Trigger>
      ))}
    </TabsP.List>
  );
}
export const TabPanel = ({ value, children, className }: { value: string; children: ReactNode; className?: string }) =>
  <TabsP.Content value={value} className={cn("mt-5 focus:outline-none", className)}>{children}</TabsP.Content>;

// ---------------------------------------------------------------- Dialog / sheet
export function Dialog({ open, onOpenChange, title, description, children, wide }:
  { open: boolean; onOpenChange: (v: boolean) => void; title: ReactNode; description?: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <DialogP.Root open={open} onOpenChange={onOpenChange}>
      <DialogP.Portal>
        <DialogP.Overlay className="fixed inset-0 z-50 bg-[rgb(6_14_12/.45)] backdrop-blur-[2px] data-[state=open]:animate-in" />
        <DialogP.Content className={cn("fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-2xl border border-line bg-surface p-6 shadow-pop focus:outline-none",
          wide ? "max-w-3xl" : "max-w-lg")}>
          <div className="mb-4 flex items-start gap-4">
            <div className="flex-1">
              <DialogP.Title className="h-display text-xl text-ink">{title}</DialogP.Title>
              {description && <DialogP.Description className="mt-1 text-[13.5px] text-mute">{description}</DialogP.Description>}
            </div>
            <DialogP.Close className="rounded-lg p-1.5 text-mute hover:bg-line/60 hover:text-ink" aria-label="Close"><X className="h-4 w-4" /></DialogP.Close>
          </div>
          {children}
        </DialogP.Content>
      </DialogP.Portal>
    </DialogP.Root>
  );
}

// ---------------------------------------------------------------- Tooltip
export function Tip({ label, children, side = "top" }: { label: ReactNode; children: ReactNode; side?: "top" | "right" | "bottom" | "left" }) {
  return (
    <TooltipP.Root delayDuration={250}>
      <TooltipP.Trigger asChild>{children}</TooltipP.Trigger>
      <TooltipP.Portal>
        <TooltipP.Content side={side} sideOffset={6} className="z-[60] rounded-md bg-ink px-2.5 py-1.5 text-[12px] font-medium text-bg shadow-pop">
          {label}
        </TooltipP.Content>
      </TooltipP.Portal>
    </TooltipP.Root>
  );
}

// ---------------------------------------------------------------- Feedback
export const Skeleton = ({ className }: { className?: string }) =>
  <div className={cn("relative overflow-hidden rounded-md bg-line/70", className)}>
    <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/40 to-transparent dark:via-white/5" />
  </div>;

export function Dots({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1", className)} aria-hidden>
      {["bg-seal", "bg-brass", "bg-brand-2"].map((c, i) => <span key={c} className={cn("h-2 w-2 rounded-full animate-dot", c)} style={{ animationDelay: `${i * 0.18}s` }} />)}
    </span>
  );
}

export function Empty({ icon: Icon, title, children, action }: { icon: LucideIcon; title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-line-2 bg-raised/60 px-6 py-10 text-center">
      <div className="mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-surface text-mute shadow-card"><Icon className="h-5 w-5" /></div>
      <p className="font-medium text-ink">{title}</p>
      {children && <p className="mt-1 max-w-sm text-[13.5px] text-mute">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export const ErrorNote = ({ error }: { error: unknown }) =>
  error ? <div role="alert" className="rounded-lg border border-bad/25 bg-bad-soft px-3.5 py-2.5 text-[13.5px] text-bad">{(error as Error).message || String(error)}</div> : null;

export const Kbd = ({ children }: { children: ReactNode }) =>
  <kbd className="rounded border border-line-2 bg-raised px-1.5 py-px font-mono text-[11px] text-mute shadow-[0_1px_0_rgb(var(--line-2))]">{children}</kbd>;

// ---------------------------------------------------------------- Page header
export function PageHeader({ eyebrow, title, subtitle, actions }: { eyebrow?: ReactNode; title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}
      className="mb-7 flex flex-wrap items-end gap-4">
      <div className="min-w-0 flex-1">
        {eyebrow && <div className="eyebrow mb-1.5">{eyebrow}</div>}
        <h1 className="h-display text-[30px] leading-[1.1] text-ink sm:text-[34px]">{title}</h1>
        {subtitle && <p className="mt-2 max-w-2xl text-[14.5px] text-mute">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </motion.div>
  );
}

export const FadeIn = ({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) =>
  <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay }} className={className}>{children}</motion.div>;
