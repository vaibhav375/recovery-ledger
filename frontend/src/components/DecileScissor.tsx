import { motion, useReducedMotion } from "motion/react";

/** What the model claimed, against what the ledger measured, ten bins deep.
 *
 * The obvious chart is bars for realised uplift with the prediction drawn over
 * them as a line — the matplotlib artifact does exactly that, and it buries
 * the finding. Both sequences climb from roughly zero to 0.29 while the errors
 * between them run 0.01 to 0.08, so a single shared axis spends its whole
 * vertical range on the quantity nobody is arguing about and renders the
 * disagreement as a rounding error.
 *
 * Two claims are being made here and they need two scales. The upper panel is
 * the ranking: claim and measurement per bin, climbing together, which is the
 * result that held. The lower panel is the calibration, at its own zoom: the
 * claim minus the measurement, against zero. The model underprices the low
 * bins and overprices the high ones. The residual is not a clean tilt — it
 * changes sign five times across the middle, where the errors are small and
 * unsigned — so the honest reading, and the one the labels point at, is that
 * the error concentrates at the two ends. That is what a prediction spread
 * wider than the effect it predicts looks like: a fan, not a lean.
 *
 * The faint ticks behind each measurement are the individual draws. This
 * project has watched five single-draw conclusions evaporate, so a chart of a
 * mean that hides its draws would be repeating the mistake in a nicer font.
 */

const W = 620;
const H = 372;
const PAD = { l: 56, r: 18 };
const TOP = { t: 16, b: 214 };      // ranking panel
const RES = { t: 252, b: 322 };     // residual panel
const AXIS = 344;                   // shared bin labels

type Bin = {
  decile: number;
  claimed: number;
  measured: number;
  perDraw: number[];
};

export default function DecileScissor({ draws }: { draws: any[] }) {
  const reduce = useReducedMotion();
  if (!draws?.length) return null;

  const n: number = draws[0].deciles.length;
  const mean = (i: number, f: string) =>
    draws.reduce((a: number, d: any) => a + d.deciles[i][f], 0) / draws.length;

  const bins: Bin[] = Array.from({ length: n }, (_, i) => ({
    decile: i + 1,
    claimed: mean(i, "mean_predicted_uplift"),
    measured: mean(i, "realised_uplift"),
    perDraw: draws.map((d: any) => d.deciles[i].realised_uplift as number),
  }));

  const levels = bins.flatMap((b) => [b.claimed, b.measured, ...b.perDraw]);
  const lo = Math.min(...levels, 0);
  const hi = Math.max(...levels);
  const gutter = (hi - lo) * 0.1;

  const x = (i: number) => PAD.l + (i / (n - 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) =>
    TOP.b - ((v - (lo - gutter)) / (hi + gutter - (lo - gutter))) * (TOP.b - TOP.t);

  const res = bins.map((b) => b.claimed - b.measured);
  const span = Math.max(...res.map(Math.abs)) * 1.15;
  const rz = (RES.t + RES.b) / 2;
  const ry = (v: number) => rz - (v / span) * ((RES.b - RES.t) / 2);

  const dur = reduce ? 0 : 0.5;
  const at = (i: number, base: number) => (reduce ? 0 : base + i * 0.045);

  return (
    <figure className="rl-scissor">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={
          "Ten bins ranked by predicted uplift. Above, the model's claims and the " +
          "measured uplift climb together, so the ordering holds. Below, the claim " +
          "minus the measurement: the error concentrates at the two ends — the model " +
          "is too pessimistic about the lowest bin and too optimistic about the " +
          "highest, and small and unsigned in between."
        }
      >
        {/* ── ranking ─────────────────────────────────────────────── */}
        <line x1={PAD.l - 10} x2={W - PAD.r} y1={y(0)} y2={y(0)} className="rl-scissor-zero" />
        <text x={PAD.l - 14} y={y(0) + 3.5} className="rl-scissor-axis" textAnchor="end">0</text>
        <text x={PAD.l - 14} y={y(hi) + 3.5} className="rl-scissor-axis" textAnchor="end">
          {hi.toFixed(2)}
        </text>
        <text x={0} y={TOP.t - 4} className="rl-scissor-panel">uplift</text>

        {bins.map((b, i) => (
          <g key={b.decile}>
            <motion.line
              x1={x(i)} x2={x(i)}
              initial={{ y1: y(b.claimed), y2: y(b.claimed) }}
              whileInView={{ y1: y(b.claimed), y2: y(b.measured) }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: dur, delay: at(i, 0.4), ease: [0.16, 1, 0.3, 1] }}
              className="rl-scissor-err"
            />
            {b.perDraw.map((v, k) => (
              <line key={k} x1={x(i) - 4} x2={x(i) + 4} y1={y(v)} y2={y(v)}
                className="rl-scissor-draw" />
            ))}
            <motion.rect
              x={x(i) - 4} y={y(b.claimed) - 4} width={8} height={8}
              initial={{ opacity: 0 }} whileInView={{ opacity: 1 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: dur, delay: at(i, 0) }}
              className="rl-scissor-claim"
            />
            <motion.circle
              cx={x(i)} cy={y(b.measured)} r={3.8}
              initial={{ opacity: 0 }} whileInView={{ opacity: 1 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: dur, delay: at(i, 0.4) }}
              className="rl-scissor-measured"
            />
          </g>
        ))}

        {/* ── residual, at its own zoom ────────────────────────────── */}
        <text x={0} y={RES.t - 6} className="rl-scissor-panel">claim − measurement</text>
        <line x1={PAD.l - 10} x2={W - PAD.r} y1={rz} y2={rz} className="rl-scissor-zero" />
        <text x={PAD.l - 14} y={rz + 3.5} className="rl-scissor-axis" textAnchor="end">0</text>

        {/* The sentence half is dropped on narrow screens, where this SVG is
            scaled to about half size and a full clause would render at five
            pixels. The number survives at every width. */}
        <text x={x(0) + 9} y={ry(res[0]) + 3} className="rl-scissor-anno">
          {res[0].toFixed(3)}
          <tspan className="rl-scissor-annolong">
            {" "}— too pessimistic about the bin it will not contact
          </tspan>
        </text>
        <text x={x(n - 1) - 9} y={ry(res[n - 1]) - 6} className="rl-scissor-anno" textAnchor="end">
          <tspan className="rl-scissor-annolong">
            too optimistic about its best bin —{" "}
          </tspan>
          {`+${res[n - 1].toFixed(3)}`}
        </text>

        {bins.map((b, i) => (
          <g key={`r${b.decile}`}>
            <motion.line
              x1={x(i)} x2={x(i)} y1={rz}
              initial={{ y2: rz }}
              whileInView={{ y2: ry(res[i]) }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: dur, delay: at(i, 0.75), ease: [0.16, 1, 0.3, 1] }}
              className={res[i] > 0 ? "rl-scissor-res is-over" : "rl-scissor-res"}
            />
            <motion.circle
              cx={x(i)} r={2.6}
              initial={{ cy: rz, opacity: 0 }}
              whileInView={{ cy: ry(res[i]), opacity: 1 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: dur, delay: at(i, 0.75), ease: [0.16, 1, 0.3, 1] }}
              className={res[i] > 0 ? "rl-scissor-resdot is-over" : "rl-scissor-resdot"}
            />
          </g>
        ))}

        {/* ── shared axis ─────────────────────────────────────────── */}
        {bins.map((b, i) => (
          <text key={`t${b.decile}`} x={x(i)} y={AXIS} className="rl-scissor-tick" textAnchor="middle">
            {b.decile}
          </text>
        ))}
        <text x={W - PAD.r} y={H - 2} className="rl-scissor-axis" textAnchor="end">
          bins ranked by predicted uplift →
        </text>
      </svg>

      <figcaption>
        <span className="rl-scissor-key is-claim">what the model claimed</span>
        <span className="rl-scissor-key is-measured">what the holdout measured</span>
        <span className="rl-scissor-key is-draw">each of 3 draws</span>
      </figcaption>
    </figure>
  );
}
