"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Landmark } from "lucide-react";
import { api, setSession, type SessionUser } from "@/lib/api";

const DEMO_ACCOUNTS = [
  { label: "Trainee - Priya (hero)", email: "priya.patil@demo.trainee" },
  { label: "Trainee - Rahul (non-placed)", email: "rahul.jadhav@demo.trainee" },
  { label: "Officer - Sunita Rao (Dept of Skills)", email: "sunita.rao@skills.mahdemo.gov" },
  { label: "Employer - SunRay Energy", email: "hr@sunray.demo" },
  { label: "Provider - ITI Pune", email: "principal@itipune.demo" },
  { label: "Provider - ITI Nashik", email: "principal@itinashik.demo" },
];

const HOME: Record<string, string> = {
  trainee: "/trainee",
  trainer: "/faculty",
  employer: "/employer/validations",
  provider: "/provider",
  officer: "/officer",
  admin: "/admin",
};

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("priya.patil@demo.trainee");
  const [password, setPassword] = useState("demo1234");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api<{ token: string; user: SessionUser }>("/auth/login", {
        method: "POST",
        body: { email, password },
      });
      setSession(res.token, res.user);
      router.replace(HOME[res.user.role] ?? "/trainee");
    } catch (err: any) {
      setError(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[#1E3A8A] via-[#1E3A8A]/90 to-[#312E81] p-6">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-2xl">
        <div className="mb-6 flex items-center gap-2">
          <Landmark className="h-8 w-8 text-primary-800" />
          <div>
            <h1 className="text-xl font-bold tracking-tight text-primary-950">ExcelUp AI</h1>
            <p className="text-xs text-stone-500">Skilling outcomes, measured honestly.</p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="label">Email</label>
            <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
          <button className="btn-primary w-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-6 border-t border-stone-100 pt-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">Demo accounts (password: demo1234)</div>
          <div className="grid grid-cols-1 gap-1.5">
            {DEMO_ACCOUNTS.map((d) => (
              <button key={d.email} onClick={() => { setEmail(d.email); setPassword("demo1234"); }}
                className="rounded-lg border border-stone-200 px-3 py-1.5 text-left text-xs text-stone-600 hover:border-primary-300 hover:bg-primary-50">
                <b>{d.label}</b> · {d.email}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
