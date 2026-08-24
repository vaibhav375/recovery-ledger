import NotRun from "./NotRun";
import type { Dashboard } from "../types";
import { money } from "../format";

export default function NegotiationPage({ data }: { data: Dashboard }) {
  const n = data.negotiation;
  if (!n) return <NotRun title="Negotiation" command="make negotiate" />;

  return (
    <main className="browse-page rl-page">
      <header className="browse-header">
        <h1>Negotiation — Section 43B(h)</h1>
        <p className="lede">
          The 45-day MSME clock, an NPV solver, and a kernel-enforced concession envelope
        </p>
      </header>

      <div className="card rl-note">
        Under Section 43B(h) a buyer who does not pay an MSME supplier within 45
        days cannot claim the expense in that financial year — the deduction is{" "}
        <strong>deferred to the year of actual payment, not forfeited</strong>.
        That precision matters: the overstated version is wrong and a CFO would
        know it. It also inverts the negotiation, because settling early is in
        the <em>buyer's</em> interest.
      </div>

      {n.map((sc: any) => {
        const denied = sc.kernel_decision === "DENY";
        const leverage = String(sc.solver_rationale ?? "").includes("Leverage, not margin");
        return (
          <section key={sc.scenario} className={`card rl-scenario${leverage ? " is-highlight" : ""}`}>
            <h2>{sc.scenario}</h2>
            <p className="rl-scenario-meta">
              {money(sc.amount)} · 43B(h): {sc["43bh_urgency"]}
              {sc["43bh_days_left"] !== null ? ` · ${sc["43bh_days_left"]}d` : ""}
            </p>

            <dl className="rl-kv">
              <dt>Solver</dt>
              <dd>
                {sc.offer_type}
                {sc.discount_pct ? ` (${(sc.discount_pct * 100).toFixed(2)}%)` : ""}
                <div className="rl-sub">{sc.solver_rationale}</div>
              </dd>

              <dt>Kernel</dt>
              <dd>
                <span className={denied ? "rl-fail" : "rl-pass"}>{sc.kernel_decision}</span>
                {denied && ` ← ${(sc.kernel_denied_rules ?? []).join(", ")}`}
              </dd>

              <dt>Message</dt>
              <dd>
                {sc.message_suppressed_by_kernel ? (
                  <span className="rl-fail">not drafted — kernel denied the action</span>
                ) : (
                  sc.message
                )}
              </dd>
            </dl>

            {leverage && <span className="rl-chip is-ok">leverage, not margin</span>}
          </section>
        );
      })}
    </main>
  );
}
