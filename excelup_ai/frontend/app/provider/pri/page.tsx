"use client";

import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { GraduationCap } from "lucide-react";
import { api } from "@/lib/api";

type PriRow = {
  id: number; name: string; pri: number; target_role: string;
  components: { coverage: number; portfolio_depth: number; freshness: number; sjt: number; interview_readiness: number };
};

export default function PriPage() {
  const { data } = useQuery({
    queryKey: ["inst-pri"],
    queryFn: () => api<{ trainees: PriRow[]; formula: string; histogram: { bin: string; count: number }[] }>("/provider/pri"),
    refetchInterval: 20_000,
  });

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <GraduationCap className="h-6 w-6" /> Placement Job-Readiness Index
        </h1>
        <div className="mt-2 rounded-xl bg-primary-950 p-4 font-mono text-xs text-primary-100">
          {data?.formula ?? "JRI = 0.35×essential_coverage + 0.25×portfolio_depth + 0.15×freshness + 0.15×SJT + 0.10×interview_readiness"}
        </div>
      </div>

      <div className="card p-5">
        <h3 className="mb-3 font-semibold text-primary-950">Cohort histogram</h3>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data?.histogram ?? []}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="bin" fontSize={10} />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="count" fill="#14532D" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="card overflow-x-auto p-5">
        <h3 className="mb-3 font-semibold text-primary-950">Per-trainee Job-Job-Readiness Index (with published math)</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-stone-200 text-left text-xs uppercase tracking-wide text-stone-400">
              <th className="py-2 pr-3">Student</th>
              <th className="py-2 pr-3">Target role</th>
              <th className="py-2 pr-3">JRI</th>
              <th className="py-2 pr-3">Coverage</th>
              <th className="py-2 pr-3">Portfolio</th>
              <th className="py-2 pr-3">Freshness</th>
              <th className="py-2 pr-3">SJT</th>
              <th className="py-2 pr-3">Interview</th>
            </tr>
          </thead>
          <tbody>
            {(data?.trainees ?? []).slice(0, 40).map((s) => (
              <tr key={s.id} className="border-b border-stone-50">
                <td className="py-2 pr-3 font-medium">{s.name}</td>
                <td className="py-2 pr-3 text-stone-500">{s.target_role || "-"}</td>
                <td className="py-2 pr-3">
                  <span className={`badge ${s.pri >= 60 ? "badge-green" : s.pri >= 40 ? "badge-amber" : "badge-red"}`}>
                    {s.pri}
                  </span>
                </td>
                <td className="py-2 pr-3 font-mono text-xs">{s.components.coverage}%</td>
                <td className="py-2 pr-3 font-mono text-xs">{s.components.portfolio_depth}%</td>
                <td className="py-2 pr-3 font-mono text-xs">{s.components.freshness}%</td>
                <td className="py-2 pr-3 font-mono text-xs">{s.components.sjt}%</td>
                <td className="py-2 pr-3 font-mono text-xs">{s.components.interview_readiness}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
