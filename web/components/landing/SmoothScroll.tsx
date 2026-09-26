"use client";

import { useEffect } from "react";

// Glides to in-page sections (#how, #example, #trust) at a calm, controlled
// speed. CSS scroll-behavior can't set a duration, so this animates it.
// People who ask their system for reduced motion get an instant jump.

const MIN_MS = 900;
const MAX_MS = 1600;

function easeInOutCubic(t: number) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

export default function SmoothScroll() {
  useEffect(() => {
    let frame = 0;

    function onClick(e: MouseEvent) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const link = (e.target as Element | null)?.closest?.('a[href^="#"]');
      const id = link?.getAttribute("href")?.slice(1);
      const target = id ? document.getElementById(id) : null;
      if (!target) return;

      e.preventDefault();
      const margin = parseFloat(getComputedStyle(target).scrollMarginTop) || 0;
      const start = window.scrollY;
      const end = Math.max(0, target.getBoundingClientRect().top + start - margin);
      history.pushState(null, "", `#${id}`);

      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        window.scrollTo(0, end);
        return;
      }

      const distance = end - start;
      const duration = Math.min(MAX_MS, Math.max(MIN_MS, Math.abs(distance) * 0.45));
      const began = performance.now();
      cancelAnimationFrame(frame);

      const step = (now: number) => {
        const t = Math.min(1, (now - began) / duration);
        window.scrollTo(0, start + distance * easeInOutCubic(t));
        if (t < 1) frame = requestAnimationFrame(step);
      };
      frame = requestAnimationFrame(step);
    }

    // Stop gliding as soon as the visitor scrolls themselves.
    const stop = () => cancelAnimationFrame(frame);

    document.addEventListener("click", onClick);
    window.addEventListener("wheel", stop, { passive: true });
    window.addEventListener("touchstart", stop, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("click", onClick);
      window.removeEventListener("wheel", stop);
      window.removeEventListener("touchstart", stop);
    };
  }, []);

  return null;
}
