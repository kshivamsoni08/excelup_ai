"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import { api } from "@/lib/api";

type FacOpp = {
  id: number; kind: string; title: string; company: string; description: string;
  location: string; stipend: string; duration: string; skills: string[];
};

export default function FacultyPage() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["faculty-opps"],
    queryFn: () => api<FacOpp[]>("/faculty/opportunities"),
    refetchInterval: 20_000,
  });

  const enroll = useMutation({
    mutationFn: (id: number) => api(`/faculty/opportunities/${id}/enroll`, { method: "POST", body: { note: "" } }),
    onSuccess: () => qc.invalidateQueries(),
  });

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <FlaskConical className="h-6 w-6" /> Industry Residency &amp; Programs
        </h1>
        <p className="text-sm text-stone-500">Residencies, industrial training, FDPs and consultancy - built for academia.</p>
      </div>
      <div className="space-y-3">
        {(data ?? []).map((o) => (
          <div key={o.id} className="card p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <span className="badge-amber">{o.kind.replace("_", " ")}</span>
                <h3 className="mt-1 font-semibold text-primary-950">{o.title}</h3>
                <div className="text-sm text-stone-500">{o.company} · {o.location} · {o.duration} {o.stipend && `· ${o.stipend}`}</div>
                <p className="mt-2 text-sm text-stone-600">{o.description}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {o.skills.map((s) => <span key={s} className="badge-gray">{s}</span>)}
                </div>
              </div>
              <button className="btn-primary" onClick={() => enroll.mutate(o.id)}>Enroll</button>
            </div>
          </div>
        ))}
        {!data?.length && <div className="card p-8 text-center text-stone-400">No faculty programs open right now.</div>}
      </div>
    </div>
  );
}
