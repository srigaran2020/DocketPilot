import { ArrowUpRight, CalendarDays, CheckCircle2, FileText, Lightbulb, MessageSquareText, Paperclip, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Stamp } from "@/components/legal";
import { Card, CardHeader, PageHeader } from "@/components/ui";
import { store } from "@/lib/utils";

const STEPS = [
  { icon: MessageSquareText, title: "Open “Ask DocketPilot”", text: "This is the chat. You can do almost everything from here." },
  { icon: Paperclip, title: "Attach your case papers", text: "Click the clip or drag files in (.pdf, .docx or .txt). DocketPilot reads the case number, files the paper under the right case and puts every date on your calendar." },
  { icon: ShieldCheck, title: "Check what was hidden", text: "Names, phone, Aadhaar, PAN, bank accounts and addresses are hidden before anything goes to the AI. Untick anything that is not private, type anything missed, then click File it." },
  { icon: FileText, title: "Ask for what you need", text: "Type in plain words, for example a draft, a legal question or the case's strengths and weaknesses." },
  { icon: CheckCircle2, title: "Review, approve, download", text: "Wrong citations are already corrected and unsupported ones removed. Tick any amber item you checked, approve, and download the Word file. Real names come back only now." },
];
const EXAMPLES: [string, string[]][] = [
  ["Ask about the law", ["What must be proved for divorce on the ground of cruelty?", "When can anticipatory bail be granted under the BNSS?"]],
  ["Make a draft", ["Draft a bail application for this case", "Draft a reply to the legal notice"]],
  ["Check citations", ["Verify this: "]],
  ["Risk and strategy", ["What strategy should I use for this case?"]],
  ["Past cases", ["Show me similar past cases"]],
  ["Dates", ["When is my next hearing?", "Remind me about the hearing on 12 November"]],
];

export default function Guide() {
  const nav = useNavigate();
  const ask = (s: string) => { store.sset("dp_prefill", s); nav("/ask"); };
  return (
    <>
      <PageHeader eyebrow="Help" title="How to use DocketPilot" subtitle="DocketPilot finds the law, writes drafts and checks every case and section it mentions. Nothing is final until you approve it." />
      <Card className="mb-6 p-6">
        <h2 className="h-display mb-5 text-[20px]">Your first case in five steps</h2>
        <ol className="grid gap-4 md:grid-cols-5">
          {STEPS.map((s, i) => (
            <li key={s.title} className="relative rounded-xl border border-line bg-raised/60 p-4">
              <span className="absolute right-3 top-3 font-display text-[28px] font-semibold leading-none text-line-2">{i + 1}</span>
              <s.icon className="mb-3 h-5 w-5 text-seal" /><p className="font-semibold leading-snug">{s.title}</p><p className="mt-1 text-[13px] text-mute">{s.text}</p>
            </li>))}
        </ol>
      </Card>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader icon={MessageSquareText} title="Things you can type" subtitle="Click any example to try it" />
          <div className="space-y-4 px-5 pb-5">{EXAMPLES.map(([h, xs]) => (
            <div key={h}><p className="mb-1.5 text-[13px] font-semibold text-ink-2">{h}</p><div className="flex flex-wrap gap-2">{xs.map(x => (
              <button key={x} onClick={() => ask(x)} className="inline-flex items-center gap-1.5 rounded-lg border border-brass/30 bg-brass-soft/60 px-3 py-1.5 text-[13px] text-ink transition hover:border-brass hover:bg-brass-soft">
                {x.trim()}<ArrowUpRight className="h-3.5 w-3.5 text-[rgb(var(--brass))]" /></button>))}</div></div>))}
            <p className="text-[12.5px] text-mute">Tip: switch on <b>Explain simply</b> for answers in easy words, and pick a case at the top of the chat so answers use its papers.</p>
          </div>
        </Card>
        <div className="space-y-6">
          <Card>
            <CardHeader icon={ShieldCheck} title="What the marks mean" />
            <div className="space-y-3 px-5 pb-5 text-[14px]">
              <p className="flex gap-3"><Stamp colour="green" /><span><b>Verified.</b> The case or section was found, and the judgment says what is claimed.</span></p>
              <p className="flex gap-3"><Stamp colour="amber" /><span><b>Check it yourself.</b> Something is uncertain, for example the case is not in the library or a quote differs slightly.</span></p>
              <p className="flex gap-3"><Stamp colour="red" /><span><b>Problem.</b> Points to a different case, the quote is not in the judgment, or the law was not in force on that date.</span></p>
            </div>
          </Card>
          <Card>
            <CardHeader icon={CalendarDays} title="Deadlines and reminders" />
            <p className="px-5 pb-5 text-[14px] text-ink-2">When you add papers, every date in them goes on the calendar with the line it came from. Drafts add the legal deadlines too. Add your own by typing “Remind me about the hearing on 12 November”, and export a case's dates to your phone calendar.</p>
          </Card>
          <Card>
            <CardHeader icon={Lightbulb} title="Good to know" />
            <ul className="list-disc space-y-1.5 px-5 pb-5 pl-10 text-[14px] text-ink-2 marker:text-brass">
              <li><b>“Not found”</b> means the case is not in the library. It does not mean the case is fake.</li>
              <li>DocketPilot gives strengths, risks and strategy, but does not predict who will win.</li>
              <li>Scanned papers without text cannot be read yet. Use a text PDF, Word or .txt file.</li>
              <li>If the AI is busy, wait a minute and try again. Search and checking still work.</li>
              <li>This is a research prototype. Always read a draft fully before filing it.</li>
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
