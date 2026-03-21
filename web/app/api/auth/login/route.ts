import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { createHash } from "crypto";

const AUTH_SECRET = process.env.AUTH_SECRET || "open_intern_default_secret";
const DASHBOARD_PASSWORD = process.env.DASHBOARD_PASSWORD || "";

function makeToken(password: string): string {
  return createHash("sha256")
    .update(password + AUTH_SECRET)
    .digest("hex");
}

export async function POST(req: NextRequest) {
  if (!DASHBOARD_PASSWORD) {
    return NextResponse.json({ error: "No password configured" }, { status: 500 });
  }

  const { password } = await req.json();
  if (password !== DASHBOARD_PASSWORD) {
    return NextResponse.json({ error: "Wrong password" }, { status: 401 });
  }

  const token = makeToken(password);
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
