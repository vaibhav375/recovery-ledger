import { useRef } from "react";
import { motion, useScroll, useTransform, useSpring } from "motion/react";

const inr = (n: number) => "₹" + Math.round(n).toLocaleString("en-IN");

/** THE SIGNATURE MOMENT.
 *
 * Every recovery vendor reports gross recovered revenue. This project's whole
 * argument (novelty claim N1) is that the honest figure is a *difference* —
 * what the agent added over a randomised no-contact holdout. So the page makes
 * that subtraction physically happen as you scroll: the full bar fills, then
 * the holdout's share visibly drains out of it, and the number that survives
 * is the only one worth quoting.
 *
 * It is scroll-linked rather than autoplayed on purpose. You have to travel
 * through the subtraction to get to the claim, which is exactly the argument.
 *
 * The stage is pinned (sticky inside a tall section) so the whole sequence
 * plays while it is centred and fully visible. Without the pin, the later
 * phases would resolve after the bar had already scrolled off the top.
 */
export default function Subtraction({
  gross, holdout, incrementalPer1000, ciLow, ciHigh, holdoutRate,
}: {
  gross: number;
  holdout: number;
  incrementalPer1000: number;
  ciLow: number;
  ciHigh: number;
  holdoutRate: number;
}) {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  const p = useSpring(scrollYProgress, { stiffness: 120, damping: 30, mass: 0.4 });

  const ours = gross - holdout;
  const holdoutShare = holdout / gross;

  // Phase 1 (0.06–0.30): the gross bar fills.
  const fill = useTransform(p, [0.06, 0.3], ["0%", "100%"]);
  // Phase 2 (0.36–0.60): the holdout's share drains away from the left.
  const drain = useTransform(p, [0.36, 0.6], ["0%", `${holdoutShare * 100}%`]);
  const drainFade = useTransform(p, [0.36, 0.6], [1, 0.3]);
  const holdoutIn = useTransform(p, [0.34, 0.46], [0, 1]);
  // Phase 3 (0.60–0.80): the surviving figure resolves.
  const claimIn = useTransform(p, [0.6, 0.8], [0, 1]);
  const claimY = useTransform(p, [0.6, 0.8], [26, 0]);

  return (
    <section className="rl-sub" ref={ref}>
      <div className="rl-sub-stage">
       <div className="rl-sub-inner">
        <p className="rl-sectionmark">The measurement</p>

        <div className="rl-sub-row">
          <span className="rl-sub-label">Recovered by the agent</span>
          <span className="rl-sub-figure">{inr(gross)}</span>
        </div>

        <div className="rl-bar">
          <motion.div className="rl-bar-fill" style={{ width: fill }}>
            <motion.div className="rl-bar-holdout" style={{ width: drain, opacity: drainFade }} />
          </motion.div>
        </div>

        <motion.div className="rl-sub-row rl-sub-row--muted" style={{ opacity: holdoutIn }}>
          <span className="rl-sub-label">
            Would have arrived anyway
            <em> — the no-contact holdout recovered {(holdoutRate * 100).toFixed(2)}% unaided</em>
          </span>
          <span className="rl-sub-figure">− {inr(holdout)}</span>
        </motion.div>

        <p className="rl-sub-caveat">
          Simulation, under stated assumptions. Method validity is proven
          separately on Criteo and Hillstrom — real randomised data — before any
          of it touches a simulator.
        </p>

        <motion.div className="rl-claim" style={{ opacity: claimIn, y: claimY }}>
          <span className="rl-claim-label">What the agent actually added</span>
          <span className="rl-claim-figure">{inr(ours)}</span>
          <span className="rl-claim-note">
            {inr(incrementalPer1000)} per 1,000 cases · 95% CI {inr(ciLow)}–{inr(ciHigh)}
          </span>
        </motion.div>
       </div>
      </div>
    </section>
  );
}
