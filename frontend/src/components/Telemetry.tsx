import { useEffect, useState } from "react";

/** A readout pinned to the viewport, never in the content.
 *
 * The reference this borrows from keeps its instrument at the edge of the
 * frame — a loading counter on a hairline, a depth marker in the corner — so
 * the page always tells you where you are without a heading ever having to.
 * This page had no such signal: nine long sections and nothing but the scroll
 * bar to say how far through the argument you were.
 *
 * It reports position, not decoration: which section you are in, and how far
 * down. `mix-blend-mode: difference` keeps it legible over both the dark
 * ground and the lit WebGL field without a plate.
 */

const SECTIONS: [string, string][] = [
  [".rl-opening", "the subtraction"],
  [".rl-subtraction", "the subtraction"],
  [".rl-frontier", "baselines"],
  [".rl-silence", "the work you cannot see"],
  [".rl-cal", "calibration"],
  [".rl-kernel", "the compliance kernel"],
  [".rl-audit", "auditing ourselves"],
  [".rl-livesection", "the live console"],
  [".rl-explorer", "the register"],
];

export default function Telemetry() {
  const [pct, setPct] = useState(0);
  const [here, setHere] = useState(SECTIONS[0][1]);

  useEffect(() => {
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setPct(max > 0 ? Math.min(100, Math.max(0, (window.scrollY / max) * 100)) : 0);

      const mid = window.innerHeight * 0.45;
      let current = SECTIONS[0][1];
      for (const [sel, name] of SECTIONS) {
        const el = document.querySelector(sel);
        if (el && el.getBoundingClientRect().top <= mid) current = name;
      }
      setHere(current);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return (
    <div className="rl-telemetry" aria-hidden="true">
      <span className="rl-telemetry-here">{here}</span>
      <span className="rl-telemetry-rule" style={{ transform: `scaleX(${pct / 100})` }} />
      <span>{String(Math.round(pct)).padStart(3, "0")}</span>
    </div>
  );
}
