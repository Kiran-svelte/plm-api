import axios from 'axios'
import { supabase } from './supabase'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://plm-api-yq26.onrender.com'

const api = axios.create({
  baseURL: API_URL,
  timeout: 30000,
})

// Attach auth token to every request
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('plm_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
  }
  return config
})

// Track whether a token refresh is already in progress to avoid concurrent refreshes
let isRefreshing = false
let refreshPromise: Promise<string | null> | null = null

// Handle 401 responses — attempt token refresh before logging out
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (
      error.response?.status === 401 &&
      typeof window !== 'undefined' &&
      !originalRequest._retry
    ) {
      originalRequest._retry = true

      try {
        // Coalesce concurrent refresh attempts into a single call
        if (!isRefreshing) {
          isRefreshing = true
          refreshPromise = supabase.auth
            .refreshSession()
            .then(({ data }) => {
              const newToken = data.session?.access_token || null
              if (newToken) {
                localStorage.setItem('plm_token', newToken)
              }
              return newToken
            })
            .finally(() => {
              isRefreshing = false
            })
        }

        const newToken = await refreshPromise
        if (newToken) {
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          return api(originalRequest)
        }
      } catch {
        // Refresh failed — fall through to logout
      }

      // No valid token after refresh — log out
      localStorage.removeItem('plm_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// Organizations
export const getOrganizations = () => api.get('/organizations')
export const getOrganization = (orgId: string) => api.get(`/organizations/${orgId}`)
export const createOrganization = (data: {
  name: string; slug: string; niche: string; tier?: string; topics?: string[]; system_prompt?: string
}) => api.post('/organizations', data)
export const updateOrganization = (orgId: string, data: any) => api.patch(`/organizations/${orgId}`, data)

// Models
export const getModels = (orgId: string) => api.get(`/organizations/${orgId}/models`)
export const getModel = (modelId: string) => api.get(`/models/${modelId}`)
export const createModel = (orgId: string, data: { name: string; base_model?: string }) =>
  api.post(`/organizations/${orgId}/models`, data)

// Query
export const queryModel = (orgId: string, modelId: string, data: {
  query: string; use_rag?: boolean; use_fact_check?: boolean; temperature?: number
}) => api.post(`/organizations/${orgId}/models/${modelId}/query`, data)

// Feedback
export const submitFeedback = (queryId: string, data: { feedback: string; comment?: string }) =>
  api.post(`/queries/${queryId}/feedback`, data)

// Training
export const generateData = (orgId: string, modelId: string, data: { num_examples: number; topics?: string[] }) =>
  api.post(`/organizations/${orgId}/models/${modelId}/generate-data`, data)
export const startTraining = (orgId: string, modelId: string, config?: {
  training_config?: any; backend?: string; base_model?: string
}) => api.post(`/organizations/${orgId}/models/${modelId}/train`, config || {})
export const getTrainingJob = (jobId: string) => api.get(`/training-jobs/${jobId}`)
export const getTrainingBackends = () => api.get('/training-backends')

// Analytics
export const getAnalytics = (orgId: string) => api.get(`/organizations/${orgId}/analytics`)
export const getQueryHistory = (orgId: string) => api.get(`/organizations/${orgId}/queries`)

// Knowledge Base
export const getKnowledge = (orgId: string, category?: string) => {
  const params = category ? `?category=${encodeURIComponent(category)}` : ''
  return api.get(`/organizations/${orgId}/knowledge${params}`)
}
export const addKnowledge = (orgId: string, data: { content: string; source?: string }) =>
  api.post(`/organizations/${orgId}/knowledge`, data)
export const deleteKnowledge = (orgId: string, kbId: string) =>
  api.delete(`/organizations/${orgId}/knowledge/${kbId}`)
export const uploadKnowledgeFile = (orgId: string, file: File, category: string = 'general') => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('category', category)
  return api.post(`/organizations/${orgId}/knowledge/upload`, formData, {
    timeout: 60000,
  })
}
export const getKnowledgeCategories = (orgId: string) =>
  api.get(`/organizations/${orgId}/knowledge/categories`)

// API Keys
export const getApiKeys = (orgId: string) => api.get(`/organizations/${orgId}/api-keys`)
export const createApiKey = (orgId: string, name: string) =>
  api.post(`/organizations/${orgId}/api-keys`, { name })
export const revokeApiKey = (orgId: string, keyId: string) =>
  api.delete(`/organizations/${orgId}/api-keys/${keyId}`)

// Invitations
export const getInvitations = (orgId: string) =>
  api.get(`/organizations/${orgId}/invitations`)
export const createInvitation = (orgId: string, data: { email: string; role?: string }) =>
  api.post(`/organizations/${orgId}/invitations`, data)
export const revokeInvitation = (orgId: string, inviteId: string) =>
  api.delete(`/organizations/${orgId}/invitations/${inviteId}`)
export const getInvitationByToken = (token: string) =>
  api.get(`/invitations/${token}`)
export const acceptInvitation = (token: string) =>
  api.post('/invitations/accept', { token })

// Users
export const getOrgUsers = (orgId: string) => api.get(`/organizations/${orgId}/users`)
export const updateUserRole = (orgId: string, userId: string, role: string) =>
  api.patch(`/organizations/${orgId}/users/${userId}/role`, { role })

// Audit Logs
export const getAuditLogs = (orgId: string) => api.get(`/organizations/${orgId}/audit-logs`)

// Learning Stats
export const getLearningStats = (orgId: string, modelId: string) =>
  api.get(`/organizations/${orgId}/learning-stats/${modelId}`)

// Health
export const getHealth = () => api.get('/health')

// User profile
export const getCurrentUser = () => api.get('/me')
export const getOnboardingStatus = () => api.get('/me/onboarding-status')

// Conversations
export const getConversations = (orgId: string) =>
  api.get(`/organizations/${orgId}/conversations`)
export const getConversation = (orgId: string, conversationId: string) =>
  api.get(`/organizations/${orgId}/conversations/${conversationId}`)
export const createConversation = (orgId: string, data: {
  title?: string; model_id?: string; assistant_id?: string
}) => api.post(`/organizations/${orgId}/conversations`, data)
export const updateConversation = (orgId: string, conversationId: string, data: { title?: string }) =>
  api.patch(`/organizations/${orgId}/conversations/${conversationId}`, data)
export const deleteConversation = (orgId: string, conversationId: string) =>
  api.delete(`/organizations/${orgId}/conversations/${conversationId}`)
export const sendMessage = (orgId: string, conversationId: string, data: {
  content: string; use_rag?: boolean; use_fact_check?: boolean; temperature?: number
}) => api.post(`/organizations/${orgId}/conversations/${conversationId}/messages`, data)

// Streaming message send (SSE)
export const sendMessageStream = async (
  orgId: string,
  conversationId: string,
  data: { content: string; use_rag?: boolean; use_fact_check?: boolean; temperature?: number; modality?: string },
  onToken: (token: string) => void,
  onDone: (metadata: any) => void,
  onError: (error: string) => void,
) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('plm_token') : null
  const response = await fetch(
    `${API_URL}/organizations/${orgId}/conversations/${conversationId}/messages/stream`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
    }
  )

  if (!response.ok) {
    const errText = await response.text()
    let detail = 'Stream request failed'
    try { detail = JSON.parse(errText).detail || detail } catch {}
    onError(detail)
    return
  }

  const reader = response.body?.getReader()
  if (!reader) { onError('No response body'); return }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6).trim()
      if (!payload) continue
      try {
        const event = JSON.parse(payload)
        if (event.type === 'token') {
          onToken(event.content)
        } else if (event.type === 'done') {
          onDone(event.content)
        } else if (event.type === 'error') {
          onError(event.content)
        }
      } catch {}
    }
  }
}

// Assistants
export const getAssistants = (orgId: string) =>
  api.get(`/organizations/${orgId}/assistants`)
export const getAssistant = (orgId: string, assistantId: string) =>
  api.get(`/organizations/${orgId}/assistants/${assistantId}`)
export const createAssistant = (orgId: string, data: {
  name: string; system_prompt: string; assistant_type?: string; description?: string;
  icon?: string; temperature?: number; use_rag?: boolean; knowledge_categories?: string[]
}) => api.post(`/organizations/${orgId}/assistants`, data)
export const updateAssistant = (orgId: string, assistantId: string, data: {
  name?: string; system_prompt?: string; description?: string; icon?: string;
  temperature?: number; use_rag?: boolean; knowledge_categories?: string[]
}) => api.patch(`/organizations/${orgId}/assistants/${assistantId}`, data)
export const deleteAssistant = (orgId: string, assistantId: string) =>
  api.delete(`/organizations/${orgId}/assistants/${assistantId}`)

// Model Phase & Training Pipeline
export const getModelPhase = (orgId: string, modelId: string) =>
  api.get(`/organizations/${orgId}/models/${modelId}/phase`)
export const configureGPU = (orgId: string, modelId: string, data: {
  backend: string; api_key?: string; hf_token?: string; base_model?: string
}) => api.post(`/organizations/${orgId}/models/${modelId}/gpu-config`, data)
export const getGenerationStats = (orgId: string, modelId: string) =>
  api.get(`/organizations/${orgId}/models/${modelId}/generation-stats`)
export const togglePrivacyMode = (orgId: string, modelId: string, enabled: boolean) =>
  api.post(`/organizations/${orgId}/models/${modelId}/privacy`, { enabled })
export const toggleAutoLearning = (orgId: string, modelId: string, enabled: boolean) =>
  api.post(`/organizations/${orgId}/models/${modelId}/auto-learning`, { enabled })

// Model Accuracy - REAL dynamic score (not hardcoded)
export const getModelAccuracy = (orgId: string, modelId: string, refresh: boolean = false) =>
  api.get(`/organizations/${orgId}/models/${modelId}/accuracy?refresh=${refresh}`)

// Pet Status - v2.0 AI Pet personality and evolution
export const getPetStatus = (orgId: string, modelId: string) =>
  api.get(`/organizations/${orgId}/models/${modelId}/pet-status`)

// Multi-Modal Query - v2.0 text/code/image/voice routing
export const multiModalQuery = (
  orgId: string,
  modelId: string,
  data: {
    query: string
    modality?: 'text' | 'code' | 'image' | 'voice'
    attachments?: Array<{ type: string; url: string }>
    temperature?: number
    use_rag?: boolean
  }
) => api.post(`/organizations/${orgId}/models/${modelId}/multi-modal`, data)

// Privacy toggle - v2.0 explicit per-model privacy control
export const getPrivacyStatus = (orgId: string, modelId: string) =>
  api.get(`/organizations/${orgId}/models/${modelId}/privacy`)

// Billing
export const createCheckout = (tier: string) => api.post(`/billing/checkout?tier=${tier}`)
export const getBillingUsage = () => api.get('/billing/usage')

// Notifications
export const getNotifications = (unreadOnly: boolean = false) =>
  api.get(`/me/notifications?unread_only=${unreadOnly}`)
export const markNotificationRead = (notificationId: string) =>
  api.post(`/me/notifications/${notificationId}/read`)
export const markAllNotificationsRead = () =>
  api.post('/me/notifications/read-all')

// Webhooks
export const getWebhooks = (orgId: string) =>
  api.get(`/organizations/${orgId}/webhooks`)
export const createWebhook = (orgId: string, data: { url: string; events: string[] }) =>
  api.post(`/organizations/${orgId}/webhooks`, data)
export const deleteWebhook = (orgId: string, webhookId: string) =>
  api.delete(`/organizations/${orgId}/webhooks/${webhookId}`)

export default api
