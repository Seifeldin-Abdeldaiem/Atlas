import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Newsreader } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";

const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans", display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });
const serif = Newsreader({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-serif", display: "swap" });

const SITE_URL = "https://atlasmatch.co.uk";
const DESCRIPTION =
  "Atlas finds the duplicate lines in your product catalogue, keeps look-alike parts apart, and shows the stock tied up in duplicates. Upload a spreadsheet, review the matches, download a clean file.";

// Public pages are listed by search engines; the signed-in app and the
// sign-in pages opt out in their own layouts (and in robots.ts).
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: "Atlas: find duplicate products in your catalogue", template: "%s · Atlas" },
  description: DESCRIPTION,
  alternates: { canonical: "/" },
  robots: { index: true, follow: true },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: "Atlas",
    title: "Atlas: find duplicate products in your catalogue",
    description: DESCRIPTION,
    locale: "en_GB",
  },
  twitter: { card: "summary", title: "Atlas: find duplicate products in your catalogue", description: DESCRIPTION },
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
