import { create } from 'zustand'
import { supabase, type AuthUser, type UserRole } from './supabase'

interface Organization {
  id: string
  name: string
  slug: string
  niche: string
  tier: string
  status: string
  metadata?: { system_prompt?: string }
  created_at?: string
  statistics?: any
}

interface Model {
  id: string
  organization_id: string
  name: string
  version: string
  status: string
  base_model: string
  metrics?: any
  deployed_at?: string
}

interface QueryResponse {
  query_id: string
  response: string
  confidence: number
  response_time_ms: number
  context_used: boolean
  fact_checked: boolean
  fact_check_results: any[]
  sources: string[]
  api_used?: string
}

interface Conversation {
  id: string
  organization_id: string
  user_id?: string
  model_id?: string
  title: string
  status: string
  assistant_id?: string
  created_at: string
  updated_at: string
}

interface Message {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  query_id?: string
  metadata?: Record<string, any>
  created_at: string
}

interface Assistant {
  id: string
  organization_id: string
  name: string
  description?: string
  assistant_type: string
  system_prompt: string
  icon: string
  temperature: number
  use_rag: boolean
  knowledge_categories?: string[]
  status: string
  created_at: string
}

interface ModelPhase {
  phase: 'collecting' | 'ready_to_train' | 'training' | 'deployed' | 'learning'
  sub_status?: string | null
  training_data_count: number
  training_data_target: number
  progress_pct: number
  has_adapter: boolean
  privacy_mode_available: boolean
  privacy_mode_forced: boolean
  auto_learning_enabled: boolean
  gpu_backend?: string | null
  base_model: string
  estimated_ready_at?: string | null
  generation_rate_per_hour: number
  examples_generated_today: number
  last_training_at?: string | null
  training_activity?: {
    started_at?: string | null
    completed_at?: string | null
    backend_used: string
    base_model: string
    data_used: number
    current_step: string
    steps_log: { step: string; time: string; detail?: string }[]
    training_results?: any
  } | null
}

interface PetStatus {
  org_id: string
  model_id: string
  stage: string
  stage_title: string
  stage_emoji: string
  stage_color: string
  personality_type: string
  mood: string
  mood_emoji: string
  mood_description: string
  mood_tone: string
  xp: number
  xp_to_next: number | null
  evolution_pct: number
  streak_days: number
  streak_xp_bonus: number
  training_examples: number
  accuracy: number
  phase: string
  has_adapter: boolean
  org_niche: string
  personality_prompt: string
  response_prefix: string
  next_stage_requirements: {
    next_stage: string
    next_stage_title: string
    next_stage_emoji: string
    examples_needed: number
    accuracy_needed_pct: number
    examples_target: number
    accuracy_target_pct: number
    description: string
  } | null
  all_stages: Array<{
    stage: string
    title: string
    emoji: string
    color: string
    min_examples: number
    min_accuracy_pct: number
    unlocked: boolean
    current: boolean
  }>
  computed_at: string
}

interface AppState {
  // Auth
  user: AuthUser | null
  token: string | null
  isLoading: boolean
  isAuthenticated: boolean

  // Data
  organizations: Organization[]
  selectedOrg: Organization | null
  models: Model[]
  selectedModel: Model | null
  modelPhase: ModelPhase | null
  petStatus: PetStatus | null

  // Conversations
  conversations: Conversation[]
  selectedConversation: Conversation | null
  messages: Message[]

  // Assistants
  assistants: Assistant[]

  // UI
  sidebarOpen: boolean
  activeTab: 'chat' | 'knowledge' | 'history' | 'health' | 'settings' | 'audit'

  // Actions
  setUser: (user: AuthUser | null) => void
  setToken: (token: string | null) => void
  setLoading: (loading: boolean) => void
  setOrganizations: (orgs: Organization[]) => void
  setSelectedOrg: (org: Organization | null) => void
  setModels: (models: Model[]) => void
  setSelectedModel: (model: Model | null) => void
  setModelPhase: (phase: ModelPhase | null) => void
  setPetStatus: (status: PetStatus | null) => void
  setConversations: (convs: Conversation[]) => void
  setSelectedConversation: (conv: Conversation | null) => void
  setMessages: (msgs: Message[]) => void
  setAssistants: (assistants: Assistant[]) => void
  setSidebarOpen: (open: boolean) => void
  setActiveTab: (tab: AppState['activeTab']) => void

  // Auth actions
  login: (email: string, password: string) => Promise<{ error?: string }>
  signup: (email: string, password: string) => Promise<{ error?: string }>
  logout: () => Promise<void>
  initAuth: () => Promise<void>
}

// Track whether onAuthStateChange has been registered
let authListenerRegistered = false

export const useStore = create<AppState>((set, get) => ({
  // Initial state
  user: null,
  token: null,
  isLoading: true,
  isAuthenticated: false,
  organizations: [],
  selectedOrg: null,
  models: [],
  selectedModel: null,
  modelPhase: null,
  petStatus: null,
  conversations: [],
  selectedConversation: null,
  messages: [],
  assistants: [],
  sidebarOpen: true,
  activeTab: 'chat',

  // Setters
  setUser: (user) => set({ user, isAuthenticated: !!user }),
  setToken: (token) => {
    if (token) {
      localStorage.setItem('plm_token', token)
    } else {
      localStorage.removeItem('plm_token')
    }
    set({ token })
  },
  setLoading: (isLoading) => set({ isLoading }),
  setOrganizations: (organizations) => set({ organizations }),
  setSelectedOrg: (selectedOrg) => set({ selectedOrg, selectedModel: null, modelPhase: null, petStatus: null, models: [], activeTab: 'chat', conversations: [], selectedConversation: null, messages: [], assistants: [] }),
  setModels: (models) => set({ models }),
  setSelectedModel: (selectedModel) => set({ selectedModel }),
  setModelPhase: (modelPhase) => set({ modelPhase }),
  setPetStatus: (petStatus) => set({ petStatus }),
  setConversations: (conversations) => set({ conversations }),
  setSelectedConversation: (selectedConversation) => set({ selectedConversation }),
  setMessages: (messages) => set({ messages }),
  setAssistants: (assistants) => set({ assistants }),
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  setActiveTab: (activeTab) => set({ activeTab }),

  // Auth
  login: async (email, password) => {
    try {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) return { error: error.message }

      const token = data.session?.access_token || null
      set({
        user: {
          id: data.user?.id || '',
          email: data.user?.email || '',
          role: 'member' as UserRole,
        },
        token,
        isAuthenticated: true,
      })
      if (token) localStorage.setItem('plm_token', token)
      return {}
    } catch (e: any) {
      return { error: e.message || 'Login failed' }
    }
  },

  signup: async (email, password) => {
    try {
      const { data, error } = await supabase.auth.signUp({ email, password })
      if (error) return { error: error.message }

      // Supabase returns a fake user with empty identities when the email
      // is already registered (instead of returning an error).
      // Detect this and show a clear message.
      if (data.user && data.user.identities && data.user.identities.length === 0) {
        return { error: 'An account with this email already exists. Please sign in instead.' }
      }

      // If email confirmation is enabled, Supabase returns user but no session.
      // The user must verify their email before they can sign in.
      if (data.user && !data.session) {
        return { error: 'Please check your email to confirm your account before signing in.' }
      }

      const token = data.session?.access_token || null
      set({
        user: {
          id: data.user?.id || '',
          email: data.user?.email || '',
          role: 'member' as UserRole,
        },
        token,
        isAuthenticated: !!token,
      })
      if (token) localStorage.setItem('plm_token', token)
      return {}
    } catch (e: any) {
      return { error: e.message || 'Signup failed' }
    }
  },

  logout: async () => {
    await supabase.auth.signOut()
    localStorage.removeItem('plm_token')
    set({
      user: null,
      token: null,
      isAuthenticated: false,
      organizations: [],
      selectedOrg: null,
      models: [],
      selectedModel: null,
      modelPhase: null,
      petStatus: null,
      conversations: [],
      selectedConversation: null,
      messages: [],
      assistants: [],
      activeTab: 'chat',
    })
  },

  initAuth: async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (session) {
        set({
          user: {
            id: session.user.id,
            email: session.user.email || '',
            role: 'member' as UserRole,
          },
          token: session.access_token,
          isAuthenticated: true,
          isLoading: false,
        })
        localStorage.setItem('plm_token', session.access_token)
      } else {
        set({ isLoading: false })
      }
    } catch {
      set({ isLoading: false })
    }

    // Listen for auth changes (register only once)
    if (!authListenerRegistered) {
      authListenerRegistered = true
      supabase.auth.onAuthStateChange((_event, session) => {
        if (session) {
          set({
            user: {
              id: session.user.id,
              email: session.user.email || '',
              role: 'member' as UserRole,
            },
            token: session.access_token,
            isAuthenticated: true,
          })
          localStorage.setItem('plm_token', session.access_token)
        } else {
          set({
            user: null,
            token: null,
            isAuthenticated: false,
          })
          localStorage.removeItem('plm_token')
        }
      })
    }
  },
}))

export type { Organization, Model, QueryResponse, Conversation, Message, Assistant, ModelPhase, PetStatus }
