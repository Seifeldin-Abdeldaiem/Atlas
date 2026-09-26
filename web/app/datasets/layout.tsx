import type { ReactNode } from "react";

import { AppShell } from "@/components/AppShell";

export default function DatasetsLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
