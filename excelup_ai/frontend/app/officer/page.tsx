"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { AlertTriangle, Landmark, ShieldCheck, TrendingDown } from "lucide-react";
import { api } from "@/lib/api";

type Dashboard = {
  overall: {
    completers: number; placement_0: number; placement_12: number;
    retention_12: number; validation_rate: number; followup_rate: number;
  };
  followups: { waves: number; attempts: number; responded: number };
  consent_coverage: { trainees: number; consented: number };
  flagged_programmes: { programme_id: number; title: string; flags: string[] }[];
  oqi_formula: string;
};

type Row = {
  programme_id: number; title: string; provider: string; sector: string;
  completions: number; placement_0: number; placement_12: number;
  oqi: number; flags: string[];
};

export default function OfficerDashboard() {
  const { data: dash } = useQuery({
    queryKey: ["officer-dashboard"],
    queryFn: () => api<Dashboard>("/officer/dashboard"),
    refetchInterval: 15_000,
  });
  const { data: progs } = useQuery({
    queryKey: ["officer-programmes", "outcomes"],
    queryFn: () => api<{ rows: Row[] }>("/officer/programmes?view=outcomes"),
    refetchInterval: 15_000,
  });

  const overall = dash?.overall;
  const decay = overall
    ? [
        { m: "Day 0", v: Math.round(overall.placement_0 * 100) },
        { m: "12 mo", v: Math.round(overall.placement_12 * 100) },
      ]
    : [];
  const top = (progs?.rows ?? []).slice(0, 6);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Landmark className="h-7 w-7 text-primary-800" />
        <div>
          <h1 className="text-2xl font-bold text-primary-950">Impact Dashboard</h1>
          <p className="text-sm text-stone-500">Department of Skills, Employment, Entrepreneurship &amp; Innovation - Government of Maharashtra (demo)</p>
        </div>
        <span className="badge-green ml-auto">
          <ShieldCheck className="mr-1 inline h-3.5 w-3.5" />
          Consent coverage {dash
            ? Math.round((100 * dash.consent_coverage.consented) / Math.max(dash.consent_coverage.trainees, 1))
            : "-"}%
        </span>
      </div>

      {/* Headline KPIs */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Kpi label="Cohort completers" value={overall ? overall.completers.toLocaleString() : "-"} />
        <Kpi label="Placement (day 0)" value={overall ? pct(overall.placement_0) : "-"} tone="amber" />
        <Kpi label="Placement (12 mo)" value={overall ? pct(overall.placement_12) : "-"} tone="green" />
        <Kpi label="Retention 12 mo" value={overall ? pct(overall.retention_12) : "-"} />
        <Kpi label="Employer validation" value={overall ? pct(overall.validation_rate) : "-"} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Placement decay curve */}
        <div className="card p-5">
          <h3 className="font-semibold text-primary-950">Placement decay - day 0 vs 12 months</h3>
          <p className="mb-3 text-xs text-stone-500">Placement-day numbers flatter programmes. Outcomes tell the truth.</p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={decay}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="m" fontSize={12} />
              <YAxis domain={[0, 100]} fontSize={12} unit="%" />
              <Tooltip formatter={(v: number) => `${v}%`} />
              <Bar dataKey="v" fill="#1E3A8A" radius={[6, 6, 0, 0]} name="placed %" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Follow-up funnel */}
        <div className="card p-5">
          <h3 className="font-semibold text-primary-950">Follow-up funnel</h3>
          <p className="mb-3 text-xs text-stone-500">One-tap responses keep the ledger alive.</p>
          <div className="grid grid-cols-3 gap-3 text-center">
            <Funnel n={dash?.followups.waves} label="waves" />
            <Funnel n={dash?.followups.attempts} label="attempts" />
            <Funnel n={dash?.followups.responded} label="responded" />
          </div>
          <div className="mt-4 rounded-lg bg-primary-50 px-3 py-2 text-xs text-primary-900">
            Overall follow-up response rate: <b>{overall ? pct(overall.followup_rate) : "-"}</b>
          </div>
          <Link href="/officer/followups" className="btn-secondary mt-4 w-full">Open assisted workbench</Link>
        </div>
      </div>

      {/* Flags strip */}
      <div className="card p-5">
        <div className="mb-2 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-saffron-600" />
          <h3 className="font-semibold text-primary-950">Programme flags (auto-detected)</h3>
        </div>
        {!dash?.flagged_programmes?.length && (
          <div className="text-sm text-stone-400">No flags right now.</div>
        )}
        <div className="flex flex-wrap gap-2">
          {dash?.flagged_programmes?.map((f) => (
            <Link key={f.programme_id} href={`/officer/programmes/${f.programme_id}`}
              className="badge-amber cursor-pointer">
              {f.title}: {f.flags.join(", ").replace(/_/g, " ")}
            </Link>
          ))}
        </div>
        <p className="mt-3 text-xs text-stone-500">Flags: vanity_metric = placement-day far above 12-month outcomes; oversupplied = completions exceed sector demand with weak outcomes; obsolete = sector postings down &gt;25% YoY.</p>
      </div>

      {/* Best/worst programmes by OQI */}
      <div className="card p-5">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-semibold text-primary-950">Outcome-adjusted leaders (top programmes by OQI)</h3>
          <Link href="/officer/programmes" className="text-sm font-medium text-primary-700 hover:underline">
            Full programmes table - see the ranking flip
          </Link>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={top.map((r) => ({ name: r.title.length > 26 ? r.title.slice(0, 24) + "…" : r.title, OQI: Math.round(r.oqi), Day0: Math.round(r.placement_0 * 100) }))}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="name" fontSize={10} interval={0} angle={-18} textAnchor="end" height={60} />
            <YAxis fontSize={12} />
            <Tooltip />
            <Bar dataKey="Day0" fill="#D97706" radius={[4, 4, 0, 0]} name="day-0 %" />
            <Bar dataKey="OQI" fill="#1E3A8A" radius={[4, 4, 0, 0]} name="OQI" />
          </BarChart>
        </ResponsiveContainer>
        <p className="mt-2 text-xs text-stone-500">OQI = 100 x (0.30·placement_12 + 0.25·retention_12 + 0.25·wage growth + 0.10·validation + 0.10·follow-up). Formula is published, always.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Link href="/officer/programmes" className="card p-5 transition hover:border-primary-300">
          <h3 className="font-semibold text-primary-950">Programmes table →</h3>
          <p className="text-sm text-stone-500">Toggle placement-day view vs outcome view - watch the ranking flip.</p>
        </Link>
        <Link href="/officer/districts" className="card p-5 transition hover:border-primary-300">
          <h3 className="font-semibold text-primary-950">District heatmap →</h3>
          <p className="text-sm text-stone-500">Outcomes by district x sector across Maharashtra.</p>
        </Link>
      </div>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "green" | "amber" }) {
  return (
    <div className="card p-4">
      <div className={`text-2xl font-bold ${tone === "green" ? "text-primary-800" : tone === "amber" ? "text-saffron-600" : "text-primary-950"}`}>
        {value}
      </div>
      <div className="mt-1 text-xs uppercase tracking-wide text-stone-400">{label}</div>
    </div>
  );
}
function Funnel({ n, label }: { n?: number; label: string }) {
  return (
    <div className="rounded-xl bg-stone-50 p-3">
      <div className="text-2xl font-bold text-primary-900">{n ?? "-"}</div>
      <div className="text-xs uppercase tracking-wide text-stone-400">{label}</div>
    </div>
  );
}
function pct(x: number) {
  return `${Math.round(x * 100)}%`;
}
