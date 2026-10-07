import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { Atkinson_Hyperlegible_Next, IBM_Plex_Mono, IBM_Plex_Sans, Newsreader } from "next/font/google";
import type { ReactNode } from "react";

import WakeOthers from "@/components/WakeOthers";

import "./globals.css";

const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans", display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });
const serif = Newsreader({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-serif", display: "swap" });
// The landing page's plain-English explanation. Designed by the Braille
// Institute so similar letters can't be mistaken for each other.
const display = Atkinson_Hyperlegible_Next({ subsets: ["latin"], variable: "--font-display", display: "swap", adjustFontFallback: false });

const SITE_URL = "https://atlasmatch.co.uk";
const DESCRIPTION =
  "Atlas finds the same product listed more than once in your spreadsheet, adds up the real stock and keeps look-alike parts apart. Upload a file, check every match, download a clean copy.";

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
      <html lang="en" className={`${sans.variable} ${mono.variable} ${serif.variable} ${display.variable}`}>
        <body>
          {children}
          <WakeOthers />
        </body>
      </html>
    </ClerkProvider>
  );
}
