import { motion, useReducedMotion } from "motion/react";

import AnimatedNumber from "../motion/AnimatedNumber";

/** What the agent's silences cost, and what they saved.
 *
 * Two-sided per bucket because the sign is the content: a refusal of a
 * persuadable customer and a refusal of a do-not-disturb are opposite events,
 * and a single-signed bar chart would add them together.
 */
export default function RegretLedger({ regret }: { regret: any }) {
  const reduce = useReducedMotion();
  if (!regret?.buckets?.length) return null;
  const t = regret.totals;
  const widest = Math.max(...regret.buckets.flatMap((b: any) => [b.cost, b.saved]), 1);
  const pct = (v: number) => `${(v / widest) * 100}%`;
  const inr = (v: number) => `₹${Math.round(v).toLocaleString("en-IN")}`;

  return (
    <div className="rl-regret">
      <h3>What the silences cost.</h3>
      <p>
        Every refusal is a bet that contacting would not have paid. On the same
        cases the headline was measured on, those bets cost <b>{inr(t.cost)}</b>,
        saved <b>{inr(t.saved)}</b>, and netted <b>{inr(t.net)}</b>.{" "}
        <span className="rl-regret-err">{t.model_errors} model errors</span> —
        refusals of customers who would have paid.
      </p>
      <ul className="rl-regret-rows">
        {regret.buckets.map((b: any, i: number) => (
          <li key={b.bucket}>
            <span className="rl-regret-name">{b.bucket.replace(/_/g, " ")}</span>
            <span className="rl-regret-fig rl-regret-fig-cost">{inr(b.cost)}</span>
            <span className="rl-regret-bar">
              <span className="rl-regret-cost" style={{ width: pct(b.cost) }} />
              <span className="rl-regret-saved" style={{ width: pct(b.saved) }} />
            </span>
            <span className="rl-regret-fig rl-regret-fig-saved">{inr(b.saved)}</span>
            <span className="rl-regret-net">{inr(b.net)}</span>
          </li>
        ))}
      </ul>
      <p className="rl-regret-foot">
        An expectation under simulator truth, not a realised measurement. Cost
        left of centre, saved right of it.
      </p>
    </div>
  );
}
