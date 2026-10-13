"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import Nav from "@/components/Nav";
import {
  getMediaAssetUrl,
  getShows,
  type ShowResponse,
} from "@/tools/api/client";

export default function BrowsePage() {
  const [shows, setShows] = useState<ShowResponse[]>([]);
  const [search, setSearch] = useState("");
  const [genre, setGenre] = useState("all");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isCurrent = true;
    getShows()
      .then((items) => {
        if (isCurrent) {
          setShows(items);
        }
      })
      .catch((loadError: unknown) => {
        if (isCurrent) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Could not load shows. Please try again.",
          );
        }
      })
      .finally(() => {
        if (isCurrent) {
          setIsLoading(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  const filteredShows = shows.filter((show) => {
    const query = search.trim().toLocaleLowerCase();
    const matchesSearch =
      !query ||
      show.title.toLocaleLowerCase().includes(query) ||
      show.description.toLocaleLowerCase().includes(query);
    return matchesSearch && (genre === "all" || show.genre === genre);
  });

  return (
    <>
      <Nav />
      <main className="min-h-screen bg-[#191919] px-5 pb-16 pt-24 text-white">
        <div className="mx-auto max-w-7xl">
          <header className="mb-8">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-red-400">
                Library
              </p>
              <h1 className="mt-3 text-3xl font-bold sm:text-4xl">
                Browse shows
              </h1>
              <p className="mt-3 text-neutral-400">
                Search the library or filter by genre.
              </p>
            </div>
          </header>

          <section
            aria-label="Search and filter shows"
            className="mb-8 grid gap-3 rounded-2xl border border-neutral-800 bg-neutral-900 p-4 sm:grid-cols-[minmax(0,1fr)_220px]"
          >
            <label className="text-sm font-medium text-neutral-300">
              Search shows
              <input
                className="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-4 py-3 text-white outline-none placeholder:text-neutral-600 focus:border-red-500 focus:ring-2 focus:ring-red-500/20"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by title or description"
              />
            </label>
            <label className="text-sm font-medium text-neutral-300">
              Genre
              <select
                className="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-4 py-3 text-white outline-none focus:border-red-500 focus:ring-2 focus:ring-red-500/20"
                value={genre}
                onChange={(event) => setGenre(event.target.value)}
              >
                <option value="all">All genres</option>
                <option value="anime">Anime</option>
                <option value="drama">Drama</option>
                <option value="action">Action</option>
                <option value="comedy">Comedy</option>
                <option value="sci-fi">Sci-fi</option>
              </select>
            </label>
          </section>

          {error && (
            <section className="rounded-xl border border-red-900 bg-red-950/40 p-5">
              <p role="alert" className="text-sm text-red-200">
                {error}
              </p>
            </section>
          )}

          {isLoading ? (
            <p className="py-16 text-center text-neutral-400">
              Loading shows...
            </p>
          ) : !error && filteredShows.length === 0 ? (
            <section className="rounded-2xl border border-dashed border-neutral-700 px-6 py-16 text-center">
              <h2 className="text-xl font-semibold">
                {shows.length === 0
                  ? "The library is empty"
                  : "No shows match your search"}
              </h2>
              <p className="mt-2 text-neutral-400">
                {shows.length === 0
                  ? "Public shows will appear here when they are added."
                  : "Try a different title or genre."}
              </p>
            </section>
          ) : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 sm:gap-6 lg:grid-cols-4 xl:grid-cols-5">
              {filteredShows.map((show) => (
                <Link
                  className="group overflow-hidden rounded-xl border border-neutral-800 bg-neutral-900 transition hover:-translate-y-1 hover:border-neutral-600"
                  href={`/view/${encodeURIComponent(show.title)}`}
                  key={show.id}
                >
                  <div className="relative aspect-[2/3] bg-gradient-to-br from-neutral-800 to-neutral-950">
                    {show.thumbnail_url ? (
                      <Image
                        alt={`${show.title} cover`}
                        className="object-cover transition duration-300 group-hover:scale-105"
                        fill
                        sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 20vw"
                        src={getMediaAssetUrl(show.thumbnail_url)}
                        unoptimized
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center p-5 text-center text-sm font-medium text-neutral-500">
                        No cover artwork
                      </div>
                    )}
                  </div>
                  <div className="p-4">
                    <h2 className="truncate font-semibold">{show.title}</h2>
                    <p className="mt-1 text-xs capitalize text-neutral-400">
                      {show.genre}
                    </p>
                    {show.created_by && (
                      <p className="mt-2 truncate text-xs text-neutral-500">
                        By {show.created_by.handle}
                      </p>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </main>
    </>
  );
}
