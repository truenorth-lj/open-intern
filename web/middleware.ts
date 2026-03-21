import { NextRequest, NextResponse } from "next/server";

const DASHBOARD_PASSWORD = process.env.DASHBOARD_PASSWORD || "";

/** Edge-compatible token generation using Web Crypto API. */
async function makeTokenEdge(password: string, secret: string): Promise<string> {
  const data = new TextEncoder().encode(password + secret);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function middleware(request: NextRequest) {
  // No password set = no auth required (local dev)
  if (!DASHBOARD_PASSWORD) {
    return NextResponse.next();
  }

  // Allow login page and auth API
  const { pathname } = request.nextUrl;
  if (pathname === "/login" || pathname.startsWith("/api/auth/")) {
    return NextResponse.next();
  }

  const secret = process.env.AUTH_SECRET;
  if (!secret) {
    // AUTH_SECRET not set — cannot validate, redirect to login
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  // Check session cookie
  const session = request.cookies.get("oi_session")?.value;
  const expected = await makeTokenEdge(DASHBOARD_PASSWORD, secret);

  if (session !== expected) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Protect everything except static files and Next.js internals
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
