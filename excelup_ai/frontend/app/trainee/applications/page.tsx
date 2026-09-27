"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sparkles, X } from "lucide-react";
import { api } from "@/lib/api";

type AppItem = {
  id: number; opp_id?: number; status: string; score: number; feedback: any;
  opportunity: { id: number; title: string; company: string; kind: string; location: string } | null;
  events: { type: string; ts: string }[];
};

const FLOW = ["applied", "viewed", "shortlisted", "interviewed", "offered", "accepted"];

export default function ApplicationsPage() {
  const [modal, setModal] = useState<AppItem | null>(null);
  const { data: apps } = useQuery({
    queryKey: ["my-applications"],
    queryFn: () => api<AppItem[]>("/me/applications"),
    refetchInterval: 10_000,
  });

  const stageIdx = (s: string) => (s === "rejected" ? -1 : FLOW.indexOf(s));

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <Sparkles className="h-6 w-6" /> My Applications
        </h1>
        <p className="text-sm text-stone-500">Live status timelines, rendered from the audit-trail events.</p>
      </div>

      <div className="space-y-4">
        {(apps ?? []).map((a) => (
          <div key={a.id} className="card p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <b className="text-primary-950">{a.opportunity?.title ?? `Posting #${a.opp_id}`}</b>
                <div className="text-sm text-stone-500">{a.opportunity?.company} · {a.opportunity?.location}</div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`badge ${a.status === "rejected" ? "badge-red" : stageIdx(a.status) >= 4 ? "badge-green" : "badge-amber"}`}>
                  {a.status}
                </span>
                {a.status === "rejected" && (
                  <button className="btn-outline" onClick={() => setModal(a)}>Why rejected?</button>
                )}
              </div>
            </div>

            {/* stepper */}
            <div className="mt-4 flex items-center">
              {FLOW.map((step, i) => {
                const reached = stageIdx(a.status) >= i && a.status !== "rejected";
                return (
                  <div key={step} className="flex flex-1 items-center last:flex-none">
                    <div className="flex flex-col items-center">
                      <div className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold ${
                        reached ? "bg-primary-800 text-white" : "bg-stone-200 text-stone-500"}`}>
                        {i + 1}
                      </div>
                      <span className="mt-1 text-[10px] capitalize text-stone-500">{step}</span>
                    </div>
                    {i < FLOW.length - 1 && (
                      <div className={`mx-1 h-0.5 flex-1 ${reached ? "bg-primary-700" : "bg-stone-200"}`} />
                    )}
                  </div>
                );
              })}
            </div>

            <div className="mt-3 text-xs text-stone-400">
              {a.events.length} events · last update {new Date(a.events[a.events.length - 1]?.ts ?? a.events[0]?.ts ?? Date.now()).toLocaleString()}
            </div>
          </div>
        ))}
        {!apps?.length && (
          <div className="card p-10 text-center text-stone-400">No applications yet - apply from your feed.</div>
        )}
      </div>

      {modal && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={() => setModal(null)}>
          <div className="card w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-semibold text-primary-950">Improvement feedback</h3>
                <p className="text-xs text-stone-400">Auto-filled from the match engine - the skill that decided it.</p>
              </div>
              <button className="btn-ghost px-2" onClick={() => setModal(null)}><X className="h-4 w-4" /></button>
            </div>
            {modal.feedback ? (
              <div className="mt-4 space-y-3 text-sm">
                <div className="rounded-lg bg-red-50 p-3 text-red-800">{modal.feedback.headline}</div>
                {modal.feedback.deciding_skill && (
                  <div className="text-stone-600">
                    <b>{modal.feedback.deciding_skill.skill}</b>: you at {modal.feedback.deciding_skill.user_level} vs {modal.feedback.deciding_skill.required} required.
                  </div>
                )}
                <div>
                  <b className="text-stone-700">Here are 2 bridges:</b>
                  <ul className="mt-1 list-inside list-disc text-stone-600">
                    {(modal.feedback.bridges ?? []).slice(0, 2).map((b: string, i: number) => <li key={i}>{b}</li>)}
                  </ul>
                </div>
              </div>
            ) : (
              <p className="mt-4 text-sm text-stone-500">No structured feedback stored for this decision.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
