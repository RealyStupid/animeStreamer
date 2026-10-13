"use client";

import Image from "next/image";
import Link from "next/link";
import { type SubmitEvent, useEffect, useState } from "react";
import {
  createEpisode,
  createSeason,
  createShow,
  deleteMyEpisode,
  deleteMySeason,
  deleteMyShow,
  type EpisodeResponse,
  getAccessToken,
  getMediaAssetUrl,
  getMySeasonEpisodes,
  getMyShowSeasons,
  type SeasonResponse,
  type ShowResponse,
  transcodeMyEpisode,
  updateMyEpisode,
  updateMySeason,
  updateMyShow,
} from "@/tools/api/client";

const fieldClass =
  "mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2.5 text-white outline-none transition placeholder:text-neutral-600 focus:border-red-500 focus:ring-2 focus:ring-red-500/20";
const buttonClass =
  "rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60";

function messageFor(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function removeEmptyFile(form: HTMLFormElement, data: FormData, name: string) {
  const input = form.querySelector<HTMLInputElement>(`input[name="${name}"]`);
  if (!input?.files?.[0]) {
    data.delete(name);
  }
}

export function CreateShowForm({
  onCreated,
}: {
  onCreated: (show: ShowResponse) => void;
}) {
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const token = getAccessToken();
    if (!token) {
      setError("Your session has expired. Sign in again to create a show.");
      return;
    }

    const form = event.currentTarget;
    const data = new FormData(form);
    removeEmptyFile(form, data, "thumbnail");
    setIsSaving(true);
    try {
      const created = await createShow(data, token);
      form.reset();
      onCreated(created);
    } catch (submitError) {
      setError(messageFor(submitError, "Could not create this show."));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="rounded-2xl border border-neutral-800 bg-neutral-900 p-6 sm:p-8">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-red-400">
          Add to your library
        </p>
        <h2 className="mt-2 text-2xl font-bold">Create a show</h2>
        <p className="mt-2 text-sm text-neutral-400">
          Start with the basics. You can add seasons and episodes afterward.
        </p>
      </div>

      <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit}>
        <label className="text-sm font-medium text-neutral-200">
          Show title
          <input
            className={fieldClass}
            name="title"
            type="text"
            maxLength={255}
            required
            placeholder="Show title"
          />
        </label>
        <label className="text-sm font-medium text-neutral-200">
          Genre
          <select className={fieldClass} name="genre" defaultValue="anime">
            <option value="anime">Anime</option>
            <option value="drama">Drama</option>
            <option value="action">Action</option>
            <option value="comedy">Comedy</option>
            <option value="sci-fi">Sci-fi</option>
          </select>
        </label>
        <label className="text-sm font-medium text-neutral-200 sm:col-span-2">
          Description
          <textarea
            className={`${fieldClass} min-h-24 resize-y`}
            name="description"
            placeholder="What is this show about?"
          />
        </label>
        <label className="text-sm font-medium text-neutral-200">
          Cover image
          <input
            className={`${fieldClass} file:mr-2 file:rounded-md file:border-0 file:bg-neutral-800 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-neutral-200`}
            name="thumbnail"
            type="file"
            accept="image/*"
          />
        </label>
        <label className="flex items-center gap-3 self-end rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-3 text-sm text-neutral-200">
          <input
            className="size-4 accent-red-600"
            name="is_private"
            type="checkbox"
            value="true"
          />
          <span>
            Keep this show private
            <span className="mt-1 block text-xs text-neutral-500">
              Only you can see and manage it.
            </span>
          </span>
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-300 sm:col-span-2">
            {error}
          </p>
        )}
        <button className={buttonClass} type="submit" disabled={isSaving}>
          {isSaving ? "Creating..." : "Create show"}
        </button>
      </form>
    </section>
  );
}

export function ManagedShowCard({
  show,
  onShowUpdated,
  onShowDeleted,
}: {
  show: ShowResponse;
  onShowUpdated: (show: ShowResponse) => void;
  onShowDeleted: (showId: string) => void;
}) {
  const [seasons, setSeasons] = useState<SeasonResponse[]>([]);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoadingSeasons, setIsLoadingSeasons] = useState(false);
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  async function toggleSeasons() {
    if (isExpanded) {
      setIsExpanded(false);
      return;
    }
    setError("");
    const token = getAccessToken();
    if (!token) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    setIsLoadingSeasons(true);
    try {
      setSeasons(await getMyShowSeasons(show.id, token));
      setIsExpanded(true);
    } catch (loadError) {
      setError(messageFor(loadError, "Could not load seasons."));
    } finally {
      setIsLoadingSeasons(false);
    }
  }

  async function handleUpdate(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const token = getAccessToken();
    if (!token) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    const privacy = form.querySelector<HTMLInputElement>(
      'input[name="is_private"]',
    );
    data.set("is_private", privacy?.checked ? "true" : "false");
    removeEmptyFile(form, data, "thumbnail");
    setIsSaving(true);
    try {
      const updated = await updateMyShow(show.id, data, token);
      onShowUpdated(updated);
    } catch (updateError) {
      setError(messageFor(updateError, "Could not update this show."));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete() {
    if (
      !window.confirm(
        `Delete "${show.title}" and all of its seasons and episodes? This cannot be undone.`,
      )
    ) {
      return;
    }
    setError("");
    const token = getAccessToken();
    if (!token) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    setIsDeleting(true);
    try {
      await deleteMyShow(show.id, token);
      onShowDeleted(show.id);
    } catch (deleteError) {
      setError(messageFor(deleteError, "Could not delete this show."));
      setIsDeleting(false);
    }
  }

  function addSeason(season: SeasonResponse) {
    setSeasons((current) =>
      [...current, season].sort((a, b) => a.season_number - b.season_number),
    );
  }

  function replaceSeason(season: SeasonResponse) {
    setSeasons((current) =>
      current.map((item) => (item.id === season.id ? season : item)),
    );
  }

  return (
    <article className="overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-900">
      <div className="grid gap-5 p-5 sm:grid-cols-[110px_minmax(0,1fr)] sm:p-6">
        <div className="relative aspect-2/3 w-full overflow-hidden rounded-lg bg-neutral-950 sm:w-27.5">
          {show.thumbnail_url && !show.is_private ? (
            <Image
              alt={`${show.title} cover`}
              className="object-cover"
              fill
              sizes="110px"
              src={getMediaAssetUrl(show.thumbnail_url)}
              unoptimized
            />
          ) : (
            <div className="flex h-full items-center justify-center px-3 text-center text-xs text-neutral-500">
              {show.is_private ? "Private show" : "No cover"}
            </div>
          )}
        </div>
        <div className="min-w-0">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-red-400">
                {show.is_private ? "Private" : "Public"} · {show.genre}
              </p>
              <h3 className="mt-1 truncate text-xl font-bold">{show.title}</h3>
              {show.created_by && (
                <p className="mt-1 text-xs text-neutral-500">
                  Created by {show.created_by.handle}
                </p>
              )}
            </div>
            {!show.is_private && (
              <Link
                className="text-sm font-medium text-red-400 transition hover:text-red-300"
                href={`/view/${encodeURIComponent(show.title)}`}
              >
                View show →
              </Link>
            )}
          </div>

          <form className="grid gap-3 sm:grid-cols-2" onSubmit={handleUpdate}>
            <label className="text-xs font-medium text-neutral-300">
              Title
              <input
                className={fieldClass}
                name="title"
                defaultValue={show.title}
                maxLength={255}
                required
              />
            </label>
            <label className="text-xs font-medium text-neutral-300">
              Genre
              <select
                className={fieldClass}
                name="genre"
                defaultValue={show.genre}
              >
                <option value="anime">Anime</option>
                <option value="drama">Drama</option>
                <option value="action">Action</option>
                <option value="comedy">Comedy</option>
                <option value="sci-fi">Sci-fi</option>
              </select>
            </label>
            <label className="text-xs font-medium text-neutral-300 sm:col-span-2">
              Description
              <textarea
                className={`${fieldClass} min-h-20 resize-y`}
                name="description"
                defaultValue={show.description}
              />
            </label>
            <label className="text-xs font-medium text-neutral-300">
              Replace cover image
              <input
                className={`${fieldClass} file:mr-2 file:rounded-md file:border-0 file:bg-neutral-800 file:px-3 file:py-2 file:text-xs`}
                name="thumbnail"
                type="file"
                accept="image/*"
              />
            </label>
            <label className="flex items-center gap-3 self-end rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-3 text-sm text-neutral-200">
              <input
                className="size-4 accent-red-600"
                name="is_private"
                type="checkbox"
                defaultChecked={show.is_private}
              />
              Make this show private
            </label>
            {error && (
              <p role="alert" className="text-sm text-red-300 sm:col-span-2">
                {error}
              </p>
            )}
            <div className="flex flex-wrap gap-3 sm:col-span-2">
              <button
                className={buttonClass}
                type="submit"
                disabled={isSaving || isDeleting}
              >
                {isSaving ? "Saving..." : "Save show"}
              </button>
              <button
                className="rounded-lg border border-neutral-700 px-4 py-2.5 text-sm font-semibold text-neutral-200 transition hover:bg-neutral-800 disabled:opacity-60"
                type="button"
                disabled={isLoadingSeasons || isDeleting}
                onClick={toggleSeasons}
              >
                {isLoadingSeasons
                  ? "Loading..."
                  : isExpanded
                    ? "Hide seasons"
                    : "Manage seasons and episodes"}
              </button>
              <button
                className="rounded-lg border border-red-900 px-4 py-2.5 text-sm font-semibold text-red-300 transition hover:bg-red-950/50 disabled:opacity-60"
                type="button"
                disabled={isDeleting || isSaving}
                onClick={() => void handleDelete()}
              >
                {isDeleting ? "Deleting show..." : "Delete show"}
              </button>
            </div>
          </form>
        </div>
      </div>

      {isExpanded && (
        <div className="border-t border-neutral-800 bg-neutral-950/40 p-5 sm:p-6">
          <CreateSeasonForm showId={show.id} onCreated={addSeason} />
          <div className="mt-5 space-y-4">
            {seasons.length > 0 ? (
              seasons.map((season) => (
                <ManagedSeasonCard
                  key={season.id}
                  season={season}
                  showTitle={show.title}
                  onSeasonUpdated={replaceSeason}
                  onSeasonDeleted={(seasonId) =>
                    setSeasons((current) =>
                      current.filter((item) => item.id !== seasonId),
                    )
                  }
                />
              ))
            ) : (
              <p className="rounded-xl border border-dashed border-neutral-700 p-5 text-sm text-neutral-400">
                No seasons yet. Add one above; season numbering is automatic.
              </p>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

function CreateSeasonForm({
  showId,
  onCreated,
}: {
  showId: string;
  onCreated: (season: SeasonResponse) => void;
}) {
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const token = getAccessToken();
    if (!token) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    removeEmptyFile(form, data, "thumbnail");
    setIsSaving(true);
    try {
      const season = await createSeason(showId, data, token);
      form.reset();
      onCreated(season);
    } catch (createError) {
      setError(messageFor(createError, "Could not create this season."));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form
      className="grid gap-3 rounded-xl border border-neutral-800 bg-neutral-900 p-4 sm:grid-cols-2"
      onSubmit={handleSubmit}
    >
      <div className="sm:col-span-2">
        <h4 className="font-semibold">Add season</h4>
        <p className="mt-1 text-xs text-neutral-500">
          Season number is assigned automatically.
        </p>
      </div>
      <label className="text-xs font-medium text-neutral-300">
        Season name
        <input
          className={fieldClass}
          name="name"
          required
          maxLength={255}
          placeholder="e.g. The First Arc"
        />
      </label>
      <label className="text-xs font-medium text-neutral-300">
        Thumbnail
        <input
          className={`${fieldClass} file:mr-2 file:rounded-md file:border-0 file:bg-neutral-800 file:px-3 file:py-2 file:text-xs`}
          name="thumbnail"
          type="file"
          accept="image/*"
        />
      </label>
      <label className="text-xs font-medium text-neutral-300 sm:col-span-2">
        Description
        <textarea
          className={`${fieldClass} min-h-16 resize-y`}
          name="description"
          placeholder="Season description"
        />
      </label>
      {error && (
        <p role="alert" className="text-sm text-red-300 sm:col-span-2">
          {error}
        </p>
      )}
      <button className={buttonClass} type="submit" disabled={isSaving}>
        {isSaving ? "Adding..." : "Add season"}
      </button>
    </form>
  );
}

function ManagedSeasonCard({
  season,
  showTitle,
  onSeasonUpdated,
  onSeasonDeleted,
}: {
  season: SeasonResponse;
  showTitle: string;
  onSeasonUpdated: (season: SeasonResponse) => void;
  onSeasonDeleted: (seasonId: string) => void;
}) {
  const [episodes, setEpisodes] = useState<EpisodeResponse[]>([]);
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    let isCurrent = true;
    const token = getAccessToken();
    if (!token) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    getMySeasonEpisodes(season.id, token)
      .then((items) => {
        if (isCurrent) {
          setEpisodes(items);
        }
      })
      .catch((loadError: unknown) => {
        if (isCurrent) {
          setError(messageFor(loadError, "Could not load episodes."));
        }
      });
    return () => {
      isCurrent = false;
    };
  }, [season.id]);

  async function handleUpdateSeason(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const token = getAccessToken();
    if (!token) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    removeEmptyFile(form, data, "thumbnail");
    setIsSaving(true);
    try {
      onSeasonUpdated(await updateMySeason(season.id, data, token));
    } catch (updateError) {
      setError(messageFor(updateError, "Could not update this season."));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDeleteSeason() {
    if (
      !window.confirm(
        `Delete Season ${season.season_number}: ${season.name} and all of its episodes? This cannot be undone.`,
      )
    ) {
      return;
    }
    setError("");
    const token = getAccessToken();
    if (!token) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    setIsDeleting(true);
    try {
      await deleteMySeason(season.id, token);
      onSeasonDeleted(season.id);
    } catch (deleteError) {
      setError(messageFor(deleteError, "Could not delete this season."));
      setIsDeleting(false);
    }
  }

  async function handleCreateEpisode(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const token = getAccessToken();
    if (!token) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    if (!data.get("duration_secs")) {
      data.delete("duration_secs");
    }
    setIsSaving(true);
    try {
      const created = await createEpisode(season.id, data, token);
      setEpisodes((current) =>
        [...current, created].sort(
          (a, b) => a.episode_number - b.episode_number,
        ),
      );
      form.reset();
    } catch (createError) {
      setError(messageFor(createError, "Could not upload the episode."));
    } finally {
      setIsSaving(false);
    }
  }

  function replaceEpisode(episode: EpisodeResponse) {
    setEpisodes((current) =>
      current.map((item) => (item.id === episode.id ? episode : item)),
    );
  }

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-900 p-4">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h4 className="font-semibold">
            Season {season.season_number}: {season.name}
          </h4>
          <Link
            className="text-sm font-medium text-red-400 transition hover:text-red-300"
            href={`/view/${encodeURIComponent(showTitle)}/${season.season_number}/watch?owner=1&showId=${encodeURIComponent(season.show_id)}`}
          >
            Watch season →
          </Link>
        </div>
        {season.created_by && (
          <p className="text-xs text-neutral-500">
            Added by {season.created_by.handle}
          </p>
        )}
      </div>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={handleUpdateSeason}>
        <label className="text-xs font-medium text-neutral-300">
          Name
          <input
            className={fieldClass}
            name="name"
            required
            maxLength={255}
            defaultValue={season.name}
          />
        </label>
        <label className="text-xs font-medium text-neutral-300">
          Replace thumbnail
          <input
            className={`${fieldClass} file:mr-2 file:rounded-md file:border-0 file:bg-neutral-800 file:px-3 file:py-2 file:text-xs`}
            name="thumbnail"
            type="file"
            accept="image/*"
          />
        </label>
        <label className="text-xs font-medium text-neutral-300 sm:col-span-2">
          Description
          <textarea
            className={`${fieldClass} min-h-16 resize-y`}
            name="description"
            defaultValue={season.description}
          />
        </label>
        <button
          className="w-fit rounded-lg border border-neutral-700 px-4 py-2 text-sm font-semibold text-neutral-200 transition hover:bg-neutral-800 disabled:opacity-60"
          type="submit"
          disabled={isSaving || isDeleting}
        >
          Save season
        </button>
        <button
          className="w-fit rounded-lg border border-red-900 px-4 py-2 text-sm font-semibold text-red-300 transition hover:bg-red-950/50 disabled:opacity-60"
          type="button"
          disabled={isSaving || isDeleting}
          onClick={() => void handleDeleteSeason()}
        >
          {isDeleting ? "Deleting season..." : "Delete season"}
        </button>
      </form>

      <form
        className="mt-5 grid gap-3 border-t border-neutral-800 pt-5 sm:grid-cols-2"
        onSubmit={handleCreateEpisode}
      >
        <h5 className="font-medium sm:col-span-2">Upload episode</h5>
        <label className="text-xs font-medium text-neutral-300">
          Episode number
          <input
            className={fieldClass}
            name="episode_number"
            type="number"
            min="1"
            required
          />
        </label>
        <label className="text-xs font-medium text-neutral-300">
          Title
          <input className={fieldClass} name="title" required maxLength={255} />
        </label>
        <label className="text-xs font-medium text-neutral-300">
          Duration (seconds)
          <input
            className={fieldClass}
            name="duration_secs"
            type="number"
            min="1"
          />
        </label>
        <label className="text-xs font-medium text-neutral-300">
          Video file
          <input
            className={`${fieldClass} file:mr-2 file:rounded-md file:border-0 file:bg-neutral-800 file:px-3 file:py-2 file:text-xs`}
            name="video"
            type="file"
            accept="video/*"
            required
          />
          <span className="mt-1 block text-xs font-normal text-neutral-500">
            Videos are converted to browser-compatible MP4 while uploading.
          </span>
        </label>
        <label className="text-xs font-medium text-neutral-300 sm:col-span-2">
          Description
          <textarea
            className={`${fieldClass} min-h-16 resize-y`}
            name="description"
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-300 sm:col-span-2">
            {error}
          </p>
        )}
        <button
          className={`${buttonClass} sm:col-span-2`}
          type="submit"
          disabled={isSaving}
        >
          {isSaving ? "Working..." : "Upload episode"}
        </button>
      </form>

      {episodes.length > 0 && (
        <ol className="mt-5 space-y-3">
          {episodes.map((episode) => (
            <ManagedEpisodeRow
              episode={episode}
              key={episode.id}
              onUpdated={replaceEpisode}
              onDeleted={(episodeId) =>
                setEpisodes((current) =>
                  current.filter((item) => item.id !== episodeId),
                )
              }
            />
          ))}
        </ol>
      )}
    </section>
  );
}

function ManagedEpisodeRow({
  episode,
  onUpdated,
  onDeleted,
}: {
  episode: EpisodeResponse;
  onUpdated: (episode: EpisodeResponse) => void;
  onDeleted: (episodeId: string) => void;
}) {
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isTranscoding, setIsTranscoding] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const token = getAccessToken();
    if (!token) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    removeEmptyFile(form, data, "video");
    if (!data.get("duration_secs")) {
      data.delete("duration_secs");
    }
    setIsSaving(true);
    try {
      onUpdated(await updateMyEpisode(episode.id, data, token));
    } catch (updateError) {
      setError(messageFor(updateError, "Could not update this episode."));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleTranscode() {
    setError("");
    const token = getAccessToken();
    if (!token) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    setIsTranscoding(true);
    try {
      onUpdated(await transcodeMyEpisode(episode.id, token));
    } catch (transcodeError) {
      setError(messageFor(transcodeError, "Could not convert this episode."));
    } finally {
      setIsTranscoding(false);
    }
  }

  async function handleDelete() {
    if (
      !window.confirm(
        `Delete Episode ${episode.episode_number}: ${episode.title}? This cannot be undone.`,
      )
    ) {
      return;
    }
    setError("");
    const token = getAccessToken();
    if (!token) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    setIsDeleting(true);
    try {
      await deleteMyEpisode(episode.id, token);
      onDeleted(episode.id);
    } catch (deleteError) {
      setError(messageFor(deleteError, "Could not delete this episode."));
      setIsDeleting(false);
    }
  }

  return (
    <li className="rounded-lg border border-neutral-800 bg-neutral-950/60 p-4">
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={handleSubmit}>
        <div className="sm:col-span-2">
          <p className="text-sm font-semibold">
            Episode {episode.episode_number}
          </p>
          {episode.created_by && (
            <p className="mt-1 text-xs text-neutral-500">
              Uploaded by {episode.created_by.handle}
            </p>
          )}
        </div>
        <label className="text-xs font-medium text-neutral-300">
          Title
          <input
            className={fieldClass}
            name="title"
            required
            maxLength={255}
            defaultValue={episode.title}
          />
        </label>
        <label className="text-xs font-medium text-neutral-300">
          Duration (seconds)
          <input
            className={fieldClass}
            name="duration_secs"
            type="number"
            min="1"
            defaultValue={episode.duration_secs ?? ""}
          />
        </label>
        <label className="text-xs font-medium text-neutral-300 sm:col-span-2">
          Description
          <textarea
            className={`${fieldClass} min-h-16 resize-y`}
            name="description"
            defaultValue={episode.description ?? ""}
          />
        </label>
        <label className="text-xs font-medium text-neutral-300 sm:col-span-2">
          Replace video (optional)
          <input
            className={`${fieldClass} file:mr-2 file:rounded-md file:border-0 file:bg-neutral-800 file:px-3 file:py-2 file:text-xs`}
            name="video"
            type="file"
            accept="video/*"
          />
          <span className="mt-1 block text-xs font-normal text-neutral-500">
            The replacement is converted to browser-compatible MP4 while
            uploading.
          </span>
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-300 sm:col-span-2">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          <button
            className="w-fit rounded-lg border border-neutral-700 px-4 py-2 text-sm font-semibold text-neutral-200 transition hover:bg-neutral-800 disabled:opacity-60"
            type="submit"
            disabled={isSaving || isTranscoding || isDeleting}
          >
            {isSaving ? "Saving..." : "Save episode"}
          </button>
          <button
            className="w-fit rounded-lg border border-red-800 px-4 py-2 text-sm font-semibold text-red-300 transition hover:bg-red-950/50 disabled:opacity-60"
            type="button"
            disabled={isSaving || isTranscoding || isDeleting}
            onClick={() => void handleTranscode()}
          >
            {isTranscoding ? "Converting..." : "Convert for browser playback"}
          </button>
          <button
            className="w-fit rounded-lg border border-red-900 px-4 py-2 text-sm font-semibold text-red-300 transition hover:bg-red-950/50 disabled:opacity-60"
            type="button"
            disabled={isSaving || isTranscoding || isDeleting}
            onClick={() => void handleDelete()}
          >
            {isDeleting ? "Deleting..." : "Delete episode"}
          </button>
        </div>
      </form>
    </li>
  );
}
