import InView from "../motion/InView";
import UpliftQuadrant from "../components/UpliftQuadrant";

/** The agent's most interesting decisions are the ones where it does nothing.
 *
 * Framed as its own section because it inverts what a recovery product is
 * assumed to be. Three different mechanisms all produce the same outcome —
 * no message sent — for three genuinely different reasons. */
export default function Silence({
  dndCases, promiseWindows, futileRetries, contactsSent, totalCases, scatter,
}: {
  dndCases: number;
  promiseWindows: number;
  futileRetries: number;
  contactsSent: number;
  totalCases: number;
  scatter?: { tau_hat: number; tau_true: number; contacted: number }[];
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
                  Every case, plotted as what the model predicted against what
                  was actually true. Below the line, contacting a customer
                  makes them <b>less</b> likely to pay — and a system built to
                  maximise contact has no way to express a customer it should
                  not contact.
                </p>
                <p className="rl-dim">
                  The cloud is wide on purpose: predicted and true uplift
                  correlate around 0.36, so the bottom-right is not empty.
                  Every point there is a case the model recommended and was
                  wrong about. A fitted line through this would imply a
                  precision the model does not have.
                </p>
              </div>
              <UpliftQuadrant points={scatter} />
            </div>
          </InView>
        )}

        <InView index={4}>
          <p className="rl-silence-foot">
            {contactsSent.toLocaleString("en-IN")} messages sent across{" "}
            {totalCases.toLocaleString("en-IN")} cases.
          </p>
        </InView>
      </div>
    </section>
  );
}
