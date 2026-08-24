import { useRef } from "react";
import { motion, useInView } from "motion/react";

/** Reveals children once, when scrolled into view. `index` staggers a grid
 *  without needing a parent variant. */
export default function InView({
  children, index = 0, className,
}: {
  children: React.ReactNode;
  index?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  return (
    <motion.div
      ref={ref}
      className={className}
      initial={{ opacity: 0, y: 14, filter: "blur(4px)" }}
      animate={inView ? { opacity: 1, y: 0, filter: "blur(0px)" } : undefined}
      transition={{ duration: 0.5, delay: Math.min(index * 0.045, 0.4), ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
