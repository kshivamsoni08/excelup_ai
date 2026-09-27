"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Filter, MapPin, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import MatchExplanation, { type Explanation } from "@/components/MatchExplanation";

type FeedItem = {
  id: number;
  kind: string;
  title: string;
  company: string;
  location: string;
  stipend: string;
  duration: string;
  description: string;
  match: { score: number; eligible: boolean; explanation: Explanation };
  requirements: { skill: string; min_level: number; essential: boolean }[];
};

const KINDS = ["", "job", "internship", "apprenticeship", "live_project"];

export default function StudentHome() {
  const [kind, setKind] = useState("");
  const [openId, setOpenId] = useState<number | null>(null);
  const qc = useQueryClient();

  const { data: feed, isLoading } = useQuery({
    queryKey: ["feed", kind],
    queryFn: () => api<FeedItem[]>(`/feed`),
    refetchInterval: 15_000,
  });

  const apply = useMutation({
    mutationFn: (id: number) => api(`/opportunities/${id}/apply`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries(),
  });

  const items = useMemo(() => {
    let list = feed ?? [];
    if (kind) list = list.filter((f) => f.kind === kind);
    return list;
  }, [feed, kind]);

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-primary-950">Recommended for you</h1>
          <p className="text-sm text-stone-500">Ranked by your verified skill match - auto-refreshing.</p>
        </div>
        <select className="input w-44" value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => (
            <option key={k} value={k}>{k ? k.replace("_", " ") : "All kinds"}</option>
          ))}
        </select>
      </div>

      {isLoading && <div className="card p-8 text-center text-stone-400">Loading your matches…</div>}

      {items?.map((o) => (
        <div key={o.id} className="card p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="badge-gray">{o.kind.replace("_", " ")}</span>
                {!o.match.eligible && <span className="badge-amber">below eligibility bar</span>}
              </div>
              <h3 className="mt-1 font-semibold text-primary-950">{o.title}</h3>
              <div className="text-sm text-stone-500">{o.company} · <MapPin className="mb-0.5 inline h-3.5 w-3.5" /> {o.location} {o.stipend && `· ${o.stipend}`}</div>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <div className={`text-2xl font-bold ${o.match.score >= 60 ? "text-primary-800" : o.match.score >= 35 ? "text-saffron-600" : "text-stone-400"}`}>
                  {Math.round(o.match.score)}%
                </div>
                <div className="text-[10px] uppercase tracking-wide text-stone-400">match</div>
              </div>
              <div className="flex flex-col gap-1.5">
                <button className="btn-primary" onClick={() => apply.mutate(o.id)} disabled={apply.isPending}>
                  {apply.isPending ? "Applying…" : "One-click apply"}
                </button>
                <button className="btn-outline" onClick={() => setOpenId(openId === o.id ? null : o.id)}>
                  Why you matched
                </button>
              </div>
            </div>
          </div>

          {openId === o.id && (
            <div className="mt-4 rounded-xl border border-stone-100 bg-stone-50 p-4">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">
                Why You Matched - {Math.round(o.match.score)}%
              </div>
              <MatchExplanation explanation={o.match.explanation} />
            </div>
          )}
        </div>
      ))}

      {!isLoading && !items?.length && (
        <div className="card p-10 text-center text-stone-400">
          <Sparkles className="mx-auto mb-2 h-6 w-6" />
          No matches yet - take an adaptive test or scan your resume to build your genome.
        </div>
      )}
    </div>
  );
}
