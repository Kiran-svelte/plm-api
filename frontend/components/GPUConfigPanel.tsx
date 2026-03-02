'use client'

import { useState, useEffect } from 'react'
import { useStore } from '@/lib/store'
import { configureGPU } from '@/lib/api'

interface GPUBackend {
  id: string
  name: string
  description: string
  fields: { key: string; label: string; placeholder: string; type: string }[]
  cost: string
}

const BACKENDS: GPUBackend[] = [
  {
    id: 'local',
    name: 'Local GPU',
    description: 'Use your own NVIDIA GPU with CUDA. Free, requires a machine with a compatible GPU.',
    fields: [],
    cost: 'Free',
  },
  {
    id: 'runpod',
    name: 'RunPod',
    description: 'Serverless GPU cloud. Pay per second of compute. Great for occasional training.',
    fields: [
      { key: 'api_key', label: 'RunPod API Key', placeholder: 'rp_xxxxxxxxxxxxxxxx', type: 'password' },
    ],
    cost: '$0.20-0.40/hr',
  },
  {
    id: 'huggingface',
    name: 'HuggingFace',
    description: 'AutoTrain on HuggingFace infrastructure. Simple setup with your HF token.',
    fields: [
      { key: 'hf_token', label: 'HuggingFace Token', placeholder: 'hf_xxxxxxxxxxxxxxxx', type: 'password' },
    ],
    cost: 'Pay-per-use',
  },
]

const BASE_MODELS = [
  { key: 'tinyllama-1.1b', name: 'TinyLlama 1.1B', vram: '6 GB', speed: 'Fastest' },
  { key: 'llama-3.2-1b', name: 'Llama 3.2 1B', vram: '8 GB', speed: 'Fast' },
  { key: 'llama-3.2-3b', name: 'Llama 3.2 3B', vram: '12 GB', speed: 'Moderate' },
  { key: 'phi-3-mini', name: 'Phi-3 Mini', vram: '14 GB', speed: 'Moderate' },
  { key: 'mistral-7b', name: 'Mistral 7B', vram: '20 GB', speed: 'Slower' },
  { key: 'llama-3.1-8b', name: 'Llama 3.1 8B', vram: '24 GB', speed: 'Slowest' },
]

export default function GPUConfigPanel() {
  const { selectedOrg, selectedModel, modelPhase, setModelPhase } = useStore()
  const [selectedBackend, setSelectedBackend] = useState<string>('')
  const [selectedBaseModel, setSelectedBaseModel] = useState<string>('tinyllama-1.1b')
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<{ ok: boolean; msg: string } | null>(null)
  // Tracks whether the backend already has credentials saved (so we show "configured" instead of empty)
  const [savedKeys, setSavedKeys] = useState<Record<string, boolean>>({})

  // Sync state from modelPhase when it loads or changes
  useEffect(() => {
    if (!modelPhase) return
    if (modelPhase.gpu_backend) {
      setSelectedBackend(modelPhase.gpu_backend)
    }
    if (modelPhase.base_model) {
      setSelectedBaseModel(modelPhase.base_model)
    }
    // If backend is set, the credentials were saved previously
    const keys: Record<string, boolean> = {}
    if (modelPhase.gpu_backend === 'runpod') keys['api_key'] = true
    if (modelPhase.gpu_backend === 'huggingface') keys['hf_token'] = true
    setSavedKeys(keys)
  }, [modelPhase?.gpu_backend, modelPhase?.base_model])

  const handleSave = async () => {
    if (!selectedOrg?.id || !selectedModel?.id || !selectedBackend) return
    setSaving(true)
    setSaveResult(null)

    try {
      const res = await configureGPU(selectedOrg.id, selectedModel.id, {
        backend: selectedBackend,
        api_key: fieldValues.api_key || undefined,
        hf_token: fieldValues.hf_token || undefined,
        base_model: selectedBaseModel,
      })
      setSaveResult({ ok: true, msg: 'GPU configuration saved' })
      // Mark the credentials as saved
      const keys: Record<string, boolean> = { ...savedKeys }
      if (fieldValues.api_key) keys['api_key'] = true
      if (fieldValues.hf_token) keys['hf_token'] = true
      setSavedKeys(keys)
      // Clear typed credentials from state (they're saved server-side)
      setFieldValues({})
      // Update phase info to reflect new GPU backend
      if (modelPhase) {
        setModelPhase({ ...modelPhase, gpu_backend: selectedBackend, base_model: selectedBaseModel })
      }
    } catch (err: any) {
      const status = err?.response?.status || 'unknown'
      const detail = err?.response?.data?.detail || err?.message || 'Failed to save GPU configuration'
      const msg = `[${status}] ${detail}`
      setSaveResult({ ok: false, msg })
      console.error('GPU config save error:', { status, detail, fullError: err })
    } finally {
      setSaving(false)
    }
  }

  const activeBackend = BACKENDS.find((b) => b.id === selectedBackend)

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-5">
      <div>
        <h3 className="text-sm font-medium text-zinc-400 mb-1">GPU Backend</h3>
        <p className="text-xs text-zinc-600 mb-4">
          Choose where to run model training. Required for fine-tuning your private model.
        </p>
      </div>

      {/* Backend Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {BACKENDS.map((backend) => {
          const isSelected = selectedBackend === backend.id
          const isSaved = modelPhase?.gpu_backend === backend.id
          return (
            <button
              key={backend.id}
              onClick={() => setSelectedBackend(backend.id)}
              className={`text-left p-3 rounded-lg border transition-all ${
                isSelected
                  ? 'border-indigo-500 bg-indigo-950/30 ring-1 ring-indigo-500/30'
                  : 'border-zinc-700 bg-zinc-800/50 hover:border-zinc-600'
              }`}
            >
              <div className="flex justify-between items-start mb-1">
                <span className="text-sm font-medium text-zinc-200">{backend.name}</span>
                <div className="flex items-center gap-1.5">
                  {isSaved && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/40 text-emerald-400">
                      Active
                    </span>
                  )}
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                    backend.cost === 'Free' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-zinc-700 text-zinc-400'
                  }`}>
                    {backend.cost}
                  </span>
                </div>
              </div>
              <p className="text-[11px] text-zinc-500 leading-relaxed">{backend.description}</p>
            </button>
          )
        })}
      </div>

      {/* Backend-specific fields */}
      {activeBackend && activeBackend.fields.length > 0 && (
        <div className="space-y-3">
          {activeBackend.fields.map((field) => {
            const alreadySaved = savedKeys[field.key]
            return (
              <div key={field.key}>
                <label className="block text-xs text-zinc-400 mb-1">
                  {field.label}
                  {alreadySaved && (
                    <span className="ml-2 text-emerald-400 text-[10px]">Saved</span>
                  )}
                </label>
                <input
                  type={field.type}
                  placeholder={alreadySaved ? '••••••••••••••• (already configured)' : field.placeholder}
                  value={fieldValues[field.key] || ''}
                  onChange={(e) => setFieldValues({ ...fieldValues, [field.key]: e.target.value })}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30"
                />
                {alreadySaved && !fieldValues[field.key] && (
                  <p className="text-[10px] text-zinc-600 mt-1">
                    Leave empty to keep existing token. Enter a new value to replace it.
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Base Model Selector */}
      <div>
        <label className="block text-xs text-zinc-400 mb-2">Base Model</label>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {BASE_MODELS.map((model) => (
            <button
              key={model.key}
              onClick={() => setSelectedBaseModel(model.key)}
              className={`text-left p-2.5 rounded-md border transition-all ${
                selectedBaseModel === model.key
                  ? 'border-indigo-500 bg-indigo-950/30'
                  : 'border-zinc-700 bg-zinc-800/50 hover:border-zinc-600'
              }`}
            >
              <div className="text-xs font-medium text-zinc-200">{model.name}</div>
              <div className="flex gap-2 mt-0.5">
                <span className="text-[10px] text-zinc-500">VRAM: {model.vram}</span>
                <span className="text-[10px] text-zinc-600">{model.speed}</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Save Button + Result */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={!selectedBackend || saving}
          className="px-4 py-2 rounded-md bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? 'Saving...' : 'Save Configuration'}
        </button>
        {saveResult && (
          <span className={`text-xs ${saveResult.ok ? 'text-emerald-400' : 'text-red-400'}`}>
            {saveResult.msg}
          </span>
        )}
      </div>
    </div>
  )
}
