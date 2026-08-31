import { useEffect, useRef, useState } from "react";
import { useInView, useMotionValue, useReducedMotion, useSpring } from "motion/react";

/** Motion Primitives pattern: a number that springs to its value when it
 *  scrolls into view. Used for the headline metrics so the figures land
 *  rather than simply existing. */
export default function AnimatedNumber({
  value, format = (n: number) => Math.round(n).toLocaleString("en-IN"), className,
}: {
  value: number;
  format?: (n: number) => string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const reduce = useReducedMotion();
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const motionValue = useMotionValue(0);
  const spring = useSpring(motionValue, { stiffness: 90, damping: 22, mass: 0.6 });
  const [display, setDisplay] = useState("0");

  useEffect(() => {
    if (inView) motionValue.set(value);
  }, [inView, value, motionValue]);

  useEffect(() => spring.on("change", (v) => setDisplay(format(v))), [spring, format]);

  // A counter that springs is a flourish; a figure that never arrives is a
  // bug. Under reduced motion the value is simply the value.
  if (reduce) return <span ref={ref} className={className}>{format(value)}</span>;

  return <span ref={ref} className={className}>{display}</span>;
}
