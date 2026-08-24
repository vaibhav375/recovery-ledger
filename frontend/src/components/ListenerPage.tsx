import Stat from "./Stat";
import NotRun from "./NotRun";
import type { Dashboard } from "../types";
import { pct } from "../format";

export default function ListenerPage({ data }: { data: Dashboard }) {
  const l = data.listener;
  if (!l) return <NotRun title="Listener" command="make listener-eval" />;
  const intents = Object.entries(l.per_intent ?? {}) as [string, any][];

  return (
    <main className="browse-page rl-page">
      <header className="browse-header">
        <h1>Listener — reply-intent classification</h1>
        <p className="lede">
          {l.n} hand-labelled replies · model <code>{l.model}</code>
        </p>
      </header>

      <div className="card rl-note is-alert">
        <strong>Opt-out is deliberately not left to the model.</strong> Measured
        alone, the LLM recalled only 0.57 of opt-outs and every miss was Hindi or
        Hinglish. Missing one is a TCCCPR violation, not a lost sale — so a
        deterministic detector runs first and overrides it.
      </div>

      <div className="rl-grid">
        <Stat label="Overall accuracy" value={pct(l.accuracy)} tone="ok" />
        {Object.entries(l.accuracy_by_language ?? {}).map(([k, v]) => (
          <Stat key={k} label={k} value={pct(v as number, 0)} />
        ))}
      </div>

      <header className="browse-header rl-section">
        <h1>Per intent</h1>
        <p className="lede">Promise-to-pay precision/recall is the metric spec 11.2 names by title</p>
      </header>
      <div className="card rl-table-wrap">
        <table className="rl-table">
          <thead><tr><th>Intent</th><th>Precision</th><th>Recall</th></tr></thead>
          <tbody>
            {intents.map(([k, m]) => (
              <tr key={k}>
                <td><code>{k}</code></td>
                <td className="rl-num">{m.precision.toFixed(2)}</td>
                <td className={`rl-num${m.recall === 1 ? " rl-pass" : ""}`}>{m.recall.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
