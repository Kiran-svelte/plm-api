'use client'

import { useCallback } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Modality = 'text' | 'code' | 'image' | 'voice'

interface ModalityOption {
  id: Modality
  label: string
  icon: string
  description: string
  shortcut: string
}

interface ModalitySelectorProps {
  selected: Modality
  onChange: (modality: Modality) => void
  /** Disable specific modalities (e.g. while a request is in-flight) */
  disabled?: Partial<Record<Modality, boolean>>
  /** Compact mode shows icons only (no label text) */
  compact?: boolean
  /** Additional class applied to the outer container */
  className?: string
}

// ---------------------------------------------------------------------------
// Modality definitions
// ---------------------------------------------------------------------------

const MODALITIES: ModalityOption[] = [
  {
    id: 'text',
    label: 'Text',
    icon: '💬',
    description: 'Standard Q&A with your niche knowledge base',
    shortcut: '1',
  },
  {
    id: 'code',
    label: 'Code',
    icon: '⌨️',
    description: 'Generate, review, or explain code with domain context',
    shortcut: '2',
  },
  {
    id: 'image',
    label: 'Image',
    icon: '🖼️',
    description: 'Analyze images through your domain expertise lens',
    shortcut: '3',
  },
  {
    id: 'voice',
    label: 'Voice',
    icon: '��️',
    description: 'Generate TTS-optimized scripts with niche terminology',
    shortcut: '4',
  },
]

// ---------------------------------------------------------------------------
// ModalitySelector component
// ---------------------------------------------------------------------------

export default function ModalitySelector({
  selected,
  onChange,
  disabled = {},
  compact = false,
  className = '',
}: ModalitySelectorProps) {
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent, modality: Modality) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        if (!disabled[modality]) onChange(modality)
      }
    },
    [onChange, disabled]
  )

  return (
    <div
      role="tablist"
      aria-label="Select input modality"
      className={`flex items-center gap-1 p-1 bg-zinc-900 border border-zinc-800 rounded-lg ${className}`}
    >
      {MODALITIES.map((m) => {
        const isSelected = selected === m.id
        const isDisabled = Boolean(disabled[m.id])

        return (
          <button
            key={m.id}
            role="tab"
            aria-selected={isSelected}
            aria-disabled={isDisabled}
            aria-label={`${m.label}: ${m.description}`}
            title={`${m.description} (Alt+${m.shortcut})`}
            tabIndex={isSelected ? 0 : -1}
            disabled={isDisabled}
            onClick={() => !isDisabled && onChange(m.id)}
            onKeyDown={(e) => handleKeyDown(e, m.id)}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium
              transition-all duration-150 select-none
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500
              ${isDisabled
                ? 'opacity-40 cursor-not-allowed'
                : 'cursor-pointer'
              }
              ${isSelected
                ? 'bg-violet-600 text-white shadow-sm shadow-violet-900/50'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/70'
              }
            `}
          >
            <span className="text-sm leading-none" aria-hidden="true">{m.icon}</span>
            {!compact && (
              <span className="hidden sm:inline leading-none">{m.label}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Modality description helper (for rendering beneath the selector)
// ---------------------------------------------------------------------------

export function ModalityDescription({ modality }: { modality: Modality }) {
  const m = MODALITIES.find((x) => x.id === modality)
  if (!m) return null
  return (
    <p className="text-xs text-zinc-500 mt-1">
      {m.icon} {m.description}
    </p>
  )
}

// ---------------------------------------------------------------------------
// Re-export modality metadata for consumers
// ---------------------------------------------------------------------------

export { MODALITIES }
