"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Route } from "lucide-react";
import { api } from "@/lib/api";

type Course = { id: number; title: string; provider: string; url: string; skills: string[]; duration_hours: number; level: string };
type Enrollment = { id: number; course_id: number; title: string; provider: string; url: string; progress: number; status: string; skills: string[] };
type Roadmap = { id: number; title: string; from_role: string; to_role: string; steps: { n: number; title: string; detail: string; course: string | null; kind: string }[] };

export default function LearningPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"path" | "courses" | "roadmaps">("path");

  const { data: courses } = useQuery({ queryKey: ["courses"], queryFn: () => api<Course[]>("/courses") });
  const { data: enrollments } = useQuery({
    queryKey: ["enrollments"],
    queryFn: () => api<Enrollment[]>("/me/enrollments"),
    refetchInterval: 12_000,
  });
  const { data: roadmaps } = useQuery({ queryKey: ["roadmaps"], queryFn: () => api<Roadmap[]>("/roadmaps") });
  const { data: gap } = useQuery({
    queryKey: ["gap", "Pharma QC Analyst"],
    queryFn: () => api<{ requirements: { skill: string; gap: number; bridge_courses: string[] }[] }>(`/me/skill-gap/Pharma%20QC%20Analyst`),
  });

  const enroll = useMutation({
    mutationFn: (id: number) => api(`/courses/${id}/enroll`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const progress = useMutation({
    mutationFn: ({ id, p }: { id: number; p: number }) =>
      api(`/enrollments/${id}/progress`, { method: "POST", body: { progress: p } }),
    onSuccess: () => qc.invalidateQueries(),
  });

  const enrolledIds = new Set((enrollments ?? []).map((e) => e.course_id));
  const gapSkills = (gap?.requirements ?? []).filter((g) => g.gap > 0).map((g) => g.skill);
  const recommended = (courses ?? []).filter((c) => (c.skills ?? []).some((s) => gapSkills.includes(s)));

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
          <BookOpen className="h-6 w-6" /> My Learning Path
        </h1>
        <div className="mt-2 flex gap-2">
          {(["path", "courses", "roadmaps"] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`rounded-full px-3 py-1.5 text-sm ${tab === t ? "bg-primary-900 text-white" : "bg-stone-100 text-stone-600"}`}>
              {t === "path" ? "Recommended" : t === "courses" ? "Course catalog" : "Career roadmaps"}
            </button>
          ))}
        </div>
      </div>

      {tab === "path" && (
        <div className="space-y-3">
          <p className="text-sm text-stone-500">Courses mapped to your top skill gaps for the chosen target role:</p>
          {recommended.map((c) => (
            <div key={c.id} className="card flex flex-wrap items-center justify-between gap-3 p-4">
              <div>
                <b className="text-primary-950">{c.title}</b>
                <div className="text-sm text-stone-500">{c.provider} · {c.duration_hours}h · {c.level}</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {(c.skills ?? []).map((s) => (
                    <span key={s} className={`badge ${gapSkills.includes(s) ? "badge-amber" : "badge-gray"}`}>{s}</span>
                  ))}
                </div>
              </div>
              {enrolledIds.has(c.id)
                ? <span className="badge-green">enrolled</span>
                : <button className="btn-primary" onClick={() => enroll.mutate(c.id)}>Enroll</button>}
            </div>
          ))}
          {!recommended.length && <div className="card p-8 text-center text-stone-400">No gaps detected for this role - nice.</div>}
        </div>
      )}

      {tab === "courses" && (
        <div className="space-y-3">
          {(courses ?? []).map((c) => (
            <div key={c.id} className="card flex flex-wrap items-center justify-between gap-3 p-4">
              <div>
                <b className="text-primary-950">{c.title}</b>
                <div className="text-sm text-stone-500">{c.provider} · {c.duration_hours}h · {c.level}</div>
              </div>
              {enrolledIds.has(c.id) ? <span className="badge-green">enrolled</span>
                : <button className="btn-outline" onClick={() => enroll.mutate(c.id)}>Enroll</button>}
            </div>
          ))}
        </div>
      )}

      {tab === "roadmaps" && (
        <div className="space-y-4">
          {(roadmaps ?? []).map((r) => (
            <div key={r.id} className="card p-5">
              <div className="flex items-center gap-2">
                <Route className="h-4 w-4 text-saffron-500" />
                <b className="text-primary-950">{r.title}</b>
                <span className="badge-gray">{r.steps.length} steps</span>
              </div>
              <div className="mt-3 space-y-0">
                {r.steps.map((s, i) => (
                  <div key={s.n} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <div className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold ${s.kind === "gauntlet" ? "bg-saffron-500 text-white" : "bg-primary-800 text-white"}`}>
                        {s.n}
                      </div>
                      {i < r.steps.length - 1 && <div className="h-6 w-0.5 bg-stone-200" />}
                    </div>
                    <div className="pb-4">
                      <div className="text-sm font-medium text-stone-800">
                        {s.title} <span className="badge-gray ml-1">{s.kind.replace("_", " ")}</span>
                      </div>
                      <div className="text-xs text-stone-500">{s.detail}{s.course && ` · ${s.course}`}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="card p-5">
        <h3 className="mb-3 font-semibold text-primary-950">My Courses - progress (completion updates your genome live)</h3>
        <div className="space-y-3">
          {(enrollments ?? []).map((e) => (
            <div key={e.id} className="rounded-lg border border-stone-100 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <b className="text-sm">{e.title}</b>
                <span className={e.status === "completed" ? "badge-green" : "badge-amber"}>{e.status}</span>
              </div>
              <div className="mt-2 flex items-center gap-3">
                <input type="range" min={0} max={100} step={10} value={e.progress}
                  className="grow accent-primary-800"
                  onChange={(ev) => progress.mutate({ id: e.id, p: Number(ev.target.value) })} />
                <span className="w-12 text-right text-sm font-mono">{e.progress}%</span>
                <button className="btn-outline" onClick={() => progress.mutate({ id: e.id, p: 50 })}>50%</button>
                <button className="btn-primary" onClick={() => progress.mutate({ id: e.id, p: 100 })}>Complete</button>
              </div>
            </div>
          ))}
          {!enrollments?.length && <div className="text-sm text-stone-400">Enroll in a course to start tracking progress.</div>}
        </div>
      </div>
    </div>
  );
}
