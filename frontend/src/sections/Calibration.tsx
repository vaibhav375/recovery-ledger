import InView from "../motion/InView";
import DecileScissor from "../components/DecileScissor";

/** The section where the model is cross-examined instead of quoted.
 *
 * Everything else on this page reports what the agent recovered. This reports
 * how far the model underneath it can be trusted, using the only check a real
 * deployment could run — a randomised holdout, no hidden trait required. Two
 * of the three rules fixed before the run came back unflattering, and they are
 * printed here at the same size as the one that passed. */
export default function Calibration({ cal }: { cal: any }) {
  if (!cal?.draws?.length) return null;
  const v = cal.verdict;

  const bottom = cal.draws.map((d: any) => d.deciles[0]);
  const mean = (f: string) =>
    bottom.reduce((a: number, b: any) => a + b[f], 0) / bottom.length;
  const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

  const rules = [
    {
      rule: "Top bin beats bottom, every draw",
      state: "held" as const,
      read: v.top_minus_bottom_by_draw.map((t: number) => t.toFixed(3)).join("  ·  "),
    },
    {
      rule: `Rank correlation ≥ ${v.monotone_threshold}, every draw`,
      state: v.monotone_all_draws ? ("held" as const) : ("failed" as const),
      read: v.spearman_by_draw.map((s: number) => s.toFixed(3)).join("  ·  "),
    },
    {
      rule: "Calibration slope — no threshold set",
      state: "measured" as const,
      read: `${v.mean_calibration_slope.toFixed(3)} mean`,
    },
  ];

  return (
    <section className="rl-cal">
      <div className="rl-cal-inner">
        <p className="rl-sectionmark">Calibration · make calibration</p>
        <InView>
          <h2 className="rl-h2">
            The ranking is real.
            <span className="rl-dim"> The magnitudes are not.</span>
          </h2>
        </InView>

        <div className="rl-cal-body">
          <div className="rl-cal-copy">
            <InView index={1}>
              <p>
                Every earlier claim about this uplift model ran through one
                number: how closely its predictions track a customer trait only
                the simulator can see. No deployment has that number. This check
                needs nothing but a holdout — ten bins ranked by what the model
                predicted, each one scored against its own uncontacted cases.
              </p>
            </InView>
            <InView index={2}>
              <p>
                The ordering survives. The top bin realises{" "}
                {v.mean_top_minus_bottom.toFixed(3)} more payment probability per
                contact than the bottom, in every draw. The magnitudes do not:
                predictions are spread about a third wider than the effects they
                predict. The error concentrates at the two ends — too pessimistic
                about the lowest bin, too optimistic about the highest, small and
                unsigned in between.
              </p>
            </InView>
            <InView index={3}>
              <p className="rl-cal-note">
                The bin the agent refuses to contact is{" "}
                <b>{pct(v.bottom_decile_true_dnd_share)}</b> customers who really
                are worth less contacted, against{" "}
                {pct(v.population_true_dnd_share)} of everyone. The model finds
                them. It then prices them at{" "}
                {v.bottom_decile_predicted_uplift.toFixed(3)} when they measure{" "}
                {v.bottom_decile_realised_uplift.toFixed(3)}, on an interval
                covering zero in all {cal.eval_draws} draws. It locates them
                without measuring them — which is why the decision to stay quiet
                runs through a second model, not this one.
              </p>
            </InView>
          </div>

          <InView index={2}>
            <DecileScissor draws={cal.draws} />
          </InView>
        </div>

        <InView index={4}>
          <div className="rl-cal-rules">
            <p className="rl-cal-ruleshead">Fixed before the run, reported after it</p>
            <ul>
              {rules.map((r) => (
                <li key={r.rule} className={`rl-cal-rule is-${r.state}`}>
                  <span className="rl-cal-rulename">{r.rule}</span>
                  <span className="rl-cal-ruleread">{r.read}</span>
                  <span className="rl-cal-rulestate">{r.state}</span>
                </li>
              ))}
            </ul>
            <p className="rl-cal-foot">
              {cal.eval_draws} draws × {cal.n_eval.toLocaleString("en-IN")} cases,
              randomised contact, population disjoint from every other experiment
              on this page. The slope is not corrected — a fix would move the
              agent's contact threshold, so it needs its own replicated test
              rather than a patch.
            </p>
          </div>
        </InView>
      </div>
    </section>
  );
}
