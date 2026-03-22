import { NextRequest, NextResponse } from "next/server";

export async function middleware(request: NextRequest) {
  // Allow login page and auth API without token
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
