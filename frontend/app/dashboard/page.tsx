'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useStore, type Organization, type Model } from '@/lib/store'
import {
  getOrganizations,
  getModels,
  getKnowledge,
  addKnowledge,
  deleteKnowledge,
  getQueryHistory,
  getAnalytics,
  generateData,
  startTraining,
  getTrainingJob,
  getLearningStats,
  updateOrganization,
  getOrgUsers,
  updateUserRole,
  getApiKeys,
  createApiKey,
  revokeApiKey,
  getAuditLogs,
  getCurrentUser,
  getOnboardingStatus,
  getGenerationStats,
  getModelAccuracy,
} from '@/lib/api'
import AuthGuard from '@/components/AuthGuard'
import ChatPanel from '@/components/ChatPanel'
import NotificationBell from '@/components/NotificationBell'
import ModelPhaseIndicator from '@/components/ModelPhaseIndicator'
import GPUConfigPanel from '@/components/GPUConfigPanel'
import PetStatus from '@/components/PetStatus'
import PrivacyBadge from '@/components/PrivacyBadge'
import ModalitySelector, { type Modality } from '@/components/ModalitySelector'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TabKey = 'chat' | 'knowledge' | 'history' | 'health' | 'settings' | 'audit'

interface KnowledgeEntry {
  id: string
  content: string
  source: string
  created_at: string
}

interface HistoryEntry {
  id: string
  query_id: string
  query: string
  response: string
  confidence: number
  response_time_ms: number
  feedback?: string
  created_at: string
}

interface AnalyticsData {
  total_queries: number
  avg_confidence: number
  avg_response_time_ms: number
  total_training_examples: number
}

interface TrainingJob {
  id: string
  status: string
  progress: number
  started_at?: string
  completed_at?: string
}

interface LearningStatsData {
  total_training_examples: number
  from_continuous_learning: number
  from_user_feedback: number
  average_quality_score: number
  knowledge_base?: { total_entries?: number; ready?: boolean }
  learning_enabled: boolean
}

interface GenerationStatsData {
  total_count: number
  source_breakdown: Record<string, number>
  generation_rate_per_hour: number
  examples_generated_today: number
}

interface AccuracyData {
  accuracy: number
  confidence: number
  tests_passed: number
  tests_total: number
  calculated_at?: string
  cache_hit?: boolean
  breakdown?: {
    raw_score: number
    rag_bonus: number
    training_examples: number
  }
}

interface OrgUser {
  id: string
  email: string
  role: string
}

interface ApiKeyEntry {
  id: string
  prefix: string
  name: string
  status: string
  last_used_at?: string
  created_at: string
}

interface AuditEntry {
  id: string
  action: string
  resource_type: string
  user_email?: string
  user_id?: string
  details?: Record<string, unknown>
  created_at: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TAB_LABELS: Record<TabKey, string> = {
  chat: 'Chat',
  knowledge: 'Knowledge Base',
  history: 'History',
  health: 'Model Health',
  settings: 'Settings',
  audit: 'Audit Log',
}

function statusColor(status: string): string {
  switch (status) {
    case 'pending':
      return 'bg-yellow-100 text-yellow-800'
    case 'training':
      return 'bg-blue-100 text-blue-800'
    case 'ready':
      return 'bg-green-100 text-green-800'
    case 'deployed':
      return 'bg-emerald-100 text-emerald-800'
    case 'failed':
      return 'bg-red-100 text-red-800'
    case 'active':
      return 'bg-green-100 text-green-700'
    default:
      return 'bg-gray-100 text-gray-700'
  }
}

function truncate(text: string, max: number): string {
  if (!text) return ''
  return text.length > max ? text.slice(0, max) + '...' : text
}

function formatDate(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ---------------------------------------------------------------------------
// Dashboard Page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  return (
    <AuthGuard>
      <DashboardContent />
    </AuthGuard>
  )
}

function DashboardContent() {
  const router = useRouter()

  // ---- Zustand store ----------------------------------------------------------
  const {
    user,
    organizations,
    selectedOrg,
    models,
    selectedModel,
    sidebarOpen,
    activeTab,
    initAuth,
    setOrganizations,
    setSelectedOrg,
    setModels,
    setSelectedModel,
    setSidebarOpen,
    setActiveTab,
    logout,
  } = useStore()

  // ---- Local state: Knowledge tab ---------------------------------------------
  const [knowledgeEntries, setKnowledgeEntries] = useState<KnowledgeEntry[]>([])
  const [kbLoading, setKbLoading] = useState(false)
  const [newKbContent, setNewKbContent] = useState('')
  const [newKbSource, setNewKbSource] = useState('')

  // ---- Local state: History tab ------------------------------------------------
  const [historyEntries, setHistoryEntries] = useState<HistoryEntry[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [expandedHistoryId, setExpandedHistoryId] = useState<string | null>(null)

  // ---- Local state: Health tab -------------------------------------------------
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null)
  const [healthLoading, setHealthLoading] = useState(false)
  const [numExamples, setNumExamples] = useState(50)
  const [genDataLoading, setGenDataLoading] = useState(false)
  const [trainLoading, setTrainLoading] = useState(false)
  const [trainingJob, setTrainingJob] = useState<TrainingJob | null>(null)
  const [learningStats, setLearningStats] = useState<LearningStatsData | null>(null)
  const [generationStats, setGenerationStats] = useState<GenerationStatsData | null>(null)
  const [accuracyData, setAccuracyData] = useState<AccuracyData | null>(null)
  const [accuracyRefreshing, setAccuracyRefreshing] = useState(false)

  // ---- Local state: Settings tab ----------------------------------------------
  const [settingsOrgName, setSettingsOrgName] = useState('')
  const [settingsNiche, setSettingsNiche] = useState('')
  const [settingsPrompt, setSettingsPrompt] = useState('')
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [orgUsers, setOrgUsers] = useState<OrgUser[]>([])
  const [apiKeys, setApiKeys] = useState<ApiKeyEntry[]>([])
  const [newKeyName, setNewKeyName] = useState('')
  const [createdKeyValue, setCreatedKeyValue] = useState<string | null>(null)

  // ---- Local state: Audit tab -------------------------------------------------
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([])
  const [auditLoading, setAuditLoading] = useState(false)

  // ---- Local state: v2.0 Modality selector ------------------------------------
  const [selectedModality, setSelectedModality] = useState<Modality>('text')

  // ---- Local state: Action error banner --------------------------------------
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)
  const actionErrorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showActionError = useCallback((msg: string) => {
    setActionError(msg)
    setActionSuccess(null)
    if (actionErrorTimeoutRef.current) clearTimeout(actionErrorTimeoutRef.current)
    actionErrorTimeoutRef.current = setTimeout(() => setActionError(null), 8000)
  }, [])

  const showActionSuccess = useCallback((msg: string) => {
    setActionSuccess(msg)
    setActionError(null)
    setTimeout(() => setActionSuccess(null), 4000)
  }, [])

  // ---- Refs -------------------------------------------------------------------
  const auditIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const trainingPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ---- Boot -------------------------------------------------------------------
  useEffect(() => {
    const boot = async () => {
      await initAuth()

      // Check if user needs onboarding (no org yet)
      try {
        const statusRes = await getOnboardingStatus()
        const status = statusRes.data
        if (!status.has_organization) {
          router.push('/onboarding')
          return
        }
      } catch {
        // If the endpoint fails, continue to dashboard — don't block
      }

      // Fetch role and org_id from backend FIRST, before fetching orgs
      let userOrgId: string | null = null
      try {
        const res = await getCurrentUser()
        const me = res.data
        const currentUser = useStore.getState().user
        if (me && currentUser) {
          useStore.getState().setUser({
            ...currentUser,
            role: me.role || currentUser.role,
            organization_id: me.org_id || undefined,
          })
          userOrgId = me.org_id || null
        }
      } catch {
        /* not logged in yet or /me not available */
      }

      // Fetch orgs and auto-select user's org
      try {
        const res = await getOrganizations()
        const orgs: Organization[] = res.data.organizations ?? res.data ?? []
        setOrganizations(orgs)

        // Auto-select: user's org, or first available
        if (orgs.length > 0 && !useStore.getState().selectedOrg) {
          const userOrg = userOrgId ? orgs.find((o) => o.id === userOrgId) : null
          setSelectedOrg(userOrg || orgs[0])
        }
      } catch (err) {
        console.error('Failed to fetch organizations', err)
      }
    }
    boot()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---- Fetch orgs -------------------------------------------------------------
  const fetchOrganizations = useCallback(async () => {
    try {
      const res = await getOrganizations()
      const orgs: Organization[] = res.data.organizations ?? res.data ?? []
      setOrganizations(orgs)
    } catch (err) {
      console.error('Failed to fetch organizations', err)
    }
  }, [setOrganizations])

  // ---- When selectedOrg changes, load models ----------------------------------
  useEffect(() => {
    if (!selectedOrg) {
      setModels([])
      return
    }
    ;(async () => {
      try {
        const res = await getModels(selectedOrg.id)
        const m: Model[] = res.data.models ?? res.data ?? []
        setModels(m)
        if (m.length > 0 && !selectedModel) {
          setSelectedModel(m[0])
        }
      } catch (err) {
        console.error('Failed to fetch models', err)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedOrg?.id])

  // ---- Tab data loading -------------------------------------------------------
  useEffect(() => {
    if (!selectedOrg) return
    if (activeTab === 'knowledge') fetchKnowledge()
    if (activeTab === 'history') fetchHistory()
    if (activeTab === 'health') fetchHealth()
    if (activeTab === 'settings') fetchSettings()
    if (activeTab === 'audit') {
      fetchAudit()
      auditIntervalRef.current = setInterval(fetchAudit, 30000)
    }
    return () => {
      if (auditIntervalRef.current) clearInterval(auditIntervalRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, selectedOrg?.id, selectedModel?.id])

  // ---- Training job polling ---------------------------------------------------
  useEffect(() => {
    if (trainingJob && trainingJob.status !== 'completed' && trainingJob.status !== 'failed') {
      trainingPollRef.current = setInterval(async () => {
        try {
          const res = await getTrainingJob(trainingJob.id)
          const job = res.data as TrainingJob
          setTrainingJob(job)
          if (job.status === 'completed' || job.status === 'failed') {
            if (trainingPollRef.current) clearInterval(trainingPollRef.current)
          }
        } catch {
          if (trainingPollRef.current) clearInterval(trainingPollRef.current)
        }
      }, 5000)
    }
    return () => {
      if (trainingPollRef.current) clearInterval(trainingPollRef.current)
    }
  }, [trainingJob?.id, trainingJob?.status])

  // ---- Data fetchers ----------------------------------------------------------

  const fetchKnowledge = useCallback(async () => {
    if (!selectedOrg) return
    setKbLoading(true)
    try {
      const res = await getKnowledge(selectedOrg.id)
      setKnowledgeEntries(res.data.knowledge ?? res.data.entries ?? res.data ?? [])
    } catch (err) {
      console.error('Failed to fetch knowledge', err)
    } finally {
      setKbLoading(false)
    }
  }, [selectedOrg])

  const fetchHistory = useCallback(async () => {
    if (!selectedOrg) return
    setHistoryLoading(true)
    try {
      const res = await getQueryHistory(selectedOrg.id)
      setHistoryEntries(res.data.queries ?? res.data ?? [])
    } catch (err) {
      console.error('Failed to fetch history', err)
    } finally {
      setHistoryLoading(false)
    }
  }, [selectedOrg])

  const fetchHealth = useCallback(async () => {
    if (!selectedOrg) return
    setHealthLoading(true)
    try {
      const res = await getAnalytics(selectedOrg.id)
      setAnalytics(res.data.statistics ?? res.data as AnalyticsData)
    } catch (err) {
      console.error('Failed to fetch analytics', err)
    }
    if (selectedModel) {
      try {
        const res = await getLearningStats(selectedOrg.id, selectedModel.id)
        setLearningStats(res.data as LearningStatsData)
      } catch {
        /* optional endpoint */
      }
      try {
        const res = await getGenerationStats(selectedOrg.id, selectedModel.id)
        setGenerationStats(res.data as GenerationStatsData)
      } catch {
        /* optional endpoint */
      }
      try {
        const res = await getModelAccuracy(selectedOrg.id, selectedModel.id, false)
        setAccuracyData(res.data as AccuracyData)
      } catch {
        /* optional endpoint */
      }
    }
    setHealthLoading(false)
  }, [selectedOrg, selectedModel])

  const fetchSettings = useCallback(async () => {
    if (!selectedOrg) return
    setSettingsOrgName(selectedOrg.name)
    setSettingsNiche(selectedOrg.niche)
    setSettingsPrompt(selectedOrg.metadata?.system_prompt ?? '')
    try {
      const usersRes = await getOrgUsers(selectedOrg.id)
      setOrgUsers(usersRes.data.users ?? usersRes.data ?? [])
    } catch {
      /* optional */
    }
    try {
      const keysRes = await getApiKeys(selectedOrg.id)
      setApiKeys(keysRes.data.api_keys ?? keysRes.data ?? [])
    } catch {
      /* optional */
    }
  }, [selectedOrg])

  const fetchAudit = useCallback(async () => {
    if (!selectedOrg) return
    setAuditLoading(true)
    try {
      const res = await getAuditLogs(selectedOrg.id)
      setAuditEntries(res.data.audit_logs ?? res.data.logs ?? res.data ?? [])
    } catch (err) {
      console.error('Failed to fetch audit logs', err)
    } finally {
      setAuditLoading(false)
    }
  }, [selectedOrg])

  // ---- Action handlers --------------------------------------------------------

  const handleSelectOrg = (org: Organization) => {
    setSelectedOrg(org)
    setSelectedModel(null)
    setCreatedKeyValue(null)
  }

  const handleAddKnowledge = async () => {
    if (!selectedOrg || !newKbContent.trim()) return
    try {
      await addKnowledge(selectedOrg.id, { content: newKbContent, source: newKbSource || undefined })
      setNewKbContent('')
      setNewKbSource('')
      fetchKnowledge()
    } catch (err) {
      console.error('Failed to add knowledge', err)
      showActionError('Failed to add knowledge entry. The knowledge system may be unavailable.')
    }
  }

  const handleDeleteKnowledge = async (kbId: string) => {
    if (!selectedOrg) return
    try {
      await deleteKnowledge(selectedOrg.id, kbId)
      fetchKnowledge()
    } catch (err) {
      console.error('Failed to delete knowledge entry', err)
      showActionError('Failed to delete knowledge entry.')
    }
  }

  const handleGenerateData = async () => {
    if (!selectedOrg || !selectedModel) return
    setGenDataLoading(true)
    try {
      await generateData(selectedOrg.id, selectedModel.id, { num_examples: numExamples })
    } catch (err) {
      console.error('Failed to generate data', err)
      showActionError('Failed to generate training data.')
    } finally {
      setGenDataLoading(false)
    }
  }

  const handleStartTraining = async () => {
    if (!selectedOrg || !selectedModel) return
    setTrainLoading(true)
    try {
      const res = await startTraining(selectedOrg.id, selectedModel.id)
      setTrainingJob(res.data as TrainingJob)
    } catch (err) {
      console.error('Failed to start training', err)
      showActionError('Failed to start training. The training pipeline may be unavailable.')
    } finally {
      setTrainLoading(false)
    }
  }

  const handleSaveSettings = async () => {
    if (!selectedOrg) return
    setSettingsSaving(true)
    try {
      await updateOrganization(selectedOrg.id, {
        name: settingsOrgName,
        niche: settingsNiche,
        system_prompt: settingsPrompt,
      })
      // Update selectedOrg immediately so UI stays in sync
      const updatedOrg = {
        ...selectedOrg,
        name: settingsOrgName,
        niche: settingsNiche,
        metadata: { ...selectedOrg.metadata, system_prompt: settingsPrompt },
      }
      setSelectedOrg(updatedOrg)
      // Also refresh organization list
      const res = await getOrganizations()
      const orgs: Organization[] = res.data.organizations ?? res.data ?? []
      setOrganizations(orgs)
      showActionSuccess('Settings saved successfully.')
    } catch (err: any) {
      console.error('Failed to save settings', err)
      const detail = err?.response?.data?.detail || err?.message || 'Failed to save organization settings.'
      showActionError(detail)
    } finally {
      setSettingsSaving(false)
    }
  }

  const handleUpdateRole = async (userId: string, role: string) => {
    if (!selectedOrg) return
    try {
      await updateUserRole(selectedOrg.id, userId, role)
      const usersRes = await getOrgUsers(selectedOrg.id)
      setOrgUsers(usersRes.data.users ?? usersRes.data ?? [])
    } catch (err) {
      console.error('Failed to update role', err)
      showActionError('Failed to update user role.')
    }
  }

  const handleCreateApiKey = async () => {
    if (!selectedOrg || !newKeyName.trim()) return
    try {
      const res = await createApiKey(selectedOrg.id, newKeyName)
      setCreatedKeyValue(res.data.key ?? res.data.api_key ?? null)
      setNewKeyName('')
      const keysRes = await getApiKeys(selectedOrg.id)
      setApiKeys(keysRes.data.api_keys ?? keysRes.data ?? [])
    } catch (err) {
      console.error('Failed to create API key', err)
      showActionError('Failed to create API key.')
    }
  }

  const handleRevokeApiKey = async (keyId: string) => {
    if (!selectedOrg) return
    try {
      await revokeApiKey(selectedOrg.id, keyId)
      const keysRes = await getApiKeys(selectedOrg.id)
      setApiKeys(keysRes.data.api_keys ?? keysRes.data ?? [])
    } catch (err) {
      console.error('Failed to revoke key', err)
      showActionError('Failed to revoke API key.')
    }
  }

  const handleLogout = async () => {
    await logout()
    window.location.href = '/login'
  }

  // ---- Role helpers -----------------------------------------------------------

  const userRole = user?.role ?? 'member'
  const isAdmin = userRole === 'admin' || userRole === 'owner'
  const isOwner = userRole === 'owner'

  // ---- Render -----------------------------------------------------------------
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* ===================== TOP HEADER BAR ===================== */}
      <header className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-gray-200/60 shadow-sm">
        <div className="flex items-center justify-between px-4 sm:px-6 h-14">
          {/* Left: hamburger + logo */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="lg:hidden p-1.5 rounded-xl text-gray-500 hover:bg-gray-100 transition"
              aria-label="Toggle sidebar"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {sidebarOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-600 to-indigo-700 flex items-center justify-center shadow-sm">
                <span className="text-white text-sm font-bold">P</span>
              </div>
              <h1 className="text-base font-bold text-gray-800 tracking-tight hidden sm:block">PLM Enterprise</h1>
            </div>
          </div>

          {/* Center: org name */}
          {selectedOrg && (
            <span className="hidden md:block text-sm font-medium text-gray-500 bg-gray-100/80 px-3 py-1 rounded-full">{selectedOrg.name}</span>
          )}

          {/* Right: user + logout */}
          <div className="flex items-center gap-2.5">
            <span className="hidden lg:block text-sm text-gray-500">{user?.email}</span>
            <NotificationBell />
            <button
              onClick={handleLogout}
              className="px-3.5 py-1.5 text-sm font-medium text-gray-600 bg-gray-100 rounded-xl hover:bg-gray-200 transition-all duration-200 btn-press"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* ===================== SIDEBAR ===================== */}
        {/* Overlay on mobile */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-20 bg-black/30 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        <aside
          className={`
            fixed lg:static inset-y-0 left-0 z-20
            w-64 bg-white/95 backdrop-blur-sm border-r border-gray-200/60
            transform transition-transform duration-300 ease-out
            ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
            flex flex-col overflow-y-auto pt-14 lg:pt-0 scrollbar-thin
          `}
        >
          <div className="p-4 border-b border-gray-100">
            <a
              href="/onboarding"
              className="flex items-center justify-center gap-2 w-full px-4 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-indigo-600 to-indigo-700 rounded-xl hover:from-indigo-700 hover:to-indigo-800 transition-all duration-200 shadow-sm hover:shadow-md btn-press"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New Organization
            </a>
          </div>

          <nav className="flex-1 p-3 space-y-1">
            {organizations.length === 0 && (
              <p className="text-sm text-gray-400 text-center py-6">No organizations yet</p>
            )}
            {organizations.map((org) => {
              const isSelected = selectedOrg?.id === org.id
              return (
                <div key={org.id}>
                  <button
                    onClick={() => {
                      handleSelectOrg(org)
                      if (window.innerWidth < 1024) setSidebarOpen(false)
                    }}
                    className={`
                      w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium transition
                      ${isSelected ? 'bg-indigo-50 text-indigo-700' : 'text-gray-700 hover:bg-gray-100'}
                    `}
                  >
                    <div className="flex items-center justify-between">
                      <span className="truncate">{org.name}</span>
                      <span className={`ml-2 shrink-0 text-xs px-1.5 py-0.5 rounded-full ${statusColor(org.status)}`}>
                        {org.status}
                      </span>
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5">{org.niche}</div>
                  </button>

                  {/* Models under selected org */}
                  {isSelected && models.length > 0 && (
                    <div className="ml-4 mt-1 space-y-0.5">
                      {models.map((model) => {
                        const modelSelected = selectedModel?.id === model.id
                        return (
                          <button
                            key={model.id}
                            onClick={() => setSelectedModel(model)}
                            className={`
                              w-full text-left px-3 py-1.5 rounded-md text-xs transition
                              ${modelSelected ? 'bg-indigo-100 text-indigo-700 font-semibold' : 'text-gray-500 hover:bg-gray-50'}
                            `}
                          >
                            <div className="flex items-center justify-between">
                              <span className="truncate">{model.name}</span>
                              <span className={`ml-1 shrink-0 px-1.5 py-0.5 rounded-full ${statusColor(model.status)}`}>
                                {model.status}
                              </span>
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </nav>
        </aside>

        {/* ===================== MAIN CONTENT ===================== */}
        <main className="flex-1 overflow-y-auto">
          {!selectedOrg ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center px-6">
                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-indigo-100 flex items-center justify-center">
                  <svg className="w-8 h-8 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                </div>
                <h2 className="text-xl font-semibold text-gray-800 mb-1">Select an Organization</h2>
                <p className="text-sm text-gray-500">Choose an organization from the sidebar to get started</p>
              </div>
            </div>
          ) : (
            <div className="flex flex-col h-full">
              {/* ---- Tab Navigation ---- */}
              <div className="border-b border-gray-200/60 bg-white/60 backdrop-blur-sm px-4 sm:px-6 overflow-x-auto scrollbar-thin">
                <nav className="flex gap-1 -mb-px" aria-label="Tabs">
                  {(Object.keys(TAB_LABELS) as TabKey[]).map((tab) => {
                    // Hide settings if not admin, hide audit if not owner
                    if (tab === 'settings' && !isAdmin) return null
                    if (tab === 'audit' && !isOwner) return null

                    const active = activeTab === tab
                    return (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`
                          whitespace-nowrap px-4 py-3 text-sm font-medium border-b-2 transition-all duration-200
                          ${active
                            ? 'border-indigo-600 text-indigo-600'
                            : 'border-transparent text-gray-400 hover:text-gray-600 hover:border-gray-300'}
                        `}
                      >
                        {TAB_LABELS[tab]}
                      </button>
                    )
                  })}
                </nav>
              </div>

              {/* ---- Tab Content ---- */}
              <div className="flex-1 overflow-y-auto p-4 sm:p-6">
                {/* Action error banner */}
                {actionError && (
                  <div className="mb-4 bg-red-50 border border-red-200 rounded-lg px-4 py-3 flex items-center justify-between">
                    <span className="text-sm text-red-700">{actionError}</span>
                    <button
                      onClick={() => setActionError(null)}
                      className="ml-3 text-red-400 hover:text-red-600 shrink-0"
                      aria-label="Dismiss"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                )}

                {/* Action success banner */}
                {actionSuccess && (
                  <div className="mb-4 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3 flex items-center justify-between animate-fade-in">
                    <div className="flex items-center gap-2">
                      <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span className="text-sm text-emerald-700">{actionSuccess}</span>
                    </div>
                    <button
                      onClick={() => setActionSuccess(null)}
                      className="ml-3 text-emerald-400 hover:text-emerald-600 shrink-0"
                      aria-label="Dismiss"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                )}

                {activeTab === 'chat' && (
                  <div className="space-y-3">
                    {/* v2.0 Modality selector */}
                    <div className="flex items-center justify-between">
                      <ModalitySelector
                        selected={selectedModality}
                        onChange={setSelectedModality}
                        className="flex-shrink-0"
                      />
                      <PrivacyBadge compact />
                    </div>
                    <ChatPanel />
                  </div>
                )}

                {activeTab === 'knowledge' && (
                  <KnowledgeTab
                    entries={knowledgeEntries}
                    loading={kbLoading}
                    newContent={newKbContent}
                    setNewContent={setNewKbContent}
                    newSource={newKbSource}
                    setNewSource={setNewKbSource}
                    onAdd={handleAddKnowledge}
                    onDelete={handleDeleteKnowledge}
                    canEdit={isAdmin}
                    orgId={selectedOrg?.id}
                    onRefresh={fetchKnowledge}
                  />
                )}

                {activeTab === 'history' && (
                  <HistoryTab
                    entries={historyEntries}
                    loading={historyLoading}
                    expandedId={expandedHistoryId}
                    onToggle={(id) => setExpandedHistoryId(expandedHistoryId === id ? null : id)}
                  />
                )}

                {activeTab === 'health' && (
                  <HealthTab
                    model={selectedModel}
                    analytics={analytics}
                    loading={healthLoading}
                    numExamples={numExamples}
                    setNumExamples={setNumExamples}
                    genDataLoading={genDataLoading}
                    trainLoading={trainLoading}
                    trainingJob={trainingJob}
                    learningStats={learningStats}
                    generationStats={generationStats}
                    accuracyData={accuracyData}
                    accuracyRefreshing={accuracyRefreshing}
                    onRefreshAccuracy={async () => {
                      if (!selectedOrg || !selectedModel) return
                      setAccuracyRefreshing(true)
                      try {
                        const res = await getModelAccuracy(selectedOrg.id, selectedModel.id, true)
                        setAccuracyData(res.data as AccuracyData)
                      } catch (err) {
                        console.error('Failed to refresh accuracy', err)
                      } finally {
                        setAccuracyRefreshing(false)
                      }
                    }}
                    onGenerateData={handleGenerateData}
                    onStartTraining={handleStartTraining}
                    canTrain={isAdmin}
                  />
                )}

                {activeTab === 'settings' && isAdmin && (
                  <SettingsTab
                    orgName={settingsOrgName}
                    setOrgName={setSettingsOrgName}
                    niche={settingsNiche}
                    setNiche={setSettingsNiche}
                    systemPrompt={settingsPrompt}
                    setSystemPrompt={setSettingsPrompt}
                    saving={settingsSaving}
                    onSave={handleSaveSettings}
                    users={orgUsers}
                    onUpdateRole={handleUpdateRole}
                    apiKeys={apiKeys}
                    newKeyName={newKeyName}
                    setNewKeyName={setNewKeyName}
                    createdKeyValue={createdKeyValue}
                    onCreateKey={handleCreateApiKey}
                    onRevokeKey={handleRevokeApiKey}
                  />
                )}

                {activeTab === 'audit' && isOwner && (
                  <AuditTab entries={auditEntries} loading={auditLoading} />
                )}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

// ===========================================================================
// TAB COMPONENTS
// ===========================================================================

// ---------------------------------------------------------------------------
// Knowledge Base Tab
// ---------------------------------------------------------------------------

interface KnowledgeTabProps {
  entries: KnowledgeEntry[]
  loading: boolean
  newContent: string
  setNewContent: (v: string) => void
  newSource: string
  setNewSource: (v: string) => void
  onAdd: () => void
  onDelete: (id: string) => void
  canEdit: boolean
  orgId: string | undefined
  onRefresh: () => void
}

function KnowledgeTab({ entries, loading, newContent, setNewContent, newSource, setNewSource, onAdd, onDelete, canEdit, orgId, onRefresh }: KnowledgeTabProps) {
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<string | null>(null)
  const [category, setCategory] = useState('general')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileDrop = async (files: FileList | null) => {
    if (!files || files.length === 0 || !orgId) return
    setUploading(true)
    setUploadMsg(null)
    try {
      const { uploadKnowledgeFile } = await import('@/lib/api')
      const file = files[0]
      const res = await uploadKnowledgeFile(orgId, file, category)
      setUploadMsg(`Uploaded ${res.data.file_name}: ${res.data.chunks_added} chunks added`)
      onRefresh()
    } catch (err: any) {
      setUploadMsg(err?.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-fade-in">
      {/* File Upload Zone */}
      {canEdit && (
        <div
          className={`bg-white/80 backdrop-blur-sm rounded-2xl border-2 border-dashed p-8 text-center transition-all duration-300 ${
            dragOver ? 'border-indigo-500 bg-indigo-50/80 scale-[1.01]' : 'border-gray-200 hover:border-indigo-300'
          }`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFileDrop(e.dataTransfer.files) }}
        >
          <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-indigo-100 to-indigo-50 flex items-center justify-center">
            <svg className="w-7 h-7 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
          </div>
          <p className="text-sm font-medium text-gray-700 mb-1">
            {uploading ? 'Processing your file...' : 'Drag & drop a file here, or click to browse'}
          </p>
          <p className="text-xs text-gray-400 mb-4">Supports PDF, TXT, CSV (max 10MB)</p>
          <div className="flex items-center justify-center gap-3 mb-4">
            <label className="text-sm text-gray-600">Category:</label>
            <input
              type="text"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="px-3 py-1.5 border border-gray-200 rounded-xl text-sm w-40 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white/80"
              placeholder="general"
            />
          </div>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="px-6 py-2.5 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 disabled:bg-gray-300 transition-all duration-200 btn-press shadow-sm hover:shadow-md"
          >
            {uploading ? 'Processing...' : 'Choose File'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.txt,.csv,.md,.log"
            className="hidden"
            onChange={(e) => handleFileDrop(e.target.files)}
          />
          {uploadMsg && (
            <p className={`mt-4 text-sm font-medium ${uploadMsg.includes('fail') || uploadMsg.includes('error') ? 'text-red-600' : 'text-emerald-600'}`}>
              {uploadMsg}
            </p>
          )}
        </div>
      )}

      {/* Manual text entry */}
      <div className="bg-white/80 backdrop-blur-sm rounded-2xl border border-gray-100 shadow-sm p-6">
        <h2 className="text-base font-semibold text-gray-800 mb-4">Add Text Entry</h2>
        <textarea
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          placeholder="Enter knowledge content..."
          rows={4}
          className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-y bg-gray-50/50 transition-colors"
        />
        <div className="flex flex-col sm:flex-row gap-3 mt-3">
          <input
            type="text"
            value={newSource}
            onChange={(e) => setNewSource(e.target.value)}
            placeholder="Source (optional)"
            className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-gray-50/50 transition-colors"
          />
          <button
            onClick={onAdd}
            disabled={!canEdit || !newContent.trim()}
            className="px-6 py-2.5 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed transition-all duration-200 btn-press shadow-sm hover:shadow-md"
          >
            {canEdit ? 'Add Entry' : 'Admin Only'}
          </button>
        </div>
      </div>

      {/* Entry count */}
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-800">Knowledge Entries</h2>
        <span className="text-sm text-gray-400 bg-gray-100 px-3 py-1 rounded-full">{entries.length} entries</span>
      </div>

      {/* Entries list */}
      {loading ? (
        <div className="space-y-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : entries.length === 0 ? (
        <EmptyState message="No knowledge entries yet. Upload a file or add text above." />
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 flex flex-col sm:flex-row sm:items-start gap-3"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-800 whitespace-pre-wrap line-clamp-3">{entry.content}</p>
                <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
                  {entry.source && <span>Source: {entry.source}</span>}
                  <span>{formatDate(entry.created_at)}</span>
                </div>
              </div>
              {canEdit && (
                <button
                  onClick={() => onDelete(entry.id)}
                  className="shrink-0 px-3 py-1 text-xs font-medium text-red-600 border border-red-200 rounded-md hover:bg-red-50 transition"
                >
                  Delete
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// History Tab
// ---------------------------------------------------------------------------

interface HistoryTabProps {
  entries: HistoryEntry[]
  loading: boolean
  expandedId: string | null
  onToggle: (id: string) => void
}

function HistoryTab({ entries, loading, expandedId, onToggle }: HistoryTabProps) {
  if (loading) return <SkeletonTable rows={5} />

  return (
    <div className="max-w-5xl mx-auto space-y-4 animate-fade-in">
      <h2 className="text-lg font-semibold text-gray-800">Query History</h2>

      {entries.length === 0 ? (
        <EmptyState message="No query history yet." />
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Query</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Response</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Confidence</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Time</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Feedback</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {entries.map((entry) => {
                  const id = entry.query_id ?? entry.id
                  const isExpanded = expandedId === id
                  return (
                    <tr
                      key={id}
                      onClick={() => onToggle(id)}
                      className="cursor-pointer hover:bg-gray-50 transition"
                    >
                      <td className="px-4 py-3 max-w-[200px]">
                        <p className={isExpanded ? 'whitespace-pre-wrap' : 'truncate'}>
                          {isExpanded ? entry.query : truncate(entry.query, 60)}
                        </p>
                      </td>
                      <td className="px-4 py-3 max-w-[250px]">
                        <p className={isExpanded ? 'whitespace-pre-wrap' : 'truncate'}>
                          {isExpanded ? entry.response : truncate(entry.response, 80)}
                        </p>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {entry.confidence != null ? `${(entry.confidence * 100).toFixed(1)}%` : '-'}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {entry.response_time_ms != null ? `${entry.response_time_ms}ms` : '-'}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap capitalize">{entry.feedback ?? '-'}</td>
                      <td className="px-4 py-3 whitespace-nowrap text-gray-400">{formatDate(entry.created_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Model Health Tab
// ---------------------------------------------------------------------------

interface HealthTabProps {
  model: Model | null
  analytics: AnalyticsData | null
  loading: boolean
  numExamples: number
  setNumExamples: (v: number) => void
  genDataLoading: boolean
  trainLoading: boolean
  trainingJob: TrainingJob | null
  learningStats: LearningStatsData | null
  generationStats: GenerationStatsData | null
  accuracyData: AccuracyData | null
  accuracyRefreshing: boolean
  onRefreshAccuracy: () => void
  onGenerateData: () => void
  onStartTraining: () => void
  canTrain: boolean
}

function HealthTab({
  model,
  analytics,
  loading,
  numExamples,
  setNumExamples,
  genDataLoading,
  trainLoading,
  trainingJob,
  learningStats,
  generationStats,
  accuracyData,
  accuracyRefreshing,
  onRefreshAccuracy,
  onGenerateData,
  onStartTraining,
  canTrain,
}: HealthTabProps) {
  if (loading) return (
    <div className="max-w-4xl mx-auto space-y-6 animate-fade-in">
      <SkeletonCard />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[1,2,3,4].map(i => <div key={i} className="skeleton h-20 rounded-2xl" />)}
      </div>
      <SkeletonCard />
    </div>
  )

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-fade-in">
      {/* Model Phase Indicator — lifecycle timeline */}
      <ModelPhaseIndicator />

      {/* v2.0: Pet Status + Privacy Badge in a two-column layout */}
      {model && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <PetStatus />
          <PrivacyBadge />
        </div>
      )}

      {/* Model status card */}
      {model && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-gray-800">{model.name}</h2>
              <p className="text-sm text-gray-500 mt-0.5">Base: {model.base_model} | Version: {model.version}</p>
            </div>
            <span className={`px-3 py-1 text-sm font-semibold rounded-full ${statusColor(model.status)}`}>
              {model.status}
            </span>
          </div>

          {model.metrics && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              {model.metrics.has_adapter ? (
                <div className="space-y-1">
                  <p className="text-xs font-semibold text-emerald-600">Fine-tuned model (real LoRA adapter)</p>
                  <p className="text-xs text-gray-500">
                    Backend: {model.metrics.backend_used ?? 'unknown'} |
                    Adapter: {model.metrics.adapter_size_mb ? `${model.metrics.adapter_size_mb}MB` : 'n/a'} |
                    Loss: {model.metrics.train_loss ?? 'n/a'}
                  </p>
                  {model.metrics.adapter_path && (
                    <p className="text-xs text-gray-400 font-mono truncate">Path: {model.metrics.adapter_path}</p>
                  )}
                </div>
              ) : (
                <div className="space-y-1">
                  <p className="text-xs font-semibold text-amber-600">Knowledge-enhanced mode (no fine-tuned adapter yet)</p>
                  <p className="text-xs text-gray-500">
                    {model.metrics.note ?? 'Using PLM inference with knowledge context. Configure a GPU backend below for real fine-tuning.'}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 🎯 MODEL ACCURACY GAUGE - Real-time accuracy score */}
      {accuracyData && (
        <div className="bg-gradient-to-br from-indigo-50 to-purple-50 rounded-xl shadow-sm border border-indigo-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-800">Model Accuracy</h3>
            <button
              onClick={onRefreshAccuracy}
              disabled={accuracyRefreshing}
              className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1 disabled:opacity-50"
            >
              {accuracyRefreshing ? (
                <span className="animate-spin">⟳</span>
              ) : (
                <span>↻</span>
              )}
              Refresh
            </button>
          </div>
          
          {/* Main accuracy display */}
          <div className="flex items-center gap-8">
            {/* Circular gauge */}
            <div className="relative w-32 h-32">
              <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                <circle
                  cx="50"
                  cy="50"
                  r="42"
                  fill="none"
                  stroke="#e5e7eb"
                  strokeWidth="12"
                />
                <circle
                  cx="50"
                  cy="50"
                  r="42"
                  fill="none"
                  stroke={accuracyData.accuracy >= 80 ? '#10b981' : accuracyData.accuracy >= 60 ? '#f59e0b' : '#ef4444'}
                  strokeWidth="12"
                  strokeLinecap="round"
                  strokeDasharray={`${(accuracyData.accuracy / 100) * 264} 264`}
                  className="transition-all duration-1000"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-3xl font-bold text-gray-800">{accuracyData.accuracy.toFixed(1)}%</span>
                <span className="text-xs text-gray-500">accuracy</span>
              </div>
            </div>

            {/* Details */}
            <div className="flex-1 space-y-3">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-gray-500">Tests Passed</p>
                  <p className="text-lg font-semibold text-gray-800">
                    {accuracyData.tests_passed}/{accuracyData.tests_total}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Confidence</p>
                  <p className="text-lg font-semibold text-gray-800">
                    {(accuracyData.confidence * 100).toFixed(0)}%
                  </p>
                </div>
              </div>
              
              {accuracyData.breakdown && (
                <div className="pt-2 border-t border-indigo-100">
                  <p className="text-xs text-gray-500 mb-1">Breakdown</p>
                  <div className="flex gap-3 text-xs">
                    <span className="text-gray-600">Base: {accuracyData.breakdown.raw_score.toFixed(1)}%</span>
                    <span className="text-emerald-600">+RAG: {accuracyData.breakdown.rag_bonus.toFixed(1)}%</span>
                    <span className="text-indigo-600">{accuracyData.breakdown.training_examples} examples</span>
                  </div>
                </div>
              )}

              <p className="text-xs text-gray-400">
                {accuracyData.cache_hit ? 'Cached result • ' : ''}
                Last updated: {accuracyData.calculated_at ? new Date(accuracyData.calculated_at).toLocaleTimeString() : 'now'}
              </p>
            </div>
          </div>

          {/* Progress bar with stages */}
          <div className="mt-4 pt-4 border-t border-indigo-100">
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>Learning</span>
              <span>Basic</span>
              <span>Competent</span>
              <span>Expert</span>
            </div>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-1000 ${
                  accuracyData.accuracy >= 90 ? 'bg-gradient-to-r from-emerald-400 to-emerald-600' :
                  accuracyData.accuracy >= 75 ? 'bg-gradient-to-r from-blue-400 to-blue-600' :
                  accuracyData.accuracy >= 60 ? 'bg-gradient-to-r from-amber-400 to-amber-600' :
                  'bg-gradient-to-r from-red-400 to-red-600'
                }`}
                style={{ width: `${accuracyData.accuracy}%` }}
              />
            </div>
            <div className="flex justify-between text-xs mt-1">
              <span className="text-gray-400">0%</span>
              <span className="text-gray-400">50%</span>
              <span className="text-gray-400">75%</span>
              <span className="text-gray-400">100%</span>
            </div>
          </div>
        </div>
      )}

      {/* Metrics cards */}
      {analytics && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard label="Total Queries" value={String(analytics.total_queries ?? 0)} />
          <MetricCard
            label="Avg Confidence"
            value={analytics.avg_confidence != null ? `${(analytics.avg_confidence * 100).toFixed(1)}%` : '-'}
          />
          <MetricCard
            label="Avg Response Time"
            value={analytics.avg_response_time_ms != null ? `${analytics.avg_response_time_ms.toFixed(0)}ms` : '-'}
          />
          <MetricCard label="Training Examples" value={String(analytics.total_training_examples ?? 0)} />
        </div>
      )}

      {/* Live Generation Stats */}
      {generationStats && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="text-md font-semibold text-gray-800 mb-4">Live Data Generation</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-800">{generationStats.total_count}</p>
              <p className="text-xs text-gray-500 mt-1">Total Generated</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-indigo-600">{generationStats.examples_generated_today}</p>
              <p className="text-xs text-gray-500 mt-1">Generated Today</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-emerald-600">{generationStats.generation_rate_per_hour.toFixed(1)}</p>
              <p className="text-xs text-gray-500 mt-1">Per Hour</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-purple-600">{Object.keys(generationStats.source_breakdown).length}</p>
              <p className="text-xs text-gray-500 mt-1">Sources</p>
            </div>
          </div>
          {Object.keys(generationStats.source_breakdown).length > 0 && (
            <div className="mt-4 pt-3 border-t border-gray-100">
              <p className="text-xs font-medium text-gray-500 mb-2">Source Breakdown</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(generationStats.source_breakdown).map(([source, count]) => (
                  <span key={source} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
                    {source.replace(/_/g, ' ')}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Training data breakdown */}
      {learningStats && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
          <h3 className="text-md font-semibold text-gray-800 mb-4">Training Data Sources</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-800">{learningStats.total_training_examples ?? 0}</p>
              <p className="text-xs text-gray-500 mt-1">Total Examples</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-indigo-600">{learningStats.from_continuous_learning ?? 0}</p>
              <p className="text-xs text-gray-500 mt-1">API Generated</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-emerald-600">{learningStats.from_user_feedback ?? 0}</p>
              <p className="text-xs text-gray-500 mt-1">From Feedback</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-purple-600">
                {(learningStats.average_quality_score ?? 0).toFixed(1)}
              </p>
              <p className="text-xs text-gray-500 mt-1">Avg Quality</p>
            </div>
          </div>

          {/* Visual breakdown bar */}
          {(learningStats.total_training_examples ?? 0) > 0 && (
            <div className="mt-4">
              <div className="flex h-3 rounded-full overflow-hidden bg-gray-100">
                {learningStats.from_continuous_learning > 0 && (
                  <div
                    className="bg-indigo-500 transition-all duration-500"
                    style={{ width: `${(learningStats.from_continuous_learning / learningStats.total_training_examples) * 100}%` }}
                    title="API Generated"
                  />
                )}
                {learningStats.from_user_feedback > 0 && (
                  <div
                    className="bg-emerald-500 transition-all duration-500"
                    style={{ width: `${(learningStats.from_user_feedback / learningStats.total_training_examples) * 100}%` }}
                    title="From Feedback"
                  />
                )}
                {(learningStats.total_training_examples - (learningStats.from_continuous_learning ?? 0) - (learningStats.from_user_feedback ?? 0)) > 0 && (
                  <div
                    className="bg-purple-500 transition-all duration-500"
                    style={{ width: `${((learningStats.total_training_examples - (learningStats.from_continuous_learning ?? 0) - (learningStats.from_user_feedback ?? 0)) / learningStats.total_training_examples) * 100}%` }}
                    title="From Chat"
                  />
                )}
              </div>
              <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-indigo-500" /> API Generated</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Feedback</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-purple-500" /> User Chat</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* GPU Configuration Panel */}
      <GPUConfigPanel />

      {/* Manual Training Controls */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 space-y-4">
        <h3 className="text-md font-semibold text-gray-800">Manual Training Controls</h3>
        <p className="text-xs text-gray-500">
          Training happens automatically when enough data is collected and a GPU is configured.
          Use these controls for manual overrides.
        </p>

        <div className="flex flex-col sm:flex-row sm:items-end gap-3">
          <div>
            <label className="block text-sm text-gray-600 mb-1">Number of examples</label>
            <input
              type="number"
              min={1}
              max={1000}
              value={numExamples}
              onChange={(e) => setNumExamples(parseInt(e.target.value) || 1)}
              className="w-32 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>
          <button
            onClick={onGenerateData}
            disabled={!canTrain || genDataLoading || !model}
            className="px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition"
          >
            {!canTrain ? 'Admin Only' : genDataLoading ? 'Generating...' : 'Generate Training Data'}
          </button>
          <button
            onClick={onStartTraining}
            disabled={!canTrain || trainLoading || !model}
            className="px-4 py-2 bg-emerald-600 text-white text-sm font-semibold rounded-lg hover:bg-emerald-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition"
          >
            {!canTrain ? 'Admin Only' : trainLoading ? 'Starting...' : 'Start Training'}
          </button>
        </div>

        {/* Training job progress */}
        {trainingJob && (
          <div className="border-t border-gray-100 pt-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-600">
                Training Job: <span className="font-mono text-xs">{trainingJob.id}</span>
              </span>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${statusColor(trainingJob.status)}`}>
                {trainingJob.status}
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2.5">
              <div
                className="bg-indigo-600 h-2.5 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(trainingJob.progress ?? 0, 100)}%` }}
              />
            </div>
            <p className="text-xs text-gray-400 mt-1">{(trainingJob.progress ?? 0).toFixed(0)}% complete</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Settings Tab (admin only)
// ---------------------------------------------------------------------------

interface SettingsTabProps {
  orgName: string
  setOrgName: (v: string) => void
  niche: string
  setNiche: (v: string) => void
  systemPrompt: string
  setSystemPrompt: (v: string) => void
  saving: boolean
  onSave: () => void
  users: OrgUser[]
  onUpdateRole: (userId: string, role: string) => void
  apiKeys: ApiKeyEntry[]
  newKeyName: string
  setNewKeyName: (v: string) => void
  createdKeyValue: string | null
  onCreateKey: () => void
  onRevokeKey: (keyId: string) => void
}

function SettingsTab({
  orgName,
  setOrgName,
  niche,
  setNiche,
  systemPrompt,
  setSystemPrompt,
  saving,
  onSave,
  users,
  onUpdateRole,
  apiKeys,
  newKeyName,
  setNewKeyName,
  createdKeyValue,
  onCreateKey,
  onRevokeKey,
}: SettingsTabProps) {
  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Organization settings */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 space-y-4">
        <h2 className="text-lg font-semibold text-gray-800">Organization Settings</h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Organization Name</label>
            <input
              type="text"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Niche</label>
            <input
              type="text"
              value={niche}
              onChange={(e) => setNiche(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">System Prompt</label>
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={5}
            className="w-full px-4 py-3 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-y font-mono"
          />
        </div>

        <button
          onClick={onSave}
          disabled={saving}
          className="px-5 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition"
        >
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>

      {/* User management */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
        <h3 className="text-md font-semibold text-gray-800 mb-4">User Management</h3>

        {users.length === 0 ? (
          <p className="text-sm text-gray-400">No users found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Email</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Role</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {users.map((u) => (
                  <tr key={u.id}>
                    <td className="px-4 py-3 text-gray-800">{u.email}</td>
                    <td className="px-4 py-3 capitalize">{u.role}</td>
                    <td className="px-4 py-3">
                      <select
                        value={u.role}
                        onChange={(e) => onUpdateRole(u.id, e.target.value)}
                        className="px-2 py-1 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      >
                        <option value="member">Member</option>
                        <option value="admin">Admin</option>
                        <option value="owner">Owner</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* API Keys */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 space-y-4">
        <h3 className="text-md font-semibold text-gray-800">API Keys</h3>

        {/* Create key form */}
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            placeholder="Key name"
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
          <button
            onClick={onCreateKey}
            disabled={!newKeyName.trim()}
            className="px-5 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition"
          >
            Create Key
          </button>
        </div>

        {/* Newly created key warning */}
        {createdKeyValue && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
            <p className="text-sm font-semibold text-amber-800 mb-1">
              Save this key now -- it will not be shown again.
            </p>
            <code className="block text-sm font-mono text-amber-900 bg-amber-100 px-3 py-2 rounded break-all select-all">
              {createdKeyValue}
            </code>
          </div>
        )}

        {/* Key list */}
        {apiKeys.length === 0 ? (
          <p className="text-sm text-gray-400">No API keys.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Prefix</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Name</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Status</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Last Used</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {apiKeys.map((k) => (
                  <tr key={k.id}>
                    <td className="px-4 py-3 font-mono text-xs text-gray-700">{k.prefix}...</td>
                    <td className="px-4 py-3 text-gray-800">{k.name}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${statusColor(k.status)}`}>
                        {k.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-400 whitespace-nowrap">
                      {k.last_used_at ? formatDate(k.last_used_at) : 'Never'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => onRevokeKey(k.id)}
                        className="px-3 py-1 text-xs font-medium text-red-600 border border-red-200 rounded-md hover:bg-red-50 transition"
                      >
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Team Model Sharing */}
      <div className="bg-gradient-to-br from-indigo-50 to-purple-50 rounded-xl border border-indigo-100 p-5 space-y-3">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center shrink-0">
            <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
              />
            </svg>
          </div>
          <div>
            <h3 className="text-md font-semibold text-gray-800">Shared Team Model</h3>
            <p className="text-sm text-gray-600 mt-1">
              All {users.length > 0 ? users.length : ''} team member{users.length !== 1 ? 's' : ''} share
              the same privately trained model. When anyone on the team chats, their interactions
              automatically improve the shared model for everyone.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                Data stays private
              </span>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                Model improves with use
              </span>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
                <span className="w-1.5 h-1.5 rounded-full bg-purple-500" />
                One model, whole team
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Audit Log Tab (owner only)
// ---------------------------------------------------------------------------

interface AuditTabProps {
  entries: AuditEntry[]
  loading: boolean
}

function AuditTab({ entries, loading }: AuditTabProps) {
  if (loading && entries.length === 0) return <SkeletonTable rows={6} />

  return (
    <div className="max-w-5xl mx-auto space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Audit Log</h2>
        <span className="text-xs text-gray-400">Auto-refreshes every 30s</span>
      </div>

      {entries.length === 0 ? (
        <EmptyState message="No audit entries found." />
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Action</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Resource Type</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">User</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Details</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {entries.map((entry) => (
                  <tr key={entry.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-800 whitespace-nowrap">{entry.action}</td>
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{entry.resource_type}</td>
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                      {entry.user_email ?? entry.user_id ?? '-'}
                    </td>
                    <td className="px-4 py-3 text-gray-500 max-w-[250px] truncate">
                      {entry.details ? truncate(JSON.stringify(entry.details), 80) : '-'}
                    </td>
                    <td className="px-4 py-3 text-gray-400 whitespace-nowrap">{formatDate(entry.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

// ===========================================================================
// Shared small components
// ===========================================================================

function MetricCard({ label, value, accent }: { label: string; value: string; accent?: string }) {
  const gradientClass = accent === 'emerald' ? 'card-gradient-emerald'
    : accent === 'amber' ? 'card-gradient-amber'
    : accent === 'rose' ? 'card-gradient-rose'
    : 'card-gradient-indigo'

  return (
    <div className={`rounded-2xl p-5 ${gradientClass} border border-white/60 shadow-sm hover:shadow-md transition-all duration-300 hover:-translate-y-0.5`}>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-2xl font-bold text-gray-800 mt-1.5">{value}</p>
    </div>
  )
}

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="relative">
        <div className="w-10 h-10 border-4 border-indigo-200 rounded-full" />
        <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin absolute inset-0" />
      </div>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-5 space-y-3 animate-fade-in">
      <div className="skeleton h-4 w-1/3" />
      <div className="skeleton h-3 w-full" />
      <div className="skeleton h-3 w-2/3" />
    </div>
  )
}

function SkeletonTable({ rows = 4 }: { rows?: number }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden animate-fade-in">
      <div className="p-4 border-b border-gray-100 flex gap-6">
        <div className="skeleton h-4 w-24" />
        <div className="skeleton h-4 w-32" />
        <div className="skeleton h-4 w-20" />
        <div className="skeleton h-4 w-16" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="p-4 border-b border-gray-50 flex gap-6">
          <div className="skeleton h-3 w-28" />
          <div className="skeleton h-3 w-36" />
          <div className="skeleton h-3 w-16" />
          <div className="skeleton h-3 w-20" />
        </div>
      ))}
    </div>
  )
}

function EmptyState({ message, icon }: { message: string; icon?: React.ReactNode }) {
  return (
    <div className="bg-white/80 backdrop-blur-sm rounded-2xl border border-gray-100 shadow-sm p-12 text-center animate-fade-in">
      {icon || (
        <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-indigo-100 to-indigo-50 flex items-center justify-center">
          <svg className="w-7 h-7 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
          </svg>
        </div>
      )}
      <p className="text-sm text-gray-500 leading-relaxed">{message}</p>
    </div>
  )
}
