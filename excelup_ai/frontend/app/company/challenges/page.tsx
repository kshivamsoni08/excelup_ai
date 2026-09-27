"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trophy } from "lucide-react";
import { api } from "@/lib/api";

type Sub = {
  id: number; gauntlet_title: string; company: string; status: string;
  submission_url: string; writeup: string; candidate_ref: string; candidate_user_id: number;
};

export default function ChallengeReviewPage() {
  const qc = useQueryClient();
  const { data: subs } = useQuery({
    queryKey: ["review-queue"],
    queryFn: () => api<Sub[]>("/company/gauntlet-submissions"),
    refetchInterval: 12_000,
  });

  const review = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: string }) =>
      api(`/company/gauntlet-submissions/${id}/review`, { method: "POST", body: { decision, notes: decision === "approve" ? "Meets rubric" : "Below rubric" } }),
    onSuccess: () => qc.invalidateQueries(),
  });

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <Trophy className="h-6 w-6 text-saffron-500" /> Skill Challenge Review
        </h1>
        <p className="text-sm text-stone-500">Approve → certificate minted & signed, candidate genome updated live.</p>
      </div>

      <div className="space-y-3">
        {(subs ?? []).map((s) => (
          <div key={s.id} className="card p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="badge-gray">{s.candidate_ref}</span>
                  <b className="text-primary-950">{s.gauntlet_title}</b>
                </div>
                <div className="mt-1 text-sm text-stone-600">{s.writeup}</div>
                <a href={s.submission_url} target="_blank" className="text-xs text-primary-700 underline">{s.submission_url}</a>
              </div>
              <div className="flex flex-col items-end gap-2">
                <span className={s.status === "approved" ? "badge-green" : s.status === "rejected" ? "badge-red" : "badge-amber"}>{s.status}</span>
                {s.status === "submitted" || s.status === "under_review" ? (
                  <div className="flex gap-2">
                    <button className="btn-primary" onClick={() => review.mutate({ id: s.id, decision: "approve" })}>Approve &amp; mint</button>
                    <button className="btn-outline" onClick={() => review.mutate({ id: s.id, decision: "reject" })}>Reject</button>
                  </div>
                ) : (
                  <span className="text-xs text-stone-400">reviewed</span>
                )}
              </div>
            </div>
          </div>
        ))}
        {!subs?.length && <div className="card p-8 text-center text-stone-400">Queue empty.</div>}
      </div>
    </div>
  );
}
