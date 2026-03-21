import { NextRequest, NextResponse } from "next/server";

const AUTH_SECRET = process.env.AUTH_SECRET || "open_intern_default_secret";
const DASHBOARD_PASSWORD = process.env.DASHBOARD_PASSWORD || "";

async function makeToken(password: string): Promise<string> {
  const data = new TextEncoder().encode(password + AUTH_SECRET);
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

  // Check session cookie
  const session = request.cookies.get("oi_session")?.value;
  const expected = await makeToken(DASHBOARD_PASSWORD);

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
