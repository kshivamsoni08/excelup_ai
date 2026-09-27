# ExcelUp AI

**Longitudinal skilling-outcomes and impact-measurement platform** - Smart India Hackathon PS 26135, Government of Maharashtra, Department of Skills, Employment, Entrepreneurship and Innovation.

Tagline: **"Skilling outcomes, measured honestly."**

ExcelUp AI turns scattered training data into a **consent-based Outcome Registry**: employment episodes over time (wage jobs, self-employment, apprenticeships), captured through one-tap follow-ups, employer validation and platform placements - then measured with outcome-adjusted analytics where **every number displays its consent coverage** and demographic cells below 5 trainees are suppressed.

---

## The thesis in one toggle

Placement-day rates flatter programmes. Twelve-month outcomes re-rank them. The officer
**Programmes** table has a toggle: *Placement-day view ⇄ Outcome view* - the ranking
visibly flips, driven by the Outcome-Adjusted Quality Index (formula published on screen):

```
OQI = 100 x ( 0.30 x placement_12 + 0.25 x retention_12 + 0.25 x wage_growth
            + 0.10 x employer_validation + 0.10 x followup_response )
wage component = clamp(growth / 30%, 0, 1)     # 30% growth = full marks
```

Auto-flags: `vanity_metric` (day-0 >> 12-mo), `oversupplied` (completions > 2x sector
median + weak placement + declining demand), `obsolete` (sector postings down > 25% YoY).

## The five engines

| Engine | What it does |
|---|---|
| **Outcome Analytics** (`engines/outcomes.py`) | placement_0 / placement_m / retention_m / wage_growth_12 / follow-up rate / validation rate / OQI / flags / k-anonymity |
| **IRT adaptive assessment** (`engines/irt.py`) | 2-PL model, EAP estimation, Fisher-information item selection, SEM stopping |
| **Skill decay** (`engines/decay.py`) | half-life model over (mu, sigma^2, last evidence) -> verified floor / potential ceiling |
| **Matching** (`engines/matching.py`) | coverage scoring with prerequisite BFS + always-explained results; reused for skill-gap diagnostics of non-placed trainees |
| **Embeddings** (`engines/embeddings.py`) | MiniLM 384-dim with deterministic fallback (LLM-free core) |

Plus: consent engine (scopes, live revocation, PII audit), follow-up engine (scheduled +
ad-hoc waves, one-tap responses, assisted workbench), employer validation (wage bands,
never exact wages), Ed25519 signed credentials with Merkle proofs, notifications, events
audit trail, APScheduler (wave scheduling + Neon keep-warm).

## Tech stack

- **Backend**: Python FastAPI + SQLModel + Pydantic v2, JWT + bcrypt RBAC
  (roles: `trainee`, `trainer`, `employer`, `provider`, `officer`, `admin`)
- **Database**: Neon serverless PostgreSQL + pgvector (`pool_pre_ping`, warm-up query, keep-warm heartbeat)
- **Frontend**: Next.js 14 (App Router) + TypeScript + Tailwind + TanStack Query + Recharts, PWA
- **No Docker, no second datastore, no local Postgres.** Modular monolith.

## Run it

```powershell
# 0) .env at project root: DATABASE_URL (Neon POOLED string), SECRET_KEY, optional GEMINI_API_KEY / GROQ_API_KEY
# 1) Backend deps (once)
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 2) Frontend deps (once)
cd frontend
npm install

# 3) Seed the demo world (bulk inserts, ~3-4 min)
#    from the project root:
make reset          # or: cd backend && .venv\Scripts\python -m seed.run --reset

# 4) Run (two terminals)
cd backend  && .venv\Scripts\python -m uvicorn app.main:app --reload   # :8000, docs at /docs
cd frontend && npm run dev                                             # :3000
```

Health check: `curl http://127.0.0.1:8000/health` -> `{"ok":true,"db":"up"}`

## Demo accounts (password: `demo1234`)

| Role | Email | Why they matter |
|---|---|---|
| **Officer (hero)** | `sunita.rao@skills.mahdemo.gov` | Impact dashboard, ranking-flip toggle, drill-downs, workbench, PII audit |
| **Trainee (hero)** | `priya.patil@demo.trainee` | Solar PV @ ITI Pune, rising wage curve, credential, responds to live wave |
| Trainee (non-placed) | `rahul.jadhav@demo.trainee` | Reason codes + skill-gap remediation story |
| Employer | `hr@sunray.demo` | Validation queue (Priya's episode is pending) |
| Provider | `principal@itipune.demo` | ITI Pune outcome dashboard |
| Provider | `principal@itinashik.demo` | ITI Nashik (EV - flagged programme) |
| Admin | `admin@excelupai.demo` | Platform stats |

Follow `DEMO_SCRIPT.md` for the full scene-by-scene walkthrough, and `TESTING_GUIDE.md`
for the feature-by-feature self-verification checklist.

## Seeded world (the demo IS the data)

- 10 Maharashtra districts, 15 providers (ITIs / polytechnics / private / NGO)
- ~30 programmes across EV, solar, CNC, textiles, logistics, IT-ITeS, healthcare...
- ~90 cohorts completing at -3 to -24 months; **2,000 trainees** with demographics and consents (~90% broad, ~10% narrow so coverage < 100% everywhere)
- Scripted hero numbers: Nashik EV day-0 92% / 12-mo 78% / retention 48% (vanity flag);
  Pune Solar day-0 85% / retention 82% / wage +31% / OQI ~87 vs Nashik ~52; Solapur
  Textiles oversupplied + obsolete; Beauty & Wellness self-employment capture; Sambhajinagar Welder apprenticeship cluster
- ~30k wage events (24-month monthly series), pre-validated employer episodes (85%) with 4-6 pending for the live beat, ~30 non-responders in the workbench, pending scheduled wave
- 193-skill vocational taxonomy with prerequisites, embeddings, 70-item adaptive bank

## Project layout

```
skillsetu/
├─ Makefile / .env.example / .gitignore
├─ backend/
│  ├─ app/engines/       # outcomes, irt, decay, matching, embeddings, llm
│  ├─ app/routers/       # officer, trainee_outcomes, employer, provider, company, ...
│  ├─ app/services/      # outcomes aggregation, followups, consents, credentials, ...
│  ├─ app/models/tables.py   # 34 tables (Outcome Ledger + kept SkillSetu schema)
│  ├─ seed/run.py        # bulk-insert seeder with scripted outcome numbers
│  └─ tests/             # pytest for engine math (47 tests)
├─ frontend/app/         # (trainee) (officer) (employer) (provider) (company) (auth)
├─ data/                 # taxonomy.csv, edges.csv, items.json, courses.json, ...
└─ DEMO_SCRIPT.md / TESTING_GUIDE.md
```

## Acceptance checklist (§9 - all pass after seed)

1. Officer Programmes: Nashik EV #1 on day-0 view; toggle flips ranking; OQI 87 vs 52; flags visible
2. EV Nashik drill-down: retention 48%, Pareto (wage 41%), Battery Diagnostics gap, suppressed demographic cell, OQI formula card
3. Solapur Textiles shows oversupplied + obsolete with reasons
4. Officer runs wave on Solar Pune -> Priya notified <= 10s -> one-tap "wage, 15-20k" -> dashboard updates within one poll
5. hr@sunray.demo confirms Priya's episode with wage band -> validation rate rises
6. Priya revokes 'wage' consent -> officer wage coverage n drops by 1, live
7. Officer opens a non-responder card -> PII_VIEWED event appears in the audit page
8. Rahul: outcome timeline + reasons, skill-gap report -> remedial learning path, JRI renders
9. Priya's credential verifies green "Authentic" (tamper -> red via dev script)
10. Empty LLM keys: all of the above unchanged; `make reset` re-seeds in < 5 min

## Deployment appendix (documented only - deploy later)

- **Backend** -> Render/Railway: start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`,
  env: `DATABASE_URL`, `SECRET_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `FRONTEND_ORIGINS`
- **Frontend** -> Vercel: env `NEXT_PUBLIC_API_URL` = deployed backend URL
- **Neon** stays the single DB (same pooled `DATABASE_URL` for dev and prod)
- Demo-day tip: snapshot the seeded state with a Neon **branch** and restore instantly instead of reseeding
