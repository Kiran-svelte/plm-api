'use client'

import { useStore } from '@/lib/store'

interface PrivacyBadgeProps {
  /** If true shows the badge in compact/icon-only mode */
  compact?: boolean
  /** If true, overrides the store-based detection (for storybook/testing) */
  forceMode?: 'full' | 'proxy' | 'off'
}

// ---------------------------------------------------------------------------
// Privacy feature list definitions
// ---------------------------------------------------------------------------

const PRIVACY_FEATURES = [
  { key: 'email', label: 'Email & phone numbers removed', alwaysActive: true },
  { key: 'company', label: 'Company names anonymized', alwaysActive: true },
  { key: 'pii', label: 'SSN, credit cards & PII stripped', alwaysActive: true },
  { key: 'ip', label: 'IP addresses & URLs redacted', alwaysActive: true },
  { key: 'adapter', label: 'Fine-tuned local model — no external API', alwaysActive: false },
] as const

export default function PrivacyBadge({ compact = false, forceMode }: PrivacyBadgeProps) {
  const { selectedModel } = useStore()

  // Determine privacy mode state from model metrics
  const modelMetrics = (selectedModel as any)?.metrics ?? {}
  const privacyEnabled: boolean = Boolean(
    modelMetrics?.privacy_mode ?? modelMetrics?.privacy_mode_enabled
  )
  const hasAdapter: boolean = Boolean(modelMetrics?.has_adapter)

  // Privacy level:
  // - full:    fine-tuned adapter exists + privacy mode on → no external API calls at all
  // - proxy:   privacy mode on but no adapter yet → PII stripped, still calls external API
  // - off:     privacy mode disabled
  type PrivacyMode = 'full' | 'proxy' | 'off'
  const computedMode: PrivacyMode = forceMode ?? (
    hasAdapter && privacyEnabled ? 'full' :
    privacyEnabled ? 'proxy' :
    'off'
  )

  const config = {
    full: {
      icon: '🔒',
      label: 'Full Privacy Mode',
      subtitle: 'Your data never leaves your infrastructure',
      badgeClasses: 'bg-emerald-900/40 text-emerald-400 border-emerald-800/50',
      cardClasses: 'bg-emerald-900/20 border-emerald-800/50',
      labelClass: 'text-emerald-400',
      dotClass: 'bg-emerald-400 animate-pulse',
      pulseActive: true,
    },
    proxy: {
      icon: '🛡️',
      label: 'Privacy Proxy Active',
      subtitle: 'PII stripped before any external API call',
      badgeClasses: 'bg-amber-900/40 text-amber-400 border-amber-800/50',
      cardClasses: 'bg-amber-900/20 border-amber-800/50',
      labelClass: 'text-amber-400',
      dotClass: 'bg-amber-400',
      pulseActive: false,
    },
    off: {
      icon: '⚠️',
      label: 'Privacy Mode Off',
      subtitle: 'Queries sent directly to external APIs',
      badgeClasses: 'bg-zinc-800/60 text-zinc-400 border-zinc-700/50',
      cardClasses: 'bg-zinc-900 border-zinc-700/50',
      labelClass: 'text-zinc-400',
      dotClass: 'bg-zinc-500',
      pulseActive: false,
    },
  }[computedMode]

  // ---------------------------------------------------------------------------
  // Compact mode: icon + dot indicator only
  // ---------------------------------------------------------------------------

  if (compact) {
    return (
      <span
        title={`${config.label} — ${config.subtitle}`}
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${config.badgeClasses}`}
      >
        <span className={`w-1.5 h-1.5 rounded-full ${config.dotClass}`} />
        {config.icon}
      </span>
    )
  }

  // ---------------------------------------------------------------------------
  // Expanded mode: full card with feature list
  // ---------------------------------------------------------------------------

  return (
    <div className={`rounded-xl border p-4 space-y-3 ${config.cardClasses}`}>
      {/* Header row */}
      <div className="flex items-center gap-2.5">
        <span className="text-xl leading-none">{config.icon}</span>
        <div className="flex-1 min-w-0">
          <div className={`text-sm font-semibold ${config.labelClass}`}>{config.label}</div>
          <div className="text-xs text-zinc-500 mt-0.5 truncate">{config.subtitle}</div>
        </div>
        {config.pulseActive && (
          <span className={`ml-auto w-2.5 h-2.5 rounded-full flex-shrink-0 ${config.dotClass}`} />
        )}
      </div>

      {/* Feature checklist */}
      <ul className="space-y-1.5">
        {PRIVACY_FEATURES.map(({ key, label, alwaysActive }) => {
          const active = alwaysActive
            ? computedMode !== 'off'
            : computedMode === 'full'
          return (
            <li key={key} className="flex items-center gap-2 text-xs">
              <span
                className={`flex-shrink-0 w-3.5 h-3.5 rounded-full flex items-center justify-center text-[10px] ${
                  active
                    ? 'bg-emerald-900/60 text-emerald-400'
                    : 'bg-zinc-800 text-zinc-600'
                }`}
              >
                {active ? '✓' : '○'}
              </span>
              <span className={active ? 'text-zinc-300' : 'text-zinc-600'}>{label}</span>
            </li>
          )
        })}
      </ul>

      {/* Contextual hint */}
      {computedMode === 'proxy' && (
        <p className="text-[11px] text-amber-500/80 leading-relaxed pt-0.5">
          Complete model training to unlock full privacy mode — all inference stays local.
        </p>
      )}
      {computedMode === 'off' && (
        <p className="text-[11px] text-zinc-500 leading-relaxed pt-0.5">
          Enable privacy mode in model settings to start stripping PII from queries.
        </p>
      )}
    </div>
  )
}
