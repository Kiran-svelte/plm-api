'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useStore } from '@/lib/store'

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, initAuth } = useStore()
  const router = useRouter()

  useEffect(() => {
    initAuth()
  }, [initAuth])

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [isLoading, isAuthenticated, router])

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4 animate-fade-in">
          <div className="relative">
            <div className="w-12 h-12 border-4 border-indigo-100 rounded-full" />
            <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin absolute inset-0" />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-gray-700">Loading PLM Enterprise</p>
            <p className="text-xs text-gray-400 mt-0.5">Preparing your workspace...</p>
          </div>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400 text-sm animate-fade-in">Redirecting to login...</p>
      </div>
    )
  }

  return <>{children}</>
}
