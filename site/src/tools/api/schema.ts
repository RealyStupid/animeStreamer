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
