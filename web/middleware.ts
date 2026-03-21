import { NextRequest, NextResponse } from "next/server";

const DASHBOARD_PASSWORD = process.env.DASHBOARD_PASSWORD || "";

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

  // Check JWT token cookie
  const token = request.cookies.get("oi_token")?.value;
  if (!token) {
    // Check legacy cookie for backward compat
    const legacySession = request.cookies.get("oi_session")?.value;
    if (!legacySession) {
      return NextResponse.redirect(new URL("/login", request.url));
    }
    // Legacy cookie exists — let it through (will be migrated on next login)
    return NextResponse.next();
  }

  // Validate JWT structure and expiry (edge-compatible)
  try {
    const parts = token.split(".");
    if (parts.length !== 3) {
      return NextResponse.redirect(new URL("/login", request.url));
    }
    const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (payload.exp && payload.exp < Date.now() / 1000) {
      return NextResponse.redirect(new URL("/login", request.url));
    }
  } catch {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // Protect everything except static files and Next.js internals
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
