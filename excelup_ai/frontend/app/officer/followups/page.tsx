"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Eye, Users } from "lucide-react";
import { api } from "@/lib/api";

type Wave = {
  id: number; cohort_id: number; batch_code: string; milestone_months: number | null;
  kind: string; status: string; due_on: string;
  issued: number; responded: number; response_rate: number;
};
type NonResponder = {
  attempt_id: number; wave_id: number; user_id: number; name: string; email: string;
  attempted_at: string; days_waiting: number;
};
type CohortRow = { id: number; batch_code: string; programme: string; provider: string; status: string };

const RESPONSES = ["wage", "self_employed", "apprenticeship", "higher_study", "unemployed", "no_response"] as const;
const BANDS = ["<10k", "10-15k", "15-20k", "20-30k", "30k+"];

export default function FollowupsWorkbench() {
  const [openCard, setOpenCard] = useState<NonResponder | null>(null);
  const [form, setForm] = useState({ response: "wage", band_idx: 2, role_title: "", notes: "" });
  const [msg, setMsg] = useState("");
  const [waveMsg, setWaveMsg] = useState("");
  const { data, refetch } = useQuery({
    queryKey: ["officer-followups"],
    queryFn: () => api<{ waves: Wave[]; non_responders: NonResponder[]; cohorts: CohortRow[] }>("/officer/followups"),
    refetchInterval: 12_000,
  });

  async function recordAttempt() {
    if (!openCard) return;
    setMsg("Recording…");
    try {
      await api(`/officer/followup-attempts/${openCard.attempt_id}`, {
        method: "POST",
        body: form,
      });
      setMsg("Outcome recorded - PII_VIEWED logged to audit trail.");
      setOpenCard(null);
      refetch();
    } catch (e: any) {
      setMsg(e.message || "Failed to record");
    }
  }

  async function runWave(cohortId: number, batch: string) {
    setWaveMsg(`Triggering wave for ${batch}…`);
    try {
      const res = await api<{ wave_id: number }>("/officer/waves", { method: "POST", body: { cohort_id: cohortId } });
      setWaveMsg(`Wave #${res.wave_id} live for ${batch} - all completers notified in-app.`);
      refetch();
    } catch (e: any) {
      setWaveMsg(e.message || "Failed");
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Users className="h-7 w-7 text-primary-800" />
        <div>
          <h1 className="text-2xl font-bold text-primary-950">Assisted Follow-up Workbench</h1>
          <p className="text-sm text-stone-500">One-tap first; assisted follow-up only after 14 days of silence. Every trainee card open is PII-audited.</p>
        </div>
      </div>

      {/* Run ad-hoc wave */}
      <div className="card p-5">
        <h3 className="mb-2 font-semibold text-primary-950">Trigger an ad-hoc wave</h3>
        <p className="mb-3 text-xs text-stone-500">Pick a cohort - every completer gets an in-app one-tap follow-up instantly.</p>
        {waveMsg && <div className="mb-3 rounded-lg bg-primary-50 px-3 py-2 text-sm text-primary-900">{waveMsg}</div>}
        <div className="grid max-h-56 gap-2 overflow-y-auto md:grid-cols-2">
          {(data?.cohorts ?? []).map((c) => (
            <div key={c.id} className="flex items-center justify-between rounded-lg border border-stone-200 px-3 py-2 text-sm">
              <div>
                <b>{c.batch_code}</b> <span className="text-stone-400">· {c.programme} · {c.provider}</span>
              </div>
              <button className="btn-primary px-3 py-1.5 text-xs" onClick={() => runWave(c.id, c.batch_code)}>
                Run wave
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Waves */}
      <div className="card p-5">
        <h3 className="mb-3 font-semibold text-primary-950">Follow-up waves</h3>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="border-b border-stone-200 text-left text-xs uppercase tracking-wide text-stone-400">
              <tr>
                <th className="py-2">Wave</th><th className="py-2">Cohort</th><th className="py-2">Kind</th>
                <th className="py-2 text-right">Issued</th><th className="py-2 text-right">Responded</th>
                <th className="py-2 text-right">Response rate</th><th className="py-2">Due</th><th className="py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {(data?.waves ?? []).map((w) => (
                <tr key={w.id} className="border-b border-stone-100">
                  <td className="py-2 font-medium">#{w.id}</td>
                  <td className="py-2">{w.batch_code}</td>
                  <td className="py-2"><span className="badge-gray">{w.kind}</span></td>
                  <td className="py-2 text-right">{w.issued}</td>
                  <td className="py-2 text-right">{w.responded}</td>
                  <td className="py-2 text-right font-semibold text-primary-800">{Math.round(w.response_rate * 100)}%</td>
                  <td className="py-2 text-stone-500">{w.due_on}</td>
                  <td className="py-2">
                    <span className={`badge-${w.status === "active" ? "green" : "gray"}`}>{w.status}</span>
                  </td>
                </tr>
              ))}
              {!data?.waves?.length && <tr><td colSpan={8} className="py-3 text-sm text-stone-400">No waves yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Non-responders */}
      <div className="card p-5">
        <h3 className="mb-1 font-semibold text-primary-950">Non-responder queue (&gt;= 14 days)</h3>
        <p className="mb-3 text-xs text-stone-500">{data?.non_responders?.length ?? 0} trainees awaiting assisted follow-up. Opening a card logs a PII_VIEWED event.</p>
        {msg && <div className="mb-3 rounded-lg bg-primary-50 px-3 py-2 text-sm text-primary-900">{msg}</div>}
        <div className="grid gap-2 md:grid-cols-2">
          {(data?.non_responders ?? []).map((nr) => (
            <button key={nr.attempt_id}
              onClick={() => { setOpenCard(nr); setMsg(""); }}
              className="flex items-center justify-between rounded-lg border border-stone-200 px-3 py-2.5 text-left text-sm hover:border-primary-300">
              <div>
                <b>{nr.name}</b> <span className="text-stone-400">· {nr.email}</span>
                <div className="text-xs text-stone-400">waiting {nr.days_waiting} days</div>
              </div>
              <Eye className="h-4 w-4 text-stone-400" />
            </button>
          ))}
          {!data?.non_responders?.length && <div className="text-sm text-stone-400">Queue is clear.</div>}
        </div>
      </div>

      {/* Assisted record modal */}
      {openCard && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={() => setOpenCard(null)}>
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 rounded-lg border border-saffron-200 bg-saffron-50 px-3 py-2 text-xs font-medium text-saffron-800">
              ⚠ PII banner: you are viewing personal data for {openCard.name} - this access is being logged (officer audit trail).
            </div>
            <h3 className="text-lg font-bold text-primary-950">Record outcome - assisted</h3>
            <p className="mb-3 text-xs text-stone-500">{openCard.name} · {openCard.email} · waiting {openCard.days_waiting} days</p>
            <div className="grid grid-cols-3 gap-2">
              {RESPONSES.map((r) => (
                <button key={r} onClick={() => setForm({ ...form, response: r })}
                  className={`rounded-lg border px-2 py-2 text-xs font-medium capitalize ${form.response === r ? "border-primary-700 bg-primary-700 text-white" : "border-stone-200 text-stone-600 hover:bg-stone-50"}`}>
                  {r.replace(/_/g, " ")}
                </button>
              ))}
            </div>
            {form.response === "wage" && (
              <div className="mt-3">
                <label className="label">Wage band (₹ / month)</label>
                <select className="input" value={form.band_idx}
                  onChange={(e) => setForm({ ...form, band_idx: Number(e.target.value) })}>
                  {BANDS.map((b, i) => <option key={b} value={i}>{b}</option>)}
                </select>
                <label className="label mt-2">Role title</label>
                <input className="input" value={form.role_title} placeholder="e.g. Solar PV Installer"
                  onChange={(e) => setForm({ ...form, role_title: e.target.value })} />
              </div>
            )}
            <label className="label mt-3">Notes</label>
            <input className="input" value={form.notes} placeholder="officer notes (optional)"
              onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            <div className="mt-4 flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setOpenCard(null)}>Cancel</button>
              <button className="btn-primary" onClick={recordAttempt}>Save outcome</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
