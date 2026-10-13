import {
  type AuthToken,
  type EpisodePlaybackResponse,
  type EpisodeResponse,
  isAuthToken,
  isEpisodePlaybackResponse,
  isEpisodeResponse,
  isEpisodeResponseList,
  isSeasonResponse,
  isSeasonResponseList,
  isShowResponse,
  isShowResponseList,
  isUserProfile,
  type LoginCredentials,
  type RegisterRequest,
  type SeasonResponse,
  type ShowResponse,
  type UserProfile,
} from "./schema";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");
const ACCESS_TOKEN_KEY = "access_token";

export type {
  AuthToken,
  EpisodePlaybackResponse,
  EpisodeResponse,
  SeasonResponse,
  ShowResponse,
  UserProfile,
} from "./schema";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function errorMessage(payload: unknown, fallback: string): string {
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("detail" in payload)
  ) {
    return fallback;
  }

  const detail = payload.detail;
  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    const firstMessage = detail.find(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        "msg" in item &&
        typeof item.msg === "string",
    );

    if (
      firstMessage &&
      "msg" in firstMessage &&
      typeof firstMessage.msg === "string"
    ) {
      return firstMessage.msg;
    }
  }

  return fallback;
}

async function request<T>(
  path: string,
  init: RequestInit,
  isResponse: (payload: unknown) => payload is T,
  fallbackMessage: string,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/v1${path}`, init);
  let payload: unknown;

  try {
    payload = await response.json();
  } catch {
    throw new ApiError(
      "The API returned an invalid response.",
      response.status,
    );
  }

  if (!response.ok) {
    throw new ApiError(errorMessage(payload, fallbackMessage), response.status);
  }

  if (!isResponse(payload)) {
    throw new ApiError("The API returned data in an unexpected format.", 502);
  }

  return payload;
}

export function registerUser(data: RegisterRequest): Promise<UserProfile> {
  return request(
    "/auth/register",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    },
    isUserProfile,
    "Could not create your account.",
  );
}

export function loginUser(credentials: LoginCredentials): Promise<AuthToken> {
  const form = new URLSearchParams({
    username: credentials.username,
    password: credentials.password,
  });

  return request(
    "/auth/token",
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    },
    isAuthToken,
    "Could not sign in.",
  );
}

export async function getCurrentUser(
  token = getAccessToken(),
): Promise<UserProfile> {
  if (!token) {
    throw new ApiError("You are not signed in.", 401);
  }

  return request(
    "/users/me",
    { headers: { Authorization: `Bearer ${token}` } },
    isUserProfile,
    "Could not load your profile.",
  );
}

export function saveAccessToken(token: string): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(ACCESS_TOKEN_KEY, token);
    window.dispatchEvent(new Event("animewatcher:auth-change"));
  }
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export async function isSignedIn(): Promise<boolean> {
  const token = getAccessToken();
  if (!token) {
    return false;
  }

  try {
    await getCurrentUser(token);
    return true;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      clearAccessToken();
      return false;
    }

    throw error;
  }
}

export function clearAccessToken(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.dispatchEvent(new Event("animewatcher:auth-change"));
  }
}

export function getMediaAssetUrl(path: string): string {
  return /^https?:\/\//i.test(path) ? path : `${API_BASE_URL}${path}`;
}

export function getShows(): Promise<ShowResponse[]> {
  return request(
    "/media/shows/list",
    {},
    isShowResponseList,
    "Could not load shows.",
  );
}

export function getMyShows(token = getAccessToken()): Promise<ShowResponse[]> {
  if (!token)
    return Promise.reject(new ApiError("You are not signed in.", 401));
  return request(
    "/media/my/shows",
    { headers: authHeaders(token) },
    isShowResponseList,
    "Could not load your shows.",
  );
}

export function getMyShow(
  showId: string,
  token = getAccessToken(),
): Promise<ShowResponse> {
  if (!token)
    return Promise.reject(new ApiError("You are not signed in.", 401));
  return request(
    `/media/my/shows/${showId}`,
    { headers: authHeaders(token) },
    isShowResponse,
    "Could not load this show.",
  );
}

export function getShowByTitle(title: string): Promise<ShowResponse> {
  return request(
    `/media/shows/title/${encodeURIComponent(title)}`,
    {},
    isShowResponse,
    "Could not load this show.",
  );
}

export function getShowSeasons(showId: string): Promise<SeasonResponse[]> {
  return request(
    `/media/shows/${showId}/seasons`,
    {},
    isSeasonResponseList,
    "Could not load seasons.",
  );
}

export function getMyShowSeasons(
  showId: string,
  token = getAccessToken(),
): Promise<SeasonResponse[]> {
  if (!token)
    return Promise.reject(new ApiError("You are not signed in.", 401));
  return request(
    `/media/my/shows/${showId}/seasons`,
    { headers: authHeaders(token) },
    isSeasonResponseList,
    "Could not load your seasons.",
  );
}
export function getSeasonEpisodes(
  seasonId: string,
): Promise<EpisodeResponse[]> {
  return request(
    `/media/seasons/${seasonId}/episodes`,
    {},
    isEpisodeResponseList,
    "Could not load episodes.",
  );
}

export function getMySeasonEpisodes(
  seasonId: string,
  token = getAccessToken(),
): Promise<EpisodeResponse[]> {
  if (!token)
    return Promise.reject(new ApiError("You are not signed in.", 401));
  return request(
    `/media/my/seasons/${seasonId}/episodes`,
    { headers: authHeaders(token) },
    isEpisodeResponseList,
    "Could not load your episodes.",
  );
}

export function getMyEpisodePlaybackUrl(
  episodeId: string,
  token = getAccessToken(),
): Promise<string> {
  if (!token)
    return Promise.reject(new ApiError("You are not signed in.", 401));
  return request(
    `/media/my/episodes/${episodeId}/playback`,
    { method: "POST", headers: authHeaders(token) },
    isEpisodePlaybackResponse,
    "Could not start private episode playback.",
  ).then((playback: EpisodePlaybackResponse) => playback.playback_url);
}

export function transcodeMyEpisode(
  episodeId: string,
  token: string,
): Promise<EpisodeResponse> {
  return request(
    `/media/my/episodes/${episodeId}/transcode`,
    { method: "POST", headers: authHeaders(token) },
    isEpisodeResponse,
    "Could not convert this episode for browser playback.",
  );
}

async function deleteMyMedia(path: string, token: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1${path}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (response.status === 204) {
    return;
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(
      "The API returned an invalid response.",
      response.status,
    );
  }

  if (!response.ok) {
    throw new ApiError(
      errorMessage(payload, "Could not delete this item."),
      response.status,
    );
  }
  throw new ApiError("The API returned an unexpected delete response.", 502);
}

export function deleteMyShow(showId: string, token: string): Promise<void> {
  return deleteMyMedia(`/media/my/shows/${showId}`, token);
}

export function deleteMySeason(seasonId: string, token: string): Promise<void> {
  return deleteMyMedia(`/media/my/seasons/${seasonId}`, token);
}

export function deleteMyEpisode(
  episodeId: string,
  token: string,
): Promise<void> {
  return deleteMyMedia(`/media/my/episodes/${episodeId}`, token);
}

// functions to communicate to backend
export async function createShow(
  formData: FormData,
  token: string,
): Promise<ShowResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/media/shows`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData, // FormData handles multipart/form-data for files and text fields automatically
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new ApiError(
      errorMessage(payload, "Could not create show."),
      response.status,
    );
  }
  if (!isShowResponse(payload)) {
    throw new ApiError("The API returned data in an unexpected format.", 502);
  }
  return payload;
}

export async function createEpisode(
  seasonId: string,
  formData: FormData,
  token: string,
): Promise<EpisodeResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/media/seasons/${seasonId}/episodes`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    },
  );

  const payload = await response.json();
  if (!response.ok) {
    throw new ApiError(
      errorMessage(payload, "Could not upload episode."),
      response.status,
    );
  }
  if (!isEpisodeResponse(payload)) {
    throw new ApiError("The API returned data in an unexpected format.", 502);
  }
  return payload;
}

function authHeaders(token: string): Record<string, string> {
  return { Authorization: "Bearer ".concat(token) };
}

async function multipartRequest<T>(
  path: string,
  method: "POST" | "PATCH",
  formData: FormData,
  token: string,
  isResponse: (payload: unknown) => payload is T,
  fallbackMessage: string,
): Promise<T> {
  return request(
    path,
    { method, headers: authHeaders(token), body: formData },
    isResponse,
    fallbackMessage,
  );
}
export function createSeason(
  showId: string,
  formData: FormData,
  token: string,
): Promise<SeasonResponse> {
  return multipartRequest(
    `/media/shows/${showId}/seasons`,
    "POST",
    formData,
    token,
    isSeasonResponse,
    "Could not create season.",
  );
}

export function updateMyShow(
  showId: string,
  formData: FormData,
  token: string,
): Promise<ShowResponse> {
  return multipartRequest(
    `/media/my/shows/${showId}`,
    "PATCH",
    formData,
    token,
    isShowResponse,
    "Could not update this show.",
  );
}

export function updateMySeason(
  seasonId: string,
  formData: FormData,
  token: string,
): Promise<SeasonResponse> {
  return multipartRequest(
    `/media/my/seasons/${seasonId}`,
    "PATCH",
    formData,
    token,
    isSeasonResponse,
    "Could not update this season.",
  );
}

export function updateMyEpisode(
  episodeId: string,
  formData: FormData,
  token: string,
): Promise<EpisodeResponse> {
  return multipartRequest(
    `/media/my/episodes/${episodeId}`,
    "PATCH",
    formData,
    token,
    isEpisodeResponse,
    "Could not update this episode.",
  );
}
