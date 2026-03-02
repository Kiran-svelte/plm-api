'use client'

import { useState, Suspense } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useStore } from '@/lib/store'

function SignupForm() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const { signup } = useStore()
  const router = useRouter()
  const searchParams = useSearchParams()
  const inviteToken = searchParams.get('invite')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setLoading(true)
    const result = await signup(email, password)
    if (result.error) {
      setError(result.error)
      setLoading(false)
    } else {
      setLoading(false)
      setSuccess(true)
      // If coming from an invite link, redirect to accept the invite instead of onboarding
      if (inviteToken) {
        setTimeout(() => router.push(`/invite/${inviteToken}`), 1500)
      } else {
        setTimeout(() => router.push('/onboarding'), 1500)
      }
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <Link href="/" className="text-3xl font-bold text-indigo-600">PLM Enterprise</Link>
          <p className="mt-2 text-gray-600">Create your account</p>
        </div>

        <div className="bg-white rounded-xl shadow-lg p-8">
          {inviteToken && !success && (
            <div className="mb-4 bg-indigo-50 border border-indigo-200 text-indigo-700 px-4 py-3 rounded-lg text-sm">
              Create an account to join your team.
            </div>
          )}

          {success ? (
            <div className="text-center py-6">
              <div className="text-4xl mb-4">&#10003;</div>
              <h3 className="text-xl font-semibold text-gray-900 mb-2">Account Created</h3>
              <p className="text-gray-600">
                {inviteToken ? 'Redirecting to accept invitation...' : 'Redirecting to setup...'}
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              {error && (
                <div className={`px-4 py-3 rounded-lg text-sm ${
                  error.includes('check your email') || error.includes('confirm')
                    ? 'bg-blue-50 border border-blue-200 text-blue-700'
                    : 'bg-red-50 border border-red-200 text-red-700'
                }`}>
                  {error}
                </div>
              )}

              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                  Work Email
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
                  placeholder="you@company.com"
                />
              </div>

              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
                  placeholder="Min 6 characters"
                />
              </div>

              <div>
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 mb-1">
                  Confirm Password
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  minLength={6}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
                  placeholder="Repeat password"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 disabled:bg-gray-400 transition"
              >
                {loading ? 'Creating account...' : 'Create Account'}
              </button>
            </form>
          )}

          <div className="mt-6 text-center text-sm text-gray-600">
            Already have an account?{' '}
            <Link
              href={inviteToken ? `/login?invite=${inviteToken}` : '/login'}
              className="text-indigo-600 font-semibold hover:text-indigo-700"
            >
              Sign in
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function SignupPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><p>Loading...</p></div>}>
      <SignupForm />
    </Suspense>
  )
}
