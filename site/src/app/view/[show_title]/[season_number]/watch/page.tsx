"use client";

import Image from "next/image";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import Nav from "@/components/Nav";
import {
  type EpisodeResponse,
  getAccessToken,
  getMediaAssetUrl,
  getMyEpisodePlaybackUrl,
  getMySeasonEpisodes,
  getMyShow,
  getMyShowSeasons,
  getSeasonEpisodes,
  getShowByTitle,
  getShowSeasons,
  type SeasonResponse,
  type ShowResponse,
} from "@/tools/api/client";

function WatchContent() {
  const params = useParams<{ show_title: string; season_number: string }>();
  const searchParams = useSearchParams();
  const title = decodeURIComponent(params.show_title);
  const seasonNumber = Number(params.season_number);
  const episodeId = searchParams.get("episodeId");
  const isOwnerView = searchParams.get("owner") === "1";
  const ownerShowId = searchParams.get("showId");
  const [show, setShow] = useState<ShowResponse | null>(null);
  const [season, setSeason] = useState<SeasonResponse | null>(null);
  const [episodes, setEpisodes] = useState<EpisodeResponse[]>([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const [playbackError, setPlaybackError] = useState("");
  const selectedEpisode = episodes.find((episode) => episode.id === episodeId);

  useEffect(() => {
    let isCurrent = true;
    setIsLoading(true);
    setError("");
    async function loadSeasonEpisodes() {
      const token = isOwnerView ? getAccessToken() : null;
      if (isOwnerView && (!token || !ownerShowId)) {
        throw new Error(
          "Sign in as the show creator to watch this private season.",
        );
      }
      const loadedShow =
        isOwnerView && token && ownerShowId
          ? await getMyShow(ownerShowId, token)
          : await getShowByTitle(title);
      const loadedSeasons =
        isOwnerView && token
          ? await getMyShowSeasons(loadedShow.id, token)
          : await getShowSeasons(loadedShow.id);
      const loadedSeason = loadedSeasons.find(
        (item) => item.season_number === seasonNumber,
      );
      if (!loadedSeason) {
        throw new Error(`Season ${seasonNumber} was not found.`);
      }
      const loadedEpisodes =
        isOwnerView && token
          ? await getMySeasonEpisodes(loadedSeason.id, token)
          : await getSeasonEpisodes(loadedSeason.id);
      if (isCurrent) {
        setShow(loadedShow);
        setSeason(loadedSeason);
        setEpisodes(loadedEpisodes);
      }
    }

    loadSeasonEpisodes()
      .catch((loadError: unknown) => {
        if (isCurrent) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Could not load episodes.",
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
  }, [isOwnerView, ownerShowId, title, seasonNumber]);

  useEffect(() => {
    let isCurrent = true;
    setPlaybackUrl(null);
    setPlaybackError("");
    if (!selectedEpisode) {
      return () => {
        isCurrent = false;
      };
    }

    if (!isOwnerView) {
      setPlaybackUrl(getMediaAssetUrl(selectedEpisode.video_url));
      return () => {
        isCurrent = false;
      };
    }

    const token = getAccessToken();
    if (!token) {
      setPlaybackError("Sign in as the show creator to watch this episode.");
      return () => {
        isCurrent = false;
      };
    }

    getMyEpisodePlaybackUrl(selectedEpisode.id, token)
      .then((url) => {
        if (isCurrent) {
          setPlaybackUrl(getMediaAssetUrl(url));
        }
      })
      .catch((playbackLoadError: unknown) => {
        if (isCurrent) {
          setPlaybackError(
            playbackLoadError instanceof Error
              ? playbackLoadError.message
              : "Could not start episode playback.",
          );
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [isOwnerView, selectedEpisode]);

  return (
    <>
      <Nav />
      <main className="min-h-screen bg-[#191919] px-5 pb-16 pt-24 text-white">
        <div className="mx-auto max-w-6xl">
          <Link
            className="text-sm font-medium text-neutral-400 transition hover:text-white"
            href={`/view/${encodeURIComponent(title)}`}
          >
            ← Back to {title}
          </Link>

          {isLoading ? (
            <p className="py-20 text-center text-neutral-400">
              Loading episodes...
            </p>
          ) : error ? (
            <section className="mt-8 rounded-2xl border border-red-900 bg-red-950/40 p-6">
              <h1 className="text-2xl font-bold">Episodes unavailable</h1>
              <p role="alert" className="mt-2 text-red-200">
                {error}
              </p>
            </section>
          ) : show && season ? (
            <>
              <header className="mt-8">
                <p className="text-sm font-semibold uppercase tracking-[0.16em] text-red-400">
                  {show.title}
                </p>
                <h1 className="mt-2 text-3xl font-bold">
                  Season {season.season_number}: {season.name}
                </h1>
                {season.created_by && (
                  <p className="mt-2 text-sm text-neutral-500">
                    Added by {season.created_by.handle}
                  </p>
                )}
                <p className="mt-3 max-w-3xl text-neutral-400">
                  {season.description}
                </p>
                {season.thumbnail_url && !(isOwnerView && show.is_private) && (
                  <div className="relative mt-5 aspect-video w-full max-w-xl overflow-hidden rounded-xl border border-neutral-800 bg-neutral-950">
                    <Image
                      alt={`${season.name} thumbnail`}
                      className="object-cover"
                      fill
                      sizes="(max-width: 640px) 100vw, 576px"
                      src={getMediaAssetUrl(season.thumbnail_url)}
                      unoptimized
                    />
                  </div>
                )}
              </header>

              <div className="mt-7 grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
                <section className="min-w-0">
                  {selectedEpisode && playbackUrl ? (
                    // biome-ignore lint/a11y/useMediaCaption: Episodes do not currently include caption tracks.
                    <video
                      key={selectedEpisode.id}
                      aria-label={`${selectedEpisode.title}, episode ${selectedEpisode.episode_number}`}
                      className="aspect-video w-full rounded-2xl border border-neutral-800 bg-black"
                      controls
                      onError={() =>
                        setPlaybackError(
                          "This video could not be played. Check that it is a supported video format and try again.",
                        )
                      }
                      playsInline
                      preload="metadata"
                      src={playbackUrl}
                    >
                      Your browser does not support HTML video playback.
                    </video>
                  ) : selectedEpisode ? (
                    <div
                      className="flex aspect-video flex-col items-center justify-center rounded-2xl border border-neutral-800 bg-neutral-950 p-8 text-center"
                      role={playbackError ? "alert" : "status"}
                    >
                      <p className="text-neutral-300">
                        {playbackError || "Preparing episode playback..."}
                      </p>
                    </div>
                  ) : (
                    <div className="flex aspect-video flex-col items-center justify-center rounded-2xl border border-neutral-800 bg-neutral-950 p-8 text-center">
                      <div
                        aria-hidden="true"
                        className="mb-4 flex size-14 items-center justify-center rounded-full bg-neutral-800 text-2xl text-neutral-300"
                      >
                        ▶
                      </div>
                      <h2 className="text-xl font-semibold">
                        Choose an episode
                      </h2>
                      <p className="mt-2 text-sm text-neutral-400">
                        Select an episode to pass its ID to the player.
                      </p>
                    </div>
                  )}
                  {selectedEpisode && (
                    <div className="mt-4">
                      <p className="text-sm font-semibold uppercase tracking-[0.14em] text-red-400">
                        Episode {selectedEpisode.episode_number}
                      </p>
                      <h2 className="mt-1 text-2xl font-bold">
                        {selectedEpisode.title}
                      </h2>
                      {selectedEpisode.created_by && (
                        <p className="mt-2 text-xs text-neutral-500">
                          Uploaded by {selectedEpisode.created_by.handle}
                        </p>
                      )}
                      {playbackError && playbackUrl && (
                        <p role="alert" className="mt-3 text-sm text-red-300">
                          {playbackError}
                        </p>
                      )}
                    </div>
                  )}
                  {selectedEpisode?.description && (
                    <p className="mt-5 whitespace-pre-wrap leading-7 text-neutral-300">
                      {selectedEpisode.description}
                    </p>
                  )}
                </section>

                <aside className="rounded-2xl border border-neutral-800 bg-neutral-900 p-5">
                  <h2 className="text-lg font-semibold">Episodes</h2>
                  {episodes.length > 0 ? (
                    <ol className="mt-4 space-y-2">
                      {episodes.map((episode) => {
                        const isSelected = episode.id === episodeId;
                        return (
                          <li key={episode.id}>
                            <Link
                              aria-current={isSelected ? "true" : undefined}
                              className={`block rounded-lg border px-4 py-3 transition ${
                                isSelected
                                  ? "border-red-500/60 bg-red-950/40"
                                  : "border-neutral-800 hover:border-neutral-600 hover:bg-neutral-800"
                              }`}
                              href={`/view/${encodeURIComponent(title)}/${seasonNumber}/watch?episodeId=${encodeURIComponent(episode.id)}`}
                            >
                              <span className="block text-xs font-medium text-neutral-400">
                                Episode {episode.episode_number}
                              </span>
                              <span className="mt-1 block font-medium">
                                {episode.title}
                              </span>
                            </Link>
                          </li>
                        );
                      })}
                    </ol>
                  ) : (
                    <p className="mt-4 text-sm leading-6 text-neutral-400">
                      No episodes have been uploaded to this season yet.
                    </p>
                  )}
                </aside>
              </div>
            </>
          ) : null}
        </div>
      </main>
    </>
  );
}

export default function WatchPage() {
  return (
    <Suspense
      fallback={
        <>
          <Nav />
          <main className="min-h-screen bg-[#191919] px-5 pt-24 text-white">
            <p className="py-20 text-center text-neutral-400">
              Loading episodes...
            </p>
          </main>
        </>
      }
    >
      <WatchContent />
    </Suspense>
  );
}
