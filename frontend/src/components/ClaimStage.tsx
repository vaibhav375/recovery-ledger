import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";

/** A section's claim, alone, holding the screen before its evidence arrives.
 *
 * The page used to state each point as a heading and then immediately bury it
 * under the material that supports it — twenty-odd elements on screen at once,
 * so nothing was ever the thing you were looking at. A claim you scroll past
 * is a heading; a claim that holds the frame while you scroll is an argument.
 *
 * The stage is pinned for roughly two viewports of travel and releases as the
 * evidence comes up. Under prefers-reduced-motion it does not pin at all: two
 * viewports of scroll-travel is exactly the motion someone opts out of, so the
 * claim becomes an ordinary block and the section shortens.
 *
 * Every number passed in here should be derived from an artifact rather than
 * typed, so a claim cannot drift from the evidence underneath it.
 */
export default function ClaimStage({
  mark,
  claim,
  sub,
  travel = 1.9,
}: {
  mark: string;
  claim: React.ReactNode;
  sub?: React.ReactNode;
  travel?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const opacity = useTransform(scrollYProgress, [0, 0.55, 0.85], [1, 1, 0]);
  const y = useTransform(scrollYProgress, [0, 0.85], [0, -40]);

  return (
    <div
      className="rl-claimstage"
      ref={ref}
      style={reduce ? undefined : { height: `${travel * 100}svh` }}
    >
      <motion.div
        className="rl-claimstage-inner"
        style={reduce ? undefined : { opacity, y }}
      >
        <p className="rl-sectionmark">{mark}</p>
        <h2 className="rl-claimstage-headline">{claim}</h2>
        {sub && <p className="rl-claimstage-sub">{sub}</p>}
      </motion.div>
    </div>
  );
}
