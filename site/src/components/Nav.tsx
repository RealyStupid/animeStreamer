"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ApiError,
  clearAccessToken,
  getAccessToken,
  getCurrentUser,
  type UserProfile,
} from "@/tools/api/client";

const navLinks = [
  { href: "/", label: "Home" },
  { href: "/browse", label: "Browse" },
];

export default function Nav() {
  const router = useRouter();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [authError, setAuthError] = useState("");
  const [checkedAuth, setCheckedAuth] = useState(false);

  useEffect(() => {
    let isCurrent = true;
    async function loadUser() {
      const token = getAccessToken();
      if (!token) {
        if (isCurrent) {
          setUser(null);
          setCheckedAuth(true);
        }
        return;
      }
      try {
        const profile = await getCurrentUser(token);
        if (isCurrent) {
          setUser(profile);
          setAuthError("");
        }
      } catch (error) {
        if (isCurrent) {
          setUser(null);
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
      } finally {
        if (isCurrent) {
          setCheckedAuth(true);
        }
      }
    }
    void loadUser();

    function syncAuth() {
      void loadUser();
    }
    window.addEventListener("storage", syncAuth);
    window.addEventListener("animewatcher:auth-change", syncAuth);
    return () => {
      isCurrent = false;
      window.removeEventListener("storage", syncAuth);
      window.removeEventListener("animewatcher:auth-change", syncAuth);
    };
  }, []);

  function handleSignOut() {
    clearAccessToken();
    setUser(null);
    router.push("/");
  }

  return (
    <nav className="nav">
      <Link href="/" className="nav-logo">
        <Image src="/globe.svg" alt="" width={26} height={26} loading="eager" />
        <span className="text-lg font-bold text-red-500 sm:text-xl">
          AnimeWatcher
        </span>
      </Link>

      <ul className="nav-links">
        {navLinks.map((link) => (
          <li key={link.href}>
            <Link
              href={link.href}
              className="text-sm font-medium text-neutral-300 transition-colors hover:text-white sm:text-base"
            >
              {link.label}
            </Link>
          </li>
        ))}
      </ul>

      <div className="flex items-center gap-2 sm:gap-3">
        {authError ? (
          <output
            className="max-w-32 text-right text-xs text-red-300"
            title={authError}
          >
            Account status unavailable
          </output>
        ) : checkedAuth && user ? (
          <>
            <Link
              href="/profile"
              className="rounded-md px-3 py-2 text-sm font-medium text-neutral-200 transition hover:bg-neutral-800 hover:text-white"
            >
              Profile
            </Link>
            <button
              className="rounded-md border border-neutral-700 px-3 py-2 text-sm font-medium text-neutral-300 transition hover:border-neutral-500 hover:text-white"
              type="button"
              onClick={handleSignOut}
            >
              Sign out
            </button>
          </>
        ) : checkedAuth ? (
          <>
            <Link
              href="/login"
              className="px-2 py-2 text-sm font-medium text-neutral-300 transition hover:text-white sm:px-3"
            >
              Login
            </Link>
            <Link
              href="/register"
              className="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-red-700 sm:px-4"
            >
              Sign up
            </Link>
          </>
        ) : (
          <output className="sr-only">Checking sign-in status</output>
        )}
      </div>
    </nav>
  );
}
