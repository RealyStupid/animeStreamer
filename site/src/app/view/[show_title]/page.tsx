"use client";

import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Nav from "@/components/Nav";
import {
  getMediaAssetUrl,
  getShowByTitle,
  getShowSeasons,
  type SeasonResponse,
  type ShowResponse,
} from "@/tools/api/client";

export default function ShowPage() {
  const params = useParams<{ show_title: string }>();
  const title = decodeURIComponent(params.show_title);
  const [show, setShow] = useState<ShowResponse | null>(null);
  const [seasons, setSeasons] = useState<SeasonResponse[]>([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isCurrent = true;
    setIsLoading(true);
    async function loadShow() {
      const loadedShow = await getShowByTitle(title);
      const loadedSeasons = await getShowSeasons(loadedShow.id);
      return { loadedShow, loadedSeasons };
    }

    loadShow()
      .then(({ loadedShow, loadedSeasons }) => {
        if (isCurrent) {
          setShow(loadedShow);
          setSeasons(loadedSeasons);
        }
      })
      .catch((loadError: unknown) => {
        if (isCurrent) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Could not load this show.",
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
  }, [title]);

  return (
    <>
      <Nav />
      <main className="min-h-screen bg-[#191919] px-5 pb-16 pt-24 text-white">
        <div className="mx-auto max-w-5xl">
          <Link
            className="text-sm font-medium text-neutral-400 transition hover:text-white"
            href="/browse"
          >
            ← Back to browse
          </Link>

          {isLoading ? (
            <p className="py-20 text-center text-neutral-400">
              Loading show...
            </p>
          ) : error ? (
            <section className="mt-8 rounded-2xl border border-red-900 bg-red-950/40 p-6">
              <h1 className="text-2xl font-bold">Show unavailable</h1>
              <p role="alert" className="mt-2 text-red-200">
                {error}
              </p>
            </section>
          ) : show ? (
            <>
              <section className="mt-8 grid gap-8 rounded-2xl border border-neutral-800 bg-neutral-900 p-6 sm:grid-cols-[220px_1fr] sm:p-8">
                <div className="relative mx-auto aspect-2/3 w-full max-w-55 overflow-hidden rounded-xl bg-neutral-950">
                  {show.thumbnail_url ? (
                    <Image
                      alt={`${show.title} cover`}
                      className="object-cover"
                      fill
                      sizes="220px"
                      src={getMediaAssetUrl(show.thumbnail_url)}
                      unoptimized
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center p-5 text-center text-sm text-neutral-500">
                      No cover artwork
                    </div>
                  )}
                </div>
                <div className="flex flex-col justify-center">
                  <p className="text-sm font-semibold uppercase tracking-[0.16em] text-red-400">
                    {show.genre}
                  </p>
                  <h1 className="mt-3 text-3xl font-bold sm:text-4xl">
                    {show.title}
                  </h1>
                  {show.created_by && (
                    <p className="mt-2 text-sm text-neutral-500">
                      Added by {show.created_by.handle}
                    </p>
                  )}
                  <p className="mt-5 whitespace-pre-wrap leading-7 text-neutral-300">
                    {show.description}
                  </p>
                  {show.tags.length > 0 && (
                    <ul className="mt-5 flex flex-wrap gap-2">
                      {show.tags.map((tag) => (
                        <li
                          className="rounded-full border border-neutral-700 px-3 py-1 text-xs text-neutral-300"
                          key={tag.id}
                        >
                          {tag.name}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </section>

              <section className="mt-10">
                <div className="mb-5 flex items-end justify-between">
                  <div>
                    <p className="text-sm font-semibold uppercase tracking-[0.16em] text-red-400">
                      Watch
                    </p>
                    <h2 className="mt-2 text-2xl font-bold">Seasons</h2>
                  </div>
                  <span className="text-sm text-neutral-400">
                    {seasons.length}{" "}
                    {seasons.length === 1 ? "season" : "seasons"}
                  </span>
                </div>
                {seasons.length > 0 ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {seasons.map((season) => (
                      <Link
                        className="flex items-center justify-between gap-4 rounded-xl border border-neutral-800 bg-neutral-900 p-5 transition hover:border-neutral-600 hover:bg-neutral-800"
                        href={`/view/${encodeURIComponent(show.title)}/${season.season_number}/watch`}
                        key={season.id}
                      >
                        {season.thumbnail_url ? (
                          <div className="relative aspect-video w-32 shrink-0 overflow-hidden rounded-lg bg-neutral-950">
                            <Image
                              alt={`${season.name} thumbnail`}
                              className="object-cover"
                              fill
                              sizes="128px"
                              src={getMediaAssetUrl(season.thumbnail_url)}
                              unoptimized
                            />
                          </div>
                        ) : null}
                        <span>
                          <span className="block text-xs font-medium uppercase tracking-wide text-neutral-500">
                            Season {season.season_number}
                          </span>
                          <span className="mt-1 block font-semibold">
                            {season.name}
                          </span>
                          <span className="mt-2 line-clamp-2 block text-sm text-neutral-400">
                            {season.description}
                          </span>
                          {season.created_by && (
                            <span className="mt-2 block text-xs text-neutral-500">
                              Added by {season.created_by.handle}
                            </span>
                          )}
                        </span>
                        <span className="shrink-0 text-sm text-red-400">
                          Episodes →
                        </span>
                      </Link>
                    ))}
                  </div>
                ) : (
                  <p className="rounded-xl border border-dashed border-neutral-700 p-6 text-neutral-400">
                    No seasons have been added to this show yet.
                  </p>
                )}
              </section>
            </>
          ) : null}
        </div>
      </main>
    </>
  );
}
