import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://hksgkdhesjcbuklsrlmo.supabase.co'
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imhrc2drZGhlc2pjYnVrbHNybG1vIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzEwNTk4MDYsImV4cCI6MjA4NjYzNTgwNn0.He8_KpvR4wP4sECGyQZxyEt94oVexAa1y3HfbNl-wDA'

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

export type UserRole = 'owner' | 'admin' | 'member'

export interface AuthUser {
  id: string
  email: string
  organization_id?: string
  role: UserRole
}
