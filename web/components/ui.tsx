import type { ReactNode } from "react";

export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="2.8" y="2.8" width="12.4" height="12.4" rx="2" stroke="#17181C" strokeWidth="1.6" />
      <rect x="8.8" y="8.8" width="12.4" height="12.4" rx="2" fill="#2A4BB0" />
    </svg>
  );
}

export function WarnIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true" style={{ marginTop: 1 }}>
      <path d="M9 2.2l7 12.6H2L9 2.2z" stroke="#86470A" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M9 7.5v3.2M9 12.6v.2" stroke="#86470A" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function InfoIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true" style={{ marginTop: 1 }}>
      <circle cx="9" cy="9" r="7" stroke="#45474F" strokeWidth="1.4" />
      <path d="M9 8v4.5M9 5.6v.2" stroke="#45474F" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function ErrorIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true" style={{ marginTop: 1 }}>
      <circle cx="9" cy="9" r="7" stroke="#9B1C22" strokeWidth="1.4" />
      <path d="M6.5 6.5l5 5M11.5 6.5l-5 5" stroke="#9B1C22" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function Spinner({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 22 22" fill="none" aria-hidden="true">
      <circle cx="11" cy="11" r="9" stroke="#D5DCF1" strokeWidth="2" />
      <path className="spin" d="M11 2a9 9 0 019 9" stroke="#2A4BB0" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function UploadGlyph() {
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <rect x="0.75" y="0.75" width="38.5" height="38.5" rx="9.25" stroke="#CFCBBF" strokeWidth="1.5" />
      <path d="M20 25V13M15 18l5-5 5 5M13 27h14" stroke="#17181C" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function FileErrorGlyph() {
  return (
    <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <path d="M14 6h14l10 10v26H14z" stroke="#CFCBBF" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M28 6v10h10" stroke="#CFCBBF" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M21 26l10 10M31 26L21 36" stroke="#9B1C22" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function EmptyGlyph() {
  return (
    <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <rect x="6" y="6" width="24" height="24" rx="3" stroke="#CFCBBF" strokeWidth="1.5" />
      <rect x="18" y="18" width="24" height="24" rx="3" stroke="#17181C" strokeWidth="1.5" strokeDasharray="3 3" />
    </svg>
  );
}

const STEP_NAMES = ["Upload", "Check data", "Analyze", "Review"];

export function Steps({ current }: { current: 1 | 2 | 3 | 4 }) {
  return (
    <ol className="steps" aria-label="Steps">
      {STEP_NAMES.map((name, i) => {
        const n = i + 1;
        const state = n < current ? "done" : n === current ? "current" : "todo";
        return (
          <li key={name} className="step" data-state={state} aria-current={state === "current" ? "step" : undefined}>
            <i>{state === "done" ? "✓" : n}</i>
            {name}
          </li>
        );
      })}
    </ol>
  );
}

export function Crumbs({ children }: { children: ReactNode }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      {children}
    </nav>
  );
}

export const Sep = () => <span className="sep" aria-hidden="true">/</span>;

const STATUS: Record<string, { label: string; className: string }> = {
  parsing: { label: "Reading", className: "badge badge-run" },
  ready: { label: "Ready", className: "badge badge-ok" },
  blocked: { label: "Needs attention", className: "badge badge-warn" },
  failed: { label: "Couldn't read", className: "badge badge-danger" },
  analysing: { label: "Finding duplicates", className: "badge badge-run" },
  analysed: { label: "Duplicates found", className: "badge badge-ok" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, className: "badge badge-neutral" };
  return <span className={s.className}>{s.label}</span>;
}
