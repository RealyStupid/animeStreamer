import {
  type AuthToken,
  isAuthToken,
  isUserProfile,
  type LoginCredentials,
  type RegisterRequest,
  type UserProfile,
} from "./schema";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");
const ACCESS_TOKEN_KEY = "access_token";

export type { AuthToken, UserProfile } from "./schema";

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
  }
}
