"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { ClipboardCheck } from "lucide-react";
import { api } from "@/lib/api";

type Episode = {
  id: number; employment_type: string; role_title: string; company: string | null;
  district: string | null; start_date: string; end_date: string | null;
  status: string; source: string; validation_status: string;
  monthly_wage_start: number | null; monthly_wage_current: number | null;
  wage_series: { month_index: number; monthly_wage: number }[];
};
type Outcomes = {
  episodes: Episode[];
  programmes: { cohort_id: number; batch_code: string; programme: string; sector: string; status: string; completed_at: string | null }[];
  next_followup: { attempt_id: number; wave_id: number; kind: string; milestone_months: number | null } | null;
};

const BANDS = ["<10k", "10-15k", "15-20k", "20-30k", "30k+"];
const RESPONSES = [
  { key: "wage", label: "Wage job", icon: "💼" },
  { key: "self_employed", label: "Self-employed", icon: "🧑‍🔧" },
  { key: "apprenticeship", label: "Apprenticeship", icon: "🛠️" },
  { key: "higher_study", label: "Higher study", icon: "🎓" },
  { key: "unemployed", label: "Unemployed", icon: "🔍" },
];

export default function OutcomeLedgerPage() {
  const [responding, setResponding] = useState(false);
  const [form, setForm] = useState<{ response: string; band_idx: number; role_title: string }>({ response: "", band_idx: 2, role_title: "" });
  const [msg, setMsg] = useState("");
  const { data, refetch } = useQuery({
    queryKey: ["me-outcomes"],
    queryFn: () => api<Outcomes>("/me/outcomes"),
    refetchInterval: 12_000,
  });

  async function submitOneTap() {
    if (!data?.next_followup || !form.response) return;
    setMsg("Submitting…");
    try {
      await api(`/me/followups/${data.next_followup.wave_id}/respond`, {
        method: "POST",
        body: { response: form.response, band_idx: form.band_idx, role_title: form.role_title },
      });
      setMsg("Thank you! Your outcome is recorded - it feeds the department's honest numbers (only in consented, anonymised aggregates).");
      setResponding(false);
      refetch();
    } catch (e: any) {
      setMsg(e.message || "Failed to submit");
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <ClipboardCheck className="h-7 w-7 text-primary-800" />
        <div>
          <h1 className="text-2xl font-bold text-primary-950">My Outcome Ledger</h1>
          <p className="text-sm text-stone-500">Your verified journey - employment episodes, wages, and check-ins over time.</p>
        </div>
      </div>

      {/* One-tap follow-up card */}
      {data?.next_followup && (
        <div className="rounded-xl border border-saffron-300 bg-saffron-50 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold text-primary-950">👋 Quick check-in requested</h3>
              <p className="text-sm text-stone-600">
                {data.next_followup.kind === "adhoc" ? "A follow-up wave" : `Your ${data.next_followup.milestone_months}-month milestone`} asks:
                where are you working now? Takes ~20 seconds.
              </p>
            </div>
            <button className="btn-primary" onClick={() => { setResponding(true); setMsg(""); }}>
              Report in one tap
            </button>
          </div>
        </div>
      )}
      {msg && <div className="rounded-lg bg-primary-50 px-4 py-3 text-sm text-primary-900">{msg}</div>}

      {/* Wage curve across all episodes */}
      {(() => {
        const series = (data?.episodes ?? []).flatMap((e) => e.wage_series);
        if (!series.length) return null;
        const chart = series.map((w) => ({ m: `M${w.month_index}`, wage: w.monthly_wage }));
        return (
          <div className="card p-5">
            <h3 className="font-semibold text-primary-950">My wage progression</h3>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={chart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="m" fontSize={12} />
                <YAxis fontSize={12} />
                <Tooltip formatter={(v: number) => [`₹${v.toLocaleString()}`, "monthly wage"]} />
                <Line type="monotone" dataKey="wage" stroke="#1E3A8A" strokeWidth={2.5} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        );
      })()}

      {/* Episodes timeline */}
      <div className="card p-5">
        <h3 className="mb-4 font-semibold text-primary-950">Employment episodes</h3>
        {!data?.episodes?.length && (
          <div className="text-sm text-stone-400">
            No episodes yet. Report your first one when a follow-up arrives - it unlocks your verified work history.
          </div>
        )}
        <div className="space-y-3">
          {data?.episodes?.map((e) => (
            <div key={e.id} className="rounded-xl border border-stone-200 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-lg">{typeIcon(e.employment_type)}</span>
                <b className="text-primary-950">{e.role_title || typeLabel(e.employment_type)}</b>
                {e.company && <span className="text-sm text-stone-500">· {e.company}</span>}
                {e.district && <span className="badge-gray">{e.district}</span>}
                <span className={`badge-${e.status === "active" ? "green" : "gray"} ml-auto`}>{e.status}</span>
              </div>
              <div className="mt-2 text-sm text-stone-500">
                {e.start_date} → {e.end_date ?? "present"}
                {e.monthly_wage_start != null && <> · ₹{e.monthly_wage_start.toLocaleString()}{e.monthly_wage_current && e.monthly_wage_current !== e.monthly_wage_start ? ` → ₹${e.monthly_wage_current.toLocaleString()}` : ""} / month</>}
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                <span className="badge-gray">source: {e.source.replace(/_/g, " ")}</span>
                <span className={`badge-${valTone(e.validation_status)}`}>{valLabel(e.validation_status)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Programmes */}
      <div className="card p-5">
        <h3 className="mb-3 font-semibold text-primary-950">My skilling programmes</h3>
        {!data?.programmes?.length && <div className="text-sm text-stone-400">Not enrolled in any cohort yet.</div>}
        <div className="space-y-2">
          {data?.programmes?.map((p, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg border border-stone-200 px-3 py-2 text-sm">
              <div>
                <b>{p.programme}</b> <span className="badge-gray ml-1">{p.sector}</span>
                <div className="text-xs text-stone-400">batch {p.batch_code}</div>
              </div>
              <span className={`badge-${p.status === "completed" ? "green" : "gray"}`}>{p.status}</span>
            </div>
          ))}
        </div>
      </div>

      {/* One-tap modal */}
      {responding && data?.next_followup && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={() => setResponding(false)}>
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl" onClick={(ev) => ev.stopPropagation()}>
            <h3 className="text-lg font-bold text-primary-950">Where are you working now?</h3>
            <p className="mb-4 text-xs text-stone-500">One tap. Your answer updates the Outcome Ledger and counts toward honest programme rankings (in consented aggregates only).</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {RESPONSES.map((r) => (
                <button key={r.key}
                  onClick={() => setForm({ ...form, response: r.key })}
                  className={`rounded-xl border px-3 py-4 text-center text-sm font-medium ${form.response === r.key ? "border-primary-700 bg-primary-700 text-white" : "border-stone-200 text-stone-700 hover:bg-stone-50"}`}>
                  <div className="text-2xl">{r.icon}</div>
                  {r.label}
                </button>
              ))}
            </div>
            {form.response === "wage" && (
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="label">Wage band (₹/month)</label>
                  <select className="input" value={form.band_idx} onChange={(e) => setForm({ ...form, band_idx: Number(e.target.value) })}>
                    {BANDS.map((b, i) => <option key={b} value={i}>{b}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label">Role title</label>
                  <input className="input" value={form.role_title} placeholder="e.g. Solar PV Installer"
                    onChange={(e) => setForm({ ...form, role_title: e.target.value })} />
                </div>
              </div>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setResponding(false)}>Cancel</button>
              <button className="btn-primary" disabled={!form.response} onClick={submitOneTap}>
                Submit - takes one tap
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function typeIcon(t: string) {
  return { wage: "💼", self_employed: "🧑‍🔧", apprenticeship: "🛠️", higher_study: "🎓", unemployed: "🔍" }[t] ?? "📋";
}
function typeLabel(t: string) {
  return t.replace(/_/g, " ");
}
function valTone(s: string) {
  return s === "validated" ? "green" : s === "disputed" ? "amber" : "gray";
}
function valLabel(s: string) {
  return s === "validated" ? "✓ employer validated" : s === "pending" ? "validation requested" : s === "disputed" ? "disputed" : "unvalidated";
}
