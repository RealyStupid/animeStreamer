export interface LoginCredentials {
  username: string;
  password: string;
}

export interface RegisterRequest {
  handle: string;
  email: string;
  password: string;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
}

export interface UserProfile {
  id: string;
  handle: string;
  email: string;
  role: string;
}

export interface ShowTag {
  id: string;
  name: string;
}

export interface MediaCreator {
  id: string;
  handle: string;
}

export interface ShowResponse {
  id: string;
  title: string;
  description: string;
  genre: string;
  thumbnail_url: string | null;
  is_private: boolean;
  created_by: MediaCreator | null;
  tags: ShowTag[];
}

export interface SeasonResponse {
  id: string;
  show_id: string;
  season_number: number;
  name: string;
  description: string;
  thumbnail_url: string | null;
  created_by: MediaCreator | null;
}

export interface EpisodeResponse {
  id: string;
  season_id: string;
  episode_number: number;
  title: string;
  description: string | null;
  video_url: string;
  duration_secs: number | null;
  created_by: MediaCreator | null;
}

export interface EpisodePlaybackResponse {
  playback_url: string;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function isAuthToken(value: unknown): value is AuthToken {
  return (
    typeof value === "object" &&
    value !== null &&
    "access_token" in value &&
    typeof value.access_token === "string" &&
    "token_type" in value &&
    typeof value.token_type === "string"
  );
}

export function isUserProfile(value: unknown): value is UserProfile {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "string" &&
    "handle" in value &&
    typeof value.handle === "string" &&
    "email" in value &&
    typeof value.email === "string"
  );
}

export function isShowResponse(value: unknown): value is ShowResponse {
  return (
    isObject(value) &&
    typeof value.id === "string" &&
    typeof value.title === "string" &&
    typeof value.description === "string" &&
    typeof value.genre === "string" &&
    (value.thumbnail_url === null || typeof value.thumbnail_url === "string") &&
    typeof value.is_private === "boolean" &&
    (value.created_by === null ||
      (isObject(value.created_by) &&
        typeof value.created_by.id === "string" &&
        typeof value.created_by.handle === "string")) &&
    Array.isArray(value.tags) &&
    value.tags.every(
      (tag) =>
        isObject(tag) &&
        typeof tag.id === "string" &&
        typeof tag.name === "string",
    )
  );
}

export function isSeasonResponse(value: unknown): value is SeasonResponse {
  return (
    isObject(value) &&
    typeof value.id === "string" &&
    typeof value.show_id === "string" &&
    typeof value.season_number === "number" &&
    typeof value.name === "string" &&
    typeof value.description === "string" &&
    (value.thumbnail_url === null || typeof value.thumbnail_url === "string") &&
    (value.created_by === null ||
      (isObject(value.created_by) &&
        typeof value.created_by.id === "string" &&
        typeof value.created_by.handle === "string"))
  );
}

export function isEpisodeResponse(value: unknown): value is EpisodeResponse {
  return (
    isObject(value) &&
    typeof value.id === "string" &&
    typeof value.season_id === "string" &&
    typeof value.episode_number === "number" &&
    typeof value.title === "string" &&
    (value.description === null || typeof value.description === "string") &&
    typeof value.video_url === "string" &&
    (value.duration_secs === null || typeof value.duration_secs === "number") &&
    (value.created_by === null ||
      (isObject(value.created_by) &&
        typeof value.created_by.id === "string" &&
        typeof value.created_by.handle === "string"))
  );
}

export function isEpisodePlaybackResponse(
  value: unknown,
): value is EpisodePlaybackResponse {
  return (
    isObject(value) &&
    typeof value.playback_url === "string" &&
    value.playback_url.startsWith("/api/v1/media/episodes/")
  );
}

export function isShowResponseList(value: unknown): value is ShowResponse[] {
  return Array.isArray(value) && value.every(isShowResponse);
}

export function isSeasonResponseList(
  value: unknown,
): value is SeasonResponse[] {
  return Array.isArray(value) && value.every(isSeasonResponse);
}

export function isEpisodeResponseList(
  value: unknown,
): value is EpisodeResponse[] {
  return Array.isArray(value) && value.every(isEpisodeResponse);
}
