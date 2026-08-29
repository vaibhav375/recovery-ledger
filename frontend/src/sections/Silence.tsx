import InView from "../motion/InView";
import UpliftQuadrant from "../components/UpliftQuadrant";
import PolicySpaceGuard from "../components/PolicySpaceGuard";

/** The agent's most interesting decisions are the ones where it does nothing.
 *
 * Framed as its own section because it inverts what a recovery product is
 * assumed to be. Three different mechanisms all produce the same outcome —
 * no message sent — for three genuinely different reasons. */
export default function Silence({
  dndCases, promiseWindows, futileRetries, contactsSent, totalCases, scatter,
  scatterCorrelation,
}: {
  dndCases: number;
  promiseWindows: number;
  futileRetries: number;
  contactsSent: number;
  totalCases: number;
  scatter?: {
    tau_hat: number; tau_true: number; contacted: number;
    amount?: number; loss_type?: string;
  }[];
  /** Correlation for the population the scatter is drawn from — not the batch
   * model's, which is measured on a different one. Passed in rather than
   * written into the prose: the sentence exists to explain how wide the cloud
   * is, so quoting a number from a different population would be describing
   * some other chart. */
  scatterCorrelation?: number;
}) {
  const items = [
    {
      k: "Negative uplift",
      v: dndCases,
      t: "Customers whose payment probability falls when contacted. A second causal model, trained on the same randomised data with the outcome swapped to opt-out, prices the damage.",
    },
    {
      k: "Promise windows",
      v: promiseWindows,
      t: "Someone said they would pay on the 5th. Chasing them on the 3rd is the harassment pattern the RBI norms exist to prevent, so the compliance kernel enforces the silence.",
    },
    {
      k: "Dead payment rails",
      v: futileRetries,
      t: "Retries suppressed into an issuer detected as down. Not a low-value action — a worthless one, and it still burns the case's attempt budget.",
    },
  ];

  return (
    <section className="rl-silence">
      <div className="rl-silence-inner">
        <p className="rl-sectionmark">The work you cannot see</p>
        <InView>
          <h2 className="rl-h2">
            Recovery is assumed to mean outreach.
            <span className="rl-dim"> Most of this agent's value is in not sending the message.</span>
          </h2>
        </InView>

        <div className="rl-silence-grid">
          {items.map((it, i) => (
            <InView key={it.k} index={i}>
              <article className="rl-silence-item">
                <span className="rl-silence-num">{it.v.toLocaleString("en-IN")}</span>
                <h3>{it.k}</h3>
                <p>{it.t}</p>
              </article>
            </InView>
          ))}
        </div>

        {scatter && scatter.length > 0 && (
          <InView index={3}>
            <div className="rl-silence-quad">
              <div>
                <h3>The quadrant conventional dunning cannot represent.</h3>
                <p>
                  Every case, predicted against true. Below the line,
                  contacting a customer makes them <b>less</b> likely to pay —
                  and a system built to maximise contact has no way to express
                  a customer it should not contact.
                </p>
                <p className="rl-dim">
                  The cloud is wide on purpose: predicted and true uplift
                  correlate{" "}
                  {scatterCorrelation != null
                    ? `at ${scatterCorrelation.toFixed(2)} on these cases`
                    : "weakly"}
                  , so the bottom-right is not empty.
                  Every point there is a case the model recommended and was
                  wrong about.
                </p>
              </div>
              <UpliftQuadrant points={scatter} />
            </div>
          </InView>
        )}

        {scatter && scatter.some((p) => p.amount != null) && (
          <InView index={4}>
            <div className="rl-space-block">
              <div className="rl-space-copy">
                <h3>The same decision, with the axis the flat chart had to drop.</h3>
                <p>
                  The agent contacts on predicted uplift <b>times rupees at
                  risk</b>, so the boundary is a surface, not a line. It answers
                  what the flat chart cannot: why a case with almost no
                  predicted uplift was contacted anyway. It was a large
                  invoice.
                </p>
                <p className="rl-dim">
                  Height is what contact was really worth, which the model
                  never sees. Below the plane it destroys value. Drag to
                  rotate.
                </p>
              </div>
              <PolicySpaceGuard points={scatter as any} />
            </div>
          </InView>
        )}

        <InView index={5}>
          <p className="rl-silence-foot">
            {contactsSent.toLocaleString("en-IN")} messages sent across{" "}
            {totalCases.toLocaleString("en-IN")} cases.
          </p>
        </InView>
      </div>
    </section>
  );
}
