"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bell, BookOpen, Brain, Building2, Dna, FileScan, FlaskConical,
  GraduationCap, HandCoins, Home, LogOut, Map, Route, School, Search,
  Settings, Shield, Sparkles, Trophy, Users, BarChart3, ClipboardCheck,
  Landmark, ScrollText,
} from "lucide-react";
import { api, clearSession, getSession, type SessionUser } from "@/lib/api";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }> };

const NAVS: Record<SessionUser["role"], { brand: string; items: NavItem[] }> = {
  trainee: {
    brand: "ExcelUp AI",
    items: [
      { href: "/trainee", label: "Home & Feed", icon: Home },
      { href: "/trainee/outcomes", label: "My Outcome Ledger", icon: ClipboardCheck },
      { href: "/trainee/consents", label: "Consent Manager", icon: Shield },
      { href: "/trainee/genome", label: "My Skill Genome", icon: Dna },
      { href: "/trainee/assess", label: "Adaptive Test", icon: Brain },
      { href: "/trainee/resume", label: "Resume Scanner", icon: FileScan },
      { href: "/trainee/challenges", label: "Skill Challenges", icon: Trophy },
      { href: "/trainee/search", label: "Search Jobs", icon: Search },
      { href: "/trainee/applications", label: "My Applications", icon: Sparkles },
      { href: "/trainee/simulator", label: "Career Simulator", icon: Route },
      { href: "/trainee/gap", label: "Skill Gap Report", icon: Map },
      { href: "/trainee/learning", label: "My Learning Path", icon: BookOpen },
    ],
  },
  // Dormant per delta-spec (kept for old accounts, hidden until used again)
  trainer: {
    brand: "ExcelUp AI",
    items: [
      { href: "/faculty", label: "Industry Residency", icon: FlaskConical },
      { href: "/faculty/learning", label: "Courses", icon: BookOpen },
    ],
  },
  employer: {
    brand: "ExcelUp AI for Employers",
    items: [
      { href: "/employer/validations", label: "Validation Queue", icon: ClipboardCheck },
      { href: "/company", label: "Postings & Pipeline", icon: Building2 },
      { href: "/company/post", label: "Posting Builder", icon: Settings },
      { href: "/company/challenges", label: "Challenge Review", icon: Trophy },
    ],
  },
  provider: {
    brand: "ExcelUp AI for Providers",
    items: [
      { href: "/provider", label: "Outcome Dashboard", icon: BarChart3 },
      { href: "/provider/pri", label: "Job-Readiness Index", icon: GraduationCap },
      { href: "/provider/growth", label: "Skill Growth", icon: Dna },
    ],
  },
  officer: {
    brand: "ExcelUp AI · Dept of Skills",
    items: [
      { href: "/officer", label: "Impact Dashboard", icon: Landmark },
      { href: "/officer/programmes", label: "Programmes", icon: BarChart3 },
      { href: "/officer/districts", label: "District View", icon: Map },
      { href: "/officer/followups", label: "Follow-up Workbench", icon: Users },
      { href: "/officer/audit", label: "PII Access Audit", icon: ScrollText },
    ],
  },
  admin: {
    brand: "ExcelUp AI Admin",
    items: [{ href: "/admin", label: "Platform Stats", icon: Shield }],
  },
};

type NotificationItem = { id: number; type: string; payload: any; read: boolean; created_at: string };

function NotificationBell() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<{ unread: number; items: NotificationItem[] }>("/notifications"),
    refetchInterval: 10_000,
  });
  const markRead = useMutation({
    mutationFn: (id: number) => api(`/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  return (
    <div className="group relative">
      <button className="btn-ghost relative px-2">
        <Bell className="h-5 w-5" />
        {!!data?.unread && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-saffron-500 px-1 text-[10px] font-bold text-white">
            {data.unread > 9 ? "9+" : data.unread}
          </span>
        )}
      </button>
      <div className="invisible absolute right-0 top-10 z-30 w-80 rounded-xl border border-stone-200 bg-white p-2 opacity-0 shadow-xl transition group-hover:visible group-hover:opacity-100">
        <div className="px-2 py-1 text-xs font-semibold uppercase text-stone-400">Notifications</div>
        {!data?.items?.length && <div className="px-2 py-4 text-sm text-stone-400">Nothing yet.</div>}
        {data?.items?.slice(0, 8).map((n) => (
          <button key={n.id}
            onClick={() => !n.read && markRead.mutate(n.id)}
            className={`block w-full rounded-lg px-2 py-2 text-left text-sm hover:bg-stone-50 ${n.read ? "text-stone-400" : "text-stone-800"}`}>
            <span className="font-medium">{humanType(n.type)}</span>
            <span className="block truncate text-xs text-stone-500">{subText(n)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function humanType(t: string) {
  return t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function subText(n: NotificationItem) {
  const p = n.payload || {};
  if (n.type === "decay_alert") return `${p.skill} decaying - floor ${p.floor} vs ${p.min_level} required`;
  if (n.type === "gauntlet_approved") return `${p.gauntlet ?? "Challenge"} approved`;
  if (n.type === "gauntlet_rejected") return `${p.gauntlet ?? "Challenge"} rejected`;
  if (n.type === "followup_wave") return `${p.title ?? "Follow-up"}: report your outcome in one tap`;
  if (n.type === "followup_due") return `Outcome check-in due (${p.milestone ?? "scheduled"})`;
  if (n.type === "validation_request") return `${p.company ?? "Employer"} asked to confirm your job episode`;
  if (n.type === "episode_validated") return `${p.role_title ?? "Your job"} validated by employer`;
  if (n.type === "outcome_recorded") return `Outcome recorded: ${p.response ?? "updated"}`;
  if (n.type?.startsWith("application_")) return `Application ${n.type.split("_")[1]}${p.feedback?.headline ? ` - ${p.feedback.headline}` : ""}`;
  if (n.type === "evidence_course") return `Completed ${p.course}`;
  return JSON.stringify(p).slice(0, 80);
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const user = getSession();

  useEffect(() => {
    if (!user) router.replace("/");
  }, [user, router]);

  if (!user) return null;
  const nav = NAVS[user.role] ?? NAVS.trainee;

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 w-60 border-r border-stone-200 bg-white">
        <div className="flex h-14 items-center gap-2 border-b border-stone-100 px-5">
          <Dna className="h-6 w-6 text-primary-800" />
          <span className="font-semibold tracking-tight text-primary-950">{nav.brand}</span>
        </div>
        <nav className="space-y-0.5 p-3">
          {nav.items.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                  active ? "bg-primary-50 font-medium text-primary-900" : "text-stone-600 hover:bg-stone-50"}`}>
                <Icon className="h-4 w-4" /> {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="ml-60 flex min-h-screen flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-end gap-3 border-b border-stone-200 bg-white/90 px-6 backdrop-blur">
          <div className="mr-auto text-sm text-stone-500">
            {user.name}
            {user.company && <span className="badge-green ml-2">{user.company.verified ? "✓ verified employer" : "employer"}</span>}
            {user.provider && <span className="badge-gray ml-2">{user.provider.name}</span>}
          </div>
          <NotificationBell />
          <button className="btn-ghost" onClick={() => { clearSession(); router.replace("/"); }}>
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
