import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

const API_URL = process.env.API_URL || "http://localhost:8000";
const API_SECRET_KEY = process.env.API_SECRET_KEY || "";

async function proxyRequest(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const targetPath = `/api/dashboard/${path.join("/")}`;
  const url = new URL(targetPath, API_URL);
  url.search = req.nextUrl.search;

  const headers = new Headers(req.headers);
  if (API_SECRET_KEY) {
    headers.set("X-API-Key", API_SECRET_KEY);
  }

  // Forward JWT token from cookie as Authorization header
  const cookieStore = await cookies();
  const token = cookieStore.get("oi_token")?.value;
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  headers.delete("host");

  const res = await fetch(url.toString(), {
    method: req.method,
    headers,
    body: req.body,
    // @ts-expect-error duplex is needed for streaming body
    duplex: "half",
  });

  return new NextResponse(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: Object.fromEntries(res.headers.entries()),
  });
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const DELETE = proxyRequest;
export const PATCH = proxyRequest;
