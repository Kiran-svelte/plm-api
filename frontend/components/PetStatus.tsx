'use client'

import { useState, useEffect, useRef } from 'react'
import { useStore, type PetStatus as PetStatusData } from '@/lib/store'
import { getPetStatus } from '@/lib/api'

// ---------------------------------------------------------------------------
// XP progress bar with smooth transition
// ---------------------------------------------------------------------------

function XPBar({ xp, xpToNext, evolutionPct }: {
  xp: number
  xpToNext: number | null
  evolutionPct: number
}) {
  if (xpToNext === null) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-amber-400 font-semibold tracking-wider uppercase">
          MAX LEVEL 🐉
        </span>
        <div className="flex-1 bg-amber-900/30 rounded-full h-2">
          <div className="h-2 rounded-full bg-amber-400 w-full" />
        </div>
      </div>
    )
  }

  const pct = Math.min(100, Math.max(0, evolutionPct))

  return (
    <div>
      <div className="flex justify-between text-xs text-zinc-400 mb-1.5">
        <span className="font-medium">{xp.toLocaleString()} XP</span>
        <span>{xpToNext.toLocaleString()} to evolve</span>
      </div>
      <div className="w-full bg-zinc-800 rounded-full h-2.5 overflow-hidden">
        <div
          className="h-2.5 rounded-full transition-all duration-1000 ease-out"
          style={{
            width: `${pct}%`,
            background: 'linear-gradient(90deg, #7c3aed, #a78bfa)',
          }}
        />
      </div>
      <div className="text-right text-[10px] text-zinc-600 mt-0.5">{pct.toFixed(1)}% to next stage</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stage roadmap showing all 6 stages
// ---------------------------------------------------------------------------

function StageRoadmap({ stages }: { stages: PetStatusData['all_stages'] }) {
  return (
    <div className="flex items-center gap-1">
      {stages.map((s, idx) => (
        <div key={s.stage} className="flex items-center">
          <div
            title={`${s.title} — ${s.min_examples.toLocaleString()} examples, ${s.min_accuracy_pct}% accuracy`}
            className={`
              flex items-center justify-center rounded-full text-base
              transition-all duration-300
              ${s.current ? 'w-8 h-8 ring-2 ring-violet-400 ring-offset-1 ring-offset-zinc-900' : 'w-6 h-6'}
              ${s.unlocked ? 'opacity-100' : 'opacity-25 grayscale'}
            `}
          >
            {s.emoji}
          </div>
          {idx < stages.length - 1 && (
            <div className={`h-0.5 w-4 mx-0.5 rounded ${s.unlocked ? 'bg-violet-600' : 'bg-zinc-700'}`} />
          )}
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Streak badge
// ---------------------------------------------------------------------------

function StreakBadge({ days }: { days: number }) {
  if (days === 0) return null
  const color = days >= 30 ? 'text-amber-400' : days >= 7 ? 'text-orange-400' : 'text-zinc-400'
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-medium ${color}`}>
      🔥 {days}d streak
    </span>
  )
}

// ---------------------------------------------------------------------------
// Stage color mapping
// ---------------------------------------------------------------------------

const STAGE_COLORS: Record<string, string> = {
  egg: 'text-slate-400',
  hatchling: 'text-amber-400',
  juvenile: 'text-emerald-400',
  adult: 'text-blue-400',
  master: 'text-violet-400',
  legend: 'text-rose-400',
}

// ---------------------------------------------------------------------------
// Main PetStatus component
// ---------------------------------------------------------------------------

export default function PetStatus() {
  const { selectedOrg, selectedModel, petStatus: cachedStatus, setPetStatus } = useStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!selectedOrg?.id || !selectedModel?.id) return

    const load = async () => {
      try {
        setLoading(true)
        const res = await getPetStatus(selectedOrg.id, selectedModel.id)
        setPetStatus(res.data)
        setError(null)
      } catch {
        setError('Unable to load pet status')
      } finally {
        setLoading(false)
      }
    }

    load()
    // Refresh every 30 seconds while component is mounted
    intervalRef.current = setInterval(load, 30000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
    // setPetStatus is a stable Zustand setter and does not trigger re-runs
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedOrg?.id, selectedModel?.id])

  if (loading && !cachedStatus) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 animate-pulse space-y-3">
        <div className="h-3 bg-zinc-800 rounded w-24" />
        <div className="h-12 bg-zinc-800 rounded w-full" />
        <div className="h-3 bg-zinc-800 rounded w-48" />
      </div>
    )
  }

  if (error || !cachedStatus) return null

  const pet = cachedStatus
  const stageColorClass = STAGE_COLORS[pet.stage] || 'text-zinc-400'

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">AI Pet</h3>
        <div className="flex items-center gap-2">
          <StreakBadge days={pet.streak_days} />
          <span className="text-xs text-zinc-500">
            {pet.mood_emoji} {pet.mood_description}
          </span>
        </div>
      </div>

      {/* Pet avatar + identity */}
      <div className="flex items-center gap-4">
        <div
          className="text-5xl select-none flex-shrink-0"
          title={`${pet.stage_title} — ${pet.personality_type} personality`}
          style={{ filter: `drop-shadow(0 0 8px ${pet.stage_color}60)` }}
        >
          {pet.stage_emoji}
        </div>
        <div className="min-w-0">
          <div className={`text-lg font-bold ${stageColorClass}`}>
            {pet.stage_title}
          </div>
          <div className="text-xs text-zinc-500 capitalize">{pet.personality_type} personality</div>
          {pet.org_niche && (
            <div className="text-xs text-zinc-600 mt-0.5">
              Specialist: <span className="text-zinc-400 capitalize">{pet.org_niche}</span>
            </div>
          )}
        </div>
      </div>

      {/* Stage roadmap */}
      {pet.all_stages && pet.all_stages.length > 0 && (
        <StageRoadmap stages={pet.all_stages} />
      )}

      {/* XP bar */}
      <XPBar
        xp={pet.xp}
        xpToNext={pet.xp_to_next}
        evolutionPct={pet.evolution_pct}
      />

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-2">
        <StatCard label="Training Examples" value={pet.training_examples.toLocaleString()} />
        <StatCard label="Accuracy" value={`${pet.accuracy}%`} />
        <StatCard
          label="Total XP"
          value={pet.xp.toLocaleString()}
          valueClassName="text-violet-400 font-semibold"
        />
        <StatCard
          label="Fine-Tuned"
          value={pet.has_adapter ? '✅ Yes' : '⏳ Pending'}
        />
      </div>

      {/* Next stage requirements */}
      {pet.next_stage_requirements && (
        <div className="rounded-lg bg-zinc-800/40 px-3 py-2 border border-zinc-700/50">
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">
            Path to {pet.next_stage_requirements.next_stage_emoji} {pet.next_stage_requirements.next_stage_title}
          </div>
          <div className="flex gap-3 text-xs text-zinc-400">
            {pet.next_stage_requirements.examples_needed > 0 && (
              <span>
                +{pet.next_stage_requirements.examples_needed.toLocaleString()} examples
              </span>
            )}
            {pet.next_stage_requirements.accuracy_needed_pct > 0 && (
              <span>
                +{pet.next_stage_requirements.accuracy_needed_pct}% accuracy
              </span>
            )}
            {pet.next_stage_requirements.examples_needed === 0 &&
              pet.next_stage_requirements.accuracy_needed_pct === 0 && (
              <span className="text-emerald-400">Ready to evolve! 🎉</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helper stat card
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  valueClassName = 'text-zinc-200',
}: {
  label: string
  value: string
  valueClassName?: string
}) {
  return (
    <div className="bg-zinc-800/50 rounded-lg px-3 py-2">
      <div className="text-[10px] text-zinc-500 uppercase tracking-wider leading-tight">{label}</div>
      <div className={`text-sm font-medium mt-0.5 ${valueClassName}`}>{value}</div>
    </div>
  )
}
