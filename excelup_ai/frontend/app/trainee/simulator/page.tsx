"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Route, TrendingUp } from "lucide-react";
import { api } from "@/lib/api";

type SimResult = {
  skill: string; hypothetical_level: number; avg_delta: number;
  newly_eligible: string[];
  results: {
    opp_id: number; title: string; company: string; kind: string;
    score_before: number; score_after: number; delta: number;
    eligible_before: boolean; eligible_after: boolean;
  }[];
};

export default function SimulatorPage() {
  const [skillId, setSkillId] = useState<number | null>(null);
  const [level, setLevel] = useState(4);
  const [res, setRes] = useState<SimResult | null>(null);

  const { data: skills } = useQuery({
    queryKey: ["skills-all"],
    queryFn: () => api<{ id: number; name: string }[]>("/skills?limit=250"),
  });

  const run = useMutation({
    mutationFn: () =>
      api<SimResult>("/simulator/what-if", {
        method: "POST",
        body: { skill_id: skillId, hypothetical_level: level },
      }),
    onSuccess: setRes,
  });

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <Route className="h-6 w-6" /> Career Simulator
        </h1>
        <p className="text-sm text-stone-500">What if you leveled up one skill? Re-runs the real matching engine - no hand-waving.</p>
      </div>

      <div className="card flex flex-wrap items-end gap-4 p-6">
        <div className="grow">
          <label className="label">Skill</label>
          <select className="input" value={skillId ?? ""} onChange={(e) => setSkillId(Number(e.target.value))}>
            <option value="" disabled>Pick a skill…</option>
            {(skills ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Hypothetical level: {level.toFixed(1)}</label>
          <input type="range" min={0} max={5} step={0.5} value={level}
            onChange={(e) => setLevel(Number(e.target.value))} className="w-56 accent-primary-800" />
        </div>
        <button className="btn-primary" disabled={!skillId || run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? "Simulating…" : "Run simulation"}
        </button>
      </div>

      {res && (
        <>
          {!!res.newly_eligible.length && (
            <div className="card border-primary-300 bg-primary-50 p-4">
              <div className="flex items-center gap-2 text-primary-900">
                <TrendingUp className="h-5 w-5" />
                <b>{res.newly_eligible.length} new role{res.newly_eligible.length > 1 ? "s" : ""} unlocked:</b>
                <span>{res.newly_eligible.join(" · ")}</span>
              </div>
            </div>
          )}

          <div className="card p-5">
            <h3 className="mb-3 font-semibold text-primary-950">
              Per-posting impact - average Δ {res.avg_delta > 0 ? "+" : ""}{res.avg_delta}%
            </h3>
            <div className="space-y-2">
              {res.results.map((r) => (
                <div key={r.opp_id} className="rounded-lg border border-stone-100 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <div>
                      <b>{r.title}</b> <span className="text-stone-400">· {r.company}</span>
                      {r.eligible_after && !r.eligible_before && <span className="badge-green ml-1">newly eligible</span>}
                    </div>
                    <div className="flex items-center gap-2 font-mono text-xs">
                      <span className="text-stone-400">{r.score_before}%</span>
                      <span>→</span>
                      <span className={r.delta > 0 ? "font-bold text-primary-800" : "text-stone-500"}>{r.score_after}%</span>
                      <span className={`w-14 text-right font-bold ${r.delta > 0 ? "text-primary-700" : "text-stone-400"}`}>
                        {r.delta > 0 ? "+" : ""}{r.delta}
                      </span>
                    </div>
                  </div>
                  {/* animated before/after bar */}
                  <div className="mt-2 h-2 rounded-full bg-stone-100">
                    <div className="h-2 rounded-full bg-stone-300 transition-all duration-700" style={{ width: `${r.score_before}%` }} />
                  </div>
                  <div className="mt-1 h-2 rounded-full bg-stone-100">
                    <div className="h-2 rounded-full bg-primary-700 transition-all duration-700" style={{ width: `${r.score_after}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
