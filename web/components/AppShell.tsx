"use client";

import { OrganizationList, OrganizationSwitcher, UserButton, useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Logo } from "./ui";

const switcherAppearance = {
  elements: {
    rootBox: { width: "100%" },
    organizationSwitcherTrigger: {
      width: "100%",
      height: 40,
      justifyContent: "space-between",
      padding: "0 10px",
      border: "1px solid #E2DFD6",
      borderRadius: 6,
      background: "#FFFFFF",
    },
  },
};

export function AppShell({ children }: { children: ReactNode }) {
  const { isLoaded, orgId } = useAuth();
  const pathname = usePathname();

  // Every dataset belongs to a workspace. Without one active, ask for one.
  if (isLoaded && !orgId) {
    return (
      <main className="state" style={{ minHeight: "100vh" }}>
        <Logo size={32} />
        <h1 className="serif" style={{ fontSize: 28, lineHeight: "34px" }}>Choose a workspace</h1>
        <p>Atlas keeps each company’s data in its own workspace. Create one for your company, or join one you’ve been invited to.</p>
        <OrganizationList hidePersonal afterSelectOrganizationUrl="/datasets" afterCreateOrganizationUrl="/datasets" />
      </main>
    );
  }

  const datasetsActive = pathname?.startsWith("/datasets");
  const settingsActive = pathname?.startsWith("/settings");

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/datasets" className="brand">
          <Logo />
          <span className="serif">Atlas</span>
        </Link>
        <div className="org-switch">
          <OrganizationSwitcher hidePersonal afterSelectOrganizationUrl="/datasets" appearance={switcherAppearance} />
        </div>
        <nav className="nav" aria-label="Workspace">
          <Link href="/datasets" aria-current={datasetsActive ? "page" : undefined}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M2.5 4.5h11v8a1 1 0 01-1 1h-9a1 1 0 01-1-1v-8zM2.5 4.5l1.5-2h8l1.5 2" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            </svg>
            <span>Datasets</span>
          </Link>
          <Link href="/settings" aria-current={settingsActive ? "page" : undefined}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <circle cx="8" cy="8" r="2.2" stroke="currentColor" strokeWidth="1.3" />
              <path d="M8 1.8v1.6M8 12.6v1.6M1.8 8h1.6M12.6 8h1.6M3.6 3.6l1.1 1.1M11.3 11.3l1.1 1.1M3.6 12.4l1.1-1.1M11.3 4.7l1.1-1.1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
            </svg>
            <span>Settings</span>
          </Link>
        </nav>
        <div className="sidebar-foot">
          <UserButton />
          <span className="who label">Account</span>
        </div>
      </aside>
      <div className="main">{children}</div>
    </div>
  );
}
