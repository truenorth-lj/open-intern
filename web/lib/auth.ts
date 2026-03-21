/**
 * Shared auth utilities — JWT-based authentication.
 */
import { createHash } from "crypto";

export function makeToken(password: string, secret: string): string {
  return createHash("sha256")
    .update(password + secret)
    .digest("hex");
}

export function getAuthSecret(): string {
  const secret = process.env.AUTH_SECRET;
  if (!secret) {
    throw new Error(
      "AUTH_SECRET environment variable is required when DASHBOARD_PASSWORD is set. " +
        "Generate one with: openssl rand -hex 32"
    );
  }
  return secret;
}

export interface AuthUser {
  user_id: string;
  email: string;
  role: "admin" | "user";
}

/**
 * Decode a JWT token and return the payload.
 * Returns null if invalid or expired.
 */
export function decodeJWT(token: string): AuthUser | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(
      Buffer.from(parts[1], "base64url").toString()
    );
    if (payload.exp && payload.exp < Date.now() / 1000) return null;
    return {
      user_id: payload.user_id,
      email: payload.email,
      role: payload.role,
    };
  } catch {
    return null;
  }
}
