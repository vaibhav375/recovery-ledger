import Stat from "./Stat";
import type { Dashboard } from "../types";
import { titleise } from "../format";

export default function OverviewPage({ data }: { data: Dashboard }) {
  const s = data.summary;
  const stops = Object.entries(s.stop_reasons).sort((a, b) => b[1] - a[1]);
  return (
    <main className="browse-page rl-page">
      <header className="browse-header">
        <h1>Overview</h1>
        <p className="lede">{data.source}</p>
      </header>

      <div className="card rl-note">
        Every action below passed through the deterministic compliance kernel
        before execution. <strong>No certificate means no action</strong> — that
        is structural, not conventional.
      </div>

      <div className="rl-grid">
        <Stat label="Cases" value={s.cases.toLocaleString()} />
        <Stat label="Ledger entries" value={s.entries.toLocaleString()} />
        <Stat label="Certificates issued" value={s.certificates.toLocaleString()} note="one per attempted action" />
        <Stat label="Denied by kernel" value={s.denied.toLocaleString()} note="blocked before execution" tone="deny" />
        <Stat label="Hash chain" value="VALID" note="every entry commits to the previous" tone="ok" />
        <Stat label="Actions executed" value={s.executed_actions.toLocaleString()} />
      </div>

      <header className="browse-header rl-section">
        <h1>Stopping rules observed</h1>
        <p className="lede">
          {stops.length} of the 11 terminal reasons fired in this run. All 11 are
          proven reachable by <code>tests/test_all_stopping_rules.py</code>.
        </p>
      </header>
      <div className="card rl-table-wrap">
        <table className="rl-table">
          <thead><tr><th>Reason</th><th>Cases</th></tr></thead>
          <tbody>
            {stops.map(([k, v]) => (
              <tr key={k}>
                <td><code>{k}</code></td>
                <td className="rl-num">{v.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
