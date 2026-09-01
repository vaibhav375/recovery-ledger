import { useCallback, useEffect, useState } from "react";

/** A readout pinned to the viewport, and the way to jump between sections.
 *
 * The reference this borrows from keeps its instrument at the edge of the
 * frame — a loading counter on a hairline, a depth marker in the corner — so
 * the page always says where you are without a heading having to.
 *
 * The page is now past twenty-six viewports, and reading it end to end is a
 * long scroll. Rather than bolt a navigation menu onto a design that has no
 * chrome, the progress rule that already spans this bar is divided into one
 * segment per section: it still reads as a progress line, and each segment is
 * a button to its section. The index and the position indicator are the same
 * object, which is why it does not look like navigation was added.
 *
 * Labels are the section marks themselves, so the bar and the page agree on
 * what each part is called.
 */

const SECTIONS: [string, string][] = [
  [".rl-opening", "the holdout"],
  [".rl-subtraction", "the subtraction"],
  [".rl-frontier", "the lever"],
  [".rl-grounding", "what is not simulated"],
  [".rl-silence", "the work you cannot see"],
  [".rl-cal", "calibration"],
  [".rl-kernel", "the constraint"],
  [".rl-audit", "the audit"],
  [".rl-livesection", "the instrument"],
  [".rl-explorer", "the evidence"],
];

export default function Telemetry() {
  const [pct, setPct] = useState(0);
  const [active, setActive] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setPct(max > 0 ? Math.min(100, Math.max(0, (window.scrollY / max) * 100)) : 0);

      const mid = window.innerHeight * 0.45;
      let current = 0;
      SECTIONS.forEach(([sel], i) => {
        const el = document.querySelector(sel);
        if (el && el.getBoundingClientRect().top <= mid) current = i;
      });
      setActive(current);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  const jump = useCallback((sel: string) => {
    const el = document.querySelector(sel);
    if (!el) return;
    // Honour the reduced-motion preference: smooth-scrolling twenty viewports
    // is a lot of motion to inflict on someone who asked for less.
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  }, []);

  const shown = hover ?? active;

  return (
    <nav className="rl-telemetry" aria-label="Sections">
      <span className="rl-telemetry-here">{SECTIONS[shown][1]}</span>

      <span className="rl-telemetry-index">
        {SECTIONS.map(([sel, name], i) => (
          <button
            key={sel}
            type="button"
            className={
              "rl-telemetry-seg" +
              (i === active ? " is-active" : "") +
              (i < active ? " is-passed" : "")
            }
            aria-label={`Jump to ${name}`}
            aria-current={i === active ? "true" : undefined}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(i)}
            onBlur={() => setHover(null)}
            onClick={() => jump(sel)}
          />
        ))}
      </span>

      <span className="rl-telemetry-pct">
        {String(Math.round(pct)).padStart(3, "0")}
      </span>
    </nav>
  );
}
