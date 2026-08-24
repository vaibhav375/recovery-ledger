import { motion, useScroll, useTransform } from "motion/react";
import { useRef } from "react";

/** The hero states the thesis, not the product category.
 *
 * A recovery agent's honest number is a *difference*, so the opening line is
 * the uncomfortable half of that: most of the money arrives on its own. The
 * page then spends the next screen proving what is actually left over. */
export default function Opening({ holdoutRate }: { holdoutRate: number }) {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [0, 140]);
  const fade = useTransform(scrollYProgress, [0, 0.7], [1, 0]);

  return (
    <section className="rl-opening" ref={ref}>
      <motion.div className="rl-opening-inner" style={{ y, opacity: fade }}>
        <div className="rl-kicker">
          <span className="rl-kicker-dot" />
          Autonomous revenue recovery · Indian payments
        </div>

        <h1 className="rl-display">
          <span className="rl-display-line">
            {"Recovery".split("").map((c, i) => (
              <motion.span
                key={i}
                initial={{ opacity: 0, y: "0.4em" }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 + i * 0.035, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
              >
                {c}
              </motion.span>
            ))}
          </span>
          <span className="rl-display-line rl-display-line--2">
            <motion.span
              className="rl-display-rule"
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ delay: 0.3, duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
            />
            {"Ledger".split("").map((c, i) => (
              <motion.span
                key={i}
                className="rl-display-accent"
                initial={{ opacity: 0, y: "0.4em" }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 + i * 0.035, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
              >
                {c}
              </motion.span>
            ))}
          </span>
        </h1>

        <motion.p
          className="rl-opening-claim"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.75, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        >
          {(holdoutRate * 100).toFixed(1)}% of these cases pay without being
          contacted at all. Every recovery tool bills you for those.
          <span className="rl-opening-turn"> This one subtracts them.</span>
        </motion.p>
      </motion.div>

      <motion.div
        className="rl-scrollcue"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.4, duration: 0.6 }}
      >
        <span>Scroll</span>
        <span className="rl-scrollcue-line" />
      </motion.div>
    </section>
  );
}
