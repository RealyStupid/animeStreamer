"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Nav from "@/components/Nav";
import {
  CreateShowForm,
  ManagedShowCard,
} from "@/components/profile/MediaManager";
import {
  ApiError,
  clearAccessToken,
  getAccessToken,
  getCurrentUser,
  getMyShows,
  type ShowResponse,
  type UserProfile,
} from "@/tools/api/client";

export default function ProfilesPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [shows, setShows] = useState<ShowResponse[]>([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  const loadProfile = useCallback(async () => {
    setError("");
    setIsLoading(true);
    try {
      const token = getAccessToken();
      const currentProfile = await getCurrentUser(token);
      const currentShows = await getMyShows(token);
      setProfile(currentProfile);
      setShows(currentShows);
    } catch (loadError: unknown) {
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
    } finally {
      setIsLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  function handleSignOut() {
    clearAccessToken();
    router.replace("/login");
  }

  function addShow(show: ShowResponse) {
    setShows((current) => [show, ...current]);
  }

  function replaceShow(updatedShow: ShowResponse) {
    setShows((current) =>
      current.map((show) => (show.id === updatedShow.id ? updatedShow : show)),
    );
  }

  function removeShow(showId: string) {
    setShows((current) => current.filter((show) => show.id !== showId));
  }

  return (
    <>
      <Nav />
      <main className="min-h-screen bg-[#191919] px-5 pb-16 pt-24 text-white">
        <div className="mx-auto max-w-6xl">
          {profile && (
            <header className="mb-10 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-red-400">
                  Creator dashboard
                </p>
                <h1 className="mt-3 text-3xl font-bold sm:text-4xl">
                  Welcome, {profile.handle}
                </h1>
                <p className="mt-2 text-neutral-400">
                  Manage your shows, seasons, and episode uploads.
                </p>
              </div>
              <button
                className="w-fit rounded-lg border border-neutral-700 px-4 py-2.5 text-sm font-medium text-neutral-200 transition hover:border-neutral-500 hover:bg-neutral-800"
                type="button"
                onClick={handleSignOut}
              >
                Sign out
              </button>
            </header>
          )}

          {error ? (
            <section className="rounded-2xl border border-neutral-800 bg-neutral-900 p-8">
              <h1 className="text-2xl font-bold">Profile unavailable</h1>
              <p role="alert" className="mt-3 text-sm text-red-300">
                {error}
              </p>
              <button
                className="mt-6 rounded-lg bg-red-600 px-4 py-2 font-semibold transition hover:bg-red-700"
                type="button"
                onClick={() => void loadProfile()}
              >
                Try again
              </button>
            </section>
          ) : isLoading ? (
            <p className="py-20 text-center text-neutral-400">
              Loading your creator dashboard...
            </p>
          ) : profile ? (
            <>
              <section className="mb-8 rounded-2xl border border-neutral-800 bg-neutral-900 p-6 sm:p-8">
                <p className="text-sm font-semibold uppercase tracking-[0.16em] text-red-400">
                  Account
                </p>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <div>
                    <p className="text-xs text-neutral-500">Handle</p>
                    <p className="mt-1 font-medium">{profile.handle}</p>
                  </div>
                  <div>
                    <p className="text-xs text-neutral-500">Email</p>
                    <p className="mt-1 font-medium">{profile.email}</p>
                  </div>
                </div>
              </section>

              <CreateShowForm onCreated={addShow} />

              <section className="mt-12">
                <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-red-400">
                      Your content
                    </p>
                    <h2 className="mt-2 text-2xl font-bold">Manage shows</h2>
                  </div>
                  <p className="text-sm text-neutral-400">
                    {shows.length} {shows.length === 1 ? "show" : "shows"}
                  </p>
                </div>

                {shows.length > 0 ? (
                  <div className="space-y-5">
                    {shows.map((show) => (
                      <ManagedShowCard
                        key={show.id}
                        show={show}
                        onShowUpdated={replaceShow}
                        onShowDeleted={removeShow}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-neutral-700 px-6 py-12 text-center">
                    <h3 className="text-lg font-semibold">
                      You haven’t created a show yet
                    </h3>
                    <p className="mt-2 text-sm text-neutral-400">
                      Use the form above to add your first show.
                    </p>
                    <Link
                      className="mt-5 inline-flex text-sm font-semibold text-red-400 hover:text-red-300"
                      href="/browse"
                    >
                      Browse the public library →
                    </Link>
                  </div>
                )}
              </section>
            </>
          ) : null}
        </div>
      </main>
    </>
  );
}
