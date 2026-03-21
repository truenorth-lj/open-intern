import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { NavSidebar } from "@/components/nav-sidebar";
import { AuthProvider } from "@/lib/auth-context";
import { cookies } from "next/headers";
import { decodeJWT } from "@/lib/auth";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "open_intern Dashboard",
  description: "Manage your AI employee",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const token = cookieStore.get("oi_token")?.value;
  const legacySession = cookieStore.get("oi_session")?.value;
  const isAuthenticated = !!token || !!legacySession;

  // Decode user role for nav sidebar
  let userRole: "admin" | "user" | null = null;
  if (token) {
    const decoded = decodeJWT(token);
    if (decoded) userRole = decoded.role;
  } else if (legacySession) {
    userRole = "admin"; // Legacy sessions are admin
  }

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="h-full flex">
        <AuthProvider>
          {isAuthenticated && <NavSidebar userRole={userRole} />}
          <main className="flex-1 overflow-auto p-6">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
