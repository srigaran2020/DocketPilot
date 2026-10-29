import { useMutation } from "@tanstack/react-query";
import { KeyRound, LogOut, UserRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "@/components/toast";
import { Badge, Button, Card, CardHeader, ErrorNote, Input, Label, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { initials } from "@/lib/utils";

export default function Account() {
  const { me, signOut } = useAuth();
  const nav = useNavigate();
  const pw = useMutation({ mutationFn: (f: { cur: string; next: string }) => api("/auth/password", { json: { current_password: f.cur, new_password: f.next } }),
    onSuccess: () => toast.success("Password changed") });
  return (
    <>
      <PageHeader eyebrow="Your account" title={me?.full_name || "Account"} />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader icon={UserRound} title="Details" />
          <div className="px-5 pb-5">
            <div className="mb-5 flex items-center gap-4">
              <span className="grid h-14 w-14 place-items-center rounded-full bg-gradient-to-br from-brand-2 to-brand text-[18px] font-semibold text-[rgb(var(--on-brand))]">{initials(me?.full_name)}</span>
              <div><p className="font-semibold">{me?.full_name}</p><p className="text-[13.5px] text-mute">{me?.email}</p></div>
              <Badge tone="brand" className="ml-auto capitalize">{me?.role}</Badge>
            </div>
            <p className="mb-4 text-[13.5px] text-mute">Your cases are private to your own workspace.</p>
            <Button variant="secondary" icon={LogOut} onClick={() => { signOut(); nav("/login"); }}>Sign out on this device</Button>
          </div>
        </Card>
        <Card>
          <CardHeader icon={KeyRound} title="Change password" />
          <form className="space-y-4 px-5 pb-5" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); pw.mutate({ cur: String(f.get("c")), next: String(f.get("n")) }); e.currentTarget.reset(); }}>
            <div><Label htmlFor="c" hint="(leave empty if you only use Google)">Current password</Label><Input id="c" name="c" type="password" autoComplete="current-password" /></div>
            <div><Label htmlFor="n" hint="(at least 8 characters)">New password</Label><Input id="n" name="n" type="password" minLength={8} autoComplete="new-password" required /></div>
            <ErrorNote error={pw.error} />
            <Button type="submit" loading={pw.isPending}>Change password</Button>
          </form>
        </Card>
      </div>
    </>
  );
}
