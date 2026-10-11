"use client";

import Link from "next/link";
import { type SubmitEvent, useState } from "react";
import { registerUser } from "@/tools/api/client";
import type { RegisterRequest } from "@/tools/api/schema";

export default function RegisterPage() {
  const [handle, setHandle] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRegistered, setIsRegistered] = useState(false);

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);

    try {
      const registration: RegisterRequest = { handle, email, password };
      await registerUser(registration);
      setIsRegistered(true);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Could not create your account. Please try again.",
      );
      setIsSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#191919] px-5 py-20">
      <section className="w-full max-w-md rounded-2xl border border-neutral-800 bg-neutral-900 p-8 shadow-2xl">
        <Link
          href="/"
          className="text-sm font-semibold uppercase tracking-[0.2em] text-red-500"
        >
          AnimeWatcher
        </Link>
        {isRegistered ? (
          <>
            <h1 className="mt-5 text-3xl font-bold text-white">
              Account created
            </h1>
            <p className="mt-2 text-sm text-neutral-400">
              Your account is ready. Sign in to view your profile.
            </p>
            <Link
              href="/login"
              className="mt-8 block w-full rounded-lg bg-red-600 px-4 py-3 text-center font-semibold text-white transition hover:bg-red-700"
            >
              Continue to sign in
            </Link>
          </>
        ) : (
          <>
            <h1 className="mt-5 text-3xl font-bold text-white">
              Create your account
            </h1>
            <p className="mt-2 text-sm text-neutral-400">
              Join AnimeWatcher and make your profile.
            </p>

            <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
              <div>
                <label
                  htmlFor="handle"
                  className="mb-2 block text-sm font-medium text-neutral-200"
                >
                  Handle
                </label>
                <input
                  id="handle"
                  name="handle"
                  type="text"
                  autoComplete="username"
                  minLength={3}
                  maxLength={30}
                  pattern="[a-zA-Z0-9_-]+"
                  title="Use 3-30 letters, numbers, underscores, or hyphens."
                  required
                  value={handle}
                  onChange={(event) => setHandle(event.target.value)}
                  className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-4 py-3 text-white outline-none transition focus:border-red-500 focus:ring-2 focus:ring-red-500/20"
                  placeholder="your_handle"
                />
              </div>

              <div>
                <label
                  htmlFor="email"
                  className="mb-2 block text-sm font-medium text-neutral-200"
                >
                  Email
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-4 py-3 text-white outline-none transition focus:border-red-500 focus:ring-2 focus:ring-red-500/20"
                  placeholder="you@example.com"
                />
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="mb-2 block text-sm font-medium text-neutral-200"
                >
                  Password
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-4 py-3 text-white outline-none transition focus:border-red-500 focus:ring-2 focus:ring-red-500/20"
                />
              </div>

              <div>
                <label
                  htmlFor="confirm-password"
                  className="mb-2 block text-sm font-medium text-neutral-200"
                >
                  Confirm password
                </label>
                <input
                  id="confirm-password"
                  name="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-4 py-3 text-white outline-none transition focus:border-red-500 focus:ring-2 focus:ring-red-500/20"
                />
              </div>

              {error && (
                <p
                  role="alert"
                  className="rounded-lg bg-red-950/60 px-4 py-3 text-sm text-red-300"
                >
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full rounded-lg bg-red-600 px-4 py-3 font-semibold text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSubmitting ? "Creating account..." : "Create account"}
              </button>
            </form>

            <p className="mt-6 text-center text-sm text-neutral-400">
              Already have an account?{" "}
              <Link
                href="/login"
                className="font-medium text-red-400 hover:text-red-300"
              >
                Sign in
              </Link>
            </p>
          </>
        )}
      </section>
    </main>
  );
}
