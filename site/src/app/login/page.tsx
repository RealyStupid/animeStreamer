'use client'

import { useState } from 'react'
import Link from 'next/link'

export default function LoginPage() {
  const [formData, setFormData] = useState({ usernameOrEmail: '', password: '' })
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    // TODO: Connect to FastAPI backend later
    // const res = await fetch('http://localhost:8000/api/v1/auth/login', {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify(formData)
    // })

    console.log('Logging in with:', formData)
    setTimeout(() => setLoading(false), 1000)
  }

  return (
    <main className="min-h-screen flex items-center justify-center pt-20 pb-12 px-4 bg-[#191919]">
      {/* Background Red Glow */}
      <div 
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-125 h-75 bg-red-600/10 blur-[120px] pointer-events-none rounded-full" 
        aria-hidden="true" 
      />

      <div className="relative w-full max-w-md bg-neutral-900/80 border border-neutral-800 backdrop-blur-md rounded-2xl p-8 shadow-2xl">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-extrabold text-white tracking-tight">
            Welcome Back to <span className="text-red-600">PiraTube</span>
          </h1>
          <p className="text-sm text-neutral-400 mt-2">
            Sign in to access your library and history
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <div>
            <label className="block text-xs font-semibold text-neutral-300 uppercase tracking-wider mb-2">
              Username or Email
            </label>
            <input
              type="text"
              required
              placeholder="EpicUsernameHere"
              value={formData.usernameOrEmail}
              onChange={(e) => setFormData({ ...formData, usernameOrEmail: e.target.value })}
              className="w-full px-4 py-3 bg-neutral-800/80 border border-neutral-700/80 rounded-xl text-white placeholder-neutral-500 focus:outline-none focus:border-red-600 transition-colors"
            />
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <label className="block text-xs font-semibold text-neutral-300 uppercase tracking-wider">
                Password
              </label>
              <Link href="#" className="text-xs text-red-500 hover:text-red-400 transition-colors">
                Forgot?
              </Link>
            </div>
            <input
              type="password"
              required
              placeholder="••••••••"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              className="w-full px-4 py-3 bg-neutral-800/80 border border-neutral-700/80 rounded-xl text-white placeholder-neutral-500 focus:outline-none focus:border-red-600 transition-colors"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-3.5 bg-red-600 hover:bg-red-700 active:scale-[0.98] transition-all font-semibold text-white rounded-xl shadow-lg shadow-red-600/20 disabled:opacity-50"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <p className="text-center text-sm text-neutral-400 mt-6">
          Don't have an account?{' '}
          <Link href="/register" className="text-red-500 font-semibold hover:text-red-400 transition-colors">
            Sign Up
          </Link>
        </p>
      </div>
    </main>
  )
}