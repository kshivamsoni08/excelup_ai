import Link from "next/link";
import { ArrowRight, Landmark } from "lucide-react";

const CONCEPTS = [
  {
    name: "Outcome Ledger",
    tagline: "Every trainee's journey, verified over time.",
    icon: "📒",
  },
  {
    name: "One-Tap Follow-Ups",
    tagline: "Outcome reporting that takes a tap, not a survey.",
    icon: "👆",
  },
  {
    name: "Consent-First Analytics",
    tagline: "Trainees share what they choose. Every number shows its coverage.",
    icon: "🛡️",
  },
  {
    name: "Outcome-Adjusted Quality Index",
    tagline: "Placement-day numbers rank providers. Outcomes re-rank them.",
    icon: "📐",
  },
  {
    name: "Validated Employment",
    tagline: "Employers confirm episodes. Credentials prove skills.",
    icon: "✅",
  },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-2">
          <Landmark className="h-7 w-7 text-primary-800" />
          <span className="text-lg font-bold tracking-tight text-primary-950">ExcelUp AI</span>
        </div>
        <Link href="/login" className="btn-primary">Sign in</Link>
      </header>

      <section className="mx-auto max-w-6xl px-6 pb-16 pt-14 text-center">
        <div className="badge-amber mx-auto mb-5">Smart India Hackathon · PS 26135 · Govt. of Maharashtra, Dept of Skills</div>
        <h1 className="mx-auto max-w-3xl text-5xl font-extrabold leading-tight tracking-tight text-primary-950">
          Skilling outcomes,
          <br />
          <span className="text-saffron-500">measured honestly.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-stone-600">
          Enrolment and certificates are not outcomes. ExcelUp AI builds a{" "}
          <b>consent-based longitudinal outcome registry</b> - employment episodes,
          wage progression, retention and reasons for non-placement, captured with
          one-tap follow-ups, employer validation and platform placements.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link href="/login" className="btn-primary px-6 py-3 text-base">
            Try the live demo <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      <section className="border-t border-stone-100 bg-stone-50 py-16">
        <div className="mx-auto grid max-w-6xl gap-5 px-6 sm:grid-cols-2 lg:grid-cols-3">
          {CONCEPTS.map((c) => (
            <div key={c.name} className="card p-6">
              <div className="text-3xl">{c.icon}</div>
              <h3 className="mt-3 text-lg font-semibold text-primary-950">{c.name}</h3>
              <p className="mt-1 text-sm text-stone-600">{c.tagline}</p>
            </div>
          ))}
          <div className="card flex flex-col justify-center bg-primary-950 p-6 text-primary-50">
            <h3 className="text-lg font-semibold">Outcomes are attracted, not chased</h3>
            <p className="mt-2 text-sm text-primary-200">
              Trainees keep their verified skill wallet alive because it pays off -
              and their outcome signals arrive <b>near-zero-burden</b> as a side
              effect. Employers confirm episodes. The department sees honest
              numbers, with consent coverage on every statistic.
            </p>
          </div>
        </div>
      </section>

      <footer className="mx-auto max-w-6xl px-6 py-10 text-center text-xs text-stone-400">
        ExcelUp AI - Longitudinal Skilling Outcomes &amp; Impact Measurement · Dept of Skills, Employment, Entrepreneurship &amp; Innovation (demo)
      </footer>
    </div>
  );
}
