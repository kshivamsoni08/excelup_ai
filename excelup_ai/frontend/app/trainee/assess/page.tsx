"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, CheckCircle2, XCircle } from "lucide-react";
import { api } from "@/lib/api";

type Served = {
  item_id: number; stem: string; options: string[];
  difficulty_b: number; difficulty_label: string; skill_type: string;
} | null;

type Session = {
  session_id: number; skill: string | null; theta: number; sem: number;
  answered_count: number; status: string; level_estimate: number; served: Served;
};

export default function AssessPage() {
  const qc = useQueryClient();
  const [skillId, setSkillId] = useState<number | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [lastCorrect, setLastCorrect] = useState<boolean | null>(null);
  const [result, setResult] = useState<Session | null>(null);

  const { data: skills } = useQuery({
    queryKey: ["skills-all"],
    queryFn: () => api<{ id: number; name: string }[]>("/skills?limit=250"),
  });

  const { data: sess } = useQuery({
    queryKey: ["assess", sessionId],
    queryFn: () => api<Session>(`/assess/${sessionId}`),
    enabled: sessionId !== null && result === null,
    refetchInterval: 10_000,
  });

  useEffect(() => {
    if (sess && sess.status === "completed" && !result) {
      setResult(sess);
      qc.invalidateQueries({ queryKey: ["genome"] });
    }
  }, [sess, result, qc]);

  async function start() {
    const s = await api<Session>(`/assess/start?skill_id=${skillId}`, { method: "POST" });
    setSessionId(s.session_id);
    setResult(null);
    setPicked(null);
    setLastCorrect(null);
    qc.setQueryData(["assess", s.session_id], s);
  }

  async function answer(choice: number) {
    if (!sess?.served) return;
    const chosen = choice;
    setPicked(chosen);
    const res = await api<Session>(`/assess/${sess.session_id}/answer`, {
      method: "POST",
      body: { item_id: sess.served.item_id, choice },
    });
    setLastCorrect(res.answered_count > (sess.answered_count ?? 0) ? null : null);
    setTimeout(async () => {
      setPicked(null);
      if (res.status === "completed") {
        setResult(res);
        qc.invalidateQueries({ queryKey: ["genome"] });
        qc.invalidateQueries({ queryKey: ["feed"] });
      } else {
        qc.setQueryData(["assess", res.session_id], res);
      }
    }, 450);
  }

  const current = result ?? sess;
  const frontierPct = current ? ((current.theta + 3) / 6) * 100 : 50;
  const bPct = current?.served ? ((current.served.difficulty_b + 3) / 6) * 100 : 50;

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <Brain className="h-6 w-6" /> Adaptive Skill Test
        </h1>
        <p className="text-sm text-stone-500">
          Questions home in on your frontier. Stop rule: standard error &lt; 0.30 or 10 items.
        </p>
      </div>

      {!current && (
        <div className="card p-6">
          <label className="label">Choose a skill with an item bank</label>
          <select className="input" value={skillId ?? ""} onChange={(e) => setSkillId(Number(e.target.value))}>
            <option value="" disabled>Pick a skill…</option>
            {(skills ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button className="btn-primary mt-4" disabled={!skillId} onClick={start}>Start test</button>
        </div>
      )}

      {current && (
        <>
          <div className="card p-5">
            <div className="flex items-center justify-between text-sm">
              <b className="text-primary-950">{current.skill}</b>
              <span className="badge-gray">item {current.answered_count}/10</span>
            </div>
            {/* live frontier indicator */}
            <div className="mt-3">
              <div className="mb-1 flex justify-between text-[11px] uppercase tracking-wide text-stone-400">
                <span>easy</span><span>serving at your frontier</span><span>hard</span>
              </div>
              <div className="relative h-3 rounded-full bg-gradient-to-r from-primary-200 via-primary-100 to-saffron-200">
                <div className="absolute -top-1 h-5 w-1 rounded bg-primary-900" style={{ left: `${frontierPct}%` }} title="your theta" />
                {current.served && (
                  <div className="absolute -top-1 h-5 w-1 rounded bg-saffron-500" style={{ left: `${bPct}%` }} title="current item difficulty" />
                )}
              </div>
              <div className="mt-1 flex justify-between text-xs text-stone-500">
                <span>θ = {current.theta.toFixed(2)}</span>
                {current.served && <span>this item: <b>{current.served.difficulty_label}</b> (b = {current.served.difficulty_b})</span>}
              </div>
            </div>
            {/* SEM countdown */}
            <div className="mt-3">
              <div className="mb-1 flex justify-between text-[11px] uppercase tracking-wide text-stone-400">
                <span>uncertainty (SEM)</span><span>stop at 0.30</span>
              </div>
              <div className="h-2 rounded-full bg-stone-100">
                <div className="h-2 rounded-full bg-saffron-500 transition-all"
                  style={{ width: `${Math.min(100, (current.sem / 1.0) * 100)}%` }} />
              </div>
            </div>
          </div>

          {result ? (
            <div className="card border-primary-200 bg-primary-50 p-6 text-center">
              <CheckCircle2 className="mx-auto h-8 w-8 text-primary-700" />
              <h3 className="mt-2 text-lg font-semibold text-primary-950">
                Estimated level: {current.level_estimate.toFixed(2)} / 5
              </h3>
              <p className="text-sm text-primary-800">Your genome has been updated live - check My Skill Genome.</p>
              <div className="mt-4 flex justify-center gap-2">
                <button className="btn-outline" onClick={() => { setResult(null); setSessionId(null); }}>Take another</button>
              </div>
            </div>
          ) : current.served ? (
            <div className="card p-6">
              <p className="font-medium text-stone-800">{current.served.stem}</p>
              <div className="mt-4 space-y-2">
                {current.served.options.map((opt, i) => (
                  <button key={i} disabled={picked !== null}
                    onClick={() => answer(i)}
                    className={`block w-full rounded-lg border px-4 py-2.5 text-left text-sm transition-colors ${
                      picked === i ? "border-primary-600 bg-primary-50" : "border-stone-200 hover:border-primary-300 hover:bg-primary-50/50"}`}>
                    <b className="mr-2 text-stone-400">{String.fromCharCode(65 + i)}.</b>{opt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="card p-6 text-center text-stone-400">Loading next item…</div>
          )}
        </>
      )}
    </div>
  );
}
