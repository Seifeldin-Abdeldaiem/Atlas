import { triggerWake } from "@/lib/wake";

// Called by components/WakeOthers.tsx when a real visitor opens a page (the
// keep-awake ping only hits /api/health). Returns whether a round started.
export const dynamic = "force-dynamic";

export function POST() {
  return Response.json({ waking: triggerWake() }, { status: 202 });
}
