"use client";

import { useMemo, useState } from "react";

export type GenomeSkill = {
  skill_id: number;
  name: string;
  domain: string;
  mu_effective: number;
  verified_floor: number;
  potential_ceiling: number;
  source: string;
  is_verified: boolean;
  months_stale: number;
  faded: boolean;
  last_evidence_at: string;
};

const SIZE = 520;
const C = SIZE / 2;
const RMAX = 200;
const LEVELS = 5;

function polar(angle: number, r: number) {
  return [C + r * Math.cos(angle), C + r * Math.sin(angle)] as const;
}

const SOURCE_LABEL: Record<string, string> = {
  assessment: "adaptive test",
  gauntlet: "company challenge",
  course: "course",
  declared: "self-declared",
  vouch: "vouched",
};

export default function SkillGenome({
  skills,
  compact = false,
}: {
  skills: GenomeSkill[];
  compact?: boolean;
}) {
  const [hover, setHover] = useState<{
    skill: GenomeSkill;
    x: number;
    y: number;
  } | null>(null);

  const n = Math.max(skills.length, 3);
  const angles = useMemo(
    () => skills.map((_, i) => (2 * Math.PI * i) / n - Math.PI / 2),
    [skills, n]
  );

  const floorPts = skills.map((s, i) => {
    const r = (Math.max(0, s.verified_floor) / LEVELS) * RMAX;
    return polar(angles[i], r);
  });
  const ceilPts = skills.map((s, i) => {
    const r = (Math.min(LEVELS, s.potential_ceiling) / LEVELS) * RMAX;
    return polar(angles[i], r);
  });

  const toPath = (pts: readonly (readonly [number, number])[]) =>
    pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ") + " Z";

  return (
    <div className="relative" style={{ width: compact ? 320 : "100%", maxWidth: compact ? 320 : 620 }}>
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-full select-none">
        {/* level rings */}
        {[1, 2, 3, 4, 5].map((lvl) => (
          <circle key={lvl} cx={C} cy={C} r={(lvl / LEVELS) * RMAX}
            fill="none" stroke="#e7e5e4" strokeWidth={1} strokeDasharray={lvl < 5 ? "3 4" : undefined} />
        ))}
        {["0", "2.5", "5"].map((lbl, i) => (
          <text key={lbl} x={C + 4} y={C - (i === 0 ? 0 : i === 1 ? RMAX / 2 : RMAX) + (i === 0 ? 14 : -4)}
            className="fill-stone-400" fontSize={10}>{lbl}</text>
        ))}
        {/* axes */}
        {angles.map((a, i) => {
          const [x, y] = polar(a, RMAX);
          return <line key={i} x1={C} y1={C} x2={x} y2={y} stroke="#e7e5e4" strokeWidth={1} />;
        })}

        {/* potential ceiling: faint dashed polygon */}
        {skills.length >= 3 && (
          <path d={toPath(ceilPts)} fill="#14532D" fillOpacity={0.05}
            stroke="#14532D" strokeOpacity={0.35} strokeWidth={1.5} strokeDasharray="5 4" />
        )}
        {skills.length < 3 && ceilPts.map(([x, y], i) => (
          <line key={i} x1={C} y1={C} x2={x} y2={y} stroke="#14532D" strokeOpacity={0.3}
            strokeWidth={2} strokeDasharray="5 4" />
        ))}

        {/* verified floor: solid filled polygon */}
        {skills.length >= 3 && floorPts.length >= 3 && (
          <path d={toPath(floorPts)} fill="#14532D" fillOpacity={0.28}
            stroke="#14532D" strokeWidth={2.5} strokeLinejoin="round" />
        )}
        {skills.length < 3 && floorPts.map(([x, y], i) => (
          <line key={`f${i}`} x1={C} y1={C} x2={x} y2={y} stroke="#14532D" strokeWidth={3} />
        ))}

        {/* per-skill markers + hover zones + labels */}
        {skills.map((s, i) => {
          const [fx, fy] = floorPts[i];
          const [cx, cy] = ceilPts[i];
          const [lx, ly] = polar(angles[i], RMAX + 26);
          const dim = s.faded ? 0.35 : 1;
          return (
            <g key={s.skill_id} opacity={dim}>
              {/* ceiling tick */}
              <circle cx={cx} cy={cy} r={4} fill="#F59E0B" fillOpacity={0.85} />
              {/* floor node */}
              <circle cx={fx} cy={fy} r={s.source === "declared" ? 5 : 6}
                fill={s.source === "declared" ? "#fff" : "#14532D"}
                stroke={s.source === "declared" ? "#78716C" : "#0F3D22"}
                strokeWidth={2}
                strokeDasharray={s.source === "declared" ? "2 2" : undefined} />
              {/* invisible fat hit area */}
              <circle cx={(fx + cx) / 2} cy={(fy + cy) / 2} r={26} fill="transparent"
                onMouseEnter={(e) => {
                  const rect = (e.target as SVGCircleElement).ownerSVGElement!.getBoundingClientRect();
                  setHover({ skill: s, x: ((fx) / SIZE) * rect.width, y: ((fy) / SIZE) * rect.height });
                }}
                onMouseLeave={() => setHover(null)} />
              <text x={lx} y={ly} fontSize={compact ? 10 : 12}
                textAnchor={Math.abs(lx - C) < 20 ? "middle" : lx > C ? "start" : "end"}
                dominantBaseline="middle"
                className={s.faded ? "fill-stone-400 italic" : "fill-stone-700"}>
                {s.name}
              </text>
            </g>
          );
        })}
        {/* center */}
        <circle cx={C} cy={C} r={3} className="fill-stone-400" />
      </svg>

      {hover && (
        <div
          className="pointer-events-none absolute z-10 w-56 rounded-lg border border-stone-200 bg-white p-3 text-xs shadow-lg"
          style={{ left: `calc(50% + ${hover.x}px - 112px)`, top: `calc(50% + ${hover.y}px - 96px)` }}
        >
          <div className="mb-1 flex items-center justify-between">
            <span className="font-semibold text-stone-800">{hover.skill.name}</span>
            {hover.skill.faded && <span className="badge-amber">fading</span>}
          </div>
          <div className="space-y-0.5 text-stone-600">
            <div>Verified floor: <b className="text-primary-800">{hover.skill.verified_floor.toFixed(2)}</b></div>
            <div>Potential ceiling: <b className="text-saffron-600">{hover.skill.potential_ceiling.toFixed(2)}</b></div>
            <div>Effective level μ: {hover.skill.mu_effective.toFixed(2)}</div>
            <div>Source: {SOURCE_LABEL[hover.skill.source] ?? hover.skill.source}
              {!hover.skill.is_verified && <span className="badge-gray ml-1">unverified</span>}
            </div>
            <div>Last verified: {new Date(hover.skill.last_evidence_at).toLocaleDateString()}
              {hover.skill.months_stale >= 1 && ` (${hover.skill.months_stale.toFixed(0)} mo ago)`}
            </div>
          </div>
        </div>
      )}

      {/* legend */}
      <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-stone-500">
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full bg-primary-900" /> solid = verified floor</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full bg-saffron-500" /> faint = potential ceiling</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-dashed border-stone-400" /> unverified</span>
        <span className="flex items-center gap-1.5 italic text-stone-400">dim = fading</span>
      </div>
    </div>
  );
}
