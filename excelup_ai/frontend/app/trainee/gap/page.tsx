"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Map } from "lucide-react";
import { api } from "@/lib/api";

type GapRow = {
  skill: string; required: number; user_level: number; user_ceiling: number;
  essential: boolean; gap: number; verified: boolean; bridge_courses: string[];
};

const ROLES = [
  "Pharma QC Analyst", "Clinical Research Associate", "Panchakarma Therapist",
  "Wellness Center Manager", "Ayurveda Formulation Scientist",
  "Regulatory Affairs Executive", "Research Associate", "Wellness Entrepreneur",
];

export default function GapPage() {
  const [role, setRole] = useState("Pharma QC Analyst");
  const { data, isLoading } = useQuery({
    queryKey: ["gap", role],
    queryFn: () => api<{ role: string; requirements: GapRow[] }>(`/me/skill-gap/${encodeURIComponent(role)}`),
  });

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <Map className="h-6 w-6" /> Skill Gap Report
        </h1>
        <p className="text-sm text-stone-500">Pick any role genome - see exactly where you stand and how to bridge it.</p>
      </div>

      <div className="card p-5">
        <label className="label">Target role</label>
        <select className="input max-w-md" value={role} onChange={(e) => setRole(e.target.value)}>
          {ROLES.map((r) => <option key={r}>{r}</option>)}
        </select>
      </div>

      {isLoading && <div className="card p-8 text-center text-stone-400">Computing gaps…</div>}
      {data && (
        <div className="card p-5">
          <h3 className="mb-3 font-semibold text-primary-950">
            You vs <span className="text-saffron-600">{data.role}</span>
          </h3>
          <div className="space-y-2">
            {data.requirements.map((g) => (
              <div key={g.skill} className="rounded-lg border border-stone-100 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <div>
                    <b>{g.skill}</b> {g.essential && <span className="badge-amber">essential</span>}
                    {!g.verified && g.user_level > 0 && <span className="badge-gray">unverified</span>}
                  </div>
                  <div className="text-xs">
                    <span className="text-stone-400">you </span>
                    <b className={g.gap > 0 ? "text-saffron-600" : "text-primary-800"}>{g.user_level}</b>
                    <span className="text-stone-400"> / {g.required}</span>
                    {g.gap > 0 && <span className="badge-red ml-2">gap {g.gap}</span>}
                    {g.gap <= 0 && <span className="badge-green ml-2">met</span>}
                  </div>
                </div>
                {/* gap bar */}
                <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-stone-100">
                  <div className="h-2 bg-primary-700" style={{ width: `${Math.min(100, (g.user_level / g.required) * 100)}%` }} />
                </div>
                {!!g.bridge_courses.length && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-stone-500">
                    <span>Bridge plan:</span>
                    {g.bridge_courses.map((c) => (
                      <span key={c} className="rounded-full bg-primary-50 px-2 py-0.5 text-primary-800">{c}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
