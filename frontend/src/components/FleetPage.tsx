import Stat from "./Stat";
import NotRun from "./NotRun";
import type { Dashboard } from "../types";
import { money } from "../format";

export default function FleetPage({ data }: { data: Dashboard }) {
  const f = data.fleet;
  if (!f) return <NotRun title="Fleet health" command="make fleet" />;
  const b = f.blind, a = f.fleet_aware;

  const rows: [string, any, any, boolean?][] = [
    ["Retries into the degraded issuer", b.retries_into_degraded_issuer, a.retries_into_degraded_issuer, true],
    ["Total retries", b.retries, a.retries],
    ["Contacts sent", b.contacts, a.contacts],
    ["₹ recovered on outage-hit cases", money(b.recovered_on_degraded_issuer), money(a.recovered_on_degraded_issuer), true],
    ["₹ recovered overall", money(b.gross_recovered), money(a.gross_recovered)],
  ];

  return (
    <main className="browse-page rl-page">
      <header className="browse-header">
        <h1>Fleet health — contact-free recovery</h1>
        <p className="lede">
          Detecting a broken payment rail and declining to retry into it. Nobody
          is messaged to produce this value.
        </p>
      </header>

      <div className="card rl-note">
        The detector is never told which issuer is down. It sees only the
        observed attempt stream, and compares each slice against{" "}
        <em>its own</em> baseline — so a structurally weak issuer is not flagged
        for being weak, only for getting worse.
      </div>

      <div className="rl-grid">
        <Stat label="Outage (ground truth)" value={f.ground_truth_outage.join(", ")} />
        <Stat
          label="Detected"
          value={f.detected.join(", ") || "none"}
          note={f.detection_correct ? "exact match" : "MISMATCH"}
          tone={f.detection_correct ? "ok" : "deny"}
        />
        <Stat label="Futile retries avoided" value={f.futile_retries_avoided} note="into a dead rail" tone="ok" />
        <Stat label="Gross ₹ change" value={"+" + Math.round(f.gross_recovery_change).toLocaleString("en-IN")} tone="ok" />
      </div>

      {f.attribution && (
        <div className="card rl-note is-alert">
          <strong>Root-cause attribution:</strong> {f.attribution}
        </div>
      )}

      <header className="browse-header rl-section">
        <h1>Blind vs fleet-aware</h1>
        <p className="lede">Same cases, same outage, same policy — only the detector differs</p>
      </header>
      <div className="card rl-table-wrap">
        <table className="rl-table">
          <thead><tr><th></th><th>blind</th><th>fleet-aware</th></tr></thead>
          <tbody>
            {rows.map(([label, x, y, hi]) => (
              <tr key={label}>
                <td>{label}</td>
                <td className="rl-num">{x}</td>
                <td className={`rl-num${hi ? " rl-hi" : ""}`}>{y}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
