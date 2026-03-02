'use client'

import { useEffect, useRef, useState } from 'react'
import { useStore, type ModelPhase } from '@/lib/store'
import { getModelPhase } from '@/lib/api'

const PHASES = [
  { key: 'collecting', label: 'Collecting Data', icon: '1' },
  { key: 'ready_to_train', label: 'Ready to Train', icon: '2' },
  { key: 'training', label: 'Training', icon: '3' },
  { key: 'deployed', label: 'Deployed', icon: '4' },
  { key: 'learning', label: 'Learning', icon: '5' },
] as const

function getPhaseIndex(phase: string): number {
  return PHASES.findIndex((p) => p.key === phase)
}

function formatRate(rate: number): string {
  if (rate >= 1000) return `${(rate / 1000).toFixed(1)}k/hr`
  if (rate >= 1) return `~${Math.round(rate)}/hr`
  return '<1/hr'
}

function formatETA(isoString: string): string {
  const target = new Date(isoString)
  const now = new Date()
  const diffMs = target.getTime() - now.getTime()
  if (diffMs <= 0) return 'Any moment now'
  const hours = Math.floor(diffMs / (1000 * 60 * 60))
  const mins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60))
  if (hours > 24) return `~${Math.round(hours / 24)} days`
  if (hours >= 1) return `~${hours}h ${mins}m`
  return `~${mins}m`
}

// ---------------------------------------------------------------------------
// Error state shown when the phase endpoint fails to respond
// ---------------------------------------------------------------------------

function PhaseError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-zinc-400">Model Lifecycle</h3>
      </div>
      <div className="flex flex-col items-center gap-3 py-4 text-center">
        <span className="text-2xl">⚠️</span>
        <p className="text-sm text-zinc-400">Could not load training status</p>
        <p className="text-xs text-zinc-600 max-w-xs leading-relaxed">
          The backend may be starting up or temporarily unreachable.
          Training data is still being collected in the background.
        </p>
        <button
          onClick={onRetry}
          className="mt-1 px-3 py-1.5 text-xs rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
        >
          Retry
        </button>
      </div>
    </div>
  )
}

export default function ModelPhaseIndicator() {
  const { selectedOrg, selectedModel, modelPhase, setModelPhase } = useStore()
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [fetchError, setFetchError] = useState(false)
  const failedAttemptsRef = useRef(0)
  // Keep a stable ref so the retry button always calls the latest fetchPhase
  const fetchPhaseRef = useRef<() => Promise<void>>(() => Promise.resolve())

  useEffect(() => {
    if (!selectedOrg?.id || !selectedModel?.id) return

    failedAttemptsRef.current = 0
    setFetchError(false)

    // Define fetchPhase inside the effect so it always closes over the current
    // org/model IDs, avoiding stale closures on the setInterval callback.
    const fetchPhase = async () => {
      try {
        const res = await getModelPhase(selectedOrg.id, selectedModel.id)
        setModelPhase(res.data)
        setFetchError(false)
        failedAttemptsRef.current = 0
      } catch {
        failedAttemptsRef.current += 1
        // Only show error after 2 consecutive failures so transient blips don't
        // immediately flip to the error state.
        if (failedAttemptsRef.current >= 2) {
          setFetchError(true)
        }
      }
    }

    // Keep ref current so the retry button works without a stale closure
    fetchPhaseRef.current = fetchPhase

    fetchPhase()
    // Adaptive interval: start at default, then the phase-aware effect below will override
    intervalRef.current = setInterval(fetchPhase, 10000)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [selectedOrg?.id, selectedModel?.id, setModelPhase])

  // Adaptive polling: replace the default 10 s interval with a phase-aware one.
  // Runs whenever the phase changes. Always clears the previous interval first so
  // there is never more than one active at a time.
  useEffect(() => {
    if (!selectedOrg?.id || !selectedModel?.id) return
    const interval =
      modelPhase?.phase === 'collecting' || modelPhase?.phase === 'training' ? 5000 : 15000
    // Clear any existing interval before setting the new one
    if (intervalRef.current) clearInterval(intervalRef.current)
    intervalRef.current = setInterval(() => fetchPhaseRef.current(), interval)
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedOrg?.id, selectedModel?.id, modelPhase?.phase])

  // Show error state only when fetch has repeatedly failed and we have no
  // stale data to fall back on.
  if (fetchError && !modelPhase) {
    return <PhaseError onRetry={() => fetchPhaseRef.current()} />
  }

  if (!modelPhase) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 animate-pulse">
        <div className="h-4 bg-zinc-800 rounded w-48 mb-4" />
        <div className="h-8 bg-zinc-800 rounded w-full" />
      </div>
    )
  }

  const currentIdx = getPhaseIndex(modelPhase.phase)
  const progressPct = Math.min(100, modelPhase.progress_pct)

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-5">
      {/* Phase Timeline */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-zinc-400">Model Lifecycle</h3>
          {/* Live indicator — shows when polling is working */}
          <span
            className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"
            title="Live — updates every 10 seconds"
          />
        </div>
        <div className="flex items-center justify-between relative">
          {/* Connecting line */}
          <div className="absolute top-4 left-4 right-4 h-0.5 bg-zinc-700" />
          <div
            className="absolute top-4 left-4 h-0.5 bg-indigo-500 transition-all duration-700"
            style={{ width: `${Math.max(0, (currentIdx / (PHASES.length - 1)) * 100)}%` }}
          />

          {PHASES.map((phase, idx) => {
            const isActive = idx === currentIdx
            const isCompleted = idx < currentIdx
            const isFuture = idx > currentIdx

            return (
              <div key={phase.key} className="flex flex-col items-center relative z-10">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all duration-300 ${
                    isActive
                      ? 'bg-indigo-600 border-indigo-400 text-white ring-2 ring-indigo-500/30'
                      : isCompleted
                      ? 'bg-indigo-600 border-indigo-500 text-white'
                      : 'bg-zinc-800 border-zinc-600 text-zinc-500'
                  }`}
                >
                  {isCompleted ? (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : isActive && modelPhase.phase === 'training' ? (
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  ) : (
                    phase.icon
                  )}
                </div>
                <span
                  className={`text-[10px] mt-1.5 text-center leading-tight max-w-[70px] ${
                    isActive ? 'text-indigo-400 font-medium' : isFuture ? 'text-zinc-600' : 'text-zinc-400'
                  }`}
                >
                  {phase.label}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Progress Bar (during collecting phase) */}
      {(modelPhase.phase === 'collecting' || modelPhase.phase === 'learning') && (
        <div>
          <div className="flex justify-between text-xs text-zinc-400 mb-1.5">
            <span>Training Data</span>
            <span>
              {modelPhase.training_data_count.toLocaleString()} / {modelPhase.training_data_target.toLocaleString()}
            </span>
          </div>
          <div className="w-full bg-zinc-800 rounded-full h-2.5">
            <div
              className="bg-indigo-600 h-2.5 rounded-full transition-all duration-500"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          {/* Animated pulse overlay when generator is running */}
          {modelPhase.generation_rate_per_hour > 0 && (
            <div className="mt-1 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
              <span className="text-[10px] text-indigo-400">
                Generating {formatRate(modelPhase.generation_rate_per_hour)} — live
              </span>
            </div>
          )}
        </div>
      )}

      {/* Stats Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {modelPhase.generation_rate_per_hour > 0 && (
          <div className="bg-zinc-800/50 rounded-md px-3 py-2">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Generation Rate</div>
            <div className="text-sm font-medium text-zinc-200">{formatRate(modelPhase.generation_rate_per_hour)}</div>
          </div>
        )}
        {modelPhase.examples_generated_today > 0 && (
          <div className="bg-zinc-800/50 rounded-md px-3 py-2">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Today</div>
            <div className="text-sm font-medium text-zinc-200">{modelPhase.examples_generated_today.toLocaleString()}</div>
          </div>
        )}
        {modelPhase.estimated_ready_at && modelPhase.phase === 'collecting' && (
          <div className="bg-zinc-800/50 rounded-md px-3 py-2">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Ready In</div>
            <div className="text-sm font-medium text-indigo-400">{formatETA(modelPhase.estimated_ready_at)}</div>
          </div>
        )}
        <div className="bg-zinc-800/50 rounded-md px-3 py-2">
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Base Model</div>
          <div className="text-sm font-medium text-zinc-200">{modelPhase.base_model}</div>
        </div>
      </div>

      {/* Training Activity (during training phase) */}
      {modelPhase.phase === 'training' && modelPhase.training_activity && (
        <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">Training Activity</h4>
            <span className="text-[10px] text-zinc-500">
              via {modelPhase.training_activity.backend_used}
            </span>
          </div>

          {/* Current step */}
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-indigo-400 animate-spin shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            <span className="text-sm font-medium text-indigo-300">
              {modelPhase.training_activity.current_step || 'Processing...'}
            </span>
          </div>

          {/* Steps log */}
          {modelPhase.training_activity.steps_log.length > 0 && (
            <div className="space-y-1 pl-2 border-l-2 border-zinc-700 ml-1.5">
              {modelPhase.training_activity.steps_log.map((entry, i) => {
                const isLatest = i === modelPhase.training_activity!.steps_log.length - 1
                const time = new Date(entry.time)
                const timeStr = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                return (
                  <div key={i} className={`flex items-start gap-2 py-0.5 ${isLatest ? 'text-zinc-200' : 'text-zinc-500'}`}>
                    <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${
                      isLatest ? 'bg-indigo-400 animate-pulse' : 'bg-zinc-600'
                    }`} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium">{entry.step}</span>
                        <span className="text-[10px] text-zinc-600">{timeStr}</span>
                      </div>
                      {entry.detail && (
                        <p className="text-[10px] text-zinc-500 truncate">{entry.detail}</p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Training info */}
          <div className="flex items-center gap-4 text-[10px] text-zinc-500 pt-1">
            <span>Model: {modelPhase.training_activity.base_model}</span>
            <span>Data: {modelPhase.training_activity.data_used.toLocaleString()} examples</span>
            {modelPhase.training_activity.started_at && (
              <span>Started: {new Date(modelPhase.training_activity.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            )}
          </div>
        </div>
      )}

      {/* Last training results (after training complete) */}
      {(modelPhase.phase === 'deployed' || modelPhase.phase === 'learning') && modelPhase.training_activity?.training_results && (
        <div className="bg-zinc-800/40 border border-zinc-700/30 rounded-lg px-4 py-3">
          <div className="flex items-center gap-2 mb-2">
            <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span className="text-xs font-medium text-emerald-400">Training Complete</span>
            {modelPhase.last_training_at && (
              <span className="text-[10px] text-zinc-500">
                {new Date(modelPhase.last_training_at).toLocaleDateString()}
              </span>
            )}
          </div>
          <div className="flex items-center gap-4 text-[10px] text-zinc-500">
            {modelPhase.training_activity.training_results.final_loss != null && (
              <span>Loss: {modelPhase.training_activity.training_results.final_loss.toFixed(4)}</span>
            )}
            {modelPhase.training_activity.training_results.training_time_minutes != null && (
              <span>Time: {Math.round(modelPhase.training_activity.training_results.training_time_minutes)}m</span>
            )}
            <span>Data: {modelPhase.training_activity.data_used.toLocaleString()} examples</span>
          </div>
        </div>
      )}

      {/* Status Badges */}
      <div className="flex flex-wrap gap-2">
        {modelPhase.privacy_mode_available ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-900/40 text-emerald-400 border border-emerald-800/50">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Privacy Mode Active
          </span>
        ) : modelPhase.phase === 'collecting' ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-900/40 text-amber-400 border border-amber-800/50">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            Learning Mode — Training your private model
          </span>
        ) : null}

        {!modelPhase.gpu_backend && modelPhase.phase === 'collecting' && progressPct >= 80 && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-900/40 text-amber-400 border border-amber-800/50">
            No GPU — Configure to enable training
          </span>
        )}

        {modelPhase.phase === 'training' && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-900/40 text-blue-400 border border-blue-800/50">
            <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Training in Progress
          </span>
        )}

        {modelPhase.sub_status === 'training_failed' && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-900/40 text-red-400 border border-red-800/50">
            Last training failed — Will retry automatically
          </span>
        )}
      </div>
    </div>
  )
}
