import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/AppShell";

// Private pages: never listed by search engines.
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function DatasetsLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
