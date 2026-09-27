"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";

import { duplicateRows, duplicateValue, groups, heroRows, money } from "./sample";

// The hero's example: five rows of a stock list, then what Atlas makes of them.
// The animation is plain CSS (globals.css, "aha") and ends on the finished
// result after about seven seconds, with the three takeaways highlighted in
// turn. On wide screens it starts on first paint, before any JavaScript loads.
// On narrow screens the answers sit below the fold, so it waits at the first
// frame until they scroll into view; the same goes for a page opened in a
// background tab. It moves for more than five seconds, so the button offers
// Skip while it plays (WCAG 2.2.2) and Replay after. Reduced motion shows the
// result straight away.

const same = heroRows.filter((h) => h.same);
// The hero's rows are the bearing group from the full example, so the money
// figure matches it: stock on the rows other than the one Atlas keeps.
const bearing = groups[0];
const other = heroRows.find((h) => !h.same)!;
const total = same.reduce((sum, h) => sum + h.row.stock, 0);
const at = (seconds: number) => ({ "--at": `${seconds}s` }) as CSSProperties;
const rowList = `${same
  .slice(0, -1)
  .map((h) => h.n)
  .join(", ")} and ${same[same.length - 1].n}`;

export default function Aha() {
  const ref = useRef<HTMLElement>(null);
  const results = useRef<HTMLDivElement>(null);
  const skip = useRef<HTMLSpanElement>(null);
  const [run, setRun] = useState(0);
  // "sm": as served (paused at the first frame on narrow screens only),
  // "wait": paused everywhere, "go": playing, "done": skipped to the end.
  const [mode, setMode] = useState<"sm" | "wait" | "go" | "done">("sm");

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) {
      setMode("go");
      return;
    }
    const inSight = () => {
      const box = results.current?.getBoundingClientRect();
      if (!box || document.visibilityState !== "visible") return false;
      // Half the answers on screen, or 40% of a screen too short for that.
      const shown = Math.min(box.bottom, window.innerHeight) - Math.max(box.top, 0);
      return shown >= Math.min(box.height * 0.5, window.innerHeight * 0.4);
    };
    if (inSight()) {
      setMode("go");
      return;
    }
    // Out of sight (below the fold, or a tab opened in the background). Wide
    // screens have been playing unseen since first paint: start again and hold.
    if (window.matchMedia("(min-width: 1024px)").matches) {
      setRun((r) => r + 1);
      setMode("wait");
    }
    const check = () => {
      if (!inSight()) return;
      stop();
      setMode("go");
    };
    const seen = new IntersectionObserver(check, { threshold: Array.from({ length: 21 }, (_, i) => i / 20) });
    const stop = () => {
      seen.disconnect();
      document.removeEventListener("visibilitychange", check);
    };
    seen.observe(el);
    document.addEventListener("visibilitychange", check);
    return stop;
  }, []);

  return (
    <figure
      ref={ref}
      className={`aha aha-${mode}`}
      aria-label="Example: five rows from a stock list, and what Atlas finds in them"
    >
      <noscript>
        <style>{".aha-sm .aha-play, .aha-sm .aha-play * { animation-play-state: running !important; }"}</style>
      </noscript>
      <div key={run} className="aha-play" style={{ "--from": same[0].row.stock, "--to": total } as CSSProperties}>
        <div className="aha-sheet">
          <div className="aha-sheet-bar">
            <span className="aha-file">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <rect x="1.5" y="1.5" width="11" height="11" rx="2" stroke="currentColor" strokeWidth="1.3" />
                <path d="M1.5 5.2h11M1.5 8.8h11M5.2 5.2v7.3" stroke="currentColor" strokeWidth="1.3" />
              </svg>
              stock-list.xlsx
            </span>
            <span className="aha-sheet-label">Your spreadsheet</span>
          </div>
          <table className="aha-table">
            <thead>
              <tr>
                <th className="aha-n">
                  <span className="visually-hidden">Row</span>
                </th>
                <th>Product name</th>
                <th className="aha-stock">Stock</th>
              </tr>
            </thead>
            <tbody>
              {heroRows.map((h) => (
                <tr
                  key={h.n}
                  className={h.same ? "is-same" : "is-other"}
                  style={{ "--row": h.n - 1, "--mark": h.same ? same.indexOf(h) : same.length } as CSSProperties}
                >
                  <td className="aha-n">
                    <span className="aha-badge">{h.n}</span>
                  </td>
                  <td className="aha-name">
                    <bdi>{h.row.name}</bdi>
                  </td>
                  <td className="aha-stock num">{h.row.stock}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="aha-status" aria-hidden="true">
          <span className="aha-checking">
            <span className="aha-dot" />
            Atlas is checking {heroRows.length} rows
          </span>
          <span className="aha-done">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M6 1.5v8.5M2.5 6.5 6 10l3.5-3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            What Atlas shows you
          </span>
        </div>

        <div className="aha-results" ref={results}>
          <div className="aha-card aha-card-same">
            <div className="aha-card-top">
              <span className="aha-badges" aria-hidden="true">
                {same.map((h) => (
                  <span key={h.n} className="aha-badge">
                    {h.n}
                  </span>
                ))}
              </span>
              <span className="aha-kind">Same product</span>
            </div>
            <p className="aha-title">
              Rows {rowList} are{" "}
              <span className="aha-hl" style={at(3.8)}>
                the same bearing
              </span>
            </p>
            <p className="aha-sum">
              <span className="num">{same.map((h) => h.row.stock).join(" + ")} =</span>
              <strong className="aha-count num" aria-hidden="true" />
              <span className="visually-hidden">{total}</span>
              <span>in stock</span>
            </p>
            <p className="aha-money">
              <strong className="num">{money(duplicateValue(bearing))}</strong> of it sits on the {duplicateRows(bearing).length} extra
              rows,{" "}
              <span className="aha-hl" style={at(5.1)}>
                easy to miss and buy again
              </span>
              .
            </p>
            <p className="aha-why">
              <b>Why:</b> same brand (SKF), same part number (6205), same seals (2RS). Row 4 is just written in Arabic.
            </p>
          </div>

          <div className="aha-card aha-card-other">
            <div className="aha-card-top">
              <span className="aha-badges" aria-hidden="true">
                <span className="aha-badge">{other.n}</span>
              </span>
              <span className="aha-kind">Kept apart</span>
            </div>
            <p className="aha-title">
              Row {other.n} looks the same,{" "}
              <span className="aha-ul" style={at(6.2)}>
                but isn&apos;t
              </span>
            </p>
            <p className="aha-why">ZZ has metal shields, 2RS has rubber seals. They are different parts.</p>
          </div>
        </div>

        <div className="aha-foot">
          <span>Test list, Atlas results</span>
          <button
            type="button"
            className="aha-replay"
            onClick={() => {
              // CSS shows "Skip" only while the animation runs.
              if (skip.current && getComputedStyle(skip.current).visibility === "visible") {
                setMode("done");
                return;
              }
              setRun((r) => r + 1);
              setMode("go");
            }}
          >
            <span ref={skip} className="aha-btn-skip">
              Skip
            </span>
            <span className="aha-btn-replay">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                <path d="M2 6a4 4 0 1 0 1.2-2.85M2 1.8v2.4h2.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Replay
            </span>
          </button>
        </div>
      </div>
    </figure>
  );
}
