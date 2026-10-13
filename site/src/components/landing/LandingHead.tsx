"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ApiError,
  clearAccessToken,
  getAccessToken,
  getCurrentUser,
} from "@/tools/api/client";

const highlights = [
  {
    number: "01",
    title: "Discover",
    description: "Browse the catalog and find a new favorite.",
  },
  {
    number: "02",
    title: "Organize",
    description: "Explore shows by genre and search by title.",
  },
  {
    number: "03",
    title: "Create",
    description: "Build and manage your own show library from your profile.",
  },
];

export default function LandingHead() {
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    let isCurrent = true;
    async function checkSignIn() {
      const token = getAccessToken();
      if (!token) {
        if (isCurrent) {
          setIsSignedIn(false);
          setAuthError("");
        }
        return;
      }
      try {
        await getCurrentUser(token);
        if (isCurrent) {
          setIsSignedIn(true);
          setAuthError("");
        }
      } catch (error) {
        if (isCurrent) {
          setIsSignedIn(false);
          if (error instanceof ApiError && error.status === 401) {
            clearAccessToken();
            setAuthError("");
          } else {
            setAuthError(
              error instanceof Error
                ? error.message
                : "Could not verify your sign-in status.",
            );
          }
        }
      }
    }
    void checkSignIn();
    window.addEventListener("animewatcher:auth-change", checkSignIn);
    return () => {
      isCurrent = false;
      window.removeEventListener("animewatcher:auth-change", checkSignIn);
    };
  }, []);

  return (
    <main className="relative overflow-hidden bg-[#191919] px-5 pb-20 pt-28 text-white sm:pt-36">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-48 left-1/2 size-[36rem] -translate-x-1/2 rounded-full bg-red-600/10 blur-[120px]"
      />
      <section className="relative mx-auto max-w-6xl">
        <div className="max-w-4xl">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-red-400">
            A library for stories worth watching
          </p>
          <h1 className="mt-6 text-5xl font-black leading-[1.05] tracking-tight sm:text-7xl">
            Your next
            <br />
            <span className="text-red-500">favorite show</span>
            <br />
            starts here.
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-neutral-400 sm:text-lg">
            Discover shows, browse seasons, and keep your own collection
            organized in one place.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link
              href="/browse"
              className="rounded-lg bg-red-600 px-6 py-3 font-semibold text-white shadow-lg shadow-red-950/40 transition hover:bg-red-700"
            >
              Explore the library
            </Link>
            <Link
              href={isSignedIn ? "/profile" : "/register"}
              className="rounded-lg border border-neutral-700 bg-neutral-900/60 px-6 py-3 font-semibold text-neutral-200 transition hover:border-neutral-500 hover:bg-neutral-800"
            >
              {isSignedIn ? "Open your profile" : "Create an account"}
            </Link>
          </div>
          {authError && (
            <output className="mt-4 block text-sm text-amber-300">
              Sign-in status could not be checked. {authError}
            </output>
          )}
        </div>

        <div className="mt-20 grid gap-px overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-800 sm:grid-cols-3">
          {highlights.map((highlight) => (
            <article className="bg-[#1d1d1d] p-6 sm:p-7" key={highlight.number}>
              <p className="font-mono text-sm text-red-400">
                {highlight.number}
              </p>
              <h2 className="mt-5 text-xl font-semibold">{highlight.title}</h2>
              <p className="mt-2 text-sm leading-6 text-neutral-400">
                {highlight.description}
              </p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
