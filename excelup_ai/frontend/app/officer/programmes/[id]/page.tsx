"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";

type Detail = {
  programme: { id: number; title: string; sector: string; provider: string; nsqf_level: number; duration_months: number };
  cohorts: { id: number; batch_code: string; end_date: string | null }[];
  completions: number;
  placement_0: number; placement_12: number; retention_12: number;
  wage_growth_12: number | null; wage_n: number;
  validation_rate: number; followup_rate: number;
  oqi: number; oqi_components: Record<string, number>; oqi_formula: string; flags: string[];
  decay_curve: { m: number; rate: number; n: number }[];
  wage_curve: { m: number; median: number | null; n: number }[];
  attrition_pareto: { code: string; label: string; count: number; share: number }[];
  demographics: { by_gender: Cell[]; by_category: Cell[] };
  skill_gaps: { non_placed: number; completers: number; top_missing: { skill: string; trainees_missing: number }[]; curriculum_updates: { skill: string; suggestion: string }[] };
  consent: { completers: number; consented: number; wage_consented: number; coverage_pct: number; wage_coverage_pct: number };
};

type Cell = { value: string; rate: number | null; n: number; suppressed: boolean };

export default function ProgrammeDrilldown() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [waveMsg, setWaveMsg] = useState("");
  const { data } = useQuery({
    queryKey: ["programme-detail", id],
    queryFn: () => api<Detail>(`/officer/programmes/${id}`),
    refetchInterval: 15_000,
  });
  const { data: cohortsData } = useQuery({
    queryKey: ["officer-cohorts"],
    queryFn: () => api<{ cohorts: { id: number; batch_code: string; programme: string; provider: string; status: string }[] }>("/officer/followups"),
  });

  const runWave = async (cohortId: number) => {
    setWaveMsg("Triggering…");
    try {
      const res = await api<{ wave_id: number }>(`/officer/waves`, { method: "POST", body: { cohort_id: cohortId } });
      setWaveMsg(`Wave #${res.wave_id} live - all completers notified in-app.`);
    } catch (e: any) {
      setWaveMsg(e.message || "Failed to trigger wave");
    }
  };

  if (!data) return <div className="text-sm text-stone-400">Loading programme…</div>;
  const p = data;

  return (
    <div className="space-y-6">
      {/* Header + OQI card */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-primary-950">{p.programme.title}</h1>
          <p className="text-sm text-stone-500">
            {p.programme.provider} · {p.programme.sector} · NSQF {p.programme.nsqf_level} · {p.programme.duration_months} months
            · {p.completions} completers
          </p>
          {p.flags.length > 0 && (
            <div className="mt-2 flex gap-2">
              {p.flags.map((f) => <span key={f} className="badge-amber">⚠ {f.replace(/_/g, " ")}</span>)}
            </div>
          )}
        </div>
        <div className="card w-full max-w-sm p-5">
          <div className="text-xs font-semibold uppercase tracking-wide text-stone-400">Outcome-Adjusted Quality Index</div>
          <div className="mt-1 text-4xl font-extrabold text-primary-800">{Math.round(p.oqi)}</div>
          <div className="mt-2 rounded-lg bg-stone-50 p-2 text-[11px] leading-snug text-stone-600">{p.oqi_formula}</div>
          <div className="mt-2 space-y-1 text-[11px] text-stone-500">
            <div>placement_12: {p.oqi_components.placement_12} · retention_12: {p.oqi_components.retention_12}</div>
            <div>wage: {p.oqi_components.wage_component} · validation: {p.oqi_components.validation} · followup: {p.oqi_components.followup}</div>
          </div>
        </div>
      </div>

      {/* Consent coverage banner */}
      <div className="rounded-xl border border-primary-200 bg-primary-50 px-4 py-3 text-sm text-primary-900">
        <ShieldCheck className="mr-1.5 inline h-4 w-4" />
        <b>Consent-first analytics:</b> outcomes use {p.consent.consented}/{p.consent.completers} completers ({p.consent.coverage_pct}% coverage)
        · wage stats: {p.consent.wage_consented}/{p.consent.completers} ({p.consent.wage_coverage_pct}%) · demographic cells with n&lt;5 are suppressed.
      </div>

      {/* KPI row */}
      <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Day 0" value={pct(p.placement_0)} tone="amber" />
        <Kpi label="12 months" value={pct(p.placement_12)} tone="green" />
        <Kpi label="Retention 12" value={pct(p.retention_12)} />
        <Kpi label="Wage growth" value={p.wage_growth_12 == null ? "-" : `+${Math.round(p.wage_growth_12 * 100)}%`} sub={`n=${p.wage_n}`} />
        <Kpi label="Validation" value={pct(p.validation_rate)} />
        <Kpi label="Follow-up" value={pct(p.followup_rate)} />
      </div>

      {/* Curves */}
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="card p-5">
          <h3 className="font-semibold text-primary-950">Placement decay curve</h3>
          <p className="mb-3 text-xs text-stone-500">Share of completers placed at month m after completion.</p>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={p.decay_curve.map((d) => ({ m: `+${d.m}mo`, pct: Math.round(d.rate * 100) }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="m" fontSize={12} />
              <YAxis domain={[0, 100]} fontSize={12} unit="%" />
              <Tooltip formatter={(v: number) => `${v}%`} />
              <Line type="monotone" dataKey="pct" stroke="#1E3A8A" strokeWidth={2.5} dot={{ r: 4 }} name="placed %" />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="card p-5">
          <h3 className="font-semibold text-primary-950">Median wage progression</h3>
          <p className="mb-3 text-xs text-stone-500">Wage-consented trainees only (n shown per point).</p>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={p.wage_curve.map((d) => ({ m: `+${d.m}mo`, inr: d.median ?? 0, n: d.n }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="m" fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip formatter={(v: number, _n, item) => [`₹${v.toLocaleString()} (n=${item?.payload?.n ?? "-"})`, "median wage"]} />
              <Line type="monotone" dataKey="inr" stroke="#D97706" strokeWidth={2.5} dot={{ r: 4 }} name="₹ / month" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Pareto + demographics */}
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="card p-5">
          <h3 className="font-semibold text-primary-950">Reasons for non-placement / attrition (Pareto)</h3>
          {!p.attrition_pareto.length && <div className="text-sm text-stone-400">No reason codes recorded.</div>}
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={p.attrition_pareto.map((d) => ({ name: d.label, count: d.count }))} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis type="number" fontSize={12} allowDecimals={false} />
              <YAxis type="category" dataKey="name" width={150} fontSize={11} />
              <Tooltip />
              <Bar dataKey="count" fill="#1E3A8A" radius={[0, 6, 6, 0]} name="trainees" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card p-5">
          <h3 className="font-semibold text-primary-950">Demographic equity (placement at 12 mo)</h3>
          <p className="mb-2 text-xs text-stone-500">Cells with fewer than 5 trainees render as suppressed - privacy by design.</p>
          <div className="space-y-3">
            <DemoRow title="Gender" cells={p.demographics.by_gender} />
            <DemoRow title="Social category" cells={p.demographics.by_category} />
          </div>
        </div>
      </div>

      {/* Skill gaps */}
      <div className="card p-5">
        <h3 className="font-semibold text-primary-950">Skill-gap diagnostics (non-placed completers)</h3>
        <p className="text-xs text-stone-500">
          The matching engine runs each non-placed trainee against live postings in their districts - near-miss skills are aggregated.
          {p.skill_gaps.non_placed > 0 && <> <b>{p.skill_gaps.non_placed}</b> non-placed of {p.skill_gaps.completers} completers.</>}
        </p>
        {!p.skill_gaps.top_missing.length && <div className="mt-2 text-sm text-stone-400">No non-placed completers - every graduate is employed. 🎉</div>}
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">Top missing proficiencies</div>
            {p.skill_gaps.top_missing.map((t) => (
              <div key={t.skill} className="mb-1.5 flex items-center justify-between rounded-lg bg-stone-50 px-3 py-2 text-sm">
                <span className="font-medium text-primary-900">{t.skill}</span>
                <span className="text-stone-500">{t.trainees_missing} trainees</span>
              </div>
            ))}
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">Suggested curriculum updates</div>
            {p.skill_gaps.curriculum_updates.map((t) => (
              <div key={t.skill} className="mb-1.5 rounded-lg border border-saffron-200 bg-saffron-50 px-3 py-2 text-sm text-stone-700">
                {t.suggestion}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Cohorts + run wave */}
      <div className="card p-5">
        <h3 className="font-semibold text-primary-950">Cohorts &amp; follow-up waves</h3>
        <p className="mb-3 text-xs text-stone-500">Run an ad-hoc wave: every completer gets an in-app one-tap follow-up instantly.</p>
        {waveMsg && <div className="mb-3 rounded-lg bg-primary-50 px-3 py-2 text-sm text-primary-900">{waveMsg}</div>}
        <div className="space-y-2">
          {p.cohorts.map((c) => (
            <div key={c.id} className="flex items-center justify-between rounded-lg border border-stone-200 px-3 py-2">
              <div className="text-sm">
                <b>{c.batch_code}</b> <span className="text-stone-400">· ended {c.end_date ?? "-"}</span>
              </div>
              <button className="btn-primary px-3 py-1.5 text-xs" onClick={() => runWave(c.id)}>
                Run follow-up wave
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function pct(x: number) {
  return `${Math.round(x * 100)}%`;
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "green" | "amber" }) {
  return (
    <div className="card p-3.5">
      <div className={`text-xl font-bold ${tone === "green" ? "text-primary-800" : tone === "amber" ? "text-saffron-600" : "text-primary-950"}`}>{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-stone-400">{label}</div>
      {sub && <div className="text-[10px] text-stone-400">{sub}</div>}
    </div>
  );
}

function DemoRow({ title, cells }: { title: string; cells: Cell[] }) {
  return (
    <div>
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-400">{title}</div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {cells.map((c) => (
          <div key={c.value} className={`rounded-lg px-3 py-2 text-sm ${c.suppressed ? "bg-stone-100 text-stone-400" : "bg-primary-50 text-primary-900"}`}>
            <div className="font-semibold">{c.value}</div>
            <div className="text-xs">{c.suppressed ? `suppressed (n=${c.n})` : `${Math.round((c.rate ?? 0) * 100)}% placed (n=${c.n})`}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
