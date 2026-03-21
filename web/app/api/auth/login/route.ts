import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

const API_URL = process.env.API_URL || "http://localhost:8000";
const API_SECRET_KEY = process.env.API_SECRET_KEY || "";

export async function POST(req: NextRequest) {
  const { email, password } = await req.json();
  if (!email || !password) {
    return NextResponse.json({ error: "Email and password required" }, { status: 400 });
  }

  // Forward login to backend auth API
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (API_SECRET_KEY) {
    headers["X-API-Key"] = API_SECRET_KEY;
  }

  const res = await fetch(`${API_URL}/api/dashboard/auth/login`, {
    method: "POST",
    headers,
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(
      { error: data.detail || "Invalid credentials" },
      { status: 401 }
    );
  }

  const data = await res.json();
  const cookieStore = await cookies();

  // Set JWT token cookie
  cookieStore.set("oi_token", data.token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7, // 7 days
  });

  // Clear legacy cookie if exists
  cookieStore.delete("oi_session");

  return NextResponse.json({
    ok: true,
    user: data.user,
  });
}
