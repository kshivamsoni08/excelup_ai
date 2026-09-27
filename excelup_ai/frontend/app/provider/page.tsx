"use client";

import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { School, TrendingDown, Users } from "lucide-react";
import { api } from "@/lib/api";

type Dash = {
  trainees: number;
  top_skills: { skill: string; count: number }[];
  top_gaps: { skill: string; count: number }[];
  participation: Record<string, number>;
  placements: number;
  at_risk: { id: number; name: string; pri: number; target_role: string }[];
  pri_mean: number;
  pri_histogram: { bin: string; count: number }[];
  pri_formula: string;
};

export default function InstitutionDashboard() {
  const { data } = useQuery({
    queryKey: ["inst-dashboard"],
    queryFn: () => api<Dash>("/provider/dashboard"),
    refetchInterval: 15_000,
  });

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <School className="h-6 w-6" /> Outcome Dashboard
        </h1>
        <p className="text-sm text-stone-500">Live cohort analytics - auto-refreshing every 15s.</p>
      </div>

      {/* KPI row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="card p-5">
          <div className="text-3xl font-bold text-primary-900">{data?.trainees ?? "-"}</div>
          <div className="text-xs uppercase tracking-wide text-stone-400">trainees on platform</div>
        </div>
        <div className="card p-5">
          <div className="text-3xl font-bold text-primary-900">{data?.placements ?? "-"}</div>
          <div className="text-xs uppercase tracking-wide text-stone-400">placements (accepted offers)</div>
        </div>
        <div className="card p-5">
          <div className="text-3xl font-bold text-primary-900">{data?.pri_mean ?? "-"}</div>
          <div className="text-xs uppercase tracking-wide text-stone-400">mean Placement Readiness</div>
        </div>
        <div className="card p-5">
          <div className="text-3xl font-bold text-primary-900">{data?.participation?.trainees_assessed ?? "-"}</div>
          <div className="text-xs uppercase tracking-wide text-stone-400">trainees assessed</div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="card p-5">
          <h3 className="mb-3 font-semibold text-primary-950">Top-10 skills held across the cohort</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data?.top_skills ?? []} layout="vertical" margin={{ left: 40 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="skill" width={130} fontSize={10} />
              <Tooltip />
              <Bar dataKey="count" fill="#14532D" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-5">
          <h3 className="mb-3 font-semibold text-primary-950">Job-Readiness histogram (cohort readiness)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data?.pri_histogram ?? []}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="bin" fontSize={10} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#F59E0B" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-2 rounded-lg bg-stone-50 p-2 text-xs text-stone-500">
            <b>Transparent by design:</b> {data?.pri_formula}
          </div>
        </div>

        <div className="card p-5">
          <h3 className="mb-3 font-semibold text-primary-950">Top skill gaps vs target roles</h3>
          <div className="space-y-1.5">
            {(data?.top_gaps ?? []).map((g) => (
              <div key={g.skill} className="flex items-center gap-2 text-sm">
                <span className="w-48 truncate text-stone-600">{g.skill}</span>
                <div className="h-2 grow rounded-full bg-stone-100">
                  <div className="h-2 rounded-full bg-saffron-500"
                    style={{ width: `${(g.count / (data?.top_gaps[0]?.count || 1)) * 100}%` }} />
                </div>
                <span className="w-8 text-right font-mono text-xs text-stone-400">{g.count}</span>
              </div>
            ))}
            {!data?.top_gaps?.length && <div className="text-sm text-stone-400">No gap data yet.</div>}
          </div>
        </div>

        <div className="card p-5">
          <h3 className="mb-3 flex items-center gap-2 font-semibold text-primary-950">
            <TrendingDown className="h-4 w-4 text-red-500" /> At-risk trainees (JRI &lt; 40)
          </h3>
          <div className="max-h-56 space-y-1.5 overflow-auto">
            {(data?.at_risk ?? []).map((s) => (
              <div key={s.id} className="flex items-center justify-between rounded-lg border border-stone-100 px-3 py-1.5 text-sm">
                <span>{s.name} <span className="text-xs text-stone-400">· {s.target_role || "no target"}</span></span>
                <span className="badge-red">JRI {s.pri}</span>
              </div>
            ))}
            {!data?.at_risk?.length && <div className="text-sm text-stone-400">No at-risk trainees 🎉</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
