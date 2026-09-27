"""ExcelUp AI seed entrypoint - Maharashtra skilling-outcomes demo data.

Usage:
    python -m seed.run --reset   # drop + recreate + reseed everything
    python -m seed.run           # seed only (idempotent-ish; resets if empty)

Bulk inserts with batches of ~500 rows. Run from the backend/ folder so `data/`
paths resolve to ../data. Writes data/seed_ids.json for demo scripting.

The demo IS the data: scripted outcome numbers make the officer-portal reveal
work (Solar Pune OQI ~87 vs EV Nashik ~52; the day-0 vs outcome toggle flips
the ranking; textile oversupplied + obsolete flags).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, select  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.engine import get_sync_engine  # noqa: E402
from app.models.tables import (  # noqa: E402
    Application, Artifact, AssessSession, Cohort, CohortEnrollment, Company,
    Consent, Course, Credential, District, EmploymentEpisode, Enrollment,
    Event, FollowupAttempt, FollowupWave, GauntletSubmission, Item,
    Notification, Opportunity, OppRequirement, Programme, Provider, Proficiency,
    ProficiencyHistory, ReasonCode, Response, Roadmap, Skill, SkillEdge,
    TraineeProfile, User, WageEvent,
)
from app.security import hash_password  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
BATCH = 1000
TODAY = date.today()
NOW = datetime.now(timezone.utc)
DEMO_PASSWORD = "demo1234"

FIRST_NAMES = ["Priya", "Rahul", "Sunita", "Amit", "Kavita", "Sagar", "Pooja",
               "Vikram", "Neha", "Ajay", "Sneha", "Rohit", "Anita", "Sunil",
               "Meena", "Rajesh", "Deepa", "Sanjay", "Rekha", "Asha", "Manoj",
               "Jyoti", "Prakash", "Shobha", "Dinesh", "Vaishali", "Ganesh",
               "Kalpana", "Nitin", "Sarita", "Mahesh", "Lata", "Umesh",
               "Divya", "Ravi", "Gauri", "Sandeep", "Manisha", "Vinod", "Trupti"]
LAST_NAMES = ["Patil", "Jadhav", "Deshmukh", "Kadam", "Shinde", "Pawar", "More",
              "Joshi", "Kulkarni", "Sawant", "Gaikwad", "Bhosale", "Salvi",
              "Naik", "Chavan", "Wagh", "Thorat", "Kamble", "Meshram", "Pardeshi"]

# --------------------------------------------------------------------- geo
DISTRICTS = [
    ("Pune", "Pune", ["Auto & EV", "Solar & Renewables", "IT-ITeS"]),
    ("Nashik", "Nashik", ["Auto & EV", "Agriculture & Allied", "Manufacturing"]),
    ("Mumbai Suburban", "Konkan", ["IT-ITeS", "Media & Entertainment", "Retail"]),
    ("Mumbai City", "Konkan", ["IT-ITeS", "Gems & Jewellery", "Tourism & Hospitality"]),
    ("Thane", "Konkan", ["Manufacturing", "Textiles", "Logistics"]),
    ("Nagpur", "Nagpur", ["Logistics", "Manufacturing", "Utilities"]),
    ("Solapur", "Pune", ["Textiles", "Manufacturing"]),
    ("Sambhajinagar", "Aurangabad", ["Auto & EV", "Manufacturing"]),
    ("Kolhapur", "Pune", ["Manufacturing", "Auto & EV", "Textiles"]),
    ("Raigad", "Konkan", ["Logistics", "Manufacturing", "Construction"]),
]

PROVIDERS = [
    # (name, city, kind, district_idx)
    ("ITI Pune (Demo)", "Pune", "iti", 0),
    ("ITI Nashik (Demo)", "Nashik", "iti", 1),
    ("ITI Solapur (Demo)", "Solapur", "iti", 6),
    ("Government Polytechnic Kolhapur", "Kolhapur", "polytechnic", 8),
    ("Sakhi Private Skill Centre", "Pune", "private", 0),
    ("ITI Sambhajinagar (Demo)", "Sambhajinagar", "iti", 7),
    ("ITI Nagpur (Demo)", "Nagpur", "iti", 5),
    ("ITI Mumbai Suburban (Demo)", "Mumbai Suburban", "iti", 2),
    ("Government Polytechnic Thane", "Thane", "polytechnic", 4),
    ("ITI Raigad (Demo)", "Alibag", "iti", 9),
    ("Skill Mission NGO Mumbai", "Mumbai City", "ngo", 3),
    ("Vidya Vikas Polytechnic Nashik", "Nashik", "polytechnic", 1),
    ("ITI Kolhapur (Demo)", "Kolhapur", "iti", 8),
    ("Ahilyabhui Skill Centre Sambhajinagar", "Sambhajinagar", "private", 7),
    ("Konkan Logistics Skill Council", "Panvel", "private", 9),
]

# (provider_idx, title, sector, nsqf, duration_months, cohorts[(months_ago, completers, dropped, active)])
PROGRAMMES = [
    (0, "Solar PV Installer", "Solar & Renewables", 4, 6, [(14, 60, 3, 0)]),          # HERO Pune
    (1, "EV Assembly Technician", "Auto & EV", 4, 6, [(15, 60, 4, 0), (12, 60, 3, 0)]),  # HERO Nashik
    (2, "Textile Machine Operator", "Textiles", 3, 6,
     [(12, 100, 6, 0), (9, 100, 5, 0), (6, 100, 4, 0)]),                              # HERO Solapur
    (4, "Beauty & Wellness Entrepreneur", "Beauty & Wellness", 4, 4,
     [(15, 80, 4, 0), (9, 80, 3, 0)]),                                                # HERO self-employment
    (5, "Welder (SMAW/MIG)", "Manufacturing", 3, 6, [(12, 60, 3, 0), (6, 60, 2, 0)]), # HERO apprenticeship
    (3, "CNC Machinist", "Manufacturing", 4, 8, [(24, 50, 3, 0), (12, 55, 2, 0), (3, 45, 2, 6)]),
    (11, "Warehouse & Logistics Assistant", "Logistics", 3, 4, [(18, 60, 3, 0), (6, 55, 3, 5)]),
    (7, "IT Support Technician", "IT-ITeS", 4, 6, [(21, 55, 2, 0), (9, 50, 2, 4)]),
    (6, "Electrician (Domestic+Industrial)", "Electrical", 3, 6, [(24, 60, 3, 0), (12, 60, 3, 0), (3, 50, 2, 8)]),
    (8, "Garment Stitching Operator", "Textiles", 3, 5, [(12, 60, 3, 0), (6, 40, 2, 0)]),
    (2, "Fabric Quality Checker", "Textiles", 4, 4, [(15, 40, 2, 0)]),
    (9, "Retail Sales Associate", "Retail", 3, 3, [(18, 55, 2, 0), (6, 50, 2, 4)]),
    (10, "Healthcare Assistant", "Healthcare", 4, 6, [(21, 50, 2, 0), (9, 45, 2, 3)]),
    (12, "Two-Wheeler Repair Technician", "Auto & EV", 3, 4, [(15, 45, 2, 0), (3, 40, 2, 5)]),
    (13, "Industrial Electrician", "Electrical", 4, 6, [(18, 50, 2, 0), (6, 45, 2, 4)]),
    (14, "Forklift & Warehouse Operator", "Logistics", 3, 3, [(12, 45, 2, 0), (3, 40, 2, 6)]),
    (0, "EV Battery Assembly Operator", "Auto & EV", 4, 5, [(18, 45, 2, 0), (6, 40, 2, 4)]),
    (3, "Lathe Operator", "Manufacturing", 3, 5, [(24, 40, 2, 0), (12, 40, 2, 0)]),
    (6, "Plumbing & Sanitation Technician", "Construction", 3, 4, [(15, 45, 2, 0)]),
    (7, "Front Office Executive", "Tourism & Hospitality", 3, 3, [(12, 40, 2, 0)]),
    (2, "Food Processing Operator", "Agriculture & Allied", 4, 4, [(18, 40, 2, 0), (3, 35, 2, 5)]),
    (10, "Home Health Aide", "Healthcare", 3, 3, [(6, 40, 2, 0)]),
    (8, "Dairy Operations Assistant", "Agriculture & Allied", 3, 3, [(12, 35, 2, 0)]),
    (9, "Construction Site Helper → Mason", "Construction", 3, 5, [(21, 45, 3, 0)]),
    (11, "Digital Payments Facilitator", "IT-ITeS", 3, 2, [(9, 35, 1, 0), (3, 30, 1, 4)]),
    (13, "Textile Design Assistant", "Textiles", 4, 6, [(24, 30, 2, 0)]),
    (5, "Sheet Metal Fabricator", "Manufacturing", 3, 5, [(15, 40, 2, 0)]),
    (14, "Customs Documentation Executive", "Logistics", 4, 5, [(21, 30, 2, 0)]),
    (4, "Salon Management Trainee", "Beauty & Wellness", 4, 4, [(12, 35, 2, 0)]),
    (0, "Greenhouse Operations Assistant", "Agriculture & Allied", 3, 4, [(6, 30, 2, 0)]),
]

REASON_CODES = [
    ("non_placement", "skills_mismatch", "Skills do not match local demand", "Trainee profile does not match available openings"),
    ("non_placement", "no_local_openings", "No local openings", "No suitable openings in commute distance"),
    ("non_placement", "family_caregiving", "Family / caregiving duties", "Care responsibilities prevent employment"),
    ("non_placement", "health", "Health reasons", "Medical issues prevent employment"),
    ("non_placement", "pursued_education", "Pursued further education", "Opted for higher studies instead"),
    ("non_placement", "wage_below_expectations", "Offers below wage expectations", "Declined offers below expected wage"),
    ("attrition", "wage_below_expectations", "Wage below expectations", "Left job over pay"),
    ("attrition", "sector_downturn", "Sector downturn", "Layoffs / slowdown in sector"),
    ("attrition", "skill_mismatch", "Skill mismatch", "Role required skills not covered by training"),
    ("attrition", "migration", "Migration", "Moved away for family or opportunity"),
    ("attrition", "other", "Other", "Other personal reasons"),
    ("wage_stagnation", "no_increment", "No increment", "Wage unchanged over 12 months"),
    ("wage_stagnation", "role_change", "Role change", "Changed trade / sector"),
]

COMPANIES = [
    # (name, sector, district_idx, verified) - first 12 are named demo anchors
    ("SunRay Energy", "Solar & Renewables", 0, True),
    ("EV Motors Maharashtra", "Auto & EV", 1, True),
    ("SolapurTex Mills", "Textiles", 6, True),
    ("JNPT Logistics Partners", "Logistics", 9, True),
    ("MIHAN Warehousing", "Logistics", 5, True),
    ("SambhajiAuto Components", "Auto & EV", 7, True),
    ("Kolhapur Precision Engineering", "Manufacturing", 8, True),
    ("Pune EV Works", "Auto & EV", 0, True),
    ("Nashik AgroTech Foods", "Agriculture & Allied", 1, True),
    ("Thane Machine Tools", "Manufacturing", 4, True),
    ("Mumbai SoftServ", "IT-ITeS", 2, True),
    ("KonkulText Apparels", "Textiles", 4, False),
    ("Nagpur Solar Field Services", "Solar & Renewables", 5, False),
    ("Raigad Port Services", "Logistics", 9, False),
    ("Kolhapur Textile Works", "Textiles", 8, False),
    ("Pune Rooftop Solar Co", "Solar & Renewables", 0, False),
    ("Sambhajinagar Fabrication", "Manufacturing", 7, False),
    ("Nashik EV Charging Network", "Auto & EV", 1, False),
    ("Solapur Powerlooms Ltd", "Textiles", 6, False),
    ("Mumbai Retail Bazaar", "Retail", 2, False),
    ("Pune Care Services", "Healthcare", 0, False),
    ("Nashik Dairy Foods", "Agriculture & Allied", 1, False),
    ("Thane Electronics Assembly", "Manufacturing", 4, False),
    ("Kolhapur Foundry Works", "Manufacturing", 8, False),
    ("Nagpur Transport Co", "Logistics", 5, False),
    ("Mumbai Fintech Assist", "IT-ITeS", 3, False),
    ("Pune Polyhouse Farms", "Agriculture & Allied", 0, False),
    ("Sambhajinagar Auto Ancillary", "Auto & EV", 7, False),
    ("Raigad Construction Co", "Construction", 9, False),
    ("Solapur Readymade Exports", "Textiles", 6, False),
    ("Pune Beauty & Spa Chain", "Beauty & Wellness", 0, False),
    ("Nashik Wine Tourism Resorts", "Tourism & Hospitality", 1, False),
    ("Thane Logistics Hub", "Logistics", 4, False),
    ("Mumbai Jewellers Guild", "Gems & Jewellery", 3, False),
    ("Kolhapur Engineering Cluster", "Manufacturing", 8, False),
    ("Pune IT Services SME", "IT-ITeS", 0, False),
    ("Nagpur Solar EPC", "Solar & Renewables", 5, False),
    ("Sambhajinagar Pharma Pack", "Manufacturing", 7, False),
    ("Raigad Fishery Exports", "Agriculture & Allied", 9, False),
    ("Solapur Chadder Mills", "Textiles", 6, False),
    ("Pune EV Fleet Mobility", "Auto & EV", 0, False),
    ("Nashik Pump Industries", "Manufacturing", 1, False),
    ("Mumbai Media Studio", "Media & Entertainment", 2, False),
    ("Thane Facility Services", "Utilities", 4, False),
    ("Kolhapur Auto Garages", "Auto & EV", 8, False),
    ("Pune Construction Builders", "Construction", 0, False),
    ("Nashik Cold Chain Co", "Logistics", 1, False),
    ("Sambhajinagar Textile Park", "Textiles", 7, False),
    ("Raigad JNPT Cargo Movers", "Logistics", 9, False),
    ("Mumbai Hospitality Group", "Tourism & Hospitality", 3, False),
    ("Pune Green Energy EPC", "Solar & Renewables", 0, False),
    ("Nagpur MIHAN Light Engg", "Manufacturing", 5, False),
    ("Solapur Towel Works", "Textiles", 6, False),
    ("Pune Staffing Solutions", "IT-ITeS", 0, False),
    ("Nashik SkillWorks NGO", "Agriculture & Allied", 1, False),
    ("Thane Plastic Moulders", "Manufacturing", 4, False),
    ("Mumbai BPO Services", "IT-ITeS", 2, False),
    ("Kolhapur Dairy Coop", "Agriculture & Allied", 8, False),
    ("Sambhajinagar Tool Room", "Manufacturing", 7, False),
    ("Pune Wellness Resorts", "Tourism & Hospitality", 0, False),
]


def months_ago_date(months: int, day: int = 26) -> date:
    mi = TODAY.month - months
    year = TODAY.year + (mi - 1) // 12
    month = (mi - 1) % 12 + 1
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, month, 28)


def chunks(lst, n=BATCH):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def bulk_save(session: Session, rows):
    """Bulk insert in batches of ~500; never row-by-row over the network.
    Retries each chunk on transient connection drops (Neon cold starts / blips)."""
    import time
    from sqlalchemy.exc import OperationalError
    total = 0
    for chunk in chunks(rows):
        for attempt in range(5):
            try:
                session.bulk_save_objects(chunk)
                session.commit()
                break
            except OperationalError as exc:
                session.rollback()
                if attempt == 4:
                    raise
                wait = 3 * (attempt + 1)
                print(f"   [transient DB error: {type(exc).__name__} - retrying in {wait}s]")
                time.sleep(wait)
        total += len(chunk)
    return total


def read_taxonomy() -> list[dict]:
    with open(DATA_DIR / "taxonomy.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def embed_text_for_skill(row) -> str:
    syns = (row.get("synonyms") or "").split("|")
    return ", ".join([row["name"]] + [s for s in syns if s])


def main(reset: bool):
    if not settings.database_url:
        print("BLOCKED: create .env with DATABASE_URL (Neon pooled string), then say 'continue'.")
        sys.exit(2)

    engine = get_sync_engine()
    print("== ExcelUp AI seed ==")

    with Session(engine) as session:
        session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        session.commit()
        if reset:
            print("Dropping all tables...")
            table_names = ", ".join(
                reversed([t.name for t in __import__("sqlmodel").SQLModel.metadata.sorted_tables]))
            session.execute(text(f"DROP TABLE IF EXISTS {table_names} CASCADE"))
            session.commit()
        from sqlmodel import SQLModel

        session.execute(text("SELECT 1"))
        SQLModel.metadata.create_all(engine)
        session.commit()

        existing = session.exec(select(Skill)).first()
        if existing is not None and not reset:
            print("DB already seeded; use --reset to reseed from scratch.")
            return

        rnd = random.Random(4242)

        # ---------------------------------------------------------- taxonomy
        print("Seeding skills (+ embeddings)...")
        from app.engines.embeddings import embed_many

        tax_rows = read_taxonomy()
        texts = [embed_text_for_skill(r) for r in tax_rows]
        vectors = embed_many(texts)
        skill_rows = [Skill(
            name=row["name"], domain=row["domain"],
            nsqf_level=int(row["nsqf_level"]),
            half_life_class=row["half_life_class"],
            synonyms=[s for s in (row.get("synonyms") or "").split("|") if s],
            embedding=vec,
        ) for row, vec in zip(tax_rows, vectors)]
        bulk_save(session, skill_rows)
        skill_by_name = {s.name: s.id for s in session.exec(select(Skill)).all()}
        skill_obj_by_name = {s.name: s for s in session.exec(select(Skill)).all()}

        # ------------------------------------------------------------- edges
        print("Seeding skill edges...")
        edge_rows = []
        with open(DATA_DIR / "edges.csv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                src, dst = row["src"], row["dst"]
                if src in skill_by_name and dst in skill_by_name:
                    edge_rows.append(SkillEdge(src_id=skill_by_name[src],
                                               dst_id=skill_by_name[dst],
                                               type="prerequisite", weight=1.0))
        bulk_save(session, edge_rows)

        # -------------------------------------------------------- geography
        print("Seeding districts, providers, companies...")
        district_rows = [District(name=n, division=d, key_sectors=s)
                         for n, d, s in DISTRICTS]
        bulk_save(session, district_rows)
        districts = session.exec(select(District)).all()
        district_by_name = {d.name: d for d in districts}

        provider_rows = [Provider(name=n, city=c, kind=k,
                                  district_id=district_by_name[DISTRICTS[di][0]].id)
                         for n, c, k, di in PROVIDERS]
        bulk_save(session, provider_rows)
        providers = session.exec(select(Provider)).all()

        company_rows = [Company(
            name=n, industry=sector, sector=sector,
            city=DISTRICTS[di][0],
            about=f"{sector} employer in {DISTRICTS[di][0]}.",
            verified=v, district_id=district_by_name[DISTRICTS[di][0]].id,
            logo_seed=n.lower().replace(" ", "-")[:24],
        ) for n, sector, di, v in COMPANIES]
        bulk_save(session, company_rows)
        companies = session.exec(select(Company)).all()
        company_by_name = {c.name: c for c in companies}
        sunray = company_by_name["SunRay Energy"]
        ev_motors = company_by_name["EV Motors Maharashtra"]

        # ------------------------------------------------- programmes/cohorts
        print("Seeding programmes & cohorts...")
        programme_rows = []
        for prov_idx, title, sector, nsqf, dur, _c in PROGRAMMES:
            programme_rows.append(Programme(
                provider_id=providers[prov_idx].id, title=title, sector=sector,
                nsqf_level=nsqf, duration_months=dur, status="active"))
        bulk_save(session, programme_rows)
        programmes = {p.title: p for p in session.exec(select(Programme)).all()}

        cohort_rows = []
        cohort_spec_meta = []  # (cohort_row, months_ago, completers, dropped, active, programme_title)
        for (prov_idx, title, sector, nsqf, dur, cohorts) in PROGRAMMES:
            prog = programmes[title]
            for ci, (m_ago, completers, dropped, active) in enumerate(cohorts):
                end = months_ago_date(m_ago)
                start = end - timedelta(days=30.44 * dur)
                cohort_rows.append(Cohort(
                    programme_id=prog.id,
                    batch_code=f"{title.split()[0].upper()[:6]}-{TODAY.year - (m_ago // 12)}-B{ci + 1}",
                    start_date=start, end_date=end,
                    planned_size=completers + dropped + active))
        bulk_save(session, cohort_rows)
        cohorts_all = session.exec(select(Cohort)).all()
        # map (programme_title, months_ago) -> cohort
        prog_of = {p.id: p for p in programmes.values()}
        cohort_key: dict[tuple[str, int], Cohort] = {}
        for c in cohorts_all:
            p = prog_of[c.programme_id]
            cohort_key[(p.title, (TODAY.year - c.end_date.year) * 12 + (TODAY.month - c.end_date.month))] = c

        # ---------------------------------------------------- reason codes
        bulk_save(session, [ReasonCode(category=cat, code=code, label=label,
                                       description=desc)
                            for cat, code, label, desc in REASON_CODES])

        # ------------------------------------------------------------- users
        print("Seeding users (bulk)...")
        pw_hash = hash_password(DEMO_PASSWORD)
        users: list[User] = []

        users.append(User(role="admin", email="admin@excelupai.demo",
                          password_hash=pw_hash, name="Platform Admin",
                          headline="ExcelUp AI core team"))

        officer = User(role="officer", email="sunita.rao@skills.mahdemo.gov",
                       password_hash=pw_hash, name="Sunita Rao",
                       headline="Programme Officer, Dept of Skills, GoM")
        users.append(officer)

        provider_users = []
        seen_emails = set()
        for i, prov in enumerate(providers):
            tokens = [t for t in prov.name.lower().replace("(", " ").replace(")", " ").split()
                      if t.isalnum() and t != "demo"]
            slug = "".join(tokens[:2])
            email = f"principal@{slug}.demo"
            if prov.name == "ITI Pune (Demo)":
                email = "principal@itipune.demo"
            elif prov.name == "ITI Nashik (Demo)":
                email = "principal@itinashik.demo"
            while email in seen_emails:
                email = f"principal{len(seen_emails) + 1}@{slug}.demo"
            seen_emails.add(email)
            provider_users.append(User(
                role="provider", email=email, password_hash=pw_hash,
                name=f"Principal, {prov.name}", provider_id=prov.id,
                headline="Provider account"))
        users.extend(provider_users)

        # dormant trainer accounts
        for i in range(4):
            users.append(User(
                role="trainer", email=f"trainer{i + 1}@itipune.demo",
                password_hash=pw_hash, name=f"Trainer {i + 1} (ITI Pune)",
                provider_id=providers[0].id, headline="Trade instructor"))

        employer_users = []
        for idx, comp in enumerate(companies):
            first = FIRST_NAMES[idx % len(FIRST_NAMES)]
            last = LAST_NAMES[(idx * 3) % len(LAST_NAMES)]
            email = "hr@sunray.demo" if comp.id == sunray.id else \
                f"hr{idx + 1}@{comp.logo_seed.replace('-', '')[:14]}.demo"
            employer_users.append(User(
                role="employer", email=email, password_hash=pw_hash,
                name="Ravi Deshpande (HR, SunRay Energy)" if comp.id == sunray.id
                else f"{first} {last}",
                company_id=comp.id, headline="HR / Employer"))
        users.extend(employer_users)

        n_trainees_total = 2000
        trainees: list[User] = []
        used_emails = set()
        for i in range(n_trainees_total - 2):
            first = FIRST_NAMES[i % len(FIRST_NAMES)]
            last = LAST_NAMES[(i * 7) % len(LAST_NAMES)]
            email = f"{first.lower()}.{last.lower()}{i}@demo.trainee"
            while email in used_emails:
                email = f"{first.lower()}.{last.lower()}{i}x{rnd.randint(2, 99)}@demo.trainee"
            used_emails.add(email)
            district = districts[i % len(districts)]
            trainees.append(User(
                role="trainee", email=email, password_hash=pw_hash,
                name=f"{first} {last}",
                headline=rnd.choice(["ITI trade certificate holder", "Skilling programme trainee",
                                     "Diploma trainee", "Short-term skilling graduate"])))
        priya = User(role="trainee", email="priya.patil@demo.trainee", password_hash=pw_hash,
                     name="Priya Patil", headline="Solar PV Installer | ITI Pune (Demo)")
        rahul = User(role="trainee", email="rahul.jadhav@demo.trainee", password_hash=pw_hash,
                     name="Rahul Jadhav", headline="EV Assembly graduate | seeking EV Service role")
        trainees.extend([priya, rahul])
        users.extend(trainees)
        bulk_save(session, users)

        # re-fetch (bulk_save_objects does not populate PKs)
        all_users = session.exec(select(User)).all()
        users_by_email = {u.email: u for u in all_users}
        officer = users_by_email["sunita.rao@skills.mahdemo.gov"]
        priya = users_by_email["priya.patil@demo.trainee"]
        rahul = users_by_email["rahul.jadhav@demo.trainee"]
        all_trainees = [u for u in all_users if u.role == "trainee"]
        trainee_ids = [t.id for t in all_trainees]

        # trainee profiles with demographics
        categories = ["gen"] * 40 + ["obc"] * 30 + ["sc"] * 15 + ["st"] * 10 + ["nt"] * 5
        profiles = []
        for i, t in enumerate(all_trainees):
            female = rnd.random() < 0.48
            profiles.append(TraineeProfile(
                user_id=t.id,
                degree=rnd.choice(["ITI", "ITI", "Diploma", "Short-term course", "12th"]),
                year="passed",
                interests=[],
                target_role=rnd.choice(["Technician", "Operator", "Service Technician",
                                        "Sales Associate", "Self-employed"]),
                gender="female" if female else "male",
                social_category=rnd.choice(categories),
                age=rnd.randint(19, 32),
                disability=rnd.random() < 0.03,
                education_level=rnd.choice(["10th", "12th", "ITI", "Diploma", "Graduate"]),
                home_district_id=districts[i % len(districts)].id,
                migrated=rnd.random() < 0.12,
                created_at=NOW - timedelta(days=rnd.randint(30, 500)),
            ))
        # heroes + scripted EV-cohort categories (2 st + 1 nt for k-anon demo)
        priya_prof = next(p for p in profiles if p.user_id == priya.id)
        priya_prof.gender, priya_prof.social_category = "female", "obc"
        priya_prof.age, priya_prof.education_level = 22, "ITI"
        priya_prof.home_district_id = district_by_name["Pune"].id
        priya_prof.target_role = "Solar PV Service Technician"
        rahul_prof = next(p for p in profiles if p.user_id == rahul.id)
        rahul_prof.gender, rahul_prof.social_category = "male", "sc"
        rahul_prof.age, rahul_prof.education_level = 23, "12th"
        rahul_prof.home_district_id = district_by_name["Nashik"].id
        rahul_prof.target_role = "EV Service Technician"
        bulk_save(session, profiles)

        # ------------------------------------------------- cohort enrollments
        print("Seeding cohort enrollments...")
        # Build slot list: each (cohort, kind) with kind completers/dropped/active
        slots: list[tuple[Cohort, str]] = []
        hero_slots: dict[tuple[str, int], list[Cohort]] = {}
        for (prov_idx, title, sector, nsqf, dur, cspecs) in PROGRAMMES:
            for (m_ago, completers, dropped, active) in cspecs:
                c = cohort_key[(title, m_ago)]
                for _ in range(completers):
                    slots.append((c, "completed"))
                for _ in range(dropped):
                    slots.append((c, "dropped"))
                for _ in range(active):
                    slots.append((c, "enrolled"))
        rnd.shuffle(slots)
        total_needed = len(slots)
        if total_needed > len(trainee_ids):
            slots = slots[:len(trainee_ids)]
        enrollments = []
        enrolled_of: dict[int, list[CohortEnrollment]] = {}
        ti = 0
        for c, kind in slots:
            t = all_trainees[ti]
            ti += 1
            dur = next(p.duration_months for p in programmes.values() if p.id == c.programme_id)
            ce = CohortEnrollment(
                cohort_id=c.id, user_id=t.id,
                enrolled_at=c.start_date,
                completed_at=(c.end_date if kind == "completed"
                              else c.end_date + timedelta(days=rnd.randint(10, 40))
                              if kind == "dropped" else None),
                cert_date=(c.end_date + timedelta(days=15) if kind == "completed" else None),
                status=kind)
            enrollments.append(ce)
            enrolled_of.setdefault(t.id, []).append(ce)
        # heroes into their scripted cohorts
        solar_prog = programmes["Solar PV Installer"]
        solar_cohort = cohort_key[("Solar PV Installer", 14)]
        ev_prog = programmes["EV Assembly Technician"]
        ev_cohort_15 = cohort_key[("EV Assembly Technician", 15)]
        for ce in enrollments:
            if ce.user_id in (priya.id, rahul.id):
                ce.status = "enrolled"  # placeholder; fixed below
        enrollments = [e for e in enrollments if e.user_id not in (priya.id, rahul.id)]
        enrollments.append(CohortEnrollment(
            cohort_id=solar_cohort.id, user_id=priya.id,
            enrolled_at=solar_cohort.start_date,
            completed_at=solar_cohort.end_date,
            cert_date=solar_cohort.end_date + timedelta(days=15),
            status="completed"))
        enrollments.append(CohortEnrollment(
            cohort_id=ev_cohort_15.id, user_id=rahul.id,
            enrolled_at=ev_cohort_15.start_date,
            completed_at=None, cert_date=None,
            status="completed" if False else "completed"))
        bulk_save(session, enrollments)
        # NOTE: Rahul IS a completer (completed but non-placed). completed_at set:
        with Session(engine) as fix:
            r_ce = fix.exec(select(CohortEnrollment).where(
                CohortEnrollment.user_id == rahul.id)).first()
            r_ce.completed_at = ev_cohort_15.end_date
            r_ce.cert_date = ev_cohort_15.end_date + timedelta(days=15)
            fix.add(r_ce)
            fix.commit()

        # --------------------------------------------------------- consents
        print("Seeding consents (90% broad, 10% narrow)...")
        consents = []
        for t in all_trainees:
            r = rnd.random()
            if r < 0.90:
                scopes = ["outcomes", "wage", "demographics", "skills"]
            elif r < 0.97:
                scopes = ["outcomes"]
            else:
                scopes = ["outcomes", "demographics"]
            consents.append(Consent(
                user_id=t.id, grantee_type="department", grantee_id=None,
                scopes=scopes, purpose="Longitudinal outcome tracking under MSEMP",
                granted_at=NOW - timedelta(days=rnd.randint(30, 400))))
            if rnd.random() < 0.5:
                consents.append(Consent(
                    user_id=t.id, grantee_type="provider",
                    grantee_id=None, scopes=["outcomes", "skills"],
                    purpose="Provider outcome feedback",
                    granted_at=NOW - timedelta(days=rnd.randint(30, 200))))
        bulk_save(session, consents)

        # ---------------------------------------------------- proficiencies
        print("Seeding trainee proficiencies (bulk)...")
        skill_ids = list(skill_by_name.values())
        domain_pools: dict[str, list[int]] = {}
        for s in skill_obj_by_name.values():
            domain_pools.setdefault(s.domain, []).append(s.id)

        profs: list[Proficiency] = []
        history: list[ProficiencyHistory] = []
        profs_by_key: dict[tuple[int, int], Proficiency] = {}
        hist_by_key: dict[tuple[int, int], ProficiencyHistory] = {}

        def add_prof(uid, sid, mu, src, months_stale, sigma=0.10):
            """Upsert-by-key within the seed: re-adding a (user, skill) updates it
            (e.g. Priya's gauntlet badge bump on an already-seeded skill) instead of
            violating the composite PK."""
            ts = NOW - timedelta(days=30.44 * months_stale)
            key = (uid, sid)
            if key in profs_by_key:
                p = profs_by_key[key]
                p.mu = round(mu, 3)
                p.sigma_sq = sigma
                p.source = src
                p.last_evidence_at = ts
                h = hist_by_key[key]
                h.mu = round(mu, 3)
                h.sigma_sq = sigma
                h.ts = ts
                return
            p = Proficiency(user_id=uid, skill_id=sid, mu=round(mu, 3),
                            sigma_sq=sigma, source=src, last_evidence_at=ts)
            h = ProficiencyHistory(user_id=uid, skill_id=sid, mu=round(mu, 3),
                                   sigma_sq=sigma, ts=ts)
            profs.append(p)
            history.append(h)
            profs_by_key[key] = p
            hist_by_key[key] = h

        sector_skill_pool = {}
        for dom, pool in domain_pools.items():
            sector_skill_pool[dom] = pool

        # programme -> representative skills (sector domain + general)
        prog_skills: dict[str, list[str]] = {}
        for (prov_idx, title, sector, nsqf, dur, cspecs) in PROGRAMMES:
            dom = sector
            pool = domain_pools.get(dom) or domain_pools["General"]
            names = [n for n, s in skill_obj_by_name.items() if s.id in pool]
            prog_skills[title] = (pool, names)

        for t in all_trainees:
            if t.id in (priya.id, rahul.id):
                continue
            ces = enrolled_of.get(t.id, [])
            if not ces:
                continue
            ce = ces[0]
            c = next(c for c in cohorts_all if c.id == ce.cohort_id)
            p = prog_of[c.programme_id]
            pool, names = prog_skills.get(p.title, (domain_pools["General"], []))
            n_skills = rnd.randint(4, 8)
            chosen = rnd.sample(pool, k=min(len(pool), n_skills))
            top = rnd.random() < 0.10
            for sid in chosen:
                if top:
                    mu = rnd.uniform(3.8, 4.7)
                elif rnd.random() < 0.15:
                    mu = rnd.uniform(3.0, 4.3)
                else:
                    mu = rnd.uniform(1.8, 3.5)
                stale = rnd.random() < 0.15 and ce.status == "completed"
                months = rnd.uniform(20, 30) if stale else rnd.uniform(0.2, 8)
                src = rnd.choice(["assessment", "assessment", "course", "gauntlet", "declared"])
                add_prof(t.id, sid, mu, src, months,
                         0.30 if src == "declared" else 0.10)
            # a couple of general skills for everyone
            for name in rnd.sample(["Communication", "Workplace Communication",
                                    "Teamwork", "Aptitude", "Documentation"], k=2):
                add_prof(t.id, skill_by_name[name], rnd.uniform(2.2, 4.2),
                         "course", rnd.uniform(0.5, 10))

        # HERO Priya: solar genome, fresh, strong
        priya_specs = [
            ("Solar PV Installation", 4.4, 0.10, "assessment", 0.4),
            ("Solar Site Survey", 4.0, 0.10, "course", 1.0),
            ("Solar Inverter Basics", 3.8, 0.10, "assessment", 1.2),
            ("Electrical Wiring", 3.9, 0.10, "assessment", 1.5),
            ("Industrial Documentation", 3.2, 0.10, "course", 2.0),
            ("Communication", 4.0, 0.10, "assessment", 0.6),
            ("Panel Wiring", 3.4, 0.10, "course", 3.0),
        ]
        for name, mu, sig, src, months in priya_specs:
            add_prof(priya.id, skill_by_name[name], mu, src, months, sig)
        # gauntlet-approved skill (badge bump; credential minted below)
        add_prof(priya.id, skill_by_name["Solar PV Installation"], 4.6, "gauntlet", 0.3)

        # HERO Rahul: EV genome with the scripted gap (Battery Diagnostics 2.1 vs 3.5)
        rahul_specs = [
            ("Battery Diagnostics", 2.1, 0.10, "assessment", 1.0),
            ("EV Powertrain", 2.8, 0.10, "assessment", 1.0),
            ("Engine Basics", 3.0, 0.10, "course", 2.0),
            ("Assembly Line Operations", 3.2, 0.10, "assessment", 2.5),
            ("Industrial Documentation", 1.8, 0.30, "declared", 4.0),
            ("Communication", 2.6, 0.10, "course", 3.0),
        ]
        for name, mu, sig, src, months in rahul_specs:
            add_prof(rahul.id, skill_by_name[name], mu, src, months, sig)
        bulk_save(session, profs)
        bulk_save(session, history)

        # --------------------------------------------------------------- items
        print("Seeding item bank...")
        items_data = json.loads((DATA_DIR / "items.json").read_text(encoding="utf-8"))
        item_rows = []
        for block in items_data:
            sid = skill_by_name.get(block["skill"])
            if sid is None:
                continue
            skill_type = ("soft" if block["skill"] == "Communication"
                          else "aptitude" if block["skill"] == "Aptitude"
                          else "technical")
            for it in block["items"]:
                item_rows.append(Item(
                    skill_id=sid, stem=it["stem"], options=it["options"],
                    correct_idx=it["correct_idx"], a=it["a"], b=it["b"],
                    calibrated=True, skill_type=skill_type))
        bulk_save(session, item_rows)

        # ------------------------------------------------- employment episodes
        print("Seeding employment episodes + wage events (scripted)...")
        episode_rows: list[EmploymentEpisode] = []
        wage_rows: list[WageEvent] = []
        episode_meta: dict[int, dict] = {}  # id -> {kind: 'hero'|'general', cohort, churn, user}

        def cohort_completers(c: Cohort) -> list[int]:
            return [ce.user_id for ce in enrollments
                    if ce.cohort_id == c.id and ce.status == "completed"]

        def pick_company_for_district(sector: str, district_name: str):
            cands = [c for c in companies
                     if c.sector == sector and c.city == district_name] or \
                    [c for c in companies if c.sector == sector] or companies
            return rnd.choice(cands)

        def district_id_of_programme(p: Programme):
            prov = next(pr for pr in providers if pr.id == p.provider_id)
            return prov.district_id

        def add_episode(uid, c: Cohort, p: Programme, start_offset_days,
                        end_after_months=None, etype="wage",
                        wage_start=None, wage_growth=0.08, wage_months=13,
                        source="self_report", validation="validated",
                        company=None, role=""):
            nonlocal episode_rows, wage_rows
            start = c.end_date + timedelta(days=start_offset_days)
            end = None
            if end_after_months is not None:
                end = start + timedelta(days=30.44 * end_after_months)
            if company is None:
                d_name = DISTRICTS[0][0]
                prov = next(pr for pr in providers if pr.id == p.provider_id)
                d_name = next(d.name for d in districts if d.id == prov.district_id)
                company = pick_company_for_district(p.sector, d_name)
            d_id = company.district_id
            ep = EmploymentEpisode(
                user_id=uid, cohort_id=c.id, company_id=company.id,
                employment_type=etype, role_title=role or f"{p.title} - {etype.replace('_', ' ').title()}",
                district_id=d_id, start_date=start, end_date=end,
                monthly_wage_start=wage_start,
                monthly_wage_current=round(wage_start * (1 + wage_growth), -2) if wage_start else None,
                status="active" if end is None else "ended",
                source=source, validation_status=validation,
                created_at=datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
                updated_at=NOW,
            )
            episode_rows.append(ep)
            # NOTE: wage events are generated by add_episode_tracked (pending_wages)
            # so episode_id can be patched with real PKs after the bulk insert.
            return ep

        # wage_rows need episode ids -> track pending (ep_index, month_index, wage)
        pending_wages: list[tuple[int, int, float, str]] = []

        def add_episode_tracked(uid, c, p, start_offset_days, end_after_months,
                                etype, wage_start, wage_growth, wage_months,
                                source, validation, company=None, role=""):
            idx_before = len(episode_rows)
            ep = add_episode(uid, c, p, start_offset_days, end_after_months, etype,
                             wage_start, wage_growth, wage_months, source, validation,
                             company, role)
            if wage_start is not None:
                months_elapsed = max(0, (TODAY.year - ep.start_date.year) * 12 + (TODAY.month - ep.start_date.month))
                n_points = min(wage_months, months_elapsed)
                for m in range(n_points + 1):
                    if end_after_months is not None and m > end_after_months:
                        break
                    w = round(wage_start * (1 + wage_growth * (m / max(wage_months, 1))), -2)
                    pending_wages.append((idx_before, m, w, source))
            return ep

        # ---- HERO: EV Assembly Technician @ ITI Nashik (vanity-metric story)
        ev_p = programmes["EV Assembly Technician"]
        ev_specs = {15: ev_cohort_15, 12: cohort_key[("EV Assembly Technician", 12)]}
        for m_ago, cohort in ev_specs.items():
            completers = cohort_completers(cohort)
            n = len(completers)  # 60
            placed0 = round(n * 0.92)          # 55
            placed = completers[:placed0]
            if m_ago == 15:
                # 26 long (retained), 21 churn+replacement, 8 churn-no-replacement
                long_n, churn_rep, churn_norep = 26, 21, 8
                for i, uid in enumerate(placed):
                    if i < long_n:
                        add_episode_tracked(uid, cohort, ev_p, rnd.randint(5, 28), None,
                                            "wage", rnd.choice([13000, 13500, 14000, 14500, 15000]),
                                            0.04, 14, "self_report",
                                            "validated" if rnd.random() < 0.60 else "unvalidated")
                    elif i < long_n + churn_rep:
                        ep = add_episode_tracked(uid, cohort, ev_p, rnd.randint(5, 28),
                                                 rnd.uniform(4, 8), "wage",
                                                 rnd.choice([12500, 13000, 14000]), 0.03, 8,
                                                 "self_report", "validated" if rnd.random() < 0.6 else "unvalidated")
                        # replacement job
                        add_episode_tracked(uid, cohort, ev_p, rnd.randint(10, 25), None,
                                            "wage", rnd.choice([13000, 14000]), 0.03, 6,
                                            "self_report", "unvalidated")
                    else:
                        add_episode_tracked(uid, cohort, ev_p, rnd.randint(5, 28),
                                            rnd.uniform(4, 8), "wage",
                                            rnd.choice([12500, 13000, 14000]), 0.02, 8,
                                            "self_report", "validated" if rnd.random() < 0.6 else "unvalidated")
            else:  # -12 months cohort: episodes start 7-30d after completion (all < 12mo old)
                active_now = round(n * 0.78)        # 47
                for i, uid in enumerate(placed):
                    if i < active_now:
                        add_episode_tracked(uid, cohort, ev_p, rnd.randint(7, 30), None,
                                            "wage", rnd.choice([13000, 14000, 15000]),
                                            0.03, 11, "self_report",
                                            "validated" if rnd.random() < 0.62 else "unvalidated")
                    else:
                        add_episode_tracked(uid, cohort, ev_p, rnd.randint(7, 30),
                                            rnd.uniform(2, 5), "wage",
                                            rnd.choice([12500, 13500]), 0.02, 5,
                                            "self_report", "unvalidated")

        # ---- HERO: Solar PV Installer @ ITI Pune (OQI ~87)
        solar_specs = {14: solar_cohort}
        for m_ago, cohort in solar_specs.items():
            completers = cohort_completers(cohort)
            n = len(completers)
            placed0 = round(n * 0.85)  # 51
            placed = completers[:placed0]
            long_n, churn_rep = 42, 6   # retention 42/51 = 82.4%
            for i, uid in enumerate(placed):
                if uid == priya.id:
                    continue  # scripted below
                if i < long_n:
                    add_episode_tracked(uid, cohort, programmes["Solar PV Installer"],
                                        rnd.randint(5, 30), None, "wage",
                                        rnd.choice([13500, 14000, 14500, 15000]),
                                        0.30, 13, "self_report",
                                        "validated" if rnd.random() < 0.85 else "unvalidated")
                else:
                    add_episode_tracked(uid, cohort, programmes["Solar PV Installer"],
                                        rnd.randint(5, 30), rnd.uniform(6, 10), "wage",
                                        rnd.choice([13000, 14000]), 0.05, 8,
                                        "self_report", "validated")
                    add_episode_tracked(uid, cohort, programmes["Solar PV Installer"],
                                        rnd.randint(16, 26), None, "wage",
                                        rnd.choice([14000, 15000]), 0.05, 5,
                                        "self_report", "unvalidated")
            # Priya: SunRay Energy, 14k -> 19.5k rising curve, PENDING validation
            add_episode_tracked(priya.id, cohort, programmes["Solar PV Installer"],
                                12, None, "wage", 14000, 0.40, 14,
                                "self_report", "pending",
                                company=sunray, role="Solar PV Installation Technician")

        # ---- HERO: Textile Machine Operator @ ITI Solapur (oversupplied + obsolete)
        textile_p = programmes["Textile Machine Operator"]
        for m_ago in (12, 9, 6):
            cohort = cohort_key[("Textile Machine Operator", m_ago)]
            completers = cohort_completers(cohort)
            n = len(completers)
            placed0 = round(n * 0.55)
            placed = completers[:placed0]
            long_n = round(placed0 * 0.42)  # ~40% placement_12
            for i, uid in enumerate(placed):
                if i < long_n:
                    add_episode_tracked(uid, cohort, textile_p, rnd.randint(5, 30), None,
                                        "wage", rnd.choice([11000, 12000, 13000]),
                                        0.06, 12, "self_report",
                                        "validated" if rnd.random() < 0.7 else "unvalidated")
                else:
                    add_episode_tracked(uid, cohort, textile_p, rnd.randint(5, 30),
                                        rnd.uniform(2, 6), "wage",
                                        rnd.choice([10500, 11500]), 0.03, 6,
                                        "self_report", "validated" if rnd.random() < 0.7 else "unvalidated")

        # ---- HERO: Beauty & Wellness Entrepreneur (55% self-employment, rising income)
        beauty_p = programmes["Beauty & Wellness Entrepreneur"]
        for m_ago in (15, 9):
            cohort = cohort_key[("Beauty & Wellness Entrepreneur", m_ago)]
            completers = cohort_completers(cohort)
            n = len(completers)
            placed0 = round(n * 0.80)
            placed = completers[:placed0]
            self_n = round(placed0 * 0.69)  # ~55% of all completers
            for i, uid in enumerate(placed):
                if i < self_n:
                    add_episode_tracked(uid, cohort, beauty_p, rnd.randint(10, 45), None,
                                        "self_employed", rnd.choice([9000, 10000, 11000, 12000]),
                                        0.45, 12, "self_report", "unvalidated")
                elif i < self_n + round(placed0 * 0.25):
                    add_episode_tracked(uid, cohort, beauty_p, rnd.randint(5, 30), None,
                                        "wage", rnd.choice([11000, 12000, 13000]),
                                        0.10, 12, "self_report",
                                        "validated" if rnd.random() < 0.75 else "unvalidated")
                else:
                    add_episode_tracked(uid, cohort, beauty_p, rnd.randint(5, 30),
                                        rnd.uniform(3, 8), "wage",
                                        rnd.choice([10000, 11000]), 0.04, 6,
                                        "self_report", "unvalidated")

        # ---- HERO: Welder @ Sambhajinagar (apprenticeship cluster)
        welder_p = programmes["Welder (SMAW/MIG)"]
        for m_ago in (12, 6):
            cohort = cohort_key[("Welder (SMAW/MIG)", m_ago)]
            completers = cohort_completers(cohort)
            n = len(completers)
            placed0 = round(n * 0.78)
            placed = completers[:placed0]
            app_n = round(placed0 * 0.70)
            for i, uid in enumerate(placed):
                if i < app_n:
                    start = cohort.end_date + timedelta(days=rnd.randint(5, 30))
                    add_episode_tracked(uid, cohort, welder_p, rnd.randint(5, 30),
                                        (None if m_ago == 12 and i % 2 == 0 else rnd.uniform(8, 12)),
                                        "apprenticeship", None, 0.0, 0,
                                        "self_report", "unvalidated")
                else:
                    add_episode_tracked(uid, cohort, welder_p, rnd.randint(5, 30), None,
                                        "wage", rnd.choice([13000, 14000, 15000]),
                                        0.12, 12, "self_report",
                                        "validated" if rnd.random() < 0.75 else "unvalidated")

        # ---- Generic programmes: simple realistic distributions
        scripted_titles = {"EV Assembly Technician", "Solar PV Installer",
                           "Textile Machine Operator", "Beauty & Wellness Entrepreneur",
                           "Welder (SMAW/MIG)"}
        for (prov_idx, title, sector, nsqf, dur, cspecs) in PROGRAMMES:
            if title in scripted_titles:
                continue
            p = programmes[title]
            for (m_ago, completers, dropped, active) in cspecs:
                cohort = cohort_key[(title, m_ago)]
                comps = cohort_completers(cohort)
                rnd.shuffle(comps)
                placed0 = round(len(comps) * rnd.uniform(0.62, 0.80))
                placed = comps[:placed0]
                long_n = round(placed0 * rnd.uniform(0.62, 0.75))
                for i, uid in enumerate(placed):
                    roll = rnd.random()
                    etype = "wage" if roll < 0.68 else "self_employed" if roll < 0.80 \
                        else "apprenticeship" if roll < 0.90 else "higher_study"
                    wage0 = rnd.choice([10000, 11000, 12000, 13000, 14000, 15000])
                    if i < long_n:
                        add_episode_tracked(uid, cohort, p, rnd.randint(5, 40), None,
                                            etype, wage0 if etype in ("wage", "self_employed") else None,
                                            rnd.uniform(0.05, 0.18), 12, "self_report",
                                            "validated" if rnd.random() < 0.82 and etype == "wage" else "unvalidated")
                    else:
                        add_episode_tracked(uid, cohort, p, rnd.randint(5, 40),
                                            rnd.uniform(2, 7), etype,
                                            wage0 if etype in ("wage", "self_employed") else None,
                                            0.04, 6, "self_report",
                                            "validated" if rnd.random() < 0.8 and etype == "wage" else "unvalidated")

        # insert episodes, then patch wage events with real ids
        bulk_save(session, episode_rows)
        # bulk_save_objects does not populate PKs -> re-fetch and align by id order:
        # episode_rows were inserted in order, so the k-th row maps to the k-th lowest id
        # within this seed run (fresh table, no concurrent writers).
        all_eps = session.exec(select(EmploymentEpisode).order_by(EmploymentEpisode.id)).all()
        assert len(all_eps) >= len(episode_rows), "episode insert count mismatch"
        offset = len(all_eps) - len(episode_rows)
        for idx, m, w, source in pending_wages:
            ep = all_eps[offset + idx]
            wage_rows.append(WageEvent(episode_id=ep.id, month_index=m,
                                       monthly_wage=w, source=source,
                                       recorded_at=NOW))
        print(f"   episodes={len(episode_rows)} wage_events={len(wage_rows)}")
        bulk_save(session, wage_rows)

        # ---- scripted skill-gap + k-anonymity post-pass (deterministic reveal) ----
        # Non-placed EV completers systematically lack Battery Diagnostics (req 3.5)
        # and Industrial Documentation (req 3.0) -> the drill-down gap panel names them.
        ev_prog_obj = programmes["EV Assembly Technician"]
        ev_cohort_ids = {c.id for c in cohorts_all if c.programme_id == ev_prog_obj.id}
        placed_positive = {e.user_id for e in all_eps if e.employment_type
                           in ("wage", "self_employed", "apprenticeship")}
        ev_completers = [ce.user_id for ce in enrollments
                         if ce.cohort_id in ev_cohort_ids and ce.status == "completed"]
        ev_nonplaced = [u for u in ev_completers if u not in placed_positive
                        and u not in (priya.id, rahul.id)]
        bd_id = skill_by_name["Battery Diagnostics"]
        idoc_id = skill_by_name["Industrial Documentation"]
        with Session(engine) as fx:
            for uid in ev_nonplaced:
                for sid, lo, hi, sig, src in ((bd_id, 1.3, 2.9, 0.10, "assessment"),
                                              (idoc_id, 1.0, 2.4, 0.30, "declared")):
                    mu = round(rnd.uniform(lo, hi), 2)
                    ts_ = NOW - timedelta(days=rnd.randint(15, 60))
                    p_ = fx.exec(select(Proficiency).where(
                        Proficiency.user_id == uid, Proficiency.skill_id == sid)).first()
                    if p_ is not None:
                        p_.mu, p_.sigma_sq, p_.source, p_.last_evidence_at = mu, sig, src, ts_
                        fx.add(p_)
                    else:
                        fx.add(Proficiency(user_id=uid, skill_id=sid, mu=mu,
                                           sigma_sq=sig, source=src, last_evidence_at=ts_))
                    fx.add(ProficiencyHistory(user_id=uid, skill_id=sid, mu=mu,
                                              sigma_sq=sig, ts=ts_))
            # guarantee a k-anonymity demo cell: exactly 4 EV completers -> 'st'
            # (normalize any existing ST members out first so the cell is exactly n=4)
            st_ids = [u for u in ev_completers if u not in (priya.id, rahul.id)]
            for uid in st_ids:
                tp_ = fx.exec(select(TraineeProfile).where(
                    TraineeProfile.user_id == uid)).first()
                if tp_ is not None and tp_.social_category == "st":
                    tp_.social_category = "obc"
                    fx.add(tp_)
            for uid in st_ids[:4]:
                tp_ = fx.exec(select(TraineeProfile).where(
                    TraineeProfile.user_id == uid)).first()
                if tp_ is not None:
                    tp_.social_category = "st"
                    fx.add(tp_)
            fx.commit()

        # leave 4-6 pending validations overall (Priya's + a few)
        pending_eps = [e for e in all_eps if e.validation_status == "validated"]
        for e in pending_eps[:5]:
            e.validation_status = "pending"
            session.add(e)
        session.commit()

        # --------------------------------------------------- follow-up waves
        print("Seeding follow-up waves & attempts (F ~ 0.80-0.85)...")
        wave_rows: list[FollowupWave] = []
        attempt_rows: list[FollowupAttempt] = []
        wave_meta: list[tuple[FollowupWave, Cohort, float]] = []

        for (prov_idx, title, sector, nsqf, dur, cspecs) in PROGRAMMES:
            p = programmes[title]
            for (m_ago, completers, dropped, active) in cspecs:
                cohort = cohort_key[(title, m_ago)]
                comps = cohort_completers(cohort)
                for milestone in (3, 6, 12, 24):
                    due = cohort.end_date + timedelta(days=30.44 * milestone)
                    if due > TODAY:
                        if rnd.random() < 0.25:
                            w = FollowupWave(cohort_id=cohort.id, milestone_months=milestone,
                                             due_on=due, kind="scheduled", status="pending",
                                             created_at=NOW)
                            wave_rows.append(w)
                        continue
                    w = FollowupWave(cohort_id=cohort.id, milestone_months=milestone,
                                     due_on=due, kind="scheduled", status="active",
                                     created_at=datetime.combine(due, datetime.min.time(), tzinfo=timezone.utc))
                    wave_rows.append(w)
                    if title == "EV Assembly Technician":
                        f_target = 0.75
                    elif title == "Solar PV Installer":
                        f_target = 0.82
                    else:
                        f_target = rnd.uniform(0.80, 0.86)
                    wave_meta.append((w, cohort, f_target))
        bulk_save(session, wave_rows)
        # re-fetch waves to get ids
        all_waves = session.exec(select(FollowupWave)).all()
        wave_by_sig = {(w.cohort_id, w.milestone_months, w.kind): w for w in all_waves}

        response_mix = ["wage", "wage", "wage", "self_employed", "apprenticeship",
                        "higher_study", "unemployed"]
        nonrespond_budget = 30
        npr_codes = ["skills_mismatch", "no_local_openings", "family_caregiving",
                     "health", "pursued_education", "wage_below_expectations"]
        nashik_attrition = (["wage_below_expectations"] * 41 + ["sector_downturn"] * 18 +
                            ["skill_mismatch"] * 15 + ["migration"] * 12 + ["other"] * 14)
        for w, cohort, f_target in wave_meta:
            real_wave = wave_by_sig[(w.cohort_id, w.milestone_months, w.kind)]
            comps = cohort_completers(cohort)
            if not comps:
                continue
            responded_n = round(len(comps) * f_target)
            # decide non-responders: prefer recent cohorts so some remain open >14d
            nonrespond_idx = set()
            if nonrespond_budget > 0 and (TODAY - w.due_on).days <= 45:
                k = min(nonrespond_budget, len(comps) - responded_n)
                nonrespond_idx = set(rnd.sample(range(len(comps)), k))
                nonrespond_budget -= k
            title_p = prog_of[cohort.programme_id].title
            for i, uid in enumerate(comps):
                if i in nonrespond_idx:
                    attempt_rows.append(FollowupAttempt(
                        wave_id=real_wave.id, user_id=uid, method="one_tap",
                        attempted_at=datetime.combine(max(w.due_on, TODAY - timedelta(days=rnd.randint(16, 40))),
                                                      datetime.min.time(), tzinfo=timezone.utc)))
                    continue
                resp = rnd.choice(response_mix)
                responded_at = datetime.combine(
                    w.due_on + timedelta(days=rnd.randint(1, 18)),
                    datetime.min.time(), tzinfo=timezone.utc)
                codes = None
                if title_p == "EV Assembly Technician" and (resp == "unemployed" or rnd.random() < 0.35):
                    codes = [rnd.choice(nashik_attrition)]
                elif resp == "unemployed":
                    codes = [rnd.choice(npr_codes)]
                elif title_p == "Textile Machine Operator" and rnd.random() < 0.3:
                    codes = ["wage_below_expectations"]
                attempt_rows.append(FollowupAttempt(
                    wave_id=real_wave.id, user_id=uid, method="one_tap",
                    response=resp,
                    reason_codes=codes,
                    responded_at=responded_at,
                    attempted_at=datetime.combine(w.due_on, datetime.min.time(), tzinfo=timezone.utc)))
        print(f"   waves={len(wave_rows)} attempts={len(attempt_rows)}")
        bulk_save(session, attempt_rows)

        # Rahul: non-placed with reason codes (attempt on his cohort's wave)
        ev_wave = wave_by_sig.get((ev_cohort_15.id, 12, "scheduled")) or \
            wave_by_sig.get((ev_cohort_15.id, 6, "scheduled"))
        # Rahul's non-placement episode (unemployed, active, self-reported)
        rahul_start = ev_cohort_15.end_date + timedelta(days=7)
        rahul_ep = EmploymentEpisode(
            user_id=rahul.id, cohort_id=ev_cohort_15.id, company_id=None,
            employment_type="unemployed", role_title="Seeking EV Service Technician role",
            district_id=None, start_date=rahul_start, end_date=None,
            monthly_wage_start=None, monthly_wage_current=None,
            status="active", source="self_report", validation_status="unvalidated",
            created_at=datetime.combine(rahul_start, datetime.min.time(), tzinfo=timezone.utc),
            updated_at=NOW)
        session.add(rahul_ep)
        session.flush()  # PK assigned (single add, not bulk)
        if ev_wave is not None:
            session.add(FollowupAttempt(
                wave_id=ev_wave.id, user_id=rahul.id, method="one_tap",
                response="unemployed", episode_id=rahul_ep.id,
                reason_codes=["skills_mismatch", "no_local_openings",
                              "wage_below_expectations"],
                notes="Looking for EV service roles near Nashik",
                responded_at=datetime.combine(ev_wave.due_on + timedelta(days=5),
                                              datetime.min.time(), tzinfo=timezone.utc),
                attempted_at=datetime.combine(ev_wave.due_on, datetime.min.time(),
                                              tzinfo=timezone.utc)))
        session.commit()

        # ---------------------------------------------------------- postings
        print("Seeding ~300 postings (+ requirements)...")
        opp_rows: list[Opportunity] = []
        titles_by_sector = {
            "Auto & EV": ["EV Assembly Operator", "EV Service Technician",
                          "Battery Pack Technician", "Auto Electrician"],
            "Manufacturing": ["CNC Operator", "Welder", "Fitter", "QC Inspector",
                              "Maintenance Technician"],
            "Solar & Renewables": ["Solar PV Installer", "Solar O&M Technician",
                                   "Field Service Engineer"],
            "Textiles": ["Textile Machine Operator", "Fabric Checker",
                         "Stitching Operator", "Dyeing Assistant"],
            "Logistics": ["Warehouse Assistant", "Forklift Operator",
                          "Delivery Coordinator", "Documentation Executive"],
            "IT-ITeS": ["IT Support Executive", "Data Entry Operator",
                        "Customer Support Associate"],
            "Retail": ["Retail Sales Associate", "Store Assistant", "Billing Executive"],
            "Healthcare": ["Healthcare Assistant", "Lab Assistant", "Home Health Aide"],
            "Agriculture & Allied": ["Food Processing Operator", "Dairy Assistant",
                                     "Greenhouse Assistant"],
            "Construction": ["Mason", "Site Helper", "Plumbing Assistant"],
            "Beauty & Wellness": ["Beautician", "Spa Therapist", "Salon Assistant"],
            "Electrical": ["Electrician", "Panel Wiring Technician"],
            "Tourism & Hospitality": ["Front Office Assistant", "F&B Service Attendant"],
        }
        kinds = ["job", "job", "internship", "apprenticeship", "live_project"]

        def add_postings_for_company(comp, count, sector_titles, status="open",
                                     days_back_range=(0, 45)):
            for _ in range(count):
                title = rnd.choice(sector_titles)
                opp_rows.append(Opportunity(
                    company_id=comp.id, kind=rnd.choice(kinds), title=title,
                    description=f"{comp.name} ({comp.city}) is hiring a {title}. "
                                "ExcelUp AI-verified skills preferred.",
                    location=comp.city,
                    stipend=rnd.choice(["", "₹9,000/month", "₹12,000/month",
                                        "₹15,000/month", "₹18,000/month"]),
                    duration=rnd.choice(["6 months", "1 year", "Full-time"]),
                    status=status,
                    posted_at=NOW - timedelta(days=rnd.randint(*days_back_range))))

        # Textiles YoY: many old postings (13-23 months), fewer recent → -25% YoY
        textile_comps = [c for c in companies if c.sector == "Textiles"]
        for c in textile_comps:
            add_postings_for_company(c, 4, titles_by_sector["Textiles"],
                                     status="closed", days_back_range=(400, 690))
            add_postings_for_company(c, 3, titles_by_sector["Textiles"],
                                     status="open", days_back_range=(0, 45))
        # EV growing (contrast)
        for c in [c for c in companies if c.sector == "Auto & EV"]:
            add_postings_for_company(c, 3, titles_by_sector["Auto & EV"],
                                     status="closed", days_back_range=(400, 690))
            add_postings_for_company(c, 5, titles_by_sector["Auto & EV"])
        # everyone else: balanced
        for c in companies:
            if c.sector in ("Textiles", "Auto & EV"):
                continue
            titles = titles_by_sector.get(c.sector, titles_by_sector["Manufacturing"])
            add_postings_for_company(c, 2, titles, status="closed", days_back_range=(400, 690))
            add_postings_for_company(c, 2, titles)
        # hero postings (exact)
        hero_ev_tech = Opportunity(
            company_id=ev_motors.id, kind="job", title="EV Service Technician",
            description=("EV Motors Maharashtra (Nashik) hiring EV service technicians. "
                         "Battery diagnostics at 3.5+ level required: pack testing, "
                         "SoC/SoH analysis, insulation tests. ITI/Diploma with EV "
                         "training preferred."),
            location="Nashik", stipend="₹18,000/month", duration="Full-time",
            status="open", posted_at=NOW - timedelta(days=6))
        hero_solar_tech = Opportunity(
            company_id=sunray.id, kind="job", title="Solar PV O&M Technician",
            description=("SunRay Energy (Pune) field O&M role: rooftop PV servicing, "
                         "inverter troubleshooting, net-metering compliance checks."),
            location="Pune", stipend="₹17,000/month", duration="Full-time",
            status="open", posted_at=NOW - timedelta(days=4))
        opp_rows.extend([hero_ev_tech, hero_solar_tech])
        bulk_save(session, opp_rows)

        all_opps = session.exec(select(Opportunity)).all()
        hero_ev_tech = next(o for o in all_opps if o.title == "EV Service Technician"
                            and o.company_id == ev_motors.id)
        hero_solar_tech = next(o for o in all_opps if o.title == "Solar PV O&M Technician")

        req_rows: list[OppRequirement] = []
        skill_obj_by_id = {s.id: s for s in skill_obj_by_name.values()}
        for o in all_opps:
            if o.kind == "gauntlet":
                continue
            comp = next(c for c in companies if c.id == o.company_id)
            sector = comp.sector
            domain = sector if sector in domain_pools else (
                "Auto & EV" if sector == "Auto & EV" else "General")
            pool = domain_pools.get(domain) or domain_pools["General"]
            picks = rnd.sample(pool, k=min(len(pool), rnd.randint(2, 4)))
            picks += rnd.sample(domain_pools["General"], k=rnd.randint(0, 2))
            essential = True
            for sid in dict.fromkeys(picks):
                req_rows.append(OppRequirement(
                    opp_id=o.id, skill_id=sid,
                    min_level=round(rnd.uniform(2.5, 4.2), 1),
                    weight=round(rnd.uniform(1.0, 3.0), 1),
                    essential=essential))
                essential = False
        # hero requirement scripting
        for req in list(req_rows):
            pass
        def upsert_req(opp_id, skill_name, min_level, weight, essential):
            req_rows[:] = [r for r in req_rows
                           if not (r.opp_id == opp_id and r.skill_id == skill_by_name[skill_name])]
            req_rows.append(OppRequirement(opp_id=opp_id, skill_id=skill_by_name[skill_name],
                                           min_level=min_level, weight=weight, essential=essential))
        upsert_req(hero_ev_tech.id, "Battery Diagnostics", 3.5, 3.0, True)
        upsert_req(hero_ev_tech.id, "Industrial Documentation", 3.0, 1.5, False)
        upsert_req(hero_ev_tech.id, "EV Powertrain", 3.0, 2.0, False)
        upsert_req(hero_solar_tech.id, "Solar PV Installation", 4.0, 3.0, True)
        upsert_req(hero_solar_tech.id, "Solar Inverter Basics", 3.5, 2.0, False)
        bulk_save(session, req_rows)

        # employer validation challenges (gauntlets, secondary flow)
        gauntlet1 = Opportunity(
            company_id=sunray.id, kind="gauntlet",
            title="Solar PV Site Safety Challenge",
            description=("Submit a site-safety protocol for a 5 kW rooftop install: "
                         "hazard assessment, PPE plan, lockout steps, earthing checks. "
                         "Reviewed by SunRay Energy engineers."),
            location="Remote", stipend="", duration="2 weeks",
            rubric={"criteria": [
                {"name": "Hazard assessment", "weight": 0.3},
                {"name": "PPE & lockout plan", "weight": 0.3},
                {"name": "Earthing/documentation", "weight": 0.25},
                {"name": "Clarity", "weight": 0.15}]},
            status="open", posted_at=NOW - timedelta(days=10))
        gauntlet2 = Opportunity(
            company_id=ev_motors.id, kind="gauntlet",
            title="EV Battery Diagnostics Challenge",
            description=("Analyze the provided battery pack test log: identify the "
                         "faulty module, justify with SoC/SoH math, propose a "
                         "remediation plan."),
            location="Remote", stipend="", duration="2 weeks",
            rubric={"criteria": [
                {"name": "Fault identification", "weight": 0.4},
                {"name": "Analysis quality", "weight": 0.3},
                {"name": "Remediation plan", "weight": 0.3}]},
            status="open", posted_at=NOW - timedelta(days=8))
        session.add_all([gauntlet1, gauntlet2])
        session.commit()
        for g in (gauntlet1, gauntlet2):
            session.refresh(g)
        req_rows = [
            OppRequirement(opp_id=gauntlet1.id, skill_id=skill_by_name["Solar PV Installation"],
                           min_level=4.0, weight=3.0, essential=True),
            OppRequirement(opp_id=gauntlet2.id, skill_id=skill_by_name["Battery Diagnostics"],
                           min_level=3.5, weight=3.0, essential=True),
        ]
        bulk_save(session, req_rows)

        # ------------------------------------------------------------- courses
        print("Seeding courses & roadmaps...")
        courses_data = json.loads((DATA_DIR / "courses.json").read_text(encoding="utf-8"))
        course_rows = [Course(**c) for c in courses_data]
        bulk_save(session, course_rows)
        course_rows = session.exec(select(Course)).all()  # populate PKs
        roads_data = json.loads((DATA_DIR / "roadmaps.json").read_text(encoding="utf-8"))
        road_rows = [Roadmap(title=r["title"], from_role=r["from_role"],
                             to_role=r["to_role"], steps=r["steps"]) for r in roads_data]
        bulk_save(session, road_rows)

        # enrollments: Priya completed one course + active one; a few generic
        enroll_rows = [
            Enrollment(user_id=priya.id, course_id=course_rows[2].id, progress=100.0,
                       status="completed", completed_at=NOW - timedelta(days=200)),
            Enrollment(user_id=priya.id, course_id=course_rows[3].id, progress=0.5,
                       status="active"),
            Enrollment(user_id=rahul.id, course_id=course_rows[0].id, progress=0.5,
                       status="active"),
        ]
        bulk_save(session, enroll_rows)

        # ---------------------------------------- artifacts / applications / gauntlets
        print("Seeding artifacts, applications, gauntlet submissions, credentials...")
        art_priya_gauntlet = Artifact(
            user_id=priya.id, kind="gauntlet",
            title="Solar PV Site Safety Challenge - approved by SunRay Energy",
            payload={"skills": ["Solar PV Installation"], "level": 4.0,
                     "submission_url": "https://drive.demo/priya-solar-safety",
                     "reviewer": "Ravi Deshpande (HR, SunRay Energy)"},
            verification="verified", created_at=NOW - timedelta(days=25))
        art_priya_project = Artifact(
            user_id=priya.id, kind="project",
            title="Village electrification awareness camp (Kolhapur)",
            payload={"skills": ["Solar PV Installation", "Communication"],
                     "summary": "Volunteer field camp"},
            verification="pending", created_at=NOW - timedelta(days=12))
        art_rahul = Artifact(
            user_id=rahul.id, kind="project",
            title="EV assembly line internship report",
            payload={"skills": ["EV Powertrain", "Assembly Line Operations"]},
            verification="pending", created_at=NOW - timedelta(days=30))
        bulk_save(session, [art_priya_gauntlet, art_priya_project, art_rahul])
        # bulk_save_objects does not populate PKs -> re-fetch for the mint step
        art_priya_gauntlet = session.exec(select(Artifact).where(
            Artifact.user_id == priya.id, Artifact.kind == "gauntlet",
            Artifact.title.like("Solar PV Site Safety%"))).first()

        # applications: a few trainees on hero postings (pipeline demo)
        app_rows = []
        pipeline = ["applied", "viewed", "shortlisted", "interviewed", "offered"]
        others = [t for t in all_trainees if t.id not in (priya.id, rahul.id)]
        for i in range(5):
            app_rows.append(Application(opp_id=hero_ev_tech.id, user_id=others[i].id,
                                        score=45 + i * 8, explanation={},
                                        status=pipeline[i], created_at=NOW - timedelta(days=i + 1),
                                        updated_at=NOW - timedelta(days=i + 1)))
        for i in range(4):
            app_rows.append(Application(opp_id=hero_solar_tech.id, user_id=others[10 + i].id,
                                        score=50 + i * 7, explanation={},
                                        status=pipeline[i], created_at=NOW - timedelta(days=i + 2),
                                        updated_at=NOW - timedelta(days=i + 2)))
        # Priya applied to the solar O&M posting (viewed) - her placement was via cohort
        app_rows.append(Application(opp_id=hero_solar_tech.id, user_id=priya.id,
                                    score=78.0, explanation={}, status="applied",
                                    created_at=NOW - timedelta(days=2), updated_at=NOW - timedelta(days=2)))
        bulk_save(session, app_rows)

        # gauntlet submissions: Priya's approved + 2 pending for review beat
        sub_rows = [
            GauntletSubmission(opp_id=gauntlet1.id, user_id=priya.id,
                               submission_url="https://drive.demo/priya-solar-safety",
                               writeup="Site safety protocol with hazard matrix, PPE plan "
                                       "and earthing checklist for 5 kW rooftop.",
                               status="approved", reviewer_id=users_by_email["hr@sunray.demo"].id,
                               reviewed_at=NOW - timedelta(days=24)),
        ]
        for s in others[:2]:
            sub_rows.append(GauntletSubmission(
                opp_id=gauntlet1.id, user_id=s.id,
                submission_url=f"https://drive.demo/{s.id}-solar-safety",
                writeup="Solar PV site safety protocol submission.", status="submitted"))
        bulk_save(session, sub_rows)

        # ------------------------------------------------- credentials + merkle
        print("Seeding credential + Merkle batch...")
        from app.services.credentials import (
            batch_merkle, credential_payload, generate_keypair, mint_credential,
        )

        pub, sec = generate_keypair()
        session.add(Event(aggregate_type="crypto", aggregate_id=0,
                          event_type="server_keypair",
                          payload={"public_key": pub, "secret_key": sec,
                                   "algo": "Ed25519"}))
        session.commit()

        async def _mint_all():
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

            e = create_async_engine(settings.async_url, pool_pre_ping=True)
            maker = async_sessionmaker(e, expire_on_commit=False)
            async with maker() as sess:
                payload = credential_payload(
                    "Priya Patil", "SunRay Energy", "Solar PV Installation", 4.0,
                    "Solar PV Site Safety Challenge", NOW)
                all_arts = (await sess.execute(select(Artifact).where(
                    Artifact.id == art_priya_gauntlet.id))).scalars().all()
                art = all_arts[0]
                cred = await mint_credential(sess, priya.id, art.id, payload)
                n = await batch_merkle(sess)
                cred_id = cred.id
                await e.dispose()
                return cred_id, n
        priya_cred_id, merkle_count = asyncio.run(_mint_all())

        # ------------------------------------------------------ notifications
        notifs = [
            Notification(user_id=priya.id, type="welcome",
                         payload={"message": "Your Solar PV credential is live. Keep your "
                                             "outcome record fresh with one-tap follow-ups."},
                         created_at=NOW - timedelta(days=2)),
            Notification(user_id=rahul.id, type="welcome",
                         payload={"message": "Complete Battery Diagnostics Bootcamp to close "
                                             "your top skill gap (2.1 vs required 3.5)."},
                         created_at=NOW - timedelta(days=2)),
            Notification(user_id=priya.id, type="episode_validated" if False else "placement_recorded",
                         payload={"episode_id": None, "company_id": sunray.id,
                                  "role": "Solar PV Installation Technician"},
                         created_at=NOW - timedelta(days=380)),
        ]
        bulk_save(session, notifs)

        # ------------------------------------------------------------- events
        session.add(Event(aggregate_type="system", aggregate_id=0,
                          event_type="seed_completed",
                          payload={"at": NOW.isoformat(), "skills": len(skill_rows),
                                   "trainees": len(all_trainees),
                                   "programmes": len(programmes),
                                   "episodes": len(episode_rows),
                                   "wage_events": len(wage_rows),
                                   "waves": len(wave_rows),
                                   "attempts": len(attempt_rows),
                                   "merkle_credentials": merkle_count}))
        session.commit()

        solar_p = programmes["Solar PV Installer"]
        textile_p = programmes["Textile Machine Operator"]
        beauty_p = programmes["Beauty & Wellness Entrepreneur"]
        welder_p = programmes["Welder (SMAW/MIG)"]
        priya_ep = next(e for e in all_eps if e.user_id == priya.id)
        ids = {
            "priya_user_id": priya.id,
            "rahul_user_id": rahul.id,
            "officer_user_id": officer.id,
            "sunray_company_id": sunray.id,
            "solar_programme_id": solar_p.id,
            "solar_cohort_id": solar_cohort.id,
            "ev_programme_id": ev_prog.id,
            "textile_programme_id": textile_p.id,
            "beauty_programme_id": beauty_p.id,
            "welder_programme_id": welder_p.id,
            "priya_episode_id": priya_ep.id,
            "priya_credential_id": priya_cred_id,
            "gauntlet_solar_opp_id": gauntlet1.id,
            "gauntlet_ev_opp_id": gauntlet2.id,
            "hero_ev_tech_opp_id": hero_ev_tech.id,
            "hero_solar_tech_opp_id": hero_solar_tech.id,
        }
        (DATA_DIR / "seed_ids.json").write_text(json.dumps(ids, indent=2), encoding="utf-8")

        print("Seed complete:")
        print(f"   skills={len(skill_rows)} edges={len(edge_rows)} "
              f"trainees={len(all_trainees)} programmes={len(programmes)} "
              f"cohorts={len(cohorts_all)} episodes={len(episode_rows)} "
              f"wage_events={len(wage_rows)} waves={len(wave_rows)} "
              f"attempts={len(attempt_rows)} postings={len(all_opps)} "
              f"merkle_creds={merkle_count}")


if __name__ == "__main__":
    import time
    from sqlalchemy.exc import InterfaceError, OperationalError

    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    reset = ap.parse_args().reset
    # Deterministic seed -> a full retry after a transient connection drop is safe.
    for attempt in range(3):
        try:
            main(reset=reset)
            break
        except (OperationalError, InterfaceError, OSError) as exc:
            if attempt == 2:
                raise
            wait = 20 * (attempt + 1)
            print(f"\n[seed retry {attempt + 1}/3 after connection failure: "
                  f"{type(exc).__name__} - restarting in {wait}s]\n", flush=True)
            time.sleep(wait)
