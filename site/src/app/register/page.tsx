'use client'

import { useState } from 'react'
import Link from 'next/link'

export default function RegisterPage() {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: ''
  })
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (formData.password !== formData.confirmPassword) {
      alert("Passwords don't match!")
      return
    }

    setLoading(true)

    // TODO: Connect to FastAPI backend later
    // const res = await fetch('http://localhost:8000/api/v1/auth/register', {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify(formData)
    // })

    console.log('Registering with:', formData)
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
            Create Your <span className="text-red-600">Account</span>
          </h1>
          <p className="text-sm text-neutral-400 mt-2">
            Join PiraTube and start streaming completely free
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="block text-xs font-semibold text-neutral-300 uppercase tracking-wider mb-2">
              Username
            </label>
            <input
              type="text"
              required
              placeholder="captain_jack"
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              className="w-full px-4 py-3 bg-neutral-800/80 border border-neutral-700/80 rounded-xl text-white placeholder-neutral-500 focus:outline-none focus:border-red-600 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-300 uppercase tracking-wider mb-2">
              Email Address
            </label>
            <input
              type="email"
              required
              placeholder="captain@blackpearl.com"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className="w-full px-4 py-3 bg-neutral-800/80 border border-neutral-700/80 rounded-xl text-white placeholder-neutral-500 focus:outline-none focus:border-red-600 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-300 uppercase tracking-wider mb-2">
              Password
            </label>
            <input
              type="password"
              required
              placeholder="••••••••"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              className="w-full px-4 py-3 bg-neutral-800/80 border border-neutral-700/80 rounded-xl text-white placeholder-neutral-500 focus:outline-none focus:border-red-600 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-300 uppercase tracking-wider mb-2">
              Confirm Password
            </label>
            <input
              type="password"
              required
              placeholder="••••••••"
              value={formData.confirmPassword}
              onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
              className="w-full px-4 py-3 bg-neutral-800/80 border border-neutral-700/80 rounded-xl text-white placeholder-neutral-500 focus:outline-none focus:border-red-600 transition-colors"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-3.5 bg-red-600 hover:bg-red-700 active:scale-[0.98] transition-all font-semibold text-white rounded-xl shadow-lg shadow-red-600/20 disabled:opacity-50"
          >
            {loading ? 'Creating Account...' : 'Create Account'}
          </button>
        </form>

        <p className="text-center text-sm text-neutral-400 mt-6">
          Already have an account?{' '}
          <Link href="/login" className="text-red-500 font-semibold hover:text-red-400 transition-colors">
            Sign In
          </Link>
        </p>
      </div>
    </main>
  )
}