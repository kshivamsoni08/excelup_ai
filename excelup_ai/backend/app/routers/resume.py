"""Resume Scanner (§5.8) - LLM enhancement + deterministic fallback.

Path A (LLM enabled): prompt → JSON list of {skill, years, context}.
Path B (always): case-insensitive scan for every taxonomy skill name + synonym.
Union of results. Each detected skill becomes a proficiency:
mu=3.0 (4.0 when "advanced/expert" within 40 chars), sigma_sq=0.30,
source='declared', last_evidence_at=now.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.engines.llm import llm_json
from app.models.tables import Proficiency, Opportunity, Skill, User
from app.security import get_current_user
from app.services.matching import load_taxonomy, requirements_for, user_skill_map

router = APIRouter(prefix="/resume", tags=["resume"])

ADVANCED_PAT = re.compile(r"\b(advanced|expert)\b", re.IGNORECASE)
YEARS_PAT = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)


def extract_pdf_text(raw: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def _find_declared(text: str, tax) -> list[dict]:
    """Deterministic scan (Path B) over names + synonyms."""
    low = text.lower()
    found: dict[str, dict] = {}

    def consider(skill_id: int, name: str, pos: int):
        entry = found.setdefault(name, {"skill_id": skill_id, "name": name,
                                        "positions": [], "advanced": False,
                                        "years": None})
        entry["positions"].append(pos)

    for sid, name in tax.skill_names.items():
        for alias in [name] + list((tax.synonyms or {}).get(sid, []) or []):
            for m in re.finditer(re.escape(alias.lower()), low):
                consider(sid, name, m.start())

    out = []
    for name, e in found.items():
        window = low[max(0, e["positions"][0] - 0): e["positions"][0] + 60]
        years = None
        for m in YEARS_PAT.finditer(low):
            if abs(m.start() - e["positions"][0]) < 80:
                years = float(m.group(1))
                break
        advanced = any(ADVANCED_PAT.search(low[max(0, p - 40): p + 40])
                       for p in e["positions"])
        out.append({
            "skill_id": e["skill_id"], "name": name, "years": years,
            "advanced": advanced, "origin": "deterministic",
            "context": low[max(0, e["positions"][0] - 30): e["positions"][0] + 60],
        })
    return out


async def _llm_extract(text: str) -> list[dict]:
    """Path A: ask the LLM for structured skill mentions. None on any failure."""
    names = ", ".join(sorted({n for n in llm_skill_names_cache or []})) or ""
    prompt = (
        "Extract every professional skill mentioned in this resume text. "
        f"Prefer these taxonomy names when they match: {names[:3000]}. "
        'Return ONLY a JSON array: [{"skill": "...", "years": number|null, '
        '"context": "...", "advanced": true|false}]. Resume text:\n\n'
        + text[:6000]
    )
    data = llm_json(prompt, system="You output strictly valid JSON, nothing else.")
    if not isinstance(data, list):
        return []
    return data


llm_skill_names_cache: list[str] = []


@router.post("/scan")
async def scan_resume(file: Optional[UploadFile] = File(None),
                      text: Optional[str] = Form(None),
                      user: User = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    if file is None and not text:
        raise HTTPException(400, "Provide a PDF file or pasted text")

    raw_text = text or ""
    if file is not None:
        raw_bytes = await file.read()
        if (file.filename or "").lower().endswith(".pdf"):
            try:
                raw_text = extract_pdf_text(raw_bytes)
            except Exception:
                raise HTTPException(400, "Could not parse PDF; paste text instead")
        else:
            raw_text = raw_bytes.decode("utf-8", errors="ignore")

    tax = await load_taxonomy(session)
    global llm_skill_names_cache
    llm_skill_names_cache = list(tax.skill_names.values())

    path_b = _find_declared(raw_text, tax)
    path_a = await _llm_extract(raw_text)

    # union, keyed by taxonomy skill id
    tax_by_lower = {v.lower(): k for k, v in tax.skill_names.items()}
    merged: dict[int, dict] = {}
    for e in path_b:
        merged[e["skill_id"]] = {**e, "origin": "deterministic"}
    for e in path_a:
        sid = tax_by_lower.get((e.get("skill") or "").strip().lower())
        if sid is None:
            continue
        cur = merged.get(sid)
        years = e.get("years")
        advanced = bool(e.get("advanced"))
        if cur:
            cur["origin"] = "llm+deterministic"
            cur["years"] = cur.get("years") or years
            cur["advanced"] = cur.get("advanced") or advanced
        else:
            merged[sid] = {"skill_id": sid, "name": tax.skill_names[sid],
                           "years": years, "advanced": advanced,
                           "origin": "llm", "context": e.get("context", "")}

    created = []
    for sid, e in merged.items():
        mu = 4.0 if e.get("advanced") else 3.0
        existing = (await session.execute(
            select(Proficiency).where(Proficiency.user_id == user.id,
                                      Proficiency.skill_id == sid)
        )).scalar_one_or_none()
        if existing:
            if existing.source == "declared" and mu > existing.mu:
                existing.mu = mu
                existing.last_evidence_at = datetime.now(timezone.utc)
                session.add(existing)
            created.append({"skill_id": sid, "name": e["name"], "mu": existing.mu,
                            "already_had": True, "verified": existing.source != "declared"})
            continue
        session.add(Proficiency(
            user_id=user.id, skill_id=sid, mu=mu, sigma_sq=0.30,
            source="declared", last_evidence_at=datetime.now(timezone.utc),
        ))
        created.append({"skill_id": sid, "name": e["name"], "mu": mu,
                        "already_had": False, "verified": False})

    await session.commit()
    return {
        "path": "llm+deterministic" if path_a else "deterministic",
        "detected": list(merged.values()),
        "added": created,
        "chars_scanned": len(raw_text),
    }


@router.get("/claimed-vs-verified/{opp_id}")
async def claimed_vs_verified(opp_id: int, user: User = Depends(get_current_user),
                              session: AsyncSession = Depends(get_session)):
    """Run matching twice vs one posting.

    claimed  = every skill counts, with declared skills at their mu.
    verified = declared skills are forced to contribute only 0.5 x their
               claimed cover (§5.8: "declared skills forced to cover=0.5*partial").
    """
    from app.engines.matching import UserSkill, match_user_to_opportunity

    opp = (await session.execute(select(Opportunity).where(Opportunity.id == opp_id))).scalar_one_or_none()
    if opp is None:
        raise HTTPException(404, "Opportunity not found")
    tax = await load_taxonomy(session)
    reqs = (await requirements_for(session, [opp_id])).get(opp_id, [])
    if not reqs:
        raise HTTPException(400, "This posting has no skill requirements")

    profs = (await session.execute(
        select(Proficiency).where(Proficiency.user_id == user.id)
    )).scalars().all()

    from app.engines.decay import effective_skill
    from app.models.tables import Skill as SkillTbl

    skill_rows = {s.id: s for s in (await session.execute(select(SkillTbl))).scalars().all()}

    claimed_map: dict[int, UserSkill] = {}
    declared_ids: set[int] = set()
    for p in profs:
        s = skill_rows.get(p.skill_id)
        if s is None:
            continue
        eff = effective_skill(p.skill_id, s.name, s.domain, s.half_life_class,
                              p.mu, p.sigma_sq, p.source, p.last_evidence_at)
        if p.source == "declared":
            declared_ids.add(p.skill_id)
            # claimed mode: declared skills count at mu (fresh, as claimed)
            claimed_map[p.skill_id] = UserSkill(p.skill_id, min(eff.mu_stored, 5.0),
                                                eff.potential_ceiling, p.source)
        else:
            claimed_map[p.skill_id] = UserSkill(p.skill_id, eff.verified_floor,
                                                eff.potential_ceiling, p.source)

    claimed_res = match_user_to_opportunity(claimed_map, reqs, tax.prereq_index,
                                            tax.skill_names, tax.courses_by_skill)

    # verified score: declared skills keep only half of their claimed credit
    total_w = sum(r.weight for r in reqs) or 1.0
    credited = {}  # skill_id -> (credit, weight)
    for entry in claimed_res.explanation.matched + claimed_res.explanation.near_miss:
        sid = next((k for k, v in tax.skill_names.items() if v == entry["skill"]), None)
        if sid is not None:
            credited[sid] = (entry["credit"], entry.get("weight", 1.0))
    verified_score = sum(
        w * (0.5 * c if sid in declared_ids else c) for sid, (c, w) in credited.items()
    ) / total_w

    per_skill = []
    for r in reqs:
        us = claimed_map.get(r.skill_id)
        is_declared = r.skill_id in declared_ids
        credit = credited.get(r.skill_id, (0.0, r.weight))[0]
        per_skill.append({
            "skill": tax.skill_names.get(r.skill_id, f"skill {r.skill_id}"),
            "required": r.min_level,
            "claimed_level": round(us.verified_floor, 2) if us else 0.0,
            "verified_level": round(0.5 * credit * r.min_level, 2) if is_declared
            else (round(us.verified_floor, 2) if us else 0.0),
            "claimed_credit": round(credit, 3),
            "verified_credit": round(0.5 * credit, 3) if is_declared else round(credit, 3),
            "is_declared_only": is_declared,
            "verified": bool(us and us.source != "declared"),
            "bridge_courses": tax.courses_by_skill.get(r.skill_id, []),
        })

    return {
        "opportunity": {"id": opp.id, "title": opp.title, "company": opp.company_id},
        "claimed_score": round(claimed_res.score * 100, 1),
        "verified_score": round(verified_score * 100, 1),
        "delta": round((claimed_res.score - verified_score) * 100, 1),
        "eligible_claimed": claimed_res.eligible,
        "declared_skill_ids": sorted(declared_ids),
        "per_skill": per_skill,
    }
