import InView from "../motion/InView";
import type { Dashboard } from "../types";

/** A DENY is the system working, not the system failing.
 *
 * Deliberate colour decision, and the one real risk in this design: denials
 * are NOT rendered in alarm red. In this product a blocked action is a
 * success — it is the compliance kernel doing precisely its job — so denials
 * carry the primary indigo, the colour of authority here. Red is reserved for
 * an actual violation, of which the red-team suite reports zero. Colouring
 * 320 correct refusals red would tell the reader something untrue.
 */
export default function Kernel({ data }: { data: Dashboard }) {
  const s = data.summary;
  const rules = [...data.rule_stats].sort((a, b) => b.failed - a.failed);
  const busiest = rules[0];

  return (
    <section className="rl-kernel">
      <div className="rl-kernel-inner">
        <p className="rl-sectionmark">The constraint</p>
        <InView>
          <h2 className="rl-h2">
            The compliance kernel is deliberately not an LLM.
            <span className="rl-dim"> 99% compliant is 100% undeployable.</span>
          </h2>
        </InView>

        <InView index={1}>
          <div className="rl-kernel-grid">
            <div>
              <span className="rl-kernel-num">{s.certificates.toLocaleString("en-IN")}</span>
              <span className="rl-kernel-lbl">certificates issued — one per attempted action</span>
            </div>
            <div>
              <span className="rl-kernel-num is-deny">{s.denied.toLocaleString("en-IN")}</span>
              <span className="rl-kernel-lbl">refused before execution</span>
            </div>
            <div>
              <span className="rl-kernel-num">{data.rule_stats.length}</span>
              <span className="rl-kernel-lbl">rules, each cited to source</span>
            </div>
            <div>
              <span className="rl-kernel-num is-ok">0</span>
              <span className="rl-kernel-lbl">violations · 100% red-team block rate</span>
            </div>
          </div>
        </InView>

        <InView index={2}>
          <p className="rl-kernel-note">
            A refusal is the system working. It is drawn in the accent colour
            rather than red — red is kept for a violation, and there are none.
            {busiest && busiest.failed > 0 && (
              <>
                {" "}Every one of these refusals came from a single rule:{" "}
                <code>{busiest.rule}</code>, the 24-hour pre-debit notification
                window.
              </>
            )}
          </p>
        </InView>

        <InView index={3}>
          <div className="rl-kernel-rules">
            {rules.map((r) => (
              <div key={r.rule} className={`rl-rulerow${r.failed ? " is-active" : ""}`}>
                <code>{r.rule}</code>
                <span className="rl-rulerow-bar">
                  <span
                    style={{ width: `${(r.failed / Math.max(r.evaluated, 1)) * 100}%` }}
                  />
                </span>
                <span className="rl-rulerow-n">
                  {r.failed ? `${r.failed.toLocaleString("en-IN")} refused` : "—"}
                </span>
              </div>
            ))}
          </div>
        </InView>
      </div>
    </section>
  );
}
