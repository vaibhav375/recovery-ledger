import ClaimStage from "../components/ClaimStage";
import InView from "../motion/InView";
import type { Dashboard } from "../types";

/** Where the numbers come from, and which ones this project did not generate.
 *
 * Everything else on this page is measured on a simulator this repository
 * wrote. That is stated everywhere, but stating it is not the same as showing
 * the reader which figures escape it — so this section is the boundary, drawn
 * explicitly.
 *
 * The currencies are deliberately not reconciled. Rupee figures come from the
 * simulator; dollar figures come from Hillstrom, a real US e-commerce
 * experiment. Converting one into the other would mean inventing an exchange
 * rate and applying it to somebody else's dataset, which would destroy the one
 * property that makes those figures worth having.
 */
export default function Grounding({ data }: { data: Dashboard }) {
  const rev = data.revenue;
  const tgt = data.targeting;
  const claims = data.claims ?? [];
  if (!rev && !tgt) return null;

  const held = claims.filter((c: any) => c.status === "HELD").length;
  const refuted = claims.filter((c: any) => c.status === "REFUTED").length;
  const unresolved = claims.filter((c: any) => c.status === "UNRESOLVED").length;

  const usd = (n: number) => `$${Math.round(n).toLocaleString("en-US")}`;

  return (
    <section className="rl-grounding">
      <ClaimStage
        mark="what is not simulated"
        claim={
          tgt ? (
            <>
              Targeting beats random.
              <span className="rl-dim"> Measured on real randomised data, not ours.</span>
            </>
          ) : (
            <>The evidence that is not ours.</>
          )
        }
        sub={
          <>
            Every rupee on this page is simulator output. These are the figures
            that are not — measured on public randomised experiments run by
            other people, with the policy chosen out of sample.
          </>
        }
      />

      <div className="rl-grounding-inner">
        <div className="rl-grounding-grid">
          {tgt && (
            <InView>
              <article className="rl-ground-card is-lead">
                <p className="rl-ground-kicker">Tier 1c · Criteo · {tgt.n_rows.toLocaleString("en-IN")} rows</p>
                <h3>B1's central claim, off the simulator</h3>
                <p className="rl-ground-figure">
                  {tgt.paired_difference > 0 ? "+" : ""}
                  {tgt.paired_difference.toFixed(5)}
                  <span> per user vs matched-volume random</span>
                </p>
                <p className="rl-ground-detail">
                  95% CI [{tgt.paired_ci_low.toFixed(5)}, {tgt.paired_ci_high.toFixed(5)}] —
                  excludes zero, <b>{tgt.standard_errors_from_zero} standard errors out</b>.
                  IPS, SNIPS and DR all agree on the sign. τ̂ was fitted on{" "}
                  {tgt.n_train.toLocaleString("en-IN")} rows and ranked the{" "}
                  {tgt.n_evaluated_out_of_sample.toLocaleString("en-IN")} it never saw.
                </p>
                <p className="rl-ground-caveat">
                  The outcome is a visit, not money — this is the policy claim,
                  not an effect size. Criteo is ad exposure, not payment recovery.
                </p>
              </article>
            </InView>
          )}

          {rev && (
            <InView index={1}>
              <article className="rl-ground-card">
                <p className="rl-ground-kicker">
                  Tier 1b · Hillstrom · {rev.effect_pooled_all_arms.n_customers.toLocaleString("en-IN")} customers
                </p>
                <h3>Incremental money, measured not modelled</h3>
                <p className="rl-ground-figure">
                  {usd(rev.effect_pooled_all_arms.incremental_per_1000)}
                  <span> per 1,000 customers</span>
                </p>
                <p className="rl-ground-detail">
                  95% CI [{usd(rev.effect_pooled_all_arms.ci_low_per_1000)},{" "}
                  {usd(rev.effect_pooled_all_arms.ci_high_per_1000)}] — excludes zero.
                  Real dollars of real spend under a randomisation the
                  experimenter controlled.
                </p>
                <p className="rl-ground-caveat">
                  <b>Dollars, deliberately.</b> This is a US e-commerce dataset.
                  Converting it to rupees would mean inventing an exchange rate
                  and applying it to somebody else's experiment — which would
                  destroy the only thing that makes this figure worth having.
                </p>
              </article>
            </InView>
          )}

          {rev?.targeting_power && (
            <InView index={2}>
              <article className="rl-ground-card">
                <p className="rl-ground-kicker">The question Hillstrom could not answer</p>
                <h3>Not unproven — unprovable there</h3>
                <p className="rl-ground-detail">
                  The same targeting test on Hillstrom's spend sat{" "}
                  <b>{rev.targeting_power.standard_errors_from_zero} standard errors from zero</b>.
                  Resolving it needed roughly{" "}
                  {rev.targeting_power.held_out_customers_needed.toLocaleString("en-IN")}{" "}
                  held-out customers against the{" "}
                  {rev.targeting_power.max_available_pooled_holdout.toLocaleString("en-IN")}{" "}
                  pooling every arm supplies. That power calculation is what
                  pointed at Criteo — the result above followed from measuring
                  the obstacle rather than guessing at a third attempt.
                </p>
              </article>
            </InView>
          )}

          {claims.length > 0 && (
            <InView index={3}>
              <article className="rl-ground-card">
                <p className="rl-ground-kicker">The claims registry · make claims</p>
                <h3>Overclaiming is a build failure</h3>
                <p className="rl-ground-figure is-small">
                  {held} held <span>·</span> {refuted} refuted <span>·</span> {unresolved} unresolved
                </p>
                <p className="rl-ground-detail">
                  Every pre-registered claim, its rule and its verdict — generated
                  from the artifacts, never written by hand. A claim the evidence
                  refuted cannot be asserted in the documents; the suite fails if
                  it is. It also fails if every claim ever comes back held, because
                  that would be evidence of selection rather than rigour.
                </p>
              </article>
            </InView>
          )}
        </div>
      </div>
    </section>
  );
}
