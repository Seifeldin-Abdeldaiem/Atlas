// Lightweight check for Render and the keep-awake ping
// (.github/workflows/keep-awake.yml). Loads no page, so it never triggers
// the wake-up in components/WakeOthers.tsx.
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ ok: true });
}
