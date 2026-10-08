"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ApiError,
  clearAccessToken,
  getAccessToken,
  getCurrentUser,
  isSignedIn,
  type UserProfile,
} from "@/tools/api/client";

export default function ProfilesPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let isCurrent = true;
    if (!isSignedIn()) {
      router.replace("/login");
      return () => {
        isCurrent = false;
      };
    }

    getCurrentUser(getAccessToken())
      .then((currentProfile) => {
        if (isCurrent) {
          setProfile(currentProfile);
        }
      })
      .catch((loadError: unknown) => {
        if (!isCurrent) {
          return;
        }

        if (loadError instanceof ApiError && loadError.status === 401) {
          clearAccessToken();
          router.replace("/login");
          return;
        }

        setError(
          loadError instanceof Error
            ? loadError.message
            : "Could not load your profile. Please try again.",
        );
      });

    return () => {
      isCurrent = false;
    };
  }, [router]);

  function handleSignOut() {
    clearAccessToken();
    router.replace("/login");
  }

  return (
    <main className="min-h-screen bg-[#191919] px-5 py-12 text-white">
      <div className="mx-auto max-w-3xl">
        <header className="flex items-center justify-between">
          <Link
            href="/"
            className="text-sm font-semibold uppercase tracking-[0.2em] text-red-500"
          >
            PiraTube
          </Link>
          {profile && (
            <button
              type="button"
              onClick={handleSignOut}
              className="rounded-lg border border-neutral-700 px-4 py-2 text-sm font-medium text-neutral-200 transition hover:border-neutral-500 hover:bg-neutral-800"
            >
              Sign out
            </button>
          )}
        </header>

        {error ? (
          <section className="mt-16 rounded-2xl border border-neutral-800 bg-neutral-900 p-8">
            <h1 className="text-2xl font-bold">Profile unavailable</h1>
            <p role="alert" className="mt-3 text-sm text-red-300">
              {error}
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-6 rounded-lg bg-red-600 px-4 py-2 font-semibold transition hover:bg-red-700"
            >
              Try again
            </button>
          </section>
        ) : profile ? (
          <section className="mt-16 rounded-2xl border border-neutral-800 bg-neutral-900 p-8 sm:p-10">
            <p className="text-sm font-medium uppercase tracking-[0.16em] text-red-400">
              Your profile
            </p>
            <h1 className="mt-3 text-3xl font-bold sm:text-4xl">
              Welcome, {profile.handle}
            </h1>
            <dl className="mt-8 divide-y divide-neutral-800 rounded-xl border border-neutral-800">
              <div className="grid gap-1 px-5 py-4 sm:grid-cols-[140px_1fr] sm:gap-4">
                <dt className="text-sm text-neutral-400">Handle</dt>
                <dd className="font-medium">{profile.handle}</dd>
              </div>
              <div className="grid gap-1 px-5 py-4 sm:grid-cols-[140px_1fr] sm:gap-4">
                <dt className="text-sm text-neutral-400">Email</dt>
                <dd className="font-medium">{profile.email}</dd>
              </div>
              <div className="grid gap-1 px-5 py-4 sm:grid-cols-[140px_1fr] sm:gap-4">
                <dt className="text-sm text-neutral-400">Account ID</dt>
                <dd className="break-all font-mono text-sm text-neutral-300">
                  {profile.id}
                </dd>
              </div>
            </dl>
          </section>
        ) : (
          <output className="mt-16 block text-center text-neutral-400">
            Loading your profile...
          </output>
        )}
      </div>
    </main>
  );
}
