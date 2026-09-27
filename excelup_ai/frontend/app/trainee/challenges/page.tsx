"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Trophy } from "lucide-react";
import { api } from "@/lib/api";

type Gauntlet = {
  id: number; title: string; company: string; description: string;
  rubric: any; duration: string;
  skills: { skill: string; min_level: number }[];
};

export default function ChallengesPage() {
  const { data: gauntlets } = useQuery({
    queryKey: ["gauntlets"],
    queryFn: () => api<Gauntlet[]>("/gauntlets"),
    refetchInterval: 15_000,
  });
  const { data: mine } = useQuery({
    queryKey: ["my-submissions"],
    queryFn: () => api<{ id: number; opp_id?: number; title?: string; status: string }[]>("/me/gauntlet-submissions"),
    refetchInterval: 10_000,
  });

  const [openId, setOpenId] = useState<number | null>(null);
  const [url, setUrl] = useState("");
  const [writeup, setWriteup] = useState("");
  const [done, setDone] = useState(false);

  async function submit(gid: number) {
    await api(`/gauntlets/${gid}/submit`, { method: "POST", body: { submission_url: url, writeup } });
    setUrl(""); setWriteup(""); setDone(true); setOpenId(null);
    setTimeout(() => setDone(false), 2500);
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <Trophy className="h-6 w-6 text-saffron-500" /> Industry Skill Challenges
        </h1>
        <p className="text-sm text-stone-500">Don't tell us you can do it. Show us. Approved challenges mint a company-verified certificate.</p>
      </div>

      {done && <div className="card border-primary-200 bg-primary-50 p-3 text-sm text-primary-900">Submitted! The company reviews it in their queue - you'll get a notification.</div>}

      <div className="grid gap-4">
        {(gauntlets ?? []).map((g) => (
          <div key={g.id} className="card p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="badge-amber">Skill Challenge</div>
                <h3 className="mt-1 font-semibold text-primary-950">{g.title}</h3>
                <div className="text-sm text-stone-500">{g.company} · {g.duration}</div>
                <p className="mt-2 text-sm text-stone-600">{g.description}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {(g.skills ?? []).map((s) => (
                    <span key={s.skill} className="badge-gray">{s.skill} ≥ {s.min_level}</span>
                  ))}
                </div>
              </div>
              <button className="btn-saffron shrink-0" onClick={() => setOpenId(openId === g.id ? null : g.id)}>
                Submit your work
              </button>
            </div>

            {g.rubric?.criteria && (
              <div className="mt-3 rounded-lg bg-stone-50 p-3 text-xs text-stone-600">
                <b>Rubric:</b>{" "}
                {g.rubric.criteria.map((c: any) => `${c.name} (${Math.round(c.weight * 100)}%)`).join(" · ")}
              </div>
            )}

            {openId === g.id && (
              <div className="mt-4 space-y-3 rounded-xl border border-stone-200 p-4">
                <div>
                  <label className="label">Submission link (Drive / GitHub / notebook PDF)</label>
                  <input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
                </div>
                <div>
                  <label className="label">Writeup - your approach &amp; findings</label>
                  <textarea className="input min-h-24" value={writeup} onChange={(e) => setWriteup(e.target.value)} />
                </div>
                <button className="btn-primary" disabled={!url || !writeup} onClick={() => submit(g.id)}>
                  Submit for review
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="card p-5">
        <h3 className="mb-3 font-semibold text-primary-950">My submissions</h3>
        <div className="space-y-2">
          {(mine ?? []).map((s) => (
            <div key={s.id} className="flex items-center justify-between rounded-lg border border-stone-100 px-3 py-2 text-sm">
              <span>{s.title ?? `Challenge #${s.opp_id}`}</span>
              <span className={s.status === "approved" ? "badge-green" : s.status === "rejected" ? "badge-red" : "badge-amber"}>
                {s.status}
                {s.status === "approved" && " · certificate minted"}
              </span>
            </div>
          ))}
          {!mine?.length && <div className="text-sm text-stone-400">No submissions yet.</div>}
        </div>
      </div>
    </div>
  );
}
