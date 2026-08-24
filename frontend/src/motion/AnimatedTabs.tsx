import { motion } from "motion/react";

/** Motion Primitives "animated background" pattern: a single pill that slides
 *  between the active item using a shared layoutId, instead of each item
 *  toggling its own background. */
export default function AnimatedTabs<T extends string>({
  items, value, onChange, className, itemClassName, layoutId,
}: {
  items: { id: T; label: string; flag?: string }[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
  itemClassName?: string;
  layoutId: string;
}) {
  return (
    <div className={className}>
      {items.map((it) => {
        const active = it.id === value;
        return (
          <button
            key={it.id}
            className={itemClassName}
            aria-current={active}
            onClick={() => onChange(it.id)}
          >
            {active && (
              <motion.span
                layoutId={layoutId}
                className="rl-tab-pill"
                transition={{ type: "spring", stiffness: 340, damping: 30 }}
              />
            )}
            <span className="rl-tab-label">{it.label}</span>
            {it.flag && <span className="rl-nav-flag">{it.flag}</span>}
          </button>
        );
      })}
    </div>
  );
}
