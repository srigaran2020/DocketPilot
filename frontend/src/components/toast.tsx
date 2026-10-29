import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

// Small accessible toasts (a live region, not a list), replacing a library whose markup failed the axe audit.
type Kind = "success" | "error" | "info";
type Item = { id: number; kind: Kind; title: string; description?: string };
let items: Item[] = [];
let listeners: ((v: Item[]) => void)[] = [];
let next = 1;
const emit = () => listeners.forEach(l => l(items));
function push(kind: Kind, title: string, opts?: { description?: string }) {
  const it = { id: next++, kind, title, description: opts?.description };
  items = [...items, it].slice(-4);
  emit();
  setTimeout(() => { items = items.filter(x => x.id !== it.id); emit(); }, kind === "error" ? 7000 : 4500);
}
export const toast = Object.assign((title: string, o?: { description?: string }) => push("info", title, o), {
  success: (title: string, o?: { description?: string }) => push("success", title, o),
  error: (title: string, o?: { description?: string }) => push("error", title, o),
});

const ICON = { success: CheckCircle2, error: AlertCircle, info: Info };
export function Toaster() {
  const [list, setList] = useState<Item[]>(items);
  useEffect(() => { listeners.push(setList); return () => { listeners = listeners.filter(l => l !== setList); }; }, []);
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed bottom-5 right-5 z-[80] flex w-[360px] max-w-[calc(100vw-40px)] flex-col gap-2">
      <AnimatePresence initial={false}>
        {list.map(t => {
          const Icon = ICON[t.kind];
          return (
            <motion.div key={t.id} layout initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, x: 40 }}
              className="pointer-events-auto flex items-start gap-3 rounded-xl border border-line bg-surface px-4 py-3 shadow-pop">
              <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", t.kind === "success" && "text-ok", t.kind === "error" && "text-bad", t.kind === "info" && "text-brand-2")} />
              <div className="min-w-0 flex-1"><p className="text-[14px] font-medium text-ink">{t.title}</p>
                {t.description && <p className="mt-0.5 text-[13px] text-ink-2">{t.description}</p>}</div>
              <button onClick={() => { items = items.filter(x => x.id !== t.id); emit(); }} className="rounded p-0.5 text-mute hover:text-ink" aria-label="Dismiss"><X className="h-4 w-4" /></button>
            </motion.div>);
        })}
      </AnimatePresence>
    </div>
  );
}
