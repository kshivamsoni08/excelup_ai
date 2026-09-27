"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Shield } from "lucide-react";
import { api } from "@/lib/api";

type Consent = {
  id: number; grantee_type: string; grantee_id: number | null; scopes: string[];
  purpose: string; granted_at: string; expires_at: string | null;
  revoked: boolean; revoked_at: string | null;
};

const SCOPES = [
  { key: "outcomes", desc: "Whether you are placed, in studies, or between jobs - counted in honest outcome statistics." },
  { key: "wage", desc: "Your wage band feeds median wage-growth curves. Never your exact salary, and never with your name." },
  { key: "demographics", desc: "Gender/category equity slices - suppressed whenever fewer than 5 trainees are in a cell." },
  { key: "skills", desc: "Your skill levels power anonymised skill-gap diagnostics that improve courses for everyone." },
];

const GRANTEES = [
  { key: "department", label: "Department of Skills (Govt. of Maharashtra)" },
  { key: "provider", label: "My training provider" },
  { key: "employer", label: "Employers (validation only)" },
];

export default function ConsentsPage() {
  const [granting, setGranting] = useState(false);
  const [form, setForm] = useState({ grantee_type: "department", scopes: ["outcomes", "wage", "demographics", "skills"] });
  const { data, refetch } = useQuery({
    queryKey: ["me-consents"],
    queryFn: () => api<Consent[]>("/me/consents"),
    refetchInterval: 12_000,
  });

  async function revoke(id: number) {
    await api(`/me/consents/${id}/revoke`, { method: "POST" });
    refetch();
  }
  async function grant() {
    await api("/me/consents", { method: "POST", body: { ...form, purpose: "Granted from consent manager" } });
    setGranting(false);
    refetch();
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Shield className="h-7 w-7 text-primary-800" />
        <div>
          <h1 className="text-2xl font-bold text-primary-950">Consent Manager</h1>
          <p className="text-sm text-stone-500">You choose what feeds the numbers. Revoking a scope removes you from those statistics on the next refresh - live.</p>
        </div>
        <button className="btn-primary ml-auto" onClick={() => setGranting(true)}>+ Grant consent</button>
      </div>

      <div className="rounded-xl border border-primary-200 bg-primary-50 px-4 py-3 text-sm text-primary-900">
        <b>Why consent matters here:</b> every officer/provider statistic shows its coverage ("n" and %). Analytics never show your name. Officers viewing your personal data get permanently logged in the PII audit trail.
      </div>

      <div className="space-y-3">
        {!data?.length && <div className="card p-5 text-sm text-stone-400">No consents yet - grant one to power honest analytics.</div>}
        {data?.map((c) => (
          <div key={c.id} className={`card p-4 ${c.revoked ? "opacity-60" : ""}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <b className="text-primary-950">{GRANTEES.find((g) => g.key === c.grantee_type)?.label ?? c.grantee_type}</b>
                <div className="text-xs text-stone-400">granted {new Date(c.granted_at).toLocaleDateString()} · {c.purpose}</div>
              </div>
              {c.revoked
                ? <span className="badge-gray">revoked {c.revoked_at ? new Date(c.revoked_at).toLocaleDateString() : ""}</span>
                : <button className="btn-ghost text-red-600" onClick={() => revoke(c.id)}>Revoke</button>}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {SCOPES.map((s) => {
                const on = (c.scopes ?? []).includes(s.key);
                return (
                  <span key={s.key} className={on ? "badge-green" : "badge-gray"}
                    title={s.desc}>
                    {on ? "✓" : "○"} {s.key}
                  </span>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Scope explanation card */}
      <div className="card p-5">
        <h3 className="mb-2 font-semibold text-primary-950">What each scope does</h3>
        <ul className="space-y-1.5 text-sm text-stone-600">
          {SCOPES.map((s) => (
            <li key={s.key}><b className="text-primary-900">{s.key}</b> - {s.desc}</li>
          ))}
        </ul>
      </div>

      {/* Grant modal */}
      {granting && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={() => setGranting(false)}>
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-primary-950">Grant consent</h3>
            <label className="label mt-3">Share with</label>
            <select className="input" value={form.grantee_type}
              onChange={(e) => setForm({ ...form, grantee_type: e.target.value })}>
              {GRANTEES.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}
            </select>
            <div className="mt-3 space-y-2">
              {SCOPES.map((s) => (
                <label key={s.key} className="flex cursor-pointer items-start gap-2 rounded-lg border border-stone-200 p-2.5 text-sm">
                  <input type="checkbox" className="mt-0.5" checked={form.scopes.includes(s.key)}
                    onChange={(e) => setForm({
                      ...form,
                      scopes: e.target.checked ? [...form.scopes, s.key] : form.scopes.filter((x) => x !== s.key),
                    })} />
                  <span><b>{s.key}</b> - <span className="text-stone-500">{s.desc}</span></span>
                </label>
              ))}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setGranting(false)}>Cancel</button>
              <button className="btn-primary" onClick={grant} disabled={!form.scopes.length}>Grant</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
