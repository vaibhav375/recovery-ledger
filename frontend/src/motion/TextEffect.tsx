import { motion } from "motion/react";

/** Motion Primitives pattern: per-word blur-and-rise entrance. Kept subtle —
 *  this is a compliance tool, so the motion should feel considered rather
 *  than showy. */
export default function TextEffect({
  children, as: Tag = "h1", className, delay = 0, accentFrom,
}: {
  children: string;
  as?: any;
  className?: string;
  delay?: number;
  /** Index from which words take the accent colour. */
  accentFrom?: number;
}) {
  const words = children.split(" ");
  const MotionTag = motion(Tag);
  return (
    <MotionTag
      className={className}
      initial="hidden"
      animate="visible"
      variants={{ visible: { transition: { staggerChildren: 0.035, delayChildren: delay } } }}
    >
      {words.map((w, i) => (
        <motion.span
          key={`${w}-${i}`}
          className={accentFrom !== undefined && i >= accentFrom ? "rl-accent-word" : undefined}
          style={{ display: "inline-block", whiteSpace: "pre" }}
          variants={{
            hidden: { opacity: 0, y: "0.3em", filter: "blur(6px)" },
            visible: {
              opacity: 1, y: 0, filter: "blur(0px)",
              transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] },
            },
          }}
        >
          {w}{i < words.length - 1 ? " " : ""}
        </motion.span>
      ))}
    </MotionTag>
  );
}
