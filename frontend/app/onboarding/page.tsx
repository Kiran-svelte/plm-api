'use client'

import { useState, useCallback, useMemo, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useStore } from '@/lib/store'
import { createOrganization, addKnowledge, getCurrentUser, getOnboardingStatus } from '@/lib/api'

// ---------------------------------------------------------------------------
// Niche options & pre-populated topic templates
// (mirrors enterprise/training_pipeline.py topic_templates)
// ---------------------------------------------------------------------------

interface NicheCard {
  id: string
  label: string
  description: string
  icon: string
  apiNiche: string
}

const NICHE_CARDS: NicheCard[] = [
  { id: 'healthcare', label: 'Healthcare', description: 'Clinical medicine, pharma, diagnostics, and health IT', icon: 'H', apiNiche: 'healthcare' },
  { id: 'legal', label: 'Legal', description: 'Contract law, compliance, litigation, and IP', icon: 'L', apiNiche: 'legal' },
  { id: 'finance', label: 'Finance', description: 'Investment, risk, portfolio management, and accounting', icon: 'F', apiNiche: 'finance' },
  { id: 'crypto', label: 'Crypto', description: 'DeFi, smart contracts, tokenomics, and Web3', icon: 'C', apiNiche: 'crypto' },
  { id: 'technology', label: 'Technology', description: 'Software engineering, cloud, DevOps, and architecture', icon: 'T', apiNiche: 'technology' },
  { id: 'devtools', label: 'DevTools', description: 'SDKs, APIs, CLI tools, testing, and developer experience', icon: 'D', apiNiche: 'devtools' },
  { id: 'education', label: 'Education', description: 'Curriculum design, assessment, e-learning, and pedagogy', icon: 'E', apiNiche: 'education' },
  { id: 'marketing', label: 'Marketing', description: 'SEO, content strategy, analytics, and growth', icon: 'M', apiNiche: 'marketing' },
  { id: 'real_estate', label: 'Real Estate', description: 'Valuation, investment analysis, zoning, and transactions', icon: 'R', apiNiche: 'real_estate' },
  { id: 'custom', label: 'Custom', description: 'Define your own industry niche', icon: '+', apiNiche: '' },
]

type NicheOption = string

const NICHE_GRADIENTS: Record<string, string> = {
  healthcare: 'from-emerald-500 to-teal-600',
  legal: 'from-slate-500 to-slate-700',
  finance: 'from-blue-500 to-indigo-600',
  crypto: 'from-orange-500 to-amber-600',
  technology: 'from-violet-500 to-purple-600',
  devtools: 'from-cyan-500 to-blue-600',
  education: 'from-pink-500 to-rose-600',
  marketing: 'from-fuchsia-500 to-pink-600',
  real_estate: 'from-lime-500 to-green-600',
  custom: 'from-gray-500 to-gray-600',
}

const SUB_NICHES: Record<string, string[]> = {
  healthcare: ['Clinical Medicine', 'Pharmaceuticals', 'Medical Devices', 'Health IT', 'Medical Research', 'Telemedicine', 'Mental Health', 'Emergency Medicine'],
  legal: ['Contract Law', 'IP & Patents', 'Regulatory Compliance', 'Corporate Law', 'Employment Law', 'Data Privacy', 'Litigation', 'Real Estate Law'],
  finance: ['Investment Banking', 'Risk Management', 'Portfolio Management', 'Corporate Finance', 'Financial Modeling', 'Tax Strategy', 'Private Equity', 'Quantitative Trading'],
  crypto: ['DeFi Protocols', 'NFTs & Digital Assets', 'Trading & Markets', 'Smart Contracts', 'Tokenomics', 'DAO Governance', 'Layer 2 Solutions', 'Wallet Security'],
  technology: ['System Architecture', 'Cloud Infrastructure', 'Frontend Development', 'Backend & APIs', 'Database Optimization', 'Security Engineering', 'ML/AI Deployment', 'DevOps'],
  devtools: ['SDK Design', 'API Architecture', 'CLI Tooling', 'Testing Frameworks', 'CI/CD Pipelines', 'Documentation', 'Package Management', 'Developer Analytics'],
  education: ['Curriculum Design', 'EdTech Platforms', 'Student Assessment', 'STEM Education', 'Special Education', 'Adaptive Learning', 'Teacher Development', 'Gamification'],
  marketing: ['Content Strategy', 'SEO Optimization', 'Social Media', 'Conversion Optimization', 'Email Marketing', 'Brand Development', 'Growth Hacking', 'Analytics'],
  real_estate: ['Property Valuation', 'Commercial RE', 'Investment Analysis', 'Development', 'Property Management', 'Real Estate Finance', 'REIT Analysis', 'Sustainable Building'],
}

const TOPIC_TEMPLATES: Record<string, string[]> = {
  healthcare: [
    'Patient data privacy and HIPAA compliance',
    'Clinical diagnosis frameworks',
    'Telemedicine best practices',
    'Pharmaceutical interactions',
    'Medical imaging analysis',
  ],
  crypto: [
    'Cryptocurrency trading strategies',
    'Blockchain security best practices',
    'DeFi protocols explained',
    'NFT marketplace analysis',
    'Crypto regulations and compliance',
  ],
  legal: [
    'Contract law fundamentals',
    'Legal due diligence process',
    'Regulatory compliance strategies',
    'Intellectual property protection',
    'Litigation best practices',
  ],
  finance: [
    'Financial risk management',
    'Portfolio diversification strategies',
    'Investment analysis techniques',
    'Financial regulations',
    'Corporate finance best practices',
  ],
  education: [
    'Curriculum design and pedagogy',
    'E-learning platform best practices',
    'Student assessment strategies',
    'Adaptive learning technologies',
    'Education policy and compliance',
  ],
  devtools: [
    'Developer experience optimization',
    'CI/CD pipeline best practices',
    'API design and documentation',
    'Code quality and testing strategies',
    'Infrastructure as code patterns',
  ],
  marketing: [
    'Content marketing strategies',
    'SEO and search engine optimization',
    'Social media analytics',
    'Customer acquisition funnels',
    'Brand positioning and messaging',
  ],
  technology: [
    'System architecture design',
    'Cloud infrastructure optimization',
    'API design patterns',
    'Security best practices',
    'Performance optimization',
  ],
  real_estate: [
    'Property valuation methods',
    'Real estate market analysis',
    'Investment ROI calculation',
    'Zoning regulations',
    'Real estate transaction process',
  ],
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/[\s_]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

// ---------------------------------------------------------------------------
// Step indicator component
// ---------------------------------------------------------------------------

const STEP_LABELS = ['Company Info', 'Focus Areas', 'Topics', 'Knowledge', 'Review & Launch']

function StepIndicator({ current }: { current: number }) {
  return (
    <nav aria-label="Onboarding progress" className="mb-10">
      {/* Mobile-friendly label */}
      <p className="text-sm text-gray-500 text-center mb-4 sm:hidden">
        Step {current + 1} of {STEP_LABELS.length}
      </p>

      <ol className="flex items-center w-full">
        {STEP_LABELS.map((label, idx) => {
          const isCompleted = idx < current
          const isActive = idx === current
          const isLast = idx === STEP_LABELS.length - 1

          return (
            <li
              key={label}
              className={`flex items-center ${isLast ? '' : 'flex-1'}`}
            >
              {/* Circle + label */}
              <div className="flex flex-col items-center">
                <span
                  className={`flex items-center justify-center w-9 h-9 rounded-full text-sm font-semibold shrink-0 transition-colors ${
                    isCompleted
                      ? 'bg-indigo-600 text-white'
                      : isActive
                        ? 'border-2 border-indigo-600 text-indigo-600 bg-white'
                        : 'border-2 border-gray-300 text-gray-400 bg-white'
                  }`}
                >
                  {isCompleted ? (
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={3}
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  ) : (
                    idx + 1
                  )}
                </span>
                <span
                  className={`hidden sm:block mt-2 text-xs font-medium ${
                    isActive
                      ? 'text-indigo-600'
                      : isCompleted
                        ? 'text-gray-700'
                        : 'text-gray-400'
                  }`}
                >
                  {label}
                </span>
              </div>

              {/* Connector line */}
              {!isLast && (
                <div
                  className={`flex-1 h-0.5 mx-2 transition-colors ${
                    isCompleted ? 'bg-indigo-600' : 'bg-gray-300'
                  }`}
                />
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

// ---------------------------------------------------------------------------
// Main onboarding page
// ---------------------------------------------------------------------------

export default function OnboardingPage() {
  const router = useRouter()
  const { setOrganizations, organizations, user, isAuthenticated, isLoading, initAuth } = useStore()

  // Auth gate: redirect to login if not authenticated,
  // redirect to dashboard if already onboarded
  const [authChecked, setAuthChecked] = useState(false)

  useEffect(() => {
    const checkAuth = async () => {
      await initAuth()
      const { isAuthenticated: authed } = useStore.getState()
      if (!authed) {
        router.push('/login')
        return
      }
      // Check if user already has an org
      try {
        const res = await getOnboardingStatus()
        if (res.data.has_organization) {
          router.push('/dashboard')
          return
        }
      } catch {
        // Endpoint unavailable, let user proceed
      }
      setAuthChecked(true)
    }
    checkAuth()
  }, [initAuth, router])

  // Wizard step (0-indexed)
  const [step, setStep] = useState(0)

  // Step 1 -- Company Info
  const [companyName, setCompanyName] = useState('')
  const [slug, setSlug] = useState('')
  const [slugTouched, setSlugTouched] = useState(false)
  const [niche, setNiche] = useState<NicheOption>('')
  const [customNiche, setCustomNiche] = useState('')

  // Step 1b -- Sub-niches / Focus Areas
  const [selectedSubNiches, setSelectedSubNiches] = useState<string[]>([])

  // Step 2 -- Topics
  const [selectedTopics, setSelectedTopics] = useState<string[]>([])
  const [newTopic, setNewTopic] = useState('')

  // Step 3 -- Initial Knowledge
  const [knowledgeContent, setKnowledgeContent] = useState('')

  // Submission state
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [successOrgId, setSuccessOrgId] = useState<string | null>(null)

  // Derived -----------------------------------------------------------------

  const effectiveNiche = niche === 'custom' ? customNiche.trim() : (NICHE_CARDS.find(c => c.id === niche)?.apiNiche || niche)

  const suggestedTopics = useMemo<string[]>(() => {
    if (!niche) return []
    if (niche === 'custom') {
      const trimmed = customNiche.trim()
      if (!trimmed) return []
      return [
        `Best practices in ${trimmed}`,
        `Advanced techniques for ${trimmed}`,
        `Common challenges in ${trimmed}`,
        `Industry standards for ${trimmed}`,
        `Future trends in ${trimmed}`,
      ]
    }
    return TOPIC_TEMPLATES[niche] ?? []
  }, [niche, customNiche])

  // When the niche changes, pre-select all suggested topics ----------------

  const handleNicheChange = useCallback(
    (value: NicheOption) => {
      setNiche(value)
      setSelectedSubNiches([])
      if (value && value !== 'custom') {
        setSelectedTopics(TOPIC_TEMPLATES[value] ?? [])
      } else {
        setSelectedTopics([])
      }
    },
    [],
  )

  // When custom niche text is committed (blur / enter), populate defaults ---
  const populateCustomTopics = useCallback(() => {
    const trimmed = customNiche.trim()
    if (niche === 'custom' && trimmed && selectedTopics.length === 0) {
      setSelectedTopics([
        `Best practices in ${trimmed}`,
        `Advanced techniques for ${trimmed}`,
        `Common challenges in ${trimmed}`,
        `Industry standards for ${trimmed}`,
        `Future trends in ${trimmed}`,
      ])
    }
  }, [niche, customNiche, selectedTopics.length])

  // Slug auto-generation ---------------------------------------------------

  const handleNameChange = useCallback(
    (value: string) => {
      setCompanyName(value)
      if (!slugTouched) {
        setSlug(slugify(value))
      }
    },
    [slugTouched],
  )

  // Topic helpers -----------------------------------------------------------

  const toggleTopic = useCallback((topic: string) => {
    setSelectedTopics((prev) =>
      prev.includes(topic) ? prev.filter((t) => t !== topic) : [...prev, topic],
    )
  }, [])

  const addCustomTopic = useCallback(() => {
    const trimmed = newTopic.trim()
    if (trimmed && !selectedTopics.includes(trimmed)) {
      setSelectedTopics((prev) => [...prev, trimmed])
      setNewTopic('')
    }
  }, [newTopic, selectedTopics])

  const removeTopic = useCallback((topic: string) => {
    setSelectedTopics((prev) => prev.filter((t) => t !== topic))
  }, [])

  // Validation per step -----------------------------------------------------

  const stepValid = useMemo(() => {
    switch (step) {
      case 0:
        return (
          companyName.trim().length >= 2 &&
          slug.trim().length >= 2 &&
          effectiveNiche.length >= 2
        )
      case 1:
        return true // sub-niches are optional
      case 2:
        return selectedTopics.length >= 1
      case 3:
        return true // knowledge is optional
      case 4:
        return true
      default:
        return false
    }
  }, [step, companyName, slug, effectiveNiche, selectedTopics])

  // Navigation --------------------------------------------------------------

  const goNext = useCallback(() => {
    if (stepValid && step < 4) setStep((s) => s + 1)
  }, [step, stepValid])

  const goBack = useCallback(() => {
    if (step > 0) setStep((s) => s - 1)
  }, [step])

  // Submission --------------------------------------------------------------

  const handleSubmit = useCallback(async () => {
    setError('')
    setSubmitting(true)

    try {
      const payload = {
        name: companyName.trim(),
        slug: slug.trim(),
        niche: effectiveNiche,
        topics: [...selectedTopics, ...selectedSubNiches.map(s => `${effectiveNiche}: ${s}`)],
      }

      const res = await createOrganization(payload)

      const orgId: string =
        res.data?.organization_id ?? res.data?.organization?.id ?? res.data?.org_id ?? res.data?.id ?? ''

      if (!orgId) {
        console.warn('Organization created but could not extract org ID from response:', res.data)
      }

      // If the user pasted initial knowledge, send it
      if (knowledgeContent.trim() && orgId) {
        try {
          await addKnowledge(orgId, {
            content: knowledgeContent.trim(),
            source: 'onboarding',
          })
        } catch {
          // Non-blocking -- org was already created
          console.error('Failed to add initial knowledge, but organization was created.')
        }
      }

      // Refresh organizations in global store
      if (orgId) {
        const newOrg = {
          id: orgId,
          name: payload.name,
          slug: payload.slug,
          niche: payload.niche,
          tier: 'free',
          status: 'active',
        }
        setOrganizations([...organizations, newOrg])

        // Refresh user auth context so backend recognizes org_id on next call
        try {
          const meRes = await getCurrentUser()
          const me = meRes.data
          if (me && user) {
            useStore.getState().setUser({
              ...user,
              role: me.role || 'owner',
              organization_id: me.org_id || orgId,
            })
          }
        } catch {
          // Non-blocking — worst case dashboard boot will fix it
        }
      }

      setSuccessOrgId(orgId || 'created')
      setTimeout(() => router.push('/dashboard'), 2000)
    } catch (err: any) {
      const message =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message ||
        'Failed to create organization. Please try again.'
      setError(message)
    } finally {
      setSubmitting(false)
    }
  }, [
    companyName,
    slug,
    effectiveNiche,
    selectedTopics,
    knowledgeContent,
    organizations,
    setOrganizations,
    router,
  ])

  // -----------------------------------------------------------------------
  // Auth loading screen
  // -----------------------------------------------------------------------

  if (!authChecked) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4 animate-fade-in">
          <div className="relative">
            <div className="w-12 h-12 border-4 border-indigo-100 rounded-full" />
            <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin absolute inset-0" />
          </div>
          <p className="text-sm font-medium text-gray-600">Preparing setup...</p>
        </div>
      </div>
    )
  }

  // -----------------------------------------------------------------------
  // Success screen
  // -----------------------------------------------------------------------

  if (successOrgId) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-950 via-slate-900 to-zinc-900 flex items-center justify-center px-4">
        <div className="max-w-md w-full text-center space-y-6">
          {/* Animated rings */}
          <div className="relative mx-auto w-24 h-24 flex items-center justify-center">
            <div className="absolute inset-0 rounded-full border-2 border-indigo-500/20 animate-ping" />
            <div className="absolute inset-2 rounded-full border-2 border-indigo-400/30 animate-pulse" />
            <div className="w-14 h-14 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
              <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
          </div>

          <div>
            <h2 className="text-2xl font-bold text-white mb-2">
              Your PLM is Now Learning
            </h2>
            <p className="text-zinc-400 text-sm">
              <span className="font-semibold text-indigo-400">{companyName}</span> has been created successfully.
            </p>
          </div>

          {/* Status items */}
          <div className="space-y-3 text-left bg-white/5 backdrop-blur-sm rounded-xl p-5 border border-white/10">
            <div className="flex items-start gap-3">
              <div className="w-5 h-5 rounded-full bg-emerald-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                <svg className="w-3 h-3 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-sm text-zinc-300">Generating domain-expert training data from AI APIs</p>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-5 h-5 rounded-full bg-emerald-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                <svg className="w-3 h-3 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-sm text-zinc-300">Your team&apos;s chats and data stay completely private</p>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-5 h-5 rounded-full bg-indigo-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                <svg className="w-3 h-3 text-indigo-400 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </div>
              <p className="text-sm text-zinc-300">Your private model will auto-train once enough data is collected</p>
            </div>
          </div>

          <p className="text-xs text-zinc-500">
            Redirecting to dashboard...
          </p>
        </div>
      </div>
    )
  }

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex flex-col">
      {/* Header */}
      <header className="py-6 px-6 flex items-center justify-between">
        <span className="text-2xl font-bold text-indigo-600">PLM Enterprise</span>
        <span className="text-sm text-gray-500">New Organization Setup</span>
      </header>

      {/* Card */}
      <main className="flex-1 flex items-start justify-center px-4 pb-12">
        <div className="w-full max-w-2xl bg-white rounded-xl shadow-lg p-8 sm:p-10">
          <StepIndicator current={step} />

          {/* Global error */}
          {error && (
            <div className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          {/* ---- Step 0: Company Info ---- */}
          {step === 0 && (
            <section>
              <h2 className="text-xl font-semibold text-gray-900 mb-1">
                Company Information
              </h2>
              <p className="text-sm text-gray-500 mb-6">
                Tell us about your organization so we can tailor the experience.
              </p>

              <div className="space-y-5">
                {/* Company name */}
                <div>
                  <label
                    htmlFor="companyName"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Company Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="companyName"
                    type="text"
                    value={companyName}
                    onChange={(e) => handleNameChange(e.target.value)}
                    placeholder="Acme Corp"
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
                    autoFocus
                  />
                </div>

                {/* Slug */}
                <div>
                  <label
                    htmlFor="slug"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    URL Slug <span className="text-red-500">*</span>
                  </label>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-400 whitespace-nowrap">
                      plm.ai/
                    </span>
                    <input
                      id="slug"
                      type="text"
                      value={slug}
                      onChange={(e) => {
                        setSlugTouched(true)
                        setSlug(slugify(e.target.value))
                      }}
                      placeholder="acme-corp"
                      className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none font-mono text-sm"
                    />
                  </div>
                  <p className="mt-1 text-xs text-gray-400">
                    Auto-generated from company name. You can customize it.
                  </p>
                </div>

                {/* Niche card picker */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-3">
                    Industry Niche <span className="text-red-500">*</span>
                  </label>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                    {NICHE_CARDS.map((card) => {
                      const isSelected = niche === card.id
                      const gradient = NICHE_GRADIENTS[card.id] || 'from-gray-500 to-gray-600'
                      return (
                        <button
                          key={card.id}
                          type="button"
                          onClick={() => handleNicheChange(card.id)}
                          className={`text-left p-3 rounded-xl border-2 transition-all ${
                            isSelected
                              ? 'border-indigo-500 bg-indigo-50 ring-2 ring-indigo-200'
                              : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
                          }`}
                        >
                          <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${gradient} flex items-center justify-center text-white text-sm font-bold mb-2`}>
                            {card.icon}
                          </div>
                          <div className="text-sm font-semibold text-gray-900">{card.label}</div>
                          <div className="text-[11px] text-gray-500 leading-tight mt-0.5">{card.description}</div>
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Custom niche input */}
                {niche === 'custom' && (
                  <div>
                    <label
                      htmlFor="customNiche"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      Custom Niche <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="customNiche"
                      type="text"
                      value={customNiche}
                      onChange={(e) => setCustomNiche(e.target.value)}
                      onBlur={populateCustomTopics}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          populateCustomTopics()
                        }
                      }}
                      placeholder="e.g. Real Estate, Biotech, Logistics"
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
                    />
                  </div>
                )}
              </div>
            </section>
          )}

          {/* ---- Step 1: Focus Areas / Sub-niches ---- */}
          {step === 1 && (
            <section>
              <h2 className="text-xl font-semibold text-gray-900 mb-1">
                Focus Areas
              </h2>
              <p className="text-sm text-gray-500 mb-6">
                Select the specific areas within <span className="font-medium text-indigo-600">{effectiveNiche}</span> your team works on.
                These help generate more targeted training data.
              </p>

              {niche && niche !== 'custom' && SUB_NICHES[niche] ? (
                <div className="flex flex-wrap gap-2">
                  {SUB_NICHES[niche].map((sub) => {
                    const isSelected = selectedSubNiches.includes(sub)
                    return (
                      <button
                        key={sub}
                        type="button"
                        onClick={() => {
                          setSelectedSubNiches((prev) =>
                            prev.includes(sub) ? prev.filter((s) => s !== sub) : [...prev, sub]
                          )
                        }}
                        className={`px-4 py-2 rounded-full text-sm font-medium border transition-all ${
                          isSelected
                            ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                            : 'bg-white text-gray-700 border-gray-300 hover:border-indigo-400 hover:bg-indigo-50'
                        }`}
                      >
                        {isSelected ? '\u2713 ' : ''}{sub}
                      </button>
                    )
                  })}
                </div>
              ) : (
                <p className="text-sm text-gray-400">
                  No predefined focus areas for this niche. You can add specific topics in the next step.
                </p>
              )}

              {selectedSubNiches.length > 0 && (
                <p className="mt-4 text-xs text-gray-500">
                  {selectedSubNiches.length} focus area{selectedSubNiches.length !== 1 ? 's' : ''} selected
                </p>
              )}
            </section>
          )}

          {/* ---- Step 2: Topics ---- */}
          {step === 2 && (
            <section>
              <h2 className="text-xl font-semibold text-gray-900 mb-1">
                Select Topics
              </h2>
              <p className="text-sm text-gray-500 mb-6">
                Choose topics relevant to your niche. These guide training data
                generation. Select at least one.
              </p>

              {/* Suggested topics */}
              {suggestedTopics.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-medium text-gray-700 mb-3">
                    Suggested for{' '}
                    <span className="text-indigo-600">{effectiveNiche}</span>
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {suggestedTopics.map((topic) => {
                      const isSelected = selectedTopics.includes(topic)
                      return (
                        <button
                          key={topic}
                          type="button"
                          onClick={() => toggleTopic(topic)}
                          className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                            isSelected
                              ? 'bg-indigo-600 text-white border-indigo-600'
                              : 'bg-white text-gray-700 border-gray-300 hover:border-indigo-400'
                          }`}
                        >
                          {isSelected ? '- ' : '+ '}
                          {topic}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Selected topics list */}
              {selectedTopics.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-medium text-gray-700 mb-3">
                    Selected Topics ({selectedTopics.length})
                  </h3>
                  <ul className="space-y-2">
                    {selectedTopics.map((topic) => (
                      <li
                        key={topic}
                        className="flex items-center justify-between bg-gray-50 rounded-lg px-4 py-2 text-sm"
                      >
                        <span className="text-gray-800">{topic}</span>
                        <button
                          type="button"
                          onClick={() => removeTopic(topic)}
                          className="text-gray-400 hover:text-red-500 transition-colors ml-2 shrink-0"
                          aria-label={`Remove ${topic}`}
                        >
                          <svg
                            className="w-4 h-4"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth={2}
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M6 18L18 6M6 6l12 12"
                            />
                          </svg>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Add custom topic */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">
                  Add Custom Topic
                </h3>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newTopic}
                    onChange={(e) => setNewTopic(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addCustomTopic()
                      }
                    }}
                    placeholder="Type a topic and press Enter"
                    className="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none text-sm"
                  />
                  <button
                    type="button"
                    onClick={addCustomTopic}
                    disabled={!newTopic.trim()}
                    className="px-4 py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                  >
                    Add
                  </button>
                </div>
              </div>
            </section>
          )}

          {/* ---- Step 3: Initial Knowledge ---- */}
          {step === 3 && (
            <section>
              <h2 className="text-xl font-semibold text-gray-900 mb-1">
                Initial Knowledge
              </h2>
              <p className="text-sm text-gray-500 mb-6">
                Optionally paste or type content to seed your knowledge base. You can
                always add more later from the dashboard.
              </p>

              <div>
                <label
                  htmlFor="knowledge"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Knowledge Content{' '}
                  <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <textarea
                  id="knowledge"
                  value={knowledgeContent}
                  onChange={(e) => setKnowledgeContent(e.target.value)}
                  rows={10}
                  placeholder={`Paste documentation, FAQs, articles, or any text that represents your domain expertise.\n\nExample:\n- Company policies\n- Product documentation\n- Industry guidelines`}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none text-sm leading-relaxed resize-y"
                />
                <p className="mt-1 text-xs text-gray-400">
                  {knowledgeContent.length > 0
                    ? `${knowledgeContent.length.toLocaleString()} characters`
                    : 'You can skip this step and add knowledge later.'}
                </p>
              </div>
            </section>
          )}

          {/* ---- Step 4: Review & Launch ---- */}
          {step === 4 && (
            <section>
              <h2 className="text-xl font-semibold text-gray-900 mb-1">
                Review & Launch
              </h2>
              <p className="text-sm text-gray-500 mb-6">
                Please review your details before creating the organization.
              </p>

              <div className="space-y-5">
                {/* Company Info summary */}
                <div className="bg-gray-50 rounded-lg p-5">
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                    Company Info
                  </h3>
                  <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
                    <div>
                      <dt className="text-gray-500">Name</dt>
                      <dd className="font-medium text-gray-900">
                        {companyName || '--'}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-gray-500">Slug</dt>
                      <dd className="font-mono text-gray-900">{slug || '--'}</dd>
                    </div>
                    <div className="sm:col-span-2">
                      <dt className="text-gray-500">Niche</dt>
                      <dd className="font-medium text-gray-900">
                        {effectiveNiche || '--'}
                      </dd>
                    </div>
                  </dl>
                </div>

                {/* Topics summary */}
                <div className="bg-gray-50 rounded-lg p-5">
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                    Topics ({selectedTopics.length})
                  </h3>
                  {selectedTopics.length > 0 ? (
                    <ul className="flex flex-wrap gap-2">
                      {selectedTopics.map((t) => (
                        <li
                          key={t}
                          className="px-3 py-1 bg-indigo-100 text-indigo-700 rounded-full text-xs font-medium"
                        >
                          {t}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-gray-400">No topics selected.</p>
                  )}
                </div>

                {/* Knowledge summary */}
                <div className="bg-gray-50 rounded-lg p-5">
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                    Initial Knowledge
                  </h3>
                  {knowledgeContent.trim() ? (
                    <div className="text-sm text-gray-700">
                      <p className="mb-1">
                        {knowledgeContent.length.toLocaleString()} characters of
                        content will be added.
                      </p>
                      <p className="text-gray-400 italic line-clamp-3">
                        {knowledgeContent.slice(0, 300)}
                        {knowledgeContent.length > 300 ? '...' : ''}
                      </p>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400">
                      No initial knowledge provided. You can add it later.
                    </p>
                  )}
                </div>
              </div>
            </section>
          )}

          {/* ---- Navigation buttons ---- */}
          <div className="mt-8 flex items-center justify-between">
            <button
              type="button"
              onClick={goBack}
              disabled={step === 0}
              className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                step === 0
                  ? 'text-gray-300 cursor-not-allowed'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
              }`}
            >
              Back
            </button>

            {step < 4 ? (
              <button
                type="button"
                onClick={goNext}
                disabled={!stepValid}
                className="px-6 py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
              >
                Next
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={submitting}
                className="px-6 py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                {submitting ? (
                  <>
                    <svg
                      className="animate-spin h-4 w-4 text-white"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                      />
                    </svg>
                    Creating...
                  </>
                ) : (
                  'Create Organization'
                )}
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
