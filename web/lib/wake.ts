/**
 * Wake the owner's other free-plan sites when a real visitor opens Atlas.
 *
 * Atlas's website is kept awake (.github/workflows/keep-awake.yml); the API
 * and the other sites sleep when idle on Render's free plan. When someone
 * opens a page, components/WakeOthers.tsx calls POST /api/wake and this
 * pings each URL in WAKE_URLS so those services start booting.
 *
 * - URLs come only from server config, never from the request, so this
 *   can't be used to make the server fetch arbitrary addresses.
 * - At most one round per WAKE_INTERVAL_SECONDS (default 15 minutes), however
 *   many visitors: a woken service stays up for about 15 minutes anyway, so
 *   pinging more often would only spend free hours twice.
 */

// A sleeping free Render service can take about a minute to answer.
const PING_TIMEOUT_MS = 90_000;

let lastStarted: number | null = null;

export function wakeUrls(): string[] {
  return (process.env.WAKE_URLS ?? "")
    .split(",")
    .map((url) => url.trim())
    .filter(Boolean);
}

function intervalMs(): number {
  const seconds = Number(process.env.WAKE_INTERVAL_SECONDS ?? 900);
  return (Number.isFinite(seconds) && seconds > 0 ? seconds : 900) * 1000;
}

/** Starts a round of pings in the background unless one started recently. */
export function triggerWake(now: number = Date.now()): boolean {
  const urls = wakeUrls();
  if (urls.length === 0) return false;
  if (lastStarted !== null && now - lastStarted < intervalMs()) return false;
  lastStarted = now;
  for (const url of urls) void ping(url);
  return true;
}

async function ping(url: string): Promise<void> {
  const started = Date.now();
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(PING_TIMEOUT_MS), cache: "no-store" });
    console.log(`Woke ${url}: HTTP ${res.status} in ${Math.round((Date.now() - started) / 1000)}s`);
  } catch (error) {
    // A failed wake must never affect Atlas itself.
    console.log(`Wake ping to ${url} failed after ${Math.round((Date.now() - started) / 1000)}s: ${String(error)}`);
  }
}
