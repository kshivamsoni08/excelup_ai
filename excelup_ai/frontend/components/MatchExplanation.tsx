"use client";

import { CheckCircle2, CircleDashed, ArrowRight } from "lucide-react";

export type Explanation = {
  matched: { skill: string; user_level: number; required: number; credit: number }[];
  near_miss: {
    skill: string; user_level: number; required: number; credit: number;
    bridge?: string;
  }[];
  eligible: boolean;
  score: number;
};

export default function MatchExplanation({ explanation }: { explanation: Explanation }) {
  return (
    <div className="space-y-2 text-xs">
      {explanation.matched.map((m) => (
        <div key={m.skill} className="flex items-center gap-2 text-stone-600">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-primary-700" />
          <span><b className="text-stone-800">{m.skill}</b> - you at {m.user_level} vs {m.required} required</span>
        </div>
      ))}
      {explanation.near_miss.map((m) => (
        <div key={m.skill} className="rounded-lg bg-saffron-50 p-2">
          <div className="flex items-center gap-2 text-stone-700">
            {m.credit > 0 ? <CircleDashed className="h-4 w-4 shrink-0 text-saffron-600" /> :
              <CircleDashed className="h-4 w-4 shrink-0 text-stone-400" />}
            <span>
              <b>{m.skill}</b> - you at {m.user_level} vs {m.required} required
              <span className="ml-1 text-stone-400">({Math.round(m.credit * 100)}% credit)</span>
            </span>
          </div>
          {m.bridge && (
            <div className="ml-6 mt-1 flex items-start gap-1 text-stone-500">
              <ArrowRight className="mt-0.5 h-3 w-3 shrink-0 text-saffron-600" />
              <span>{m.bridge}</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
