"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Eye, UserCheck } from "lucide-react";
import { api } from "@/lib/api";
import MatchExplanation, { type Explanation } from "@/components/MatchExplanation";
import SkillGenome, { type GenomeSkill } from "@/components/SkillGenome";

type Posting = { id: number; title: string; kind: string; location: string; status: string };
type Candidate = {
  application_id: number; anon_ref: string; revealed: boolean;
  genome: GenomeSkill[]; score: number; explanation: Explanation; pipeline_status: string;
  identity: { name: string; institution: string | null; headline: string | null } | null;
};

const STATUS_FLOW = ["applied", "viewed", "shortlisted", "interviewed", "offered", "accepted"];

export default function CompanyHome() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const [checked, setChecked] = useState<Set<number>>(new Set());

  const { data: postings } = useQuery({
    queryKey: ["my-postings"],
    queryFn: () => api<Posting[]>("/opportunities?kind=internship"),
    refetchInterval: 15_000,
  });

  const { data: pipeline } = useQuery({
    queryKey: ["pipeline"],
    queryFn: () => api<any[]>("/company/applications"),
    refetchInterval: 12_000,
  });

  const { data: cands, isLoading } = useQuery({
    queryKey: ["candidates", selected],
    queryFn: () => api<{ title: string; candidates: Candidate[] }>(`/company/candidates/${selected}`),
    enabled: selected !== null,
    refetchInterval: 15_000,
  });

  const shortlist = useMutation({
    mutationFn: (ids: number[]) => api("/company/shortlist", { method: "POST", body: { application_ids: ids } }),
    onSuccess: () => { setChecked(new Set()); qc.invalidateQueries(); },
  });

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api(`/company/applications/${id}/status`, { method: "POST", body: { status } }),
    onSuccess: () => qc.invalidateQueries(),
  });

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
            <Building2 className="h-6 w-6" /> Postings &amp; Blind Pipeline
          </h1>
          <p className="text-sm text-stone-500">Skills first. Names later - shortlisting reveals identity.</p>
        </div>
        <a className="btn-primary" href="/company/post">+ New posting</a>
      </div>

      <div className="card p-4">
        <label className="label">Select a posting to review candidates</label>
        <select className="input max-w-lg" value={selected ?? ""} onChange={(e) => setSelected(Number(e.target.value))}>
          <option value="" disabled>Choose…</option>
          {(postings ?? []).map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
        </select>
      </div>

      {selected !== null && (
        <div className="card p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold text-primary-950">
              {cands?.title} - candidates <span className="text-stone-400">({cands?.candidates.length ?? 0})</span>
            </h3>
            <button className="btn-saffron" disabled={!checked.size || shortlist.isPending}
              onClick={() => shortlist.mutate([...checked])}>
              <UserCheck className="h-4 w-4" /> Shortlist &amp; reveal ({checked.size})
            </button>
          </div>
          {isLoading && <div className="py-8 text-center text-stone-400">Blinding genomes…</div>}
          <div className="grid gap-3 lg:grid-cols-2">
            {(cands?.candidates ?? []).map((c) => (
              <div key={c.application_id} className={`rounded-xl border p-4 ${c.revealed ? "border-primary-300 bg-primary-50/40" : "border-stone-200"}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <input type="checkbox" className="h-4 w-4 accent-primary-800"
                        checked={checked.has(c.application_id)}
                        onChange={(e) => {
                          const next = new Set(checked);
                          e.target.checked ? next.add(c.application_id) : next.delete(c.application_id);
                          setChecked(next);
                        }} />
                      <b>{c.anon_ref}</b>
                      {c.revealed && c.identity && (
                        <span className="badge-green">✓ {c.identity.name} · {c.identity.institution ?? "-"}</span>
                      )}
                    </div>
                    {c.revealed && c.identity?.headline && (
                      <div className="ml-6 text-xs text-stone-500">{c.identity.headline}</div>
                    )}
                  </div>
                  <div className="text-right">
                    <div className="text-xl font-bold text-primary-800">{c.score}%</div>
                    <div className="text-[10px] uppercase text-stone-400">match</div>
                  </div>
                </div>
                <div className="mt-2 flex justify-center">
                  <SkillGenome skills={c.genome} compact />
                </div>
                <details className="mt-1">
                  <summary className="cursor-pointer text-xs text-stone-400">Why this score</summary>
                  <div className="mt-2"><MatchExplanation explanation={c.explanation} /></div>
                </details>
                <div className="mt-2 flex items-center gap-1.5">
                  {STATUS_FLOW.map((st) => (
                    <button key={st}
                      onClick={() => setStatus.mutate({ id: c.application_id, status: st })}
                      className={`rounded px-1.5 py-0.5 text-[10px] capitalize ${
                        c.pipeline_status === st ? "bg-primary-800 text-white"
                          : c.revealed ? "bg-stone-100 text-stone-600 hover:bg-stone-200" : "bg-stone-50 text-stone-300"}`}>
                      {st}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card p-5">
        <h3 className="mb-3 font-semibold text-primary-950">Applicant pipeline (all postings)</h3>
        <div className="space-y-2">
          {(pipeline ?? []).slice(0, 15).map((a) => (
            <div key={a.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-stone-100 px-3 py-2 text-sm">
              <span><b>{a.candidate_name}</b> · {a.opp_title}</span>
              <span className="flex items-center gap-2">
                <span className="text-xs text-stone-400">score {a.score}</span>
                <span className={a.status === "accepted" ? "badge-green" : a.status === "rejected" ? "badge-red" : "badge-amber"}>{a.status}</span>
              </span>
            </div>
          ))}
          {!pipeline?.length && <div className="text-sm text-stone-400">No applications yet.</div>}
        </div>
      </div>
    </div>
  );
}
