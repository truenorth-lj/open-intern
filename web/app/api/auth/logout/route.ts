import { NextResponse } from "next/server";
import { cookies } from "next/headers";

export async function POST() {
  const cookieStore = await cookies();
  cookieStore.delete("oi_token");
  cookieStore.delete("oi_session"); // Clear legacy cookie too
  return NextResponse.json({ ok: true });
}
