import { motion } from "motion/react";

/** The negative-uplift quadrant.
 *
 * Every case in the batch, plotted as what the model predicted against what
 * was actually true. The horizontal line at zero is the one that matters:
 * below it, contact makes a customer *less* likely to pay. Those are the
 * do-not-disturbs, and nothing in conventional dunning models their
 * existence — a system built to maximise contact cannot represent a customer
 * it should not contact.
 *
 * Two things are visible here that no summary statistic conveys.
 *
 * The first is the argument: filled points are cases the agent chose to
 * contact, and they thin out sharply below the line. The agent is declining
 * to work cases that a volume-maximising policy would treat as inventory.
 *
 * The second is the honest limit, and it is why this is drawn as a cloud
 * rather than a trend line. Predicted and true uplift correlate around 0.33
 * on the population this scatter is drawn from.
 * The scatter is wide, the bottom-right quadrant is not empty, and every
 * point in it is a case the model recommended contacting and was wrong about.
 * Drawing a fitted line through this would imply a precision the model does
 * not have.
 */

const W = 620;
const H = 400;
const PAD = { l: 58, r: 20, t: 20, b: 46 };

type P = { tau_hat: number; tau_true: number; contacted: number };

export default function UpliftQuadrant({ points }: { points: P[] }) {
  if (!points?.length) return null;

  // Robust axis range, not min-to-max. A handful of extreme tau_hat values
  // stretch the plane and squeeze the bulk of the cloud into a narrow band,
  // hiding the thing the chart exists to show. The outliers are not dropped —
  // they are clipped by the plot area and counted in the caption, because
  // silently discarding the model's most confident predictions would be
  // exactly the wrong points to lose.
  const q = (arr: number[], f: number) => {
    const a = [...arr].sort((m, n) => m - n);
    return a[Math.round(f * (a.length - 1))];
  };
  const xs = points.map((p) => p.tau_hat);
  const ys = points.map((p) => p.tau_true);
  const pad = (lo: number, hi: number) => {
    const m = (hi - lo) * 0.06;
    return [lo - m, hi + m] as const;
  };
  const [x0, x1] = pad(q(xs, 0.01), q(xs, 0.99));
  const [y0, y1] = pad(q(ys, 0.01), q(ys, 0.99));
  const outside = points.filter(
    (p) => p.tau_hat < x0 || p.tau_hat > x1 || p.tau_true < y0 || p.tau_true > y1,
  ).length;
  const X = (v: number) => PAD.l + ((v - x0) / (x1 - x0)) * (W - PAD.l - PAD.r);
  const Y = (v: number) => H - PAD.b - ((v - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);

  const harmful = points.filter((p) => p.tau_true < 0);
  const contactedHarmful = harmful.filter((p) => p.contacted).length;
  const contacted = points.filter((p) => p.contacted).length;
  // The share of do-not-disturbs the agent left alone — the claim, computed
  // from the same points that are drawn, so the caption cannot drift from
  // the picture.
  const spared = harmful.length
    ? 1 - contactedHarmful / harmful.length
    : 0;

  return (
    <figure className="rl-quad">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label="Predicted uplift against true uplift for each case, showing which were contacted">
        <defs>
          <clipPath id="rl-quad-clip">
            <rect x={PAD.l} y={PAD.t} width={W - PAD.l - PAD.r} height={H - PAD.t - PAD.b} />
          </clipPath>
        </defs>
        {/* the quadrant below zero true uplift: contact here destroys value */}
        <rect
          x={PAD.l} y={Y(0)} width={W - PAD.l - PAD.r} height={Math.max(0, H - PAD.b - Y(0))}
          className="rl-quad-bad"
        />

        <line x1={PAD.l} x2={W - PAD.r} y1={Y(0)} y2={Y(0)} className="rl-quad-zero" />
        <line x1={X(0)} x2={X(0)} y1={PAD.t} y2={H - PAD.b} className="rl-quad-zero is-v" />

        <g clipPath="url(#rl-quad-clip)">
        {points.map((p, i) => (
          <motion.circle
            key={i}
            cx={X(p.tau_hat)}
            cy={Y(p.tau_true)}
            r={p.contacted ? 2.4 : 1.7}
            className={p.contacted ? "rl-quad-pt is-contacted" : "rl-quad-pt"}
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: Math.min(0.5, i * 0.0006), duration: 0.4 }}
          />
        ))}
        </g>

        {/* Bottom-left is the sparsest corner, but "sparsest" is not "empty" —
            a few points still fall under the label. A backing plate keeps it
            legible without moving it away from the region it describes. */}
        <rect
          x={PAD.l + 2} y={H - PAD.b - 21} width={318} height={17} rx={3}
          className="rl-quad-annobg"
        />
        <text x={PAD.l + 8} y={H - PAD.b - 8} className="rl-quad-anno">
          below the line, contacting makes them less likely to pay
        </text>

        <text x={PAD.l} y={H - 12} className="rl-quad-axis">
          predicted uplift τ̂ →
        </text>
        <text
          transform={`rotate(-90 14 ${(PAD.t + H - PAD.b) / 2})`}
          x={14} y={(PAD.t + H - PAD.b) / 2}
          className="rl-quad-axis" textAnchor="middle"
        >
          ↑ true uplift
        </text>
      </svg>
      <figcaption>
        <span className="rl-quad-key is-contacted">contacted ({contacted})</span>
        <span className="rl-quad-key">left alone ({points.length - contacted})</span>
        {outside > 0 && (
          <span className="rl-quad-out">
            {outside} of {points.length} outside the axis range
          </span>
        )}
        <span className="rl-quad-stat">
          {Math.round(spared * 100)}% of the {harmful.length} do-not-disturbs in this
          sample were never contacted
        </span>
      </figcaption>
    </figure>
  );
}
