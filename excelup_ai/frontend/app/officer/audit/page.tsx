"use client";

import { useQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";
import { api } from "@/lib/api";

type Entry = {
  id: number; officer_id: number; officer_name: string;
  trainee_id: number; context: string; ts: string;
};

export default function AuditPage() {
  const { data } = useQuery({
    queryKey: ["officer-audit"],
    queryFn: () => api<{ entries: Entry[] }>("/officer/audit"),
    refetchInterval: 12_000,
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <ScrollText className="h-7 w-7 text-primary-800" />
        <div>
          <h1 className="text-2xl font-bold text-primary-950">PII Access Audit</h1>
          <p className="text-sm text-stone-500">Every officer view of individual-level personal data, permanently logged. Analytics never expose PII.</p>
        </div>
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="border-b border-stone-200 bg-stone-50 text-left text-xs uppercase tracking-wide text-stone-400">
            <tr>
              <th className="px-4 py-3">When</th>
              <th className="px-4 py-3">Officer</th>
              <th className="px-4 py-3">Trainee ref</th>
              <th className="px-4 py-3">Context</th>
            </tr>
          </thead>
          <tbody>
            {(data?.entries ?? []).map((e) => (
              <tr key={e.id} className="border-b border-stone-100">
                <td className="whitespace-nowrap px-4 py-3 text-stone-500">{new Date(e.ts).toLocaleString()}</td>
                <td className="px-4 py-3 font-medium text-primary-900">{e.officer_name}</td>
                <td className="px-4 py-3">TRN-{String(e.trainee_id).padStart(5, "0")}</td>
                <td className="px-4 py-3 text-stone-600">{e.context}</td>
              </tr>
            ))}
            {!data?.entries?.length && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-sm text-stone-400">No PII access recorded yet - open a trainee card in the workbench to see the audit trail in action.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
