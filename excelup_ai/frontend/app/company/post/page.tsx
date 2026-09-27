"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Settings } from "lucide-react";
import { api } from "@/lib/api";

type Skill = { id: number; name: string; domain: string };
type Req = { skill_id: number; name: string; min_level: number; weight: number; essential: boolean };

const KINDS = ["job", "internship", "apprenticeship", "live_project", "gauntlet"];

export default function PostingBuilder() {
  const [kind, setKind] = useState("internship");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [location, setLocation] = useState("");
  const [stipend, setStipend] = useState("");
  const [duration, setDuration] = useState("6 months");
  const [reqs, setReqs] = useState<Req[]>([]);
  const [q, setQ] = useState("");
  const [posted, setPosted] = useState<number | null>(null);

  const { data: skills } = useQuery({
    queryKey: ["skills-all"],
    queryFn: () => api<Skill[]>("/skills?limit=250"),
  });

  const suggestions = useMemo(() => {
    if (!q.trim()) return [];
    const low = q.toLowerCase();
    return (skills ?? []).filter((s) => s.name.toLowerCase().includes(low)).slice(0, 6);
  }, [q, skills]);

  const create = useMutation({
    mutationFn: () =>
      api("/opportunities", {
        method: "POST",
        body: {
          kind, title, description, location, stipend, duration,
          requirements: reqs.map(({ skill_id, min_level, weight, essential }) =>
            ({ skill_id, min_level, weight, essential })),
        },
      }),
    onSuccess: (r: any) => { setPosted(r.id); setReqs([]); setTitle(""); },
  });

  const addSkill = (s: Skill) => {
    if (reqs.some((r) => r.skill_id === s.id)) return;
    setReqs([...reqs, { skill_id: s.id, name: s.name, min_level: 3.5, weight: 2, essential: reqs.length === 0 }]);
    setQ("");
  };

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <Settings className="h-6 w-6" /> Posting Builder
        </h1>
        <p className="text-sm text-stone-500">Define the requirement genome - the engine matches against it exactly.</p>
      </div>

      <div className="card grid gap-4 p-6 md:grid-cols-2">
        <div>
          <label className="label">Kind</label>
          <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => <option key={k} value={k}>{k.replace("_", " ")}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Title</label>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. QC Analyst - Herbal QC" />
        </div>
        <div className="md:col-span-2">
          <label className="label">Description</label>
          <textarea className="input min-h-20" value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div><label className="label">Location</label><input className="input" value={location} onChange={(e) => setLocation(e.target.value)} /></div>
        <div><label className="label">Stipend / salary</label><input className="input" value={stipend} onChange={(e) => setStipend(e.target.value)} placeholder="₹20,000/month" /></div>
        <div className="md:col-span-2"><label className="label">Duration</label><input className="input" value={duration} onChange={(e) => setDuration(e.target.value)} /></div>

        <div className="md:col-span-2">
          <label className="label">Requirement genome - pick skills from the taxonomy</label>
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type to autocomplete (e.g. HPTLC)…" />
          {!!suggestions.length && (
            <div className="mt-1 rounded-lg border border-stone-200 bg-white shadow-lg">
              {suggestions.map((s) => (
                <button key={s.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-primary-50"
                  onClick={() => addSkill(s)}>
                  {s.name} <span className="text-xs text-stone-400">· {s.domain}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {reqs.map((r, i) => (
          <div key={r.skill_id} className="rounded-xl border border-stone-200 p-3 md:col-span-2">
            <div className="flex items-center justify-between">
              <b className="text-sm text-primary-950">{r.name}</b>
              <button className="text-xs text-red-500 hover:underline"
                onClick={() => setReqs(reqs.filter((_, j) => j !== i))}>remove</button>
            </div>
            <div className="mt-2 grid gap-3 md:grid-cols-3">
              <div>
                <label className="label">Min level: {r.min_level.toFixed(1)}</label>
                <input type="range" min={0} max={5} step={0.5} value={r.min_level}
                  className="w-full accent-primary-800"
                  onChange={(e) => {
                    const next = [...reqs]; next[i] = { ...r, min_level: Number(e.target.value) };
                    setReqs(next);
                  }} />
              </div>
              <div>
                <label className="label">Weight: {r.weight.toFixed(1)}</label>
                <input type="range" min={0.5} max={3} step={0.5} value={r.weight}
                  className="w-full accent-saffron-500"
                  onChange={(e) => {
                    const next = [...reqs]; next[i] = { ...r, weight: Number(e.target.value) };
                    setReqs(next);
                  }} />
              </div>
              <label className="flex items-center gap-2 self-end text-sm">
                <input type="checkbox" className="h-4 w-4 accent-primary-800" checked={r.essential}
                  onChange={(e) => {
                    const next = [...reqs]; next[i] = { ...r, essential: e.target.checked };
                    setReqs(next);
                  }} />
                Essential (eligibility gate)
              </label>
            </div>
          </div>
        ))}

        <div className="md:col-span-2 flex items-center gap-3">
          <button className="btn-primary" disabled={!title || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "Posting…" : "Publish posting"}
          </button>
          {posted && <span className="badge-green">✓ Posted as #{posted}</span>}
        </div>
      </div>

      {/* live preview */}
      <div className="card p-5">
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-stone-400">Live requirement genome preview</h3>
        {reqs.length ? (
          <div className="flex items-end justify-center gap-6 px-4 pt-4">
            {reqs.map((r) => {
              const h = Math.max(8, (r.min_level / 5) * 120);
              return (
                <div key={r.skill_id} className="flex flex-col items-center gap-1">
                  <div className={`w-14 rounded-t-md ${r.essential ? "bg-primary-800" : "bg-primary-400"}`}
                    style={{ height: h }} title={`min level ${r.min_level}`} />
                  <span className="max-w-20 truncate text-[10px] text-stone-500">{r.name}</span>
                  <span className="text-[10px] font-bold text-primary-900">{r.min_level}</span>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-stone-400">Add skills above to preview the requirement genome.</p>
        )}
      </div>
    </div>
  );
}
