# ExcelUp AI - Live Demo Script

**PS 26135 - Govt. of Maharashtra, Dept of Skills, Employment, Entrepreneurship & Innovation.**
All demo accounts use password `demo1234`.

Start the stack (two terminals):

```powershell
# Terminal 1 - backend (port 8000)
cd backend
.venv\Scripts\python -m uvicorn app.main:app --reload

# Terminal 2 - frontend (port 3000)
cd frontend
npm run dev
```

Open http://localhost:3000. Works with or without LLM keys (all core flows are deterministic).

The demo arc: **day-0 placement numbers flatter everyone - outcomes re-rank them.**

---

## Scene 0 - Landing (30s)

Open http://localhost:3000. Tagline: *"Skilling outcomes, measured honestly."*
Point at the 5 branded terms: Outcome Ledger, One-Tap Follow-Ups, Consent-First Analytics,
Outcome-Adjusted Quality Index, Validated Employment.

## Scene 1 - Officer: the ranking flip (2 min)  <- HERO MOMENT

1. Sign in as **sunita.rao@skills.mahdemo.gov** (Programme Officer).
2. Impact Dashboard: headline KPIs, placement decay (day-0 vs 12-mo), follow-up funnel,
   consent-coverage banner, flags strip.
3. Go to **Programmes**. Default **Placement-day view**: *EV Assembly Technician (ITI Nashik)*
   sits **#1** (day-0 ~92%).
4. Toggle **Outcome view**: ranking flips - *Solar PV Installer (ITI Pune)* jumps to **#1**
   (OQI ~87) while Nashik EV falls to mid-table (OQI ~52). Flags visible:
   `vanity metric` on Nashik EV (day-0 far above 12-mo), `oversupplied` + `obsolete` on
   *Textile Machine Operator (ITI Solapur)*.
   - Line to say: "Placement-day numbers rank providers. Outcomes re-rank them."

## Scene 2 - Programme drill-down (2 min)

Open **EV Assembly Technician (ITI Nashik)** from the table:

- OQI formula card (published math, component breakdown).
- Placement decay curve (92% -> 78% -> ...) and wage curve (wage-consented only, n shown).
- Attrition Pareto: *wage below expectations* 41% on top.
- Skill-gap panel: **Battery Diagnostics** tops the missing proficiencies for non-placed
  completers -> suggested curriculum updates on the right.
- Demographic equity: at least one **"suppressed (n<5)"** cell - privacy by design.

## Scene 3 - Run a follow-up wave (1 min)

On the same drill-down (or Workbench), click **Run follow-up wave** on the Solar Pune
cohort. Toast: every completer notified in-app.

## Scene 4 - Trainee one-tap response (1 min)

1. In a second browser/incognito window, sign in as **priya.patil@demo.trainee**.
2. Within seconds the bell shows the wave notification; **My Outcome Ledger** has the
   check-in card. Click **Report in one tap** -> "Wage job" + band **15-20k** -> Submit.
3. Back in the officer tab: within one poll (~15s) the dashboard/follow-up numbers tick up.

## Scene 5 - Employer validation (1.5 min)

1. Sign in as **hr@sunray.demo** (SunRay Energy) -> **Validation Queue**.
2. Priya's episode is pending. Click **Confirm** -> pick wage band **15-20k**.
3. Status flips to `validated`; the provider/officer validation-rate % rises live.
   Note: wage bands only - exact salaries are never exposed.

## Scene 6 - Consent is real (1 min)

1. As **priya.patil@demo.trainee** -> **Consent Manager** -> **Revoke** the `wage` scope
   on the Department consent.
2. Officer tab: the Solar Pune wage curve loses one trainee - coverage n drops by 1
   with updated coverage %. Revoking is immediate and visible.

## Scene 7 - Assisted workbench + PII audit (1.5 min)

1. Officer -> **Follow-up Workbench**: non-responder queue (>= 14 days silent).
2. Open a trainee card - the **PII banner** warns access is logged.
3. Record an assisted outcome (or "no response").
4. **PII Access Audit** page: your view appears with officer name, trainee ref, context, time.

## Scene 8 - Rahul: the non-placement story (1.5 min)

1. Sign in as **rahul.jadhav@demo.trainee** (EV @ ITI Nashik, non-placed).
2. **My Outcome Ledger**: non-placement with reason codes on the timeline.
3. **Skill Gap Report**: Battery Diagnostics 2.1 vs required 3.5 -> remedial learning
   path mapped to courses. This is how "reasons for non-placement" closes the loop.

## Scene 9 - Trust layer (1 min)

1. Priya -> genome/credential: gauntlet-approved **Solar PV Site Safety Challenge**.
2. Open her credential's public link (or /verify/{id}): green banner -
   signature valid, Merkle proof valid, issued date. "Authentic."

## Scene 10 - Close (30s)

Back on the officer dashboard: "Enrolment tells you where the money went.
**Outcomes** tell you what it bought. Every number here shows its consent coverage -
that is why trainees keep answering, and why these numbers can be trusted."

---

## Demo accounts

| Role | Email | Notes |
|---|---|---|
| Trainee (hero) | priya.patil@demo.trainee | Solar PV @ ITI Pune, wage curve rising, full consent, credential issued |
| Trainee (non-placed) | rahul.jadhav@demo.trainee | EV @ ITI Nashik, skill gaps + remedial path |
| Officer (hero) | sunita.rao@skills.mahdemo.gov | Dept of Skills - all analytics + workbench + audit |
| Employer | hr@sunray.demo | SunRay Energy - pending validation on Priya's episode |
| Provider | principal@itipune.demo | ITI Pune |
| Provider | principal@itinashik.demo | ITI Nashik (EV) |
| Admin | admin@excelupai.demo | Platform stats |

Password for all: `demo1234`
