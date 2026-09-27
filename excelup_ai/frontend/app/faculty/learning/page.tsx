"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import { api } from "@/lib/api";

type Course = { id: number; title: string; provider: string; url: string; skills: string[]; duration_hours: number; level: string };

export default function FacultyCourses() {
  const qc = useQueryClient();
  const { data: courses } = useQuery({ queryKey: ["courses"], queryFn: () => api<Course[]>("/courses") });
  const enroll = useMutation({
    mutationFn: (id: number) => api(`/courses/${id}/enroll`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries(),
  });

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-primary-950">
        <BookOpen className="h-6 w-6" /> Courses for faculty
      </h1>
      {(courses ?? []).slice(0, 20).map((c) => (
        <div key={c.id} className="card flex items-center justify-between p-4">
          <div>
            <b className="text-primary-950">{c.title}</b>
            <div className="text-sm text-stone-500">{c.provider} · {c.duration_hours}h</div>
          </div>
          <button className="btn-outline" onClick={() => enroll.mutate(c.id)}>Enroll</button>
        </div>
      ))}
    </div>
  );
}
