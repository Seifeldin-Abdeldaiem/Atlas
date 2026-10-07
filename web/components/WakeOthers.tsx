"use client";

import { useEffect } from "react";

/**
 * A real visitor opened Atlas (bots that don't run JavaScript and the
 * keep-awake health ping never get here): ask the server to wake the API and
 * the owner's other sleeping sites. Mounted once in the root layout, so it
 * runs once per page load; the server limits it to one round per 15 minutes.
 */
export default function WakeOthers() {
  useEffect(() => {
    fetch("/api/wake", { method: "POST", keepalive: true }).catch(() => {});
  }, []);
  return null;
}
