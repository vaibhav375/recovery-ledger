import { motion } from "motion/react";

/** Where caution stops buying money and keeps buying harm reduction.
 *
 * The claim in the prose is that these two things come apart, and a claim
 * about two quantities diverging is a claim about two curves. Net value rises
 * to a peak and turns back down; contacts to cases the model should never
 * have touched fall the whole way. The gap between where one stops improving
 * and the other keeps going is the entire argument for treating k as a policy
 * choice rather than something to maximise.
 *
 * Both series are normalised to their own range so they share a plane. That
 * is a legitimate way to show two quantities with different units diverging,
 * and an illegitimate way to compare their magnitudes — so the axis carries
 * no numbers, the peak is annotated with its real value, and the endpoints
 * are labelled. Everything is read from the pessimism artifact.
 */

const W = 480;
const H = 210;
const PAD = { l: 14, r: 14, t: 22, b: 30 };

export default function CautionCurve({ draws }: { draws: any[] }) {
  if (!draws?.length) return null;
  const ks: number[] = draws[0].sweep.map((r: any) => r.uncertainty_k);
  const mean = (i: number, f: string) =>
    draws.reduce((a: number, d: any) => a + d.sweep[i][f], 0) / draws.length;

  const value = ks.map((_, i) => mean(i, "net_value_per_case"));
  const harm = ks.map((_, i) => mean(i, "harmful_contacts"));

  const x = (i: number) => PAD.l + (i / (ks.length - 1)) * (W - PAD.l - PAD.r);
  const norm = (arr: number[]) => {
    const lo = Math.min(...arr);
    const hi = Math.max(...arr);
    return arr.map((v) => (hi === lo ? 0.5 : (v - lo) / (hi - lo)));
  };
  const y = (t: number) => H - PAD.b - t * (H - PAD.t - PAD.b);

  const vN = norm(value);
  const hN = norm(harm);
  const path = (n: number[]) => n.map((t, i) => `${i ? "L" : "M"}${x(i)},${y(t)}`).join(" ");

  const peak = value.indexOf(Math.max(...value));

  return (
    <figure className="rl-curve">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label="Net value per case peaks and falls as caution rises, while contacts to negative-value cases fall throughout">
        {/* the peak, marked where it happens */}
        <line x1={x(peak)} x2={x(peak)} y1={PAD.t - 6} y2={H - PAD.b} className="rl-curve-peak" />

        <path d={path(hN)} className="rl-curve-harm" />
        <motion.path
          d={path(vN)}
          className="rl-curve-value"
          initial={{ pathLength: 0 }}
          whileInView={{ pathLength: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
        />

        {vN.map((t, i) => (
          <circle key={i} cx={x(i)} cy={y(t)} r={i === peak ? 4 : 2.5}
            className={i === peak ? "rl-curve-dot is-peak" : "rl-curve-dot"} />
        ))}
        {hN.map((t, i) => (
          <circle key={`h${i}`} cx={x(i)} cy={y(t)} r={2} className="rl-curve-dot is-harm" />
        ))}

        <text x={x(peak)} y={PAD.t - 10} className="rl-curve-anno" textAnchor="middle">
          peak ₹{Math.round(value[peak])}/case at k = {ks[peak]}
        </text>

        {ks.map((k, i) => (
          <text key={k} x={x(i)} y={H - 12} className="rl-curve-tick" textAnchor="middle">
            {k}
          </text>
        ))}
      </svg>
      <figcaption>
        <span className="rl-curve-key is-value">net value per case</span>
        <span className="rl-curve-key is-harm">
          contacts to negative-value cases ({Math.round(harm[0])} → {Math.round(harm[harm.length - 1])})
        </span>
        <span className="rl-curve-axis">caution k →</span>
      </figcaption>
    </figure>
  );
}
