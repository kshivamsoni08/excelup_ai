"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { BadgeCheck } from "lucide-react";
import { api } from "@/lib/api";

type Validation = {
  episode_id: number; trainee_ref: string; identity_revealed: boolean;
  trainee_name: string | null; role_title: string; start_date: string;
  source: string; validation_status: string; created_at: string;
};

const BANDS = ["<10k", "10-15k", "15-20k", "20-30k", "30k+"];

export default function ValidationsPage() {
  const [disputing, setDisputing] = useState<Validation | null>(null);
  const [disputeNote, setDisputeNote] = useState("");
  const { data, refetch } = useQuery({
    queryKey: ["employer-validations"],
    queryFn: () => api<Validation[]>("/employer/validations"),
    refetchInterval: 12_000,
  });

  async function confirm(v: Validation, bandIdx: number) {
    await api(`/employer/validations/${v.episode_id}`, {
      method: "POST",
      body: { decision: "confirm", wage_band: bandIdx },
    });
    refetch();
  }
  async function dispute() {
    if (!disputing) return;
    await api(`/employer/validations/${disputing.episode_id}`, {
      method: "POST",
      body: { decision: "dispute", role_title: disputeNote },
    });
    setDisputing(null);
    setDisputeNote("");
    refetch();
  }

  const queue = data ?? [];
  const validated = queue.filter((v) => v.validation_status === "validated").length;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <BadgeCheck className="h-7 w-7 text-primary-800" />
        <div>
          <h1 className="text-2xl font-bold text-primary-950">Validation Queue</h1>
          <p className="text-sm text-stone-500">Confirm the employment episodes your company hosted. Wage bands only - exact salaries are never shown or stored here.</p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Kpi label="Pending requests" value={String(queue.filter((v) => v.validation_status !== "validated").length)} tone="amber" />
        <Kpi label="Validated" value={String(validated)} tone="green" />
        <Kpi label="Validation rate (queue)" value={queue.length ? `${Math.round((100 * validated) / queue.length)}%` : "-"} />
      </div>

      <div className="space-y-3">
        {!queue.length && (
          <div className="card p-6 text-sm text-stone-400">
            Nothing to validate right now. When trainees report working with your company (or are placed via the platform), the request appears here.
          </div>
        )}
        {queue.map((v) => (
          <div key={v.episode_id} className="card p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="font-semibold text-primary-950">
                  {v.role_title} <span className="text-sm font-normal text-stone-400">· started {v.start_date}</span>
                </div>
                <div className="mt-0.5 text-xs text-stone-500">
                  Trainee <b>{v.identity_revealed ? v.trainee_name : v.trainee_ref}</b>
                  {" "}· reported via {v.source.replace(/_/g, " ")}
                </div>
              </div>
              {v.validation_status === "validated" ? (
                <span className="badge-green">✓ validated</span>
              ) : (
                <div className="flex items-center gap-2">
                  <BandPicker onPick={(i) => confirm(v, i)} />
                  <button className="btn-ghost text-red-600" onClick={() => setDisputing(v)}>Dispute</button>
                </div>
              )}
            </div>
            {v.validation_status === "disputed" && (
              <div className="mt-2 text-xs text-red-600">Disputed - the department may follow up with the trainee.</div>
            )}
          </div>
        ))}
      </div>

      {/* Dispute modal */}
      {disputing && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={() => setDisputing(null)}>
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-primary-950">Dispute episode</h3>
            <p className="mb-3 text-xs text-stone-500">{disputing.trainee_ref} · {disputing.role_title} · started {disputing.start_date}</p>
            <label className="label">Reason / note</label>
            <input className="input" value={disputeNote} onChange={(e) => setDisputeNote(e.target.value)}
              placeholder="e.g. no record of this employment" />
            <div className="mt-4 flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setDisputing(null)}>Cancel</button>
              <button className="btn-primary bg-red-600" onClick={dispute}>Mark disputed</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function BandPicker({ onPick }: { onPick: (idx: number) => void }) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return <button className="btn-primary" onClick={() => setOpen(true)}>Confirm</button>;
  }
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-stone-500">wage band:</span>
      {BANDS.map((b, i) => (
        <button key={b} onClick={() => { setOpen(false); onPick(i); }}
          className="rounded-lg border border-primary-200 bg-primary-50 px-2 py-1.5 text-xs font-medium text-primary-800 hover:bg-primary-100">
          {b}
        </button>
      ))}
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "green" | "amber" }) {
  return (
    <div className="card p-4">
      <div className={`text-2xl font-bold ${tone === "green" ? "text-primary-800" : tone === "amber" ? "text-saffron-600" : "text-primary-950"}`}>{value}</div>
      <div className="mt-1 text-xs uppercase tracking-wide text-stone-400">{label}</div>
    </div>
  );
}
