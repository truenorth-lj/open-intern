import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "open_intern — AI that actually works here",
  description:
    "An open-source AI employee that joins your team as a real colleague. Self-hosted, enterprise-grade, with organizational memory.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
