"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SearchIcon } from "lucide-react";
import { api } from "@/lib/api";

type Opp = {
  id: number; kind: string; title: string; company: string; location: string;
  stipend: string; duration: string; description: string;
  requirements: { skill: string; min_level: number; essential: boolean }[];
};

const KINDS = ["", "job", "internship", "apprenticeship", "live_project"];

export default function SearchPage() {
  const qc = useQueryClient();
  const [kind, setKind] = useState("");
  const [location, setLocation] = useState("");
  const [minStipend, setMinStipend] = useState("");
  const [skill, setSkill] = useState("");

  const { data: results } = useQuery({
    queryKey: ["search", kind, location, minStipend, skill],
    queryFn: () =>
      api<Opp[]>(
        `/opportunities?${new URLSearchParams({
          ...(kind && { kind }),
          ...(location && { location }),
          ...(minStipend && { min_stipend: minStipend }),
          ...(skill && { skill }),
        }).toString()}`
      ),
    refetchInterval: 20_000,
  });

  const apply = useMutation({
    mutationFn: (id: number) => api(`/opportunities/${id}/apply`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries(),
  });

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <SearchIcon className="h-6 w-6" /> Search Jobs &amp; Internships
        </h1>
      </div>

      <div className="card grid grid-cols-2 gap-3 p-4 md:grid-cols-5">
        <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => <option key={k} value={k}>{k ? k.replace("_", " ") : "All kinds"}</option>)}
        </select>
        <input className="input" placeholder="Location" value={location} onChange={(e) => setLocation(e.target.value)} />
        <input className="input" placeholder="Min stipend (e.g. 15000)" value={minStipend} onChange={(e) => setMinStipend(e.target.value)} />
        <input className="input" placeholder="Skill (e.g. HPTLC)" value={skill} onChange={(e) => setSkill(e.target.value)} />
        <div className="text-right text-xs text-stone-400 md:col-span-1 self-center">
          {results?.length ?? 0} postings
        </div>
      </div>

      <div className="space-y-3">
        {(results ?? []).map((o) => (
          <div key={o.id} className="card flex flex-wrap items-center justify-between gap-3 p-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="badge-gray">{o.kind.replace("_", " ")}</span>
                <b className="text-primary-950">{o.title}</b>
              </div>
              <div className="text-sm text-stone-500">{o.company} · {o.location} {o.stipend && `· ${o.stipend}`}</div>
              <div className="mt-1 flex flex-wrap gap-1">
                {(o.requirements ?? []).slice(0, 5).map((r) => (
                  <span key={r.skill} className={`badge ${r.essential ? "badge-amber" : "badge-gray"}`}>
                    {r.skill} ≥ {r.min_level}{r.essential ? " ★" : ""}
                  </span>
                ))}
              </div>
            </div>
            <button className="btn-primary" onClick={() => apply.mutate(o.id)}>Apply</button>
          </div>
        ))}
        {!results?.length && <div className="card p-8 text-center text-stone-400">No postings match these filters.</div>}
      </div>
    </div>
  );
}
