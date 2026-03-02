'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useStore } from '@/lib/store'
import { getInvitationByToken, acceptInvitation } from '@/lib/api'

interface InviteDetails {
  id: string
  email: string
  role: string
  organization_name: string
  expires_at: string
}

export default function InvitePage() {
  const params = useParams()
  const router = useRouter()
  const token = params.token as string
  const { isAuthenticated, isLoading, initAuth } = useStore()

  const [invite, setInvite] = useState<InviteDetails | null>(null)
  const [loading, setLoading] = useState(true)
  const [accepting, setAccepting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    initAuth()
  }, [initAuth])

  // Fetch invite details
  useEffect(() => {
    if (!token) return
    ;(async () => {
      try {
        const res = await getInvitationByToken(token)
        setInvite(res.data)
      } catch (err: any) {
        setError(err?.response?.data?.detail || 'Invalid or expired invitation')
      } finally {
        setLoading(false)
      }
    })()
  }, [token])

  const handleAccept = async () => {
    if (!isAuthenticated) {
      // Redirect to login with invite token
      router.push(`/login?invite=${token}`)
      return
    }

    setAccepting(true)
    setError(null)
    try {
      await acceptInvitation(token)
      setSuccess(true)
      setTimeout(() => router.push('/dashboard'), 2000)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to accept invitation')
    } finally {
      setAccepting(false)
    }
  }

  if (isLoading || loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-600">Loading invitation...</p>
        </div>
      </div>
    )
  }

  if (error && !invite) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 max-w-md mx-auto text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-red-100 flex items-center justify-center">
            <svg className="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-gray-800 mb-2">Invalid Invitation</h1>
          <p className="text-sm text-gray-600 mb-6">{error}</p>
          <a href="/login" className="text-indigo-600 text-sm font-medium hover:text-indigo-700">
            Go to Login
          </a>
        </div>
      </div>
    )
  }

  if (success) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 max-w-md mx-auto text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-green-100 flex items-center justify-center">
            <svg className="w-6 h-6 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-gray-800 mb-2">Welcome!</h1>
          <p className="text-sm text-gray-600">You have joined {invite?.organization_name}. Redirecting to dashboard...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 max-w-md mx-auto">
        <div className="text-center mb-6">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-indigo-100 flex items-center justify-center">
            <svg className="w-6 h-6 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
              />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-gray-800 mb-1">You&apos;re Invited!</h1>
          <p className="text-sm text-gray-600">
            You have been invited to join <span className="font-semibold">{invite?.organization_name}</span>
          </p>
        </div>

        <div className="bg-gray-50 rounded-lg p-4 mb-6 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">Email:</span>
            <span className="text-gray-800 font-medium">{invite?.email}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-500">Role:</span>
            <span className="text-gray-800 font-medium capitalize">{invite?.role}</span>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-2 mb-4 text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          onClick={handleAccept}
          disabled={accepting}
          className="w-full px-6 py-3 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition"
        >
          {accepting ? 'Accepting...' : isAuthenticated ? 'Accept Invitation' : 'Sign In to Accept'}
        </button>

        {!isAuthenticated && (
          <p className="mt-4 text-center text-xs text-gray-500">
            Don&apos;t have an account?{' '}
            <a href={`/signup?invite=${token}`} className="text-indigo-600 hover:text-indigo-700 font-medium">
              Sign up
            </a>
          </p>
        )}
      </div>
    </div>
  )
}
