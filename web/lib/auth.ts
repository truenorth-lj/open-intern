/**
 * Shared auth utilities.
 *
 * Token generation for the login API route (Node.js runtime).
 * Middleware uses its own edge-compatible implementation.
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
