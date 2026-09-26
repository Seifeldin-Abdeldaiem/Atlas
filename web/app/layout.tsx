import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Newsreader } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";

const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans", display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });
const serif = Newsreader({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-serif", display: "swap" });

export const metadata: Metadata = {
  title: "Atlas",
  description: "Find the work you're doing twice.",
  robots: { index: false, follow: false },
};

const clerkAppearance = {
  variables: { colorPrimary: "#2A4BB0", colorText: "#17181C", borderRadius: "6px", fontFamily: "var(--font-sans)" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <ClerkProvider appearance={clerkAppearance}>
      <html lang="en" className={`${sans.variable} ${mono.variable} ${serif.variable}`}>
        <body>{children}</body>
      </html>
    </ClerkProvider>
  );
}
