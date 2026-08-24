import type { Dashboard } from "../types";

export default function CompliancePage({ data }: { data: Dashboard }) {
  const rows = [...data.rule_stats].sort((a, b) => b.failed - a.failed || b.evaluated - a.evaluated);
  return (
    <main className="browse-page rl-page">
      <header className="browse-header">
        <h1>Compliance kernel</h1>
        <p className="lede">
          {data.summary.certificates.toLocaleString()} certificates ·{" "}
          {data.summary.denied.toLocaleString()} denials · every rule evaluated on every action
        </p>
      </header>

      <div className="card rl-note">
        The kernel is deterministic and contains <strong>no LLM</strong>. A
        build-breaking test (<code>tests/test_kernel_no_llm_imports.py</code>)
        fails if anything under <code>kernel/</code> imports an LLM client — and
        it is mutation-tested, so it can actually fail.
      </div>

      <div className="card rl-table-wrap">
        <table className="rl-table">
          <thead>
            <tr><th>Rule</th><th>Evaluated</th><th>Passed</th><th>Denied</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.rule}>
                <td><code>{r.rule}</code></td>
                <td className="rl-num">{r.evaluated.toLocaleString()}</td>
                <td className="rl-num rl-pass">{r.passed.toLocaleString()}</td>
                <td className={`rl-num${r.failed ? " rl-fail" : ""}`}>{r.failed.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
