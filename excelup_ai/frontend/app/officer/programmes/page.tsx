"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { BarChart3, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";

type Row = {
  programme_id: number; title: string; provider: string; sector: string;
  nsqf_level: number; completions: number; placement_0: number;
  placement_12: number; retention_12: number; wage_growth_12: number | null;
  wage_n: number; validation_rate: number; followup_rate: number;
  oqi: number; flags: string[];
  consent: { completers: number; consented: number; coverage_pct: number };
};

type Resp = { view: string; rows: Row[]; oqi_formula: string; flags_legend: Record<string, string> };

export default function ProgrammesPage() {
  const [view, setView] = useState<"day0" | "outcomes">("day0");
  const { data, isFetching } = useQuery({
    queryKey: ["officer-programmes", view],
    queryFn: () => api<Resp>(`/officer/programmes?view=${view}`),
    refetchInterval: 15_000,
  });

  const rows = data?.rows ?? [];

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <BarChart3 className="h-7 w-7 text-primary-800" />
        <div>
          <h1 className="text-2xl font-bold text-primary-950">Programmes</h1>
          <p className="text-sm text-stone-500">Ranked by {view === "day0" ? "placement-day rate (the vanity view)" : "OQI - outcome-adjusted quality"}. {isFetching && "Refreshing…"}</p>
        </div>
      </div>

      {/* THE toggle - the demo moment */}
      <div className="card flex items-center justify-between p-4">
        <div>
          <div className="font-semibold text-primary-950">Placement-day view ⇄ Outcome view</div>
          <div className="text-xs text-stone-500">Same data, honest denominator: day-0 flatters; outcomes re-rank providers.</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setView("day0")}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${view === "day0" ? "bg-saffron-500 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200"}`}>
            Placement-day view
          </button>
          <button
            onClick={() => setView("outcomes")}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${view === "outcomes" ? "bg-primary-800 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200"}`}>
            Outcome view
          </button>
        </div>
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="w-full min-w-[980px] text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-left text-xs uppercase tracking-wide text-stone-400">
            <tr>
              <th className="px-4 py-3">#</th>
              <th className="px-4 py-3">Programme</th>
              <th className="px-4 py-3">Provider / Sector</th>
              <th className="px-4 py-3 text-right">Completions</th>
              <th className="px-4 py-3 text-right">Day 0</th>
              <th className="px-4 py-3 text-right">12 mo</th>
              <th className="px-4 py-3 text-right">Retention</th>
              <th className="px-4 py-3 text-right">Wage Δ</th>
              <th className="px-4 py-3 text-right">Validation</th>
              <th className="px-4 py-3 text-right">OQI</th>
              <th className="px-4 py-3">Flags</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.programme_id} className={`border-b border-stone-100 hover:bg-stone-50 ${i === 0 ? "bg-primary-50/50" : ""}`}>
                <td className="px-4 py-3 font-bold text-primary-800">{i + 1}</td>
                <td className="px-4 py-3">
                  <Link href={`/officer/programmes/${r.programme_id}`} className="font-medium text-primary-900 hover:underline">
                    {r.title}
                  </Link>
                </td>
                <td className="px-4 py-3 text-stone-500">
                  {r.provider}
                  <span className="badge-gray ml-1.5">{r.sector}</span>
                </td>
                <td className="px-4 py-3 text-right">{r.completions}</td>
                <td className="px-4 py-3 text-right font-semibold text-saffron-600">{pct(r.placement_0)}</td>
                <td className="px-4 py-3 text-right">{pct(r.placement_12)}</td>
                <td className="px-4 py-3 text-right">{pct(r.retention_12)}</td>
                <td className="px-4 py-3 text-right">
                  {r.wage_growth_12 == null ? "-" : `+${Math.round(r.wage_growth_12 * 100)}%`}
                  <span className="ml-1 text-[10px] text-stone-400">(n={r.wage_n})</span>
                </td>
                <td className="px-4 py-3 text-right">{pct(r.validation_rate)}</td>
                <td className="px-4 py-3 text-right font-bold text-primary-800">{Math.round(r.oqi)}</td>
                <td className="px-4 py-3">
                  {r.flags.length === 0 && <span className="text-stone-300">-</span>}
                  {r.flags.map((f) => (
                    <span key={f} className="badge-amber mr-1 whitespace-nowrap">{f.replace(/_/g, " ")}</span>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card p-4 text-xs text-stone-600">
          <b className="text-primary-950">OQI formula (published):</b> {data?.oqi_formula}
          <div className="mt-1 text-stone-400">Wage stats show n = trainees with 'wage' consent scope. Coverage never assumed.</div>
        </div>
        <div className="card p-4 text-xs text-stone-600">
          <b className="text-primary-950">Flag legend:</b>
          <ul className="mt-1 list-disc pl-4">
            {Object.entries(data?.flags_legend ?? {}).map(([k, v]) => (
              <li key={k}><b>{k.replace(/_/g, " ")}</b> - {v}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function pct(x: number) {
  return `${Math.round(x * 100)}%`;
}
