import { jwtVerify } from "jose";
import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/api/auth/", "/api/dashboard/"];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p));
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  const token = request.cookies.get("oi_token")?.value;
  if (!token) {
    const response = NextResponse.redirect(new URL("/login", request.url));
    response.cookies.delete("oi_session");
    return response;
  }

  // Verify JWT signature + expiry using jose (Edge-compatible)
  const secret = process.env.AUTH_SECRET;
  if (secret) {
    try {
      const key = new TextEncoder().encode(secret);
      await jwtVerify(token, key, { algorithms: ["HS256"] });
    } catch {
      // Invalid signature or expired
      const response = NextResponse.redirect(new URL("/login", request.url));
      response.cookies.delete("oi_token");
      return response;
    }
  } else {
    // No AUTH_SECRET — fall back to structure + expiry check only
    try {
      const parts = token.split(".");
      if (parts.length !== 3) {
        return NextResponse.redirect(new URL("/login", request.url));
      }
      const payload = JSON.parse(
        atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"))
      );
      if (payload.exp && payload.exp < Date.now() / 1000) {
        return NextResponse.redirect(new URL("/login", request.url));
      }
    } catch {
      return NextResponse.redirect(new URL("/login", request.url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
