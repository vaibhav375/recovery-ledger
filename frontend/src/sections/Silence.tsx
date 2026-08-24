import InView from "../motion/InView";

/** The agent's most interesting decisions are the ones where it does nothing.
 *
 * Framed as its own section because it inverts what a recovery product is
 * assumed to be. Three different mechanisms all produce the same outcome —
 * no message sent — for three genuinely different reasons. */
export default function Silence({
  dndCases, promiseWindows, futileRetries, contactsSent, totalCases,
}: {
  dndCases: number;
  promiseWindows: number;
  futileRetries: number;
  contactsSent: number;
  totalCases: number;
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

        <InView index={3}>
          <p className="rl-silence-foot">
            {contactsSent.toLocaleString("en-IN")} messages sent across{" "}
            {totalCases.toLocaleString("en-IN")} cases.
          </p>
        </InView>
      </div>
    </section>
  );
}
