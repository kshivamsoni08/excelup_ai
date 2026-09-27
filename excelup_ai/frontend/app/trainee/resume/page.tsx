"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileScan, Upload } from "lucide-react";
import { api } from "@/lib/api";

type Cv = {
  claimed_score: number; verified_score: number; delta: number; eligible_claimed: boolean;
  declared_skill_ids: number[];
  per_skill: {
    skill: string; required: number; claimed_level: number; verified_level: number;
    claimed_credit: number; verified_credit: number; is_declared_only: boolean; verified: boolean;
    bridge_courses: string[];
  }[];
};

export default function ResumePage() {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [scan, setScan] = useState<any>(null);
  const [cv, setCv] = useState<Cv | null>(null);

  const { data: opps } = useQuery({
    queryKey: ["opps-internship"],
    queryFn: () => api<{ id: number; title: string; company: string }[]>("/opportunities?kind=internship"),
  });

  const doScan = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      if (file) fd.append("file", file);
      if (text) fd.append("text", text);
      return api<any>("/resume/scan", { method: "POST", formData: fd });
    },
    onSuccess: (res) => {
      setScan(res);
      qc.invalidateQueries({ queryKey: ["genome"] });
    },
  });

  const compare = useMutation({
    mutationFn: (oppId: number) => api<Cv>(`/resume/claimed-vs-verified/${oppId}`),
    onSuccess: setCv,
  });

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <FileScan className="h-6 w-6" /> Resume Scanner
        </h1>
        <p className="text-sm text-stone-500">We don't just read your resume - we check if it's true.</p>
      </div>

      <div className="card space-y-4 p-6">
        <div>
          <label className="label">Upload PDF or paste resume text</label>
          <input type="file" accept=".pdf,.txt" className="input" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
        <textarea className="input min-h-32" placeholder="…or paste resume text here"
          value={text} onChange={(e) => setText(e.target.value)} />
        <button className="btn-primary" disabled={doScan.isPending || (!file && !text)}
          onClick={() => doScan.mutate()}>
          <Upload className="h-4 w-4" /> {doScan.isPending ? "Scanning…" : "Scan resume"}
        </button>
        {scan && (
          <div className="rounded-lg bg-stone-50 p-3 text-sm">
            <b>{scan.added?.length ?? 0}</b> skills detected &amp; added as <span className="badge-gray">unverified</span>{" "}
            <span className="text-stone-400">(parser: {scan.path})</span>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {scan.added?.map((a: any) => (
                <span key={a.skill_id} className="rounded-full border-2 border-dashed border-stone-300 px-2.5 py-0.5 text-xs text-stone-500">
                  {a.name} · unverified
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="card space-y-4 p-6">
        <h3 className="font-semibold text-primary-950">Claimed vs Verified - pick a posting</h3>
        <select className="input" onChange={(e) => e.target.value && compare.mutate(Number(e.target.value))} defaultValue="">
          <option value="">Choose a posting to compare against…</option>
          {(opps ?? []).map((o) => <option key={o.id} value={o.id}>{o.title} - {o.company}</option>)}
        </select>

        {cv && (
          <>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-xl bg-stone-50 p-4">
                <div className="text-3xl font-bold text-stone-700">{cv.claimed_score}%</div>
                <div className="text-xs uppercase tracking-wide text-stone-400">claimed</div>
              </div>
              <div className="rounded-xl bg-primary-50 p-4">
                <div className="text-3xl font-bold text-primary-800">{cv.verified_score}%</div>
                <div className="text-xs uppercase tracking-wide text-primary-600">verified</div>
              </div>
              <div className="rounded-xl bg-saffron-50 p-4">
                <div className="text-3xl font-bold text-saffron-600">{cv.delta}%</div>
                <div className="text-xs uppercase tracking-wide text-saffron-600">truth gap</div>
              </div>
            </div>
            <div className="space-y-2">
              {cv.per_skill.map((p) => (
                <div key={p.skill} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-stone-100 p-3 text-sm">
                  <div>
                    <b>{p.skill}</b> <span className="text-stone-400">vs {p.required} required</span>
                    <div className="text-xs text-stone-500">
                      claimed {p.claimed_level} → verified {p.verified_level}
                      {p.is_declared_only && <span className="badge-gray ml-1">unverified claim</span>}
                    </div>
                  </div>
                  {!p.verified ? (
                    <div className="flex items-center gap-2">
                      {p.bridge_courses?.[0] && <span className="text-xs text-stone-400">bridge: {p.bridge_courses[0]}</span>}
                      <a className="btn-saffron" href="/trainee/assess">Verify now</a>
                    </div>
                  ) : (
                    <span className="badge-green">✓ verified</span>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
