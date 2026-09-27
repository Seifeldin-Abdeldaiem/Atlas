import type { Metadata } from "next";
import type { ReactNode } from "react";

// Private pages: never listed by search engines.
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function SignUpLayout({ children }: { children: ReactNode }) {
  return children;
}
