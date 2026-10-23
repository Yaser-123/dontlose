import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Fraunces, Outfit } from "next/font/google";

import { AppShell } from "@/components/AppShell";
import "./globals.css";

const sans = Outfit({ subsets: ["latin"], variable: "--font-sans" });
const display = Fraunces({ subsets: ["latin"], variable: "--font-display" });

export const metadata: Metadata = {
  title: "Don'tLose",
  description: "A personal deadline safety net for returns, warranties, renewals, and expiring documents.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className={`${sans.variable} ${display.variable} font-sans text-ink antialiased`}>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
