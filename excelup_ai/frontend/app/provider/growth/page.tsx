"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Line, LineChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Dna } from "lucide-react";
import { api } from "@/lib/api";

type Growth = { series: Record<string, Record<string, number>>; formula: string };

export default function GrowthPage() {
  const { data } = useQuery({
    queryKey: ["inst-growth"],
    queryFn: () => api<Growth>("/provider/growth"),
    refetchInterval: 20_000,
  });

  const skills = Object.keys(data?.series ?? {});
  const [selected, setSelected] = useState<string[]>([]);
  const shown = selected.length ? selected : skills.slice(0, 6);

  const chartData = useMemo(() => {
    const months = new Set<string>();
    shown.forEach((s) => Object.keys(data?.series[s] ?? {}).forEach((m) => months.add(m)));
    return [...months].sort().map((m) => {
      const row: Record<string, number | string> = { month: m };
      shown.forEach((s) => { row[s] = data?.series[s]?.[m] ?? 0; });
      return row;
    });
  }, [data, shown]);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <Dna className="h-6 w-6" /> Cohort Skill Growth
        </h1>
        <p className="text-sm text-stone-500">Cohort mean μ per month, straight from proficiency_history (append-only).</p>
      </div>

      <div className="card p-5">
        <div className="mb-3 flex flex-wrap gap-1.5">
          {skills.map((s) => {
            const on = shown.includes(s);
            return (
              <button key={s}
                onClick={() =>
                  setSelected(on ? selected.filter((x) => x !== s) : [...selected, s])
                }
                className={`rounded-full px-2.5 py-1 text-xs ${on ? "bg-primary-900 text-white" : "bg-stone-100 text-stone-500"}`}>
                {s}
              </button>
            );
          })}
        </div>
        <ResponsiveContainer width="100%" height={420}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" fontSize={11} />
            <YAxis domain={[0, 5]} />
            <Tooltip />
            <Legend />
            {shown.map((s, i) => (
              <Line key={s} type="monotone" dataKey={s} stroke={COLORS[i % COLORS.length]}
                connectNulls dot={false} strokeWidth={2} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

const COLORS = ["#14532D", "#F59E0B", "#0EA5E9", "#DC2626", "#7C3AED", "#059669", "#DB2777", "#CA8A04"];
