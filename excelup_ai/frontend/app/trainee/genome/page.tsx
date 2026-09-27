"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import SkillGenome, { type GenomeSkill } from "@/components/SkillGenome";

type Notification = { id: number; type: string; payload: any; read: boolean };

export default function GenomePage() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["genome"],
    queryFn: () => api<{ skills: GenomeSkill[] }>("/me/genome"),
    refetchInterval: 12_000,
  });
  const { data: notifs } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<{ unread: number; items: Notification[] }>("/notifications"),
    refetchInterval: 10_000,
  });
  const { data: allSkills } = useQuery({
    queryKey: ["skills-all"],
    queryFn: () => api<{ id: number; name: string; domain: string }[]>("/skills?limit=250"),
  });

  const [pick, setPick] = useState("");
  const [domain, setDomain] = useState("");

  const declare = useMutation({
    mutationFn: (skill_ids: number[]) =>
      api("/me/declared-skills", { method: "POST", body: { skill_ids } }),
    onSuccess: () => {
      setPick("");
      qc.invalidateQueries();
    },
  });

  const domains = [...new Set((allSkills ?? []).map((s) => s.domain))];
  const filtered = (allSkills ?? []).filter((s) => !domain || s.domain === domain);
  const heldIds = new Set((data?.skills ?? []).map((s) => s.skill_id));
  const decayAlerts = (notifs?.items ?? []).filter((n) => n.type === "decay_alert");

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-primary-950">My Skill Genome</h1>
        <p className="text-sm text-stone-500">
          Solid arc = verified floor (what recruiters see). Faint arc = potential ceiling. Dim = fading.
        </p>
      </div>

      {!!decayAlerts.length && (
        <div className="card border-saffron-300 bg-saffron-50 p-4">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-5 w-5 text-saffron-600" />
            <div className="text-sm">
              <b className="text-saffron-800">Skill freshness alert.</b>{" "}
              {decayAlerts.map((n, i) => (
                <span key={n.id}>
                  {i > 0 && " · "}
                  <b>{n.payload.skill}</b> has decayed to floor {n.payload.floor} but{" "}
                  <i>{n.payload.required_by}</i> needs {n.payload.min_level}.
                </span>
              ))}{" "}
              Take an adaptive test, complete a bridge course, or prove it in a challenge.
            </div>
          </div>
        </div>
      )}

      <div className="card grid gap-6 p-6 lg:grid-cols-[auto_1fr]">
        <SkillGenome skills={data?.skills ?? []} />
        <div>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-stone-400">Per-skill detail</h3>
          <div className="max-h-80 space-y-2 overflow-auto pr-1">
            {(data?.skills ?? []).map((s) => (
              <div key={s.skill_id} className={`rounded-lg border p-3 ${s.faded ? "border-dashed border-stone-300 opacity-70" : "border-stone-200"}`}>
                <div className="flex items-center justify-between">
                  <b className="text-sm text-stone-800">{s.name}</b>
                  {s.source === "declared" ? <span className="badge-gray">unverified</span> :
                    <span className="badge-green">✓ {s.source}</span>}
                </div>
                <div className="mt-1 grid grid-cols-3 gap-2 text-xs text-stone-500">
                  <span>floor <b className="text-primary-800">{s.verified_floor.toFixed(2)}</b></span>
                  <span>ceiling <b className="text-saffron-600">{s.potential_ceiling.toFixed(2)}</b></span>
                  <span>{s.months_stale < 1 ? "fresh" : `${s.months_stale.toFixed(0)} mo old`}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 border-t border-stone-100 pt-4">
            <h3 className="mb-2 text-sm font-semibold text-stone-700">Add my skills <span className="badge-gray">unverified chips</span></h3>
            <div className="flex flex-wrap gap-2">
              <select className="input w-44" value={domain} onChange={(e) => setDomain(e.target.value)}>
                <option value="">All domains</option>
                {domains.map((d) => <option key={d}>{d}</option>)}
              </select>
              <select className="input w-52" value={pick} onChange={(e) => setPick(e.target.value)}>
                <option value="">Pick a skill…</option>
                {filtered.filter((s) => !heldIds.has(s.id)).map((s) => (
                  <option key={s.id} value={s.id}>{s.name} ({s.domain})</option>
                ))}
              </select>
              <button className="btn-outline" disabled={!pick || declare.isPending}
                onClick={() => declare.mutate([Number(pick)])}>
                + Add as unverified
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
