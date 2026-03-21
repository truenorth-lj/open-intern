import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { makeToken, getAuthSecret } from "@/lib/auth";

const DASHBOARD_PASSWORD = process.env.DASHBOARD_PASSWORD || "";

export async function POST(req: NextRequest) {
  if (!DASHBOARD_PASSWORD) {
    return NextResponse.json({ error: "No password configured" }, { status: 500 });
  }

  const { password } = await req.json();
  if (password !== DASHBOARD_PASSWORD) {
    return NextResponse.json({ error: "Wrong password" }, { status: 401 });
  }

  let token: string;
  try {
    token = makeToken(password, getAuthSecret());
  } catch {
    return NextResponse.json({ error: "Server misconfiguration: AUTH_SECRET not set" }, { status: 500 });
  }
  const cookieStore = await cookies();
  cookieStore.set("oi_session", token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7, // 7 days
  });

  return NextResponse.json({ ok: true });
}
