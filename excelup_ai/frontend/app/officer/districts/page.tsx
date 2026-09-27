"use client";

import { useQuery } from "@tanstack/react-query";
import { Map as MapIcon } from "lucide-react";
import { api } from "@/lib/api";

type Cell = { district: string; sector: string; episodes: number; active: number };

type Demographics = {
  total_completers: number; consented: number; coverage_pct: number;
  by_gender: DCell[]; by_category: DCell[];
};
type DCell = { value: string; rate: number | null; n: number; suppressed: boolean };

export default function DistrictsPage() {
  const { data } = useQuery({
    queryKey: ["officer-districts"],
    queryFn: () => api<{ cells: Cell[]; note: string }>("/officer/districts"),
    refetchInterval: 15_000,
  });
  const { data: demo } = useQuery({
    queryKey: ["officer-demographics"],
    queryFn: () => api<Demographics>("/officer/demographics"),
    refetchInterval: 15_000,
  });

  const cells = data?.cells ?? [];
  const districts = [...new Set(cells.map((c) => c.district))].sort();
  const sectors = [...new Set(cells.map((c) => c.sector))].sort();
  const at = (d: string, s: string) => cells.find((c) => c.district === d && c.sector === s);
  const intensity = (c?: Cell) =>
    !c || c.episodes === 0 ? 0 : Math.min(1, c.active / c.episodes);

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <MapIcon className="h-7 w-7 text-primary-800" />
        <div>
          <h1 className="text-2xl font-bold text-primary-950">District View</h1>
          <p className="text-sm text-stone-500">{data?.note ?? "District x sector outcomes"} · Maharashtra (demo)</p>
        </div>
      </div>

      <div className="card overflow-x-auto p-4">
        <table className="w-full min-w-[760px] border-separate border-spacing-1 text-sm">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left text-xs uppercase text-stone-400">District</th>
              {sectors.map((s) => (
                <th key={s} className="px-2 py-1 text-xs uppercase text-stone-400">{s}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {districts.map((d) => (
              <tr key={d}>
                <td className="whitespace-nowrap px-2 py-1 text-sm font-medium text-primary-900">{d}</td>
                {sectors.map((s) => {
                  const c = at(d, s);
                  const v = intensity(c);
                  return (
                    <td key={s} className="p-0">
                      <div
                        className="flex h-11 min-w-[86px] items-center justify-center rounded-md text-xs font-semibold"
                        style={{
                          backgroundColor: `rgba(30, 58, 138, ${0.08 + v * 0.72})`,
                          color: v > 0.55 ? "#fff" : "#1E3A8A",
                        }}
                        title={c ? `${c.district} x ${c.sector}: ${c.active}/${c.episodes} active` : "no episodes"}
                      >
                        {c ? `${c.active}/${c.episodes}` : "·"}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-stone-500">Each cell: active positive episodes / total episodes (employer-linked). Darker = healthier outcome share.</p>
      </div>

      {/* Demographics overview */}
      <div className="card p-5">
        <h3 className="font-semibold text-primary-950">Demographics overview (placement at 12 mo)</h3>
        <p className="text-xs text-stone-500">
          {demo ? `${demo.consented}/${demo.total_completers} completers consented (${demo.coverage_pct}% coverage).` : ""} Cells with n&lt;5 suppressed.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">Gender</div>
            <div className="grid grid-cols-3 gap-2">
              {demo?.by_gender.map((c) => <DemoCell key={c.value} c={c} />)}
            </div>
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">Social category</div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {demo?.by_category.map((c) => <DemoCell key={c.value} c={c} />)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DemoCell({ c }: { c: DCell }) {
  return (
    <div className={`rounded-lg px-3 py-2 text-sm ${c.suppressed ? "bg-stone-100 text-stone-400" : "bg-primary-50 text-primary-900"}`}>
      <div className="font-semibold">{c.value}</div>
      <div className="text-xs">{c.suppressed ? `suppressed (n=${c.n})` : `${Math.round((c.rate ?? 0) * 100)}% (n=${c.n})`}</div>
    </div>
  );
}
