import { Suspense, lazy } from "react";
import SafeCanvas from "./SafeCanvas";
import { prefersReducedMotion, supportsWebGL } from "../motion/webgl";
import AnimatedNumber from "../motion/AnimatedNumber";
import TextEffect from "../motion/TextEffect";
import InView from "../motion/InView";
import type { Dashboard } from "../types";

/** ThreeUI's DotMatrixBackground — a real WebGL shader template from
 *  @designcodeio/threeui, lazily loaded so the ~150KB three.js chunk never
 *  blocks first paint and never loads at all for reduced-motion users. */
const DotMatrixBackground = lazy(() =>
  import("@designcodeio/threeui/components/DotMatrixBackground").then((m) => ({
    default: m.DotMatrixBackground,
  })),
);

export default function Hero({ data }: { data: Dashboard }) {
  const s = data.summary;
  // Only attempt the WebGL background when the browser can actually provide a
  // context AND the user has not asked for reduced motion. Without the first
  // check, THREE's renderer throws during render and unmounts the app.
  const showCanvas = supportsWebGL() && !prefersReducedMotion();

  const figures = [
    { label: "Cases worked", value: s.cases },
    { label: "Ledger entries", value: s.entries },
    { label: "Certificates issued", value: s.certificates },
    { label: "Blocked by the kernel", value: s.denied, tone: "deny" as const },
  ];

  return (
    <section className="rl-hero">
      <div className="rl-hero-bg" aria-hidden="true">
        {showCanvas && (
          <SafeCanvas>
          <Suspense fallback={null}>
            <DotMatrixBackground
              speed={0.5}
              gridScale={46}
              opacity={0.22}
              radius={0.13}
              pulseSpeed={0.3}
              mouseAmount={0.05}
            />
          </Suspense>
          </SafeCanvas>
        )}
      </div>

      <div className="rl-hero-inner">
        <InView>
          <span className="rl-eyebrow">Razorpay Buildathon · Track 03</span>
        </InView>

        <TextEffect as="h1" className="rl-hero-title" delay={0.05} accentFrom={1}>
          Recovery Ledger
        </TextEffect>

        <InView index={1}>
          <p className="rl-hero-lede">
            An autonomous revenue-recovery agent for Indian payments. It reports{" "}
            <strong>incremental</strong> rupees recovered against a randomised
            no-contact holdout, and every outbound action is gated by a
            deterministic compliance kernel that is deliberately not an LLM.
          </p>
        </InView>

        <div className="rl-hero-figures">
          {figures.map((f, i) => (
            <InView key={f.label} index={i + 2}>
              <div className="rl-hero-figure">
                <AnimatedNumber
                  value={f.value}
                  className={`rl-hero-num${f.tone === "deny" ? " is-deny" : ""}`}
                />
                <span className="rl-hero-figure-label">{f.label}</span>
              </div>
            </InView>
          ))}
        </div>
      </div>
    </section>
  );
}
